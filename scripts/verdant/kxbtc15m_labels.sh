#!/usr/bin/env bash
# Harvest live KXBTC15M settlement labels + refresh validation_status (paper only).
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=env.sh
source "$SCRIPT_DIR/env.sh"

LOG_DIR="${HOME}/Library/Logs/verdant"
mkdir -p "$LOG_DIR"

if [[ -d "$BTC_KALSHI_REMOTE_ROOT" ]]; then
  OUT_ROOT="$BTC_KALSHI_REMOTE_ROOT"
else
  OUT_ROOT="$BTC_KALSHI_LOCAL_ROOT"
  mkdir -p "$OUT_ROOT"
fi

DECISION_DIR="${KXBTC15M_OUTPUT_DIR:-$OUT_ROOT/live_outputs/kxbtc15m}"
LABELS_DIR="${KXBTC15M_LABELS_DIR:-$DECISION_DIR/labels}"
LABELS_JSON="${KXBTC15M_LABELS_JSON:-$LABELS_DIR/settled_labels.json}"
STATUS_JSON="${KXBTC15M_VALIDATION_STATUS:-$LABELS_DIR/validation_status.json}"
EVIDENCE_DIR="${REPO_ROOT}/.agent/evidence/kxbtc15m-verified-index-labels"
mkdir -p "$LABELS_DIR" "$EVIDENCE_DIR"

cd "$REPO_ROOT"
echo "=== kxbtc15m labels $(date -u +%Y-%m-%dT%H:%M:%SZ) dir=$LABELS_DIR ==="

"$PY" "$REPO_ROOT/kxbtc15m_live_labels.py" \
  --decision-dir "$DECISION_DIR" \
  --out-json "$LABELS_JSON" \
  --max-pages "${KXBTC15M_LABEL_PAGES:-5}"

"$PY" "$REPO_ROOT/scripts/execution-gate/kxbtc15m_validation_status.py" \
  --decision-dir "$DECISION_DIR" \
  --labels "$LABELS_JSON" \
  --out "$STATUS_JSON"

cp "$STATUS_JSON" "$EVIDENCE_DIR/validation_status.json" 2>/dev/null || true
echo "=== kxbtc15m labels done $(date -u +%Y-%m-%dT%H:%M:%SZ) ==="
