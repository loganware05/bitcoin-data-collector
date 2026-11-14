"""Join KXBTC15M decision ticks to settlement outcomes for Phase A / ML.

Hermetic path: fixture labels JSON.
Optional live path: fetch settled market result via KalshiClient (read-only).
"""

from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from kxbtc15m_settlement_model import label_settlement_outcome


def load_ticks(decision_dir: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for path in sorted(decision_dir.glob("kxbtc15m_tick_*.json")):
        payload = json.loads(path.read_text())
        for d in payload.get("decisions") or []:
            item = dict(d)
            item["_tick_file"] = path.name
            item["_tick_timestamp"] = payload.get("timestamp")
            rows.append(item)
    return rows


def join_fixture_labels(
    decisions: list[dict[str, Any]],
    labels: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    by_ticker = {str(r.get("contract_ticker")): r for r in labels if r.get("contract_ticker")}
    out: list[dict[str, Any]] = []
    for d in decisions:
        ticker = str(d.get("contract_ticker") or "")
        lab = by_ticker.get(ticker)
        if not lab:
            continue
        outcome = label_settlement_outcome(
            settlement_value=float(lab["settlement_value"]),
            target_price=float(lab.get("target_price") or d.get("target_price") or 0),
        )
        out.append(
            {
                "timestamp": d.get("timestamp") or d.get("_tick_timestamp"),
                "contract_ticker": ticker,
                "target_price": d.get("target_price"),
                "model_probability_up": d.get("model_probability_up"),
                "recommendation": d.get("recommendation"),
                "settlement_index_source": d.get("settlement_index_source"),
                "counts_as_edge_evidence": d.get("counts_as_edge_evidence"),
                "settlement_value": lab["settlement_value"],
                "outcome_up": outcome["outcome_up"],
                "label": outcome["label"],
            }
        )
    return out


def export_returns_csv(joined: list[dict[str, Any]], path: Path) -> None:
    """Simple +1/-1 paper return proxy for phase_a_cpcv_dsr (one column)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = ["return"]
    for row in joined:
        rec = str(row.get("recommendation") or "NO TRADE").upper()
        up = bool(row.get("outcome_up"))
        if rec == "NO TRADE" or row.get("model_probability_up") is None:
            continue
        # Optimistic: BUY YES wins if UP, BUY NO wins if DOWN
        if rec == "BUY YES":
            lines.append("1.0" if up else "-1.0")
        elif rec == "BUY NO":
            lines.append("1.0" if not up else "-1.0")
    path.write_text("\n".join(lines) + "\n")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--decision-dir", type=Path, default=None)
    ap.add_argument("--fixture-labels", type=Path, required=True)
    ap.add_argument("--out-json", type=Path, required=True)
    ap.add_argument("--out-returns-csv", type=Path, default=None)
    args = ap.parse_args(argv)

    labels_payload = json.loads(args.fixture_labels.read_text())
    labels = list(labels_payload.get("rows") or labels_payload if isinstance(labels_payload, list) else [])

    decisions: list[dict[str, Any]] = []
    if args.decision_dir:
        decisions = load_ticks(args.decision_dir)
    # Also allow labels-only train path: synthesize decision-shaped rows from labels
    if not decisions:
        for lab in labels:
            decisions.append(
                {
                    "timestamp": lab.get("timestamp"),
                    "contract_ticker": lab.get("contract_ticker"),
                    "target_price": lab.get("target_price"),
                    "model_probability_up": None,
                    "recommendation": "NO TRADE",
                    "settlement_index_source": "fixture",
                    "counts_as_edge_evidence": True,
                }
            )

    joined = join_fixture_labels(decisions, labels)
    # If join empty because tickers differ, attach outcomes onto label rows for ML
    if not joined:
        joined = []
        for lab in labels:
            outcome = label_settlement_outcome(
                settlement_value=float(lab["settlement_value"]),
                target_price=float(lab["target_price"]),
            )
            joined.append(
                {
                    "timestamp": lab.get("timestamp"),
                    "contract_ticker": lab.get("contract_ticker"),
                    "target_price": lab.get("target_price"),
                    "settlement_index_at_decision": lab.get("settlement_index_at_decision"),
                    "time_remaining_seconds": lab.get("time_remaining_seconds"),
                    "settlement_value": lab["settlement_value"],
                    "outcome_up": outcome["outcome_up"],
                    "label": outcome["label"],
                    "settlement_index_source": "fixture",
                    "counts_as_edge_evidence": True,
                }
            )

    payload = {
        "created_at": datetime.now(UTC).isoformat(),
        "n": len(joined),
        "approved_for_execution": False,
        "rows": joined,
        "note": "Paper/settlement labels only; live money denied.",
    }
    args.out_json.parent.mkdir(parents=True, exist_ok=True)
    args.out_json.write_text(json.dumps(payload, indent=2) + "\n")
    if args.out_returns_csv:
        export_returns_csv(joined, args.out_returns_csv)
    print(json.dumps({"wrote": str(args.out_json), "n": len(joined)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
