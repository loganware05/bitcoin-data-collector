from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from kalshi_client import KalshiClient, KalshiClientConfig
from metrics import calibration_table_binary


@dataclass(frozen=True)
class SettlementEvalConfig:
    min_samples: int = 10
    calibration_bins: int = 10


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


def evaluate_scan_settlements(
    scan_paths: list[Path],
    *,
    cfg: SettlementEvalConfig | None = None,
    client: KalshiClient | None = None,
) -> dict[str, Any]:
    """
    Join historical scan outputs to Kalshi settled market results.
    Scores model_yes_probability vs binary YES outcome.
    """
    cfg = cfg or SettlementEvalConfig()
    client = client or KalshiClient(KalshiClientConfig(status="settled"))
    df = load_scan_rows(scan_paths)
    if df.empty:
        return {"n": 0, "warnings": ["no scan rows found"]}

    outcomes: list[int | None] = []
    for ticker in df["ticker"]:
        raw = fetch_settled_market(client, str(ticker))
        if not raw:
            outcomes.append(None)
            continue
        result = raw.get("result") or raw.get("settlement_value")
        outcomes.append(_parse_result_yes(str(result) if result is not None else None))

    df["y_true"] = outcomes
    labeled = df.dropna(subset=["y_true"]).copy()
    labeled["y_true"] = labeled["y_true"].astype(int)
    if len(labeled) < cfg.min_samples:
        return {
            "n": int(len(labeled)),
            "warnings": [f"need at least {cfg.min_samples} settled contracts; found {len(labeled)}"],
        }

    brier = float(np.mean((labeled["model_yes_probability"] - labeled["y_true"]) ** 2))
    acc = float(((labeled["model_yes_probability"] >= 0.5).astype(int) == labeled["y_true"]).mean())
    calib = calibration_table_binary(
        labeled["model_yes_probability"],
        labeled["y_true"] == 1,
        n_bins=cfg.calibration_bins,
    )
    max_gap = float((calib["mean_pred"] - calib["frac_pos"]).abs().max()) if not calib.empty else float("nan")

    return {
        "n": int(len(labeled)),
        "brier_score": round(brier, 4),
        "accuracy_at_50pct": round(acc, 4),
        "max_calibration_gap": None if not np.isfinite(max_gap) else round(max_gap, 4),
        "by_recommendation": labeled.groupby("recommendation", dropna=False)["y_true"].agg(["count", "mean"]).to_dict(),
    }


def main(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Evaluate Kalshi scan probabilities against settled outcomes.")
    parser.add_argument(
        "--scan-dir",
        type=Path,
        required=True,
        help="Directory containing scan_*.json files",
    )
    parser.add_argument("--min-samples", type=int, default=10)
    args = parser.parse_args(argv)

    paths = sorted(args.scan_dir.glob("scan_*.json"))
    result = evaluate_scan_settlements(paths, cfg=SettlementEvalConfig(min_samples=args.min_samples))
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
