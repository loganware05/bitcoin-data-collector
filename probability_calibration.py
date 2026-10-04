from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd
from sklearn.isotonic import IsotonicRegression

from metrics import calibration_table_binary


def _utc_stamp() -> str:
    return datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")


def calibration_dir(models_base_dir: Path) -> Path:
    """Directory for settlement probability calibrators under the Verdant models tree."""
    return Path(models_base_dir) / "calibration"


@dataclass(frozen=True)
class CalibratorConfig:
    min_samples: int = 30
    min_actionable_samples: int = 10
    exclude_no_trade_for_fit: bool = True
    exclude_no_trade_for_eval: bool = True
    calibration_bins: int = 10


class SettlementProbabilityCalibrator:
    """Isotonic recalibration of model YES probabilities from settled Kalshi outcomes."""

    def __init__(self) -> None:
        self._iso = IsotonicRegression(out_of_bounds="clip", y_min=0.0, y_max=1.0)
        self._fitted = False
        self.meta: dict[str, Any] = {}

    @property
    def fitted(self) -> bool:
        return self._fitted

    def fit(self, df: pd.DataFrame, *, cfg: CalibratorConfig | None = None) -> dict[str, Any]:
        cfg = cfg or CalibratorConfig()
        if df.empty or "model_yes_probability" not in df.columns or "y_true" not in df.columns:
            raise ValueError("Need model_yes_probability and y_true columns to fit calibrator.")

        work = df.dropna(subset=["model_yes_probability", "y_true"]).copy()
        work["y_true"] = work["y_true"].astype(int)

        fit_df = work
        fit_source = "all_settled"
        if cfg.exclude_no_trade_for_fit and "recommendation" in work.columns:
            actionable = work[work["recommendation"].isin(["BUY YES", "BUY NO"])]
            if len(actionable) >= cfg.min_actionable_samples:
                fit_df = actionable
                fit_source = "actionable_only"
            elif len(work) < cfg.min_samples:
                raise ValueError(
                    f"Need at least {cfg.min_samples} settled rows to fit; have {len(work)} "
                    f"({len(actionable)} actionable)."
                )

        if len(fit_df) < cfg.min_samples and fit_source == "all_settled":
            raise ValueError(f"Need at least {cfg.min_samples} settled rows to fit; have {len(fit_df)}.")

        x = fit_df["model_yes_probability"].astype(float).to_numpy()
        y = fit_df["y_true"].astype(float).to_numpy()
        self._iso.fit(x, y)
        self._fitted = True

        calibrated = self.transform(x)
        raw_gap = _max_calibration_gap(x, y, n_bins=cfg.calibration_bins)
        cal_gap = _max_calibration_gap(calibrated, y, n_bins=cfg.calibration_bins)

        self.meta = {
            "fitted_at_utc": _utc_stamp(),
            "n_fit": int(len(fit_df)),
            "n_total_settled": int(len(work)),
            "fit_source": fit_source,
            "raw_max_calibration_gap": raw_gap,
            "calibrated_max_calibration_gap": cal_gap,
            "exclude_no_trade_for_fit": cfg.exclude_no_trade_for_fit,
            "exclude_no_trade_for_eval": cfg.exclude_no_trade_for_eval,
        }
        return dict(self.meta)

    def transform(self, p: np.ndarray | float | pd.Series) -> np.ndarray:
        if not self._fitted:
            arr = np.asarray(p, dtype=float)
            return arr
        arr = np.asarray(p, dtype=float).reshape(-1)
        return self._iso.predict(arr)

    def calibrate_yes_no(self, model_yes: float) -> tuple[float, float]:
        p = float(self.transform(np.array([model_yes]))[0])
        p = max(0.01, min(0.99, p))
        return p, 1.0 - p


def _max_calibration_gap(p: np.ndarray, y: np.ndarray, *, n_bins: int) -> float | None:
    tab = calibration_table_binary(p, y == 1, n_bins=n_bins)
    if tab.empty:
        return None
    gap = (tab["mean_pred"] - tab["frac_pos"]).abs()
    return float(gap.max()) if len(gap) else None


def save_calibrator(calibrator: SettlementProbabilityCalibrator, out_dir: Path) -> Path:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    model_path = out_dir / "settlement_isotonic.joblib"
    manifest_path = out_dir / "manifest.json"
    joblib.dump(calibrator, model_path)
    payload = {"model_path": str(model_path), **calibrator.meta}
    manifest_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return manifest_path


def load_settlement_calibrator(models_base_dir: Path) -> SettlementProbabilityCalibrator | None:
    path = calibration_dir(models_base_dir) / "settlement_isotonic.joblib"
    if not path.exists():
        return None
    try:
        obj = joblib.load(path)
    except Exception:  # noqa: BLE001
        return None
    return obj if isinstance(obj, SettlementProbabilityCalibrator) else None


def evaluate_calibration_slices(
    df: pd.DataFrame,
    *,
    cfg: CalibratorConfig | None = None,
    calibrator: SettlementProbabilityCalibrator | None = None,
) -> dict[str, Any]:
    """Report calibration metrics on all rows vs excluding NO TRADE abstentions."""
    cfg = cfg or CalibratorConfig()
    work = df.dropna(subset=["model_yes_probability", "y_true"]).copy()
    if work.empty:
        return {"n": 0, "warnings": ["no labeled rows"]}

    work["y_true"] = work["y_true"].astype(int)
    slices: dict[str, pd.DataFrame] = {"all_settled": work}
    if "recommendation" in work.columns:
        actionable = work[work["recommendation"].isin(["BUY YES", "BUY NO"])]
        no_trade = work[work["recommendation"] == "NO TRADE"]
        slices["actionable"] = actionable
        slices["no_trade_excluded"] = actionable if cfg.exclude_no_trade_for_eval else work
        slices["no_trade_only"] = no_trade

    out: dict[str, Any] = {"n_total": int(len(work))}
    for name, subset in slices.items():
        if subset.empty:
            out[name] = {"n": 0, "warnings": ["empty slice"]}
            continue
        p_raw = subset["model_yes_probability"].astype(float).to_numpy()
        y = subset["y_true"].astype(int).to_numpy()
        entry: dict[str, Any] = {
            "n": int(len(subset)),
            "brier_score": round(float(np.mean((p_raw - y) ** 2)), 4),
            "max_calibration_gap_raw": _max_calibration_gap(p_raw, y, n_bins=cfg.calibration_bins),
        }
        if calibrator is not None and calibrator.fitted:
            p_cal = calibrator.transform(p_raw)
            entry["max_calibration_gap_calibrated"] = _max_calibration_gap(
                p_cal, y, n_bins=cfg.calibration_bins
            )
            entry["brier_score_calibrated"] = round(float(np.mean((p_cal - y) ** 2)), 4)
        out[name] = entry

    primary = out.get("no_trade_excluded") or out.get("actionable") or {}
    if not primary or int(primary.get("n") or 0) == 0:
        primary = out.get("all_settled") or {}
    if isinstance(primary, dict):
        out["max_calibration_gap"] = primary.get("max_calibration_gap_calibrated") or primary.get(
            "max_calibration_gap_raw"
        )
        out["brier_score"] = primary.get("brier_score_calibrated") or primary.get("brier_score")

    return out


__all__ = [
    "CalibratorConfig",
    "SettlementProbabilityCalibrator",
    "calibration_dir",
    "evaluate_calibration_slices",
    "load_settlement_calibrator",
    "save_calibrator",
]
