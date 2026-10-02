#!/usr/bin/env bash
# Replay actionable settlement eval for Sep 13–Oct 2 (postfix-buy-no-calibration).
# Eval only — calibrator fit stays disabled (SETTLEMENT_FIT_ENABLE defaults 0).
#
# Usage:
#   ./scripts/verdant/settlement_sep13_oct2_replay.sh
#   SETTLEMENT_SINCE=2026-09-13 SETTLEMENT_UNTIL=2026-10-02 ./scripts/verdant/settlement_sep13_oct2_replay.sh
#
# Prefers Verdant remote; falls back to local staging if models were pulled.
set -euo pipefail
source "$(dirname "$0")/env.sh"
# shellcheck source=verdant_staging.sh
source "$(dirname "$0")/verdant_staging.sh"
cd "$REPO_ROOT"

SETTLEMENT_SINCE="${SETTLEMENT_SINCE:-2026-09-13}"
SETTLEMENT_UNTIL="${SETTLEMENT_UNTIL:-2026-10-02}"
SETTLEMENT_FIT_ENABLE="${SETTLEMENT_FIT_ENABLE:-0}"
SETTLEMENT_BATCH_SIZE="${SETTLEMENT_BATCH_SIZE:-25}"

if ! verdant_resolve_active_root; then
  echo "ERROR: cannot resolve BTC_KALSHI_ROOT for Sep13–Oct2 replay" >&2
  exit 1
fi

CACHE_DIR="${SETTLEMENT_CACHE_DIR:-$BTC_KALSHI_ROOT/settlement_cache}"
REPORT_DIR="${SETTLEMENT_REPORT_DIR:-$BTC_KALSHI_ROOT/logs}"
EVIDENCE_DIR="${REPO_ROOT}/.agent/evidence/postfix-buy-no-calibration"
mkdir -p "$CACHE_DIR" "$REPORT_DIR" "$EVIDENCE_DIR"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
REPORT_OUT="$REPORT_DIR/settlement_sep13_oct2_replay_${STAMP}.json"
EVIDENCE_OUT="$EVIDENCE_DIR/sep13_oct2_replay_${STAMP}.json"

echo "=== Postfix BUY NO replay ${SETTLEMENT_SINCE} → ${SETTLEMENT_UNTIL} (fit=${SETTLEMENT_FIT_ENABLE}) ==="
echo "Root: $BTC_KALSHI_ROOT"

SCAN_COUNT="$(find "$BTC_KALSHI_ROOT/hourly_outputs" -maxdepth 1 -name 'scan_*.json' 2>/dev/null | wc -l | tr -d ' ')"
if [[ "${SCAN_COUNT}" == "0" ]]; then
  cat > "$EVIDENCE_OUT" <<JSON
{
  "success": false,
  "blocker": "no_scan_files",
  "btc_kalshi_root": "$BTC_KALSHI_ROOT",
  "since": "$SETTLEMENT_SINCE",
  "until": "$SETTLEMENT_UNTIL",
  "message": "No scan_*.json under hourly_outputs. Mount Verdant or sync local staging, then re-run."
}
JSON
  cp "$EVIDENCE_OUT" "$REPORT_OUT" 2>/dev/null || true
  echo "BLOCKER: no scans at $BTC_KALSHI_ROOT/hourly_outputs" >&2
  echo "Evidence: $EVIDENCE_OUT"
  exit 2
fi

"$PY" kalshi_settlement_eval.py \
  --mode eval \
  --scan-dir "$BTC_KALSHI_ROOT/hourly_outputs" \
  --models-base-dir "$BTC_KALSHI_ROOT/models" \
  --cache-dir "$CACHE_DIR" \
  --batch-size "$SETTLEMENT_BATCH_SIZE" \
  --since "$SETTLEMENT_SINCE" \
  --until "$SETTLEMENT_UNTIL" \
  --report-out "$REPORT_OUT"

cp "$REPORT_OUT" "$EVIDENCE_OUT"
echo "Report: $REPORT_OUT"
echo "Evidence: $EVIDENCE_OUT"

if [[ "$SETTLEMENT_FIT_ENABLE" == "1" ]]; then
  echo "=== Fit calibrator (explicit Captain enable) ==="
  "$PY" kalshi_settlement_eval.py \
    --mode fit \
    --models-base-dir "$BTC_KALSHI_ROOT/models" \
    --cache-dir "$CACHE_DIR"
else
  echo "Fit skipped (SETTLEMENT_FIT_ENABLE=${SETTLEMENT_FIT_ENABLE}) — postfix-buy-no-calibration is eval-only."
fi
