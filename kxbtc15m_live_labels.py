"""Harvest live KXBTC15M settlement labels from public finalized Kalshi markets.

Paper-only. Joins finalize `expiration_value` / `floor_strike` / `result` to
decision ticks when `--decision-dir` is provided. Does not unlock live trading.
"""

from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from kalshi_client import KalshiClient
from kxbtc15m_settlement_labels import export_returns_csv, join_fixture_labels, load_ticks
from kxbtc15m_settlement_model import label_settlement_outcome


def market_to_label_row(raw: dict[str, Any]) -> dict[str, Any] | None:
    ticker = str(raw.get("ticker") or "")
    if not ticker:
        return None
    exp = raw.get("expiration_value")
    try:
        settlement_value = float(str(exp).strip()) if exp not in (None, "") else None
    except (TypeError, ValueError):
        settlement_value = None
    if settlement_value is None or settlement_value <= 0:
        return None
    floor = raw.get("floor_strike")
    try:
        target_price = float(floor) if floor is not None else None
    except (TypeError, ValueError):
        target_price = None
    if target_price is None or target_price <= 0:
        return None
    outcome = label_settlement_outcome(
        settlement_value=settlement_value,
        target_price=target_price,
    )
    result = str(raw.get("result") or "").strip().lower()
    return {
        "contract_ticker": ticker,
        "event_ticker": raw.get("event_ticker"),
        "timestamp": raw.get("close_time") or raw.get("expiration_time"),
        "target_price": target_price,
        "settlement_value": settlement_value,
        "outcome_up": outcome["outcome_up"],
        "label": outcome["label"],
        "kalshi_result": result or None,
        "settlement_index_source": "kalshi_api",
        "counts_as_edge_evidence": False,
        "note": "Live finalize label; decision-time edge provenance is separate.",
    }


def harvest_settled_labels(
    client: KalshiClient | None = None,
    *,
    max_pages: int = 5,
) -> list[dict[str, Any]]:
    client = client or KalshiClient()
    raw_markets = client.fetch_settled_kxbtc15m_markets(max_pages=max_pages)
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    for raw in raw_markets:
        row = market_to_label_row(raw)
        if not row:
            continue
        ticker = str(row["contract_ticker"])
        if ticker in seen:
            continue
        seen.add(ticker)
        rows.append(row)
    return rows


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--decision-dir", type=Path, default=None)
    ap.add_argument("--out-json", type=Path, required=True)
    ap.add_argument("--out-returns-csv", type=Path, default=None)
    ap.add_argument("--max-pages", type=int, default=5)
    args = ap.parse_args(argv)

    labels = harvest_settled_labels(max_pages=args.max_pages)
    joined: list[dict[str, Any]]
    if args.decision_dir and args.decision_dir.is_dir():
        decisions = load_ticks(args.decision_dir)
        joined = join_fixture_labels(decisions, labels)
        if not joined:
            # Fall back to label rows alone so n_settled_labels can still grow.
            joined = labels
    else:
        joined = labels

    payload = {
        "created_at": datetime.now(UTC).isoformat(),
        "n": len(joined),
        "n_harvested_markets": len(labels),
        "approved_for_execution": False,
        "live_money": "DENIED",
        "rows": joined,
        "note": "Live Kalshi finalize labels; paper only; does not unlock live trading.",
    }
    args.out_json.parent.mkdir(parents=True, exist_ok=True)
    args.out_json.write_text(json.dumps(payload, indent=2) + "\n")
    if args.out_returns_csv:
        export_returns_csv(joined, args.out_returns_csv)
    print(
        json.dumps(
            {
                "wrote": str(args.out_json),
                "n": len(joined),
                "n_harvested_markets": len(labels),
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
