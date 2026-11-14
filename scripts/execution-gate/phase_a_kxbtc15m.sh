#!/usr/bin/env bash
# Phase A harness for paper_kxbtc15m_v1 (hermetic fixture path by default).
# Never unlocks live execution.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
PY="${PY:-$(command -v python3)}"
EVIDENCE="${REPO_ROOT}/.agent/evidence/kxbtc15m-live-readiness/wave-3"
LABELS="${1:-$REPO_ROOT/tests/fixtures/kxbtc15m/settlement_labels.json}"
mkdir -p "$EVIDENCE"

"$PY" "$REPO_ROOT/kxbtc15m_settlement_labels.py" \
  --fixture-labels "$LABELS" \
  --out-json "$EVIDENCE/joined_labels.json" \
  --out-returns-csv "$EVIDENCE/paper_returns.csv"

"$PY" "$REPO_ROOT/kxbtc15m_ml.py" \
  --labels "$LABELS" \
  --out "$EVIDENCE/train_eval.json"

if [[ -f "$EVIDENCE/paper_returns.csv" ]] && [[ "$(wc -l < "$EVIDENCE/paper_returns.csv" | tr -d ' ')" -gt 1 ]]; then
  "$PY" "$REPO_ROOT/scripts/execution-gate/phase_a_cpcv_dsr.py" \
    --returns "$EVIDENCE/paper_returns.csv" \
    --data-class fixture \
    --out "$EVIDENCE/phase_a_report.json" || true
else
  "$PY" "$REPO_ROOT/scripts/execution-gate/phase_a_cpcv_dsr.py" \
    --data-class fixture \
    --out "$EVIDENCE/phase_a_report.json"
fi

"$PY" - <<PY
import json
from pathlib import Path
ev = Path(r"$EVIDENCE")
summary = {
    "schema": "bdc.kxbtc15m.phase_a_summary.v1",
    "approved_for_execution": False,
    "live_money": "DENIED",
    "artifacts": sorted(p.name for p in ev.glob("*")),
    "note": "Fixture/hermetic Phase A path; does not unlock live trading.",
}
(ev / "SUMMARY.json").write_text(json.dumps(summary, indent=2) + "\n")
print(json.dumps(summary, indent=2))
PY
