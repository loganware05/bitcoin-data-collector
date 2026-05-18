from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from metrics import calibration_table_binary, multiclass_brier_score, multiclass_log_loss, predicted_class


def _read_jsonl(path: str | Path) -> list[dict[str, Any]]:
    p = Path(path)
    if not p.exists():
        return []
    out: list[dict[str, Any]] = []
    with p.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(obj, dict):
                out.append(obj)
    return out


def _safe_float(x: Any) -> float | None:
    try:
        if x is None or isinstance(x, bool):
            return None
        return float(x)
    except (TypeError, ValueError):
        return None


@dataclass(frozen=True)
class EvalConfig:
    rolling_window: int = 250
    drift_bins: int = 10

    # Trigger warnings
    min_outcomes_for_eval: int = 80
    max_brier: float = 0.72
    max_logloss: float = 1.25
    min_accuracy: float = 0.38

    # Calibration drift: max absolute gap between mean_pred and frac_pos in any bin
    max_calibration_gap: float = 0.12


def build_eval_frame(predictions_log: str | Path, outcomes_log: str | Path) -> pd.DataFrame:
    preds = _read_jsonl(predictions_log)
    outs = _read_jsonl(outcomes_log)
    if not preds or not outs:
        return pd.DataFrame()

    dfp = pd.DataFrame(preds)
    # Extract fused probabilities (prefer fused, else decision probability isn't per-class)
    fused = dfp.get("fused_probabilities")
    if fused is None:
        return pd.DataFrame()

    def getprob(obj: Any, k: str) -> float:
        if not isinstance(obj, dict):
            return float("nan")
        v = _safe_float(obj.get(k))
        return float("nan") if v is None else float(v)

    df = pd.DataFrame(
        {
            "timestamp": pd.to_datetime(dfp.get("timestamp"), utc=True, errors="coerce"),
            "p_up": fused.map(lambda o: getprob(o, "up")),
            "p_down": fused.map(lambda o: getprob(o, "down")),
            "p_range": fused.map(lambda o: getprob(o, "range")),
        }
    )
    df = df.dropna(subset=["timestamp"]).sort_values("timestamp").reset_index(drop=True)

    dfo = pd.DataFrame(outs)
    dfo["timestamp"] = pd.to_datetime(dfo["timestamp"], utc=True, errors="coerce")
    dfo = dfo.dropna(subset=["timestamp"])
    if "y_true" not in dfo.columns:
        return pd.DataFrame()

    merged = df.merge(dfo[["timestamp", "y_true"]], on="timestamp", how="inner")
    if merged.empty:
        return pd.DataFrame()
    merged["y_pred"] = predicted_class(merged["p_up"], merged["p_down"], merged["p_range"])
    merged = merged.dropna(subset=["p_up", "p_down", "p_range", "y_true", "y_pred"])
    return merged.reset_index(drop=True)


def evaluate_live_logs(
    predictions_log: str | Path,
    outcomes_log: str | Path,
    cfg: EvalConfig | None = None,
) -> dict[str, Any]:
    cfg = cfg or EvalConfig()
    df = build_eval_frame(predictions_log, outcomes_log)
    if df.empty or len(df) < cfg.min_outcomes_for_eval:
        return {"n": int(len(df)), "warnings": ["not enough labeled outcomes yet"]}

    # Rolling view uses tail window
    tail = df.tail(int(cfg.rolling_window)).copy()
    acc = float((tail["y_true"] == tail["y_pred"]).mean())
    brier = float(multiclass_brier_score(tail["y_true"], tail["p_up"], tail["p_down"], tail["p_range"]))
    ll = float(multiclass_log_loss(tail["y_true"], tail["p_up"], tail["p_down"], tail["p_range"]))

    calib_up = calibration_table_binary(tail["p_up"], tail["y_true"] == "up", n_bins=cfg.drift_bins)
    calib_down = calibration_table_binary(tail["p_down"], tail["y_true"] == "down", n_bins=cfg.drift_bins)
    calib_range = calibration_table_binary(tail["p_range"], tail["y_true"] == "range", n_bins=cfg.drift_bins)

    def max_gap(tab: pd.DataFrame) -> float:
        if tab.empty:
            return float("nan")
        g = (tab["mean_pred"] - tab["frac_pos"]).abs()
        return float(g.max()) if len(g) else float("nan")

    gaps = {
        "up": max_gap(calib_up),
        "down": max_gap(calib_down),
        "range": max_gap(calib_range),
    }

    warnings: list[str] = []
    retrain_recommended = False

    if np.isfinite(acc) and acc < cfg.min_accuracy:
        warnings.append("rolling accuracy below threshold")
        retrain_recommended = True
    if np.isfinite(brier) and brier > cfg.max_brier:
        warnings.append("rolling Brier score above threshold")
        retrain_recommended = True
    if np.isfinite(ll) and ll > cfg.max_logloss:
        warnings.append("rolling log loss above threshold")
        retrain_recommended = True

    for k, g in gaps.items():
        if np.isfinite(g) and g > cfg.max_calibration_gap:
            warnings.append(f"calibration drift high for {k} (gap={g:.3f})")
            retrain_recommended = True

    summary = {
        "n": int(len(df)),
        "window_n": int(len(tail)),
        "accuracy": float(round(acc, 4)),
        "brier_score": float(round(brier, 4)),
        "log_loss": float(round(ll, 4)),
        "calibration_gaps": {k: (None if not np.isfinite(v) else float(round(v, 4))) for k, v in gaps.items()},
        "retrain_recommended": bool(retrain_recommended),
        "warnings": warnings,
    }
    return summary


def main(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Evaluate live prediction logs (rolling accuracy + calibration drift).")
    parser.add_argument("--predictions-log", default="live_outputs/predictions_log.jsonl")
    parser.add_argument("--outcomes-log", default="live_outputs/outcomes_log.jsonl")
    parser.add_argument("--window", type=int, default=250)
    args = parser.parse_args(argv)

    cfg = EvalConfig(rolling_window=int(args.window))
    out = evaluate_live_logs(args.predictions_log, args.outcomes_log, cfg=cfg)
    print(json.dumps(out, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

