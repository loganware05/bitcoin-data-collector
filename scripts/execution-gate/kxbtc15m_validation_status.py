#!/usr/bin/env python3
"""Summarize KXBTC15M real-market validation floors (paper-only).

Dual floor (approved): >=14 edge-eligible calendar days AND >=50 settled labels
for non-fixture Phase A attempt. Does not unlock live trading.
"""

from __future__ import annotations

import argparse
import json
from datetime import date
from pathlib import Path
from typing import Any


def _load_ticks(decision_dir: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if not decision_dir.is_dir():
        return rows
    for path in sorted(decision_dir.glob("kxbtc15m_tick_*.json")):
        payload = json.loads(path.read_text())
        day = str(payload.get("timestamp") or path.stem)[:10]
        for d in payload.get("decisions") or []:
            item = dict(d)
            item["_day"] = day
            rows.append(item)
    return rows


def summarize(
    *,
    decision_dir: Path,
    labels_path: Path | None,
    min_edge_days: int = 14,
    min_labels: int = 50,
) -> dict[str, Any]:
    decisions = _load_ticks(decision_dir)
    edge_days = {
        d["_day"]
        for d in decisions
        if d.get("counts_as_edge_evidence")
        or str(d.get("settlement_index_source") or "") in {"kalshi_api", "cf_benchmarks"}
    }
    n_labels = 0
    if labels_path and labels_path.is_file():
        payload = json.loads(labels_path.read_text())
        rows = payload.get("rows") if isinstance(payload, dict) else payload
        n_labels = len(rows or [])

    edge_day_count = len(edge_days)
    phase_a_ready = edge_day_count >= min_edge_days and n_labels >= min_labels
    return {
        "schema": "bdc.kxbtc15m.validation_status.v1",
        "approved_for_execution": False,
        "live_money": "DENIED",
        "decision_dir": str(decision_dir),
        "n_decisions": len(decisions),
        "edge_eligible_calendar_days": edge_day_count,
        "min_edge_days": min_edge_days,
        "n_settled_labels": n_labels,
        "min_labels": min_labels,
        "phase_a_non_fixture_ready": phase_a_ready,
        "note": "Dual floor for Phase A attempt only; does not authorize live trading.",
        "as_of": date.today().isoformat(),
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--decision-dir", type=Path, required=True)
    ap.add_argument("--labels", type=Path, default=None)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--min-edge-days", type=int, default=14)
    ap.add_argument("--min-labels", type=int, default=50)
    args = ap.parse_args()
    payload = summarize(
        decision_dir=args.decision_dir,
        labels_path=args.labels,
        min_edge_days=args.min_edge_days,
        min_labels=args.min_labels,
    )
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(payload, indent=2) + "\n")
    print(json.dumps(payload, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
