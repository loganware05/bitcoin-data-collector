from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from kalshi_client import KalshiClient, KalshiClientConfig
from probability_calibration import (
    CalibratorConfig,
    SettlementProbabilityCalibrator,
    evaluate_calibration_slices,
    load_settlement_calibrator,
    save_calibrator,
)
from probability_calibration import calibration_dir as _calibration_dir


@dataclass(frozen=True)
class SettlementEvalConfig:
    min_samples: int = 10
    calibration_bins: int = 10
    exclude_no_trade_for_eval: bool = True


def _parse_result_yes(result: str | None) -> int | None:
    if not result:
        return None
    r = str(result).strip().lower()
    if r in ("yes", "true", "1"):
        return 1
    if r in ("no", "false", "0"):
        return 0
    return None


def fetch_settled_market(client: KalshiClient, ticker: str) -> dict[str, Any] | None:
    """Fetch a single market by ticker (any status) for settlement outcome."""
    try:
        data = client._get(f"/markets/{ticker}")  # noqa: SLF001
        market = data.get("market") if isinstance(data, dict) else None
        return market if isinstance(market, dict) else data if isinstance(data, dict) else None
    except Exception:  # noqa: BLE001
        return None


def load_scan_rows(scan_paths: list[Path]) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for path in scan_paths:
        if not path.exists():
            continue
        try:
            obj = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(obj, dict):
            continue
        snap_ts = obj.get("timestamp")
        ranked = obj.get("ranked") or {}
        for bucket in ("buy_yes", "buy_no", "no_trade"):
            for item in ranked.get(bucket) or []:
                if not isinstance(item, dict):
                    continue
                rows.append(
                    {
                        "scan_file": str(path),
                        "snapshot_timestamp": snap_ts,
                        "ticker": item.get("contract_ticker") or item.get("ticker"),
                        "model_yes_probability": item.get("model_yes_probability") or item.get("model_probability"),
                        "market_yes_probability": item.get("market_yes_probability")
                        or item.get("market_implied_probability"),
                        "recommendation": item.get("recommendation"),
                    }
                )
        for item in obj.get("ranked_opportunities") or []:
            if not isinstance(item, dict):
                continue
            rows.append(
                {
                    "scan_file": str(path),
                    "snapshot_timestamp": snap_ts,
                    "ticker": item.get("ticker"),
                    "model_yes_probability": item.get("model_probability"),
                    "market_yes_probability": item.get("market_implied_probability"),
                    "recommendation": item.get("recommendation"),
                }
            )
    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame(rows)
    df["model_yes_probability"] = pd.to_numeric(df["model_yes_probability"], errors="coerce")
    df = df.dropna(subset=["ticker", "model_yes_probability"])
    return df.reset_index(drop=True)


def attach_settlement_outcomes(
    df: pd.DataFrame,
    *,
    client: KalshiClient | None = None,
) -> pd.DataFrame:
    client = client or KalshiClient(KalshiClientConfig(status="settled"))
    outcomes: list[int | None] = []
    for ticker in df["ticker"]:
        raw = fetch_settled_market(client, str(ticker))
        if not raw:
            outcomes.append(None)
            continue
        result = raw.get("result") or raw.get("settlement_value")
        outcomes.append(_parse_result_yes(str(result) if result is not None else None))
    out = df.copy()
    out["y_true"] = outcomes
    return out


def fit_settlement_calibrator(
    scan_paths: list[Path],
    models_base_dir: Path,
    *,
    cfg: CalibratorConfig | None = None,
    client: KalshiClient | None = None,
) -> dict[str, Any]:
    """Fit isotonic YES-probability calibrator from settled scan history and persist."""
    cfg = cfg or CalibratorConfig()
    df = load_scan_rows(scan_paths)
    if df.empty:
        return {"success": False, "warnings": ["no scan rows found"]}

    labeled = attach_settlement_outcomes(df, client=client).dropna(subset=["y_true"])
    if len(labeled) < cfg.min_samples:
        return {
            "success": False,
            "warnings": [f"need at least {cfg.min_samples} settled contracts; found {len(labeled)}"],
        }

    calibrator = SettlementProbabilityCalibrator()
    try:
        meta = calibrator.fit(labeled, cfg=cfg)
    except ValueError as exc:
        return {"success": False, "warnings": [str(exc)]}

    manifest = save_calibrator(calibrator, _calibration_dir(Path(models_base_dir)))
    slices = evaluate_calibration_slices(labeled, cfg=cfg, calibrator=calibrator)
    return {
        "success": True,
        "manifest": str(manifest),
        "fit_meta": meta,
        "calibration_slices": slices,
    }


def evaluate_scan_settlements(
    scan_paths: list[Path],
    *,
    cfg: SettlementEvalConfig | None = None,
    client: KalshiClient | None = None,
    models_base_dir: Path | None = None,
) -> dict[str, Any]:
    """
    Join historical scan outputs to Kalshi settled market results.

    Primary calibration gap excludes NO TRADE abstentions (not committed predictions).
    When a saved settlement calibrator exists, also reports calibrated metrics.
    """
    cfg = cfg or SettlementEvalConfig()
    cal_cfg = CalibratorConfig(
        min_samples=cfg.min_samples,
        exclude_no_trade_for_eval=cfg.exclude_no_trade_for_eval,
        calibration_bins=cfg.calibration_bins,
    )
    df = load_scan_rows(scan_paths)
    if df.empty:
        return {"n": 0, "warnings": ["no scan rows found"]}

    labeled = attach_settlement_outcomes(df, client=client).dropna(subset=["y_true"])
    labeled["y_true"] = labeled["y_true"].astype(int)
    if len(labeled) < cfg.min_samples:
        return {
            "n": int(len(labeled)),
            "warnings": [f"need at least {cfg.min_samples} settled contracts; found {len(labeled)}"],
        }

    calibrator = load_settlement_calibrator(Path(models_base_dir)) if models_base_dir else None
    slices = evaluate_calibration_slices(labeled, cfg=cal_cfg, calibrator=calibrator)

    p_raw = labeled["model_yes_probability"].astype(float).to_numpy()
    y = labeled["y_true"].astype(int).to_numpy()
    brier = float(np.mean((p_raw - y) ** 2))
    acc = float(((p_raw >= 0.5).astype(int) == y).mean())

    primary = slices.get("no_trade_excluded") or slices.get("actionable") or {}
    if not primary or int(primary.get("n") or 0) == 0:
        primary = slices.get("all_settled") or {}
    result: dict[str, Any] = {
        "n": int(len(labeled)),
        "brier_score": round(brier, 4),
        "accuracy_at_50pct": round(acc, 4),
        "max_calibration_gap": primary.get("max_calibration_gap"),
        "max_calibration_gap_raw_all": (slices.get("all_settled") or {}).get("max_calibration_gap_raw"),
        "calibration_slices": slices,
        "exclude_no_trade_for_eval": cfg.exclude_no_trade_for_eval,
        "by_recommendation": labeled.groupby("recommendation", dropna=False)["y_true"].agg(["count", "mean"]).to_dict(),
    }
    if calibrator is not None and calibrator.fitted:
        result["calibrator_loaded"] = True
        result["calibrator_meta"] = calibrator.meta
    return result


def main(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Evaluate Kalshi scan probabilities against settled outcomes.")
    parser.add_argument(
        "--scan-dir",
        type=Path,
        required=True,
        help="Directory containing scan_*.json files",
    )
    parser.add_argument("--models-base-dir", type=Path, default=None, help="Base models dir for calibrator I/O")
    parser.add_argument("--min-samples", type=int, default=10)
    parser.add_argument("--fit-calibration", action="store_true", help="Fit and save settlement isotonic calibrator")
    parser.add_argument(
        "--include-no-trade-calibration",
        action="store_true",
        help="Include NO TRADE rows in primary calibration gap (default: exclude)",
    )
    args = parser.parse_args(argv)

    paths = sorted(args.scan_dir.glob("scan_*.json"))
    models_base = args.models_base_dir

    if args.fit_calibration:
        if models_base is None:
            parser.error("--fit-calibration requires --models-base-dir")
        fit_out = fit_settlement_calibrator(
            paths,
            models_base,
            cfg=CalibratorConfig(min_samples=max(30, args.min_samples)),
        )
        print(json.dumps(fit_out, indent=2))
        if not fit_out.get("success"):
            return 1

    result = evaluate_scan_settlements(
        paths,
        cfg=SettlementEvalConfig(
            min_samples=args.min_samples,
            exclude_no_trade_for_eval=not args.include_no_trade_calibration,
        ),
        models_base_dir=models_base,
    )
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
