#!/usr/bin/env python3
"""Export conservative per-trade returns from Verdant settled actionable scans.

Research-bar series for Phase A (CPCV/DSR). This is NOT live-forward edge proof
and must not be labeled as paper_track_record evidence.

Fill model (optimistic ceiling / conservative entry):
- Cross the spread using market_yes/no + bid_ask_spread when available
- Apply fee_bps + slippage_bps
- Deduplicate by contract_ticker (first actionable recommendation wins)
"""

from __future__ import annotations

import argparse
import csv
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def load_outcomes(path: Path) -> dict[str, int]:
    raw = json.loads(path.read_text())
    if not isinstance(raw, dict):
        raise SystemExit(f"outcomes must be ticker->0/1 dict: {path}")
    out: dict[str, int] = {}
    for k, v in raw.items():
        try:
            out[str(k)] = int(v)
        except (TypeError, ValueError):
            continue
    return out


def iter_actionable(scan: dict[str, Any]) -> list[dict[str, Any]]:
    ranked = scan.get("ranked") or {}
    rows: list[dict[str, Any]] = []
    for key in ("buy_yes", "buy_no"):
        for row in ranked.get(key) or []:
            if isinstance(row, dict):
                rows.append(row)
    return rows


def fill_price(row: dict[str, Any], side: str) -> float | None:
    spread = float(row.get("bid_ask_spread") or 0.0)
    half = max(spread, 0.0) / 2.0
    if side == "BUY YES":
        p = row.get("market_yes_probability")
        if p is None:
            return None
        return min(0.99, max(0.01, float(p) + half))
    if side == "BUY NO":
        p = row.get("market_no_probability")
        if p is None:
            yes = row.get("market_yes_probability")
            if yes is None:
                return None
            p = 1.0 - float(yes)
        return min(0.99, max(0.01, float(p) + half))
    return None


def trade_return(side: str, px: float, yes_won: int, fee_bps: float, slip_bps: float) -> float:
    fees = px * ((fee_bps + slip_bps) / 10_000.0)
    if side == "BUY YES":
        raw = (1.0 - px) if yes_won == 1 else (-px)
    else:  # BUY NO
        raw = (1.0 - px) if yes_won == 0 else (-px)
    return raw - fees


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--hourly-outputs",
        type=Path,
        default=Path("/Volumes/Verdant_AI/btc_kalshi/hourly_outputs"),
    )
    ap.add_argument(
        "--outcomes",
        type=Path,
        default=Path("/Volumes/Verdant_AI/btc_kalshi/settlement_cache_sep13_oct2/ticker_outcomes.json"),
    )
    ap.add_argument("--fee-bps", type=float, default=7.0)
    ap.add_argument("--slippage-bps", type=float, default=5.0)
    ap.add_argument("--out-csv", type=Path, required=True)
    ap.add_argument("--out-meta", type=Path, required=True)
    args = ap.parse_args()

    if not args.hourly_outputs.is_dir():
        raise SystemExit(f"hourly_outputs missing: {args.hourly_outputs}")
    if not args.outcomes.is_file():
        raise SystemExit(f"outcomes missing: {args.outcomes}")

    outcomes = load_outcomes(args.outcomes)
    seen: set[str] = set()
    rows_out: list[dict[str, Any]] = []

    for path in sorted(args.hourly_outputs.glob("scan_*.json")):
        try:
            scan = json.loads(path.read_text())
        except (OSError, json.JSONDecodeError):
            continue
        for row in iter_actionable(scan):
            ticker = str(row.get("contract_ticker") or "")
            side = str(row.get("recommendation") or "").upper().strip()
            if not ticker or ticker in seen or ticker not in outcomes:
                continue
            if side not in {"BUY YES", "BUY NO"}:
                continue
            px = fill_price(row, side)
            if px is None:
                continue
            yes_won = outcomes[ticker]
            ret = trade_return(side, px, yes_won, args.fee_bps, args.slippage_bps)
            seen.add(ticker)
            rows_out.append(
                {
                    "timestamp": row.get("timestamp") or scan.get("timestamp"),
                    "contract_ticker": ticker,
                    "recommendation": side,
                    "fill_price": round(px, 6),
                    "yes_won": yes_won,
                    "return": ret,
                    "source_scan": path.name,
                }
            )

    rows_out.sort(key=lambda r: str(r.get("timestamp") or ""))
    args.out_csv.parent.mkdir(parents=True, exist_ok=True)
    with args.out_csv.open("w", newline="") as f:
        w = csv.DictWriter(
            f,
            fieldnames=[
                "timestamp",
                "contract_ticker",
                "recommendation",
                "fill_price",
                "yes_won",
                "return",
                "source_scan",
            ],
        )
        w.writeheader()
        w.writerows(rows_out)

    rets = [float(r["return"]) for r in rows_out]
    meta = {
        "schema": "bdc.execution_gate.verdant_actionable_returns.v1",
        "created_at": utc_now(),
        "data_class": "verdant_staging",
        "edge_proof": False,
        "paper_track_record": False,
        "note": (
            "Settled Verdant actionable joins with conservative cross-spread fills. "
            "Valid for Phase A research bar only — not live-forward paper edge proof."
        ),
        "n_trades": len(rows_out),
        "n_outcomes_available": len(outcomes),
        "fee_bps": args.fee_bps,
        "slippage_bps": args.slippage_bps,
        "hourly_outputs": str(args.hourly_outputs),
        "outcomes": str(args.outcomes),
        "mean_return": (sum(rets) / len(rets)) if rets else None,
        "approved_for_execution": False,
    }
    args.out_meta.write_text(json.dumps(meta, indent=2) + "\n")
    print(json.dumps({"n_trades": len(rows_out), "out_csv": str(args.out_csv)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
