#!/usr/bin/env bash
# Run settlement eval (+ optional fit) on the Aug 28+ post-guard window.
# Requires Verdant mounted. Example:
#   SETTLEMENT_FIT_ENABLE=1 ./scripts/verdant/settlement_aug28_window.sh
set -euo pipefail
source "$(dirname "$0")/env.sh"
# shellcheck source=verdant_staging.sh
source "$(dirname "$0")/verdant_staging.sh"
cd "$REPO_ROOT"

if ! verdant_remote_mounted; then
  echo "ERROR: Verdant not mounted at $BTC_KALSHI_REMOTE_ROOT" >&2
  exit 1
fi
export BTC_KALSHI_ROOT="$BTC_KALSHI_REMOTE_ROOT"

SETTLEMENT_FIT_ENABLE="${SETTLEMENT_FIT_ENABLE:-0}"
SETTLEMENT_SINCE="${SETTLEMENT_SINCE:-2026-08-28}"
SETTLEMENT_BATCH_SIZE="${SETTLEMENT_BATCH_SIZE:-25}"
CACHE_DIR="${SETTLEMENT_CACHE_DIR:-$BTC_KALSHI_ROOT/settlement_cache}"
REPORT_DIR="${SETTLEMENT_REPORT_DIR:-$BTC_KALSHI_ROOT/logs}"
mkdir -p "$CACHE_DIR" "$REPORT_DIR"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
REPORT_OUT="$REPORT_DIR/settlement_eval_since_${SETTLEMENT_SINCE//-/}_${STAMP}.json"

echo "=== Settlement window eval since ${SETTLEMENT_SINCE} ==="
"$PY" kalshi_settlement_eval.py \
  --mode eval \
  --scan-dir "$BTC_KALSHI_ROOT/hourly_outputs" \
  --models-base-dir "$BTC_KALSHI_ROOT/models" \
  --cache-dir "$CACHE_DIR" \
  --batch-size "$SETTLEMENT_BATCH_SIZE" \
  --since "$SETTLEMENT_SINCE" \
  --report-out "$REPORT_OUT"

echo "Report: $REPORT_OUT"
if [[ "$SETTLEMENT_FIT_ENABLE" == "1" ]]; then
  echo "=== Fit calibrator from cache (Aug 28+ labeled rows) ==="
  "$PY" kalshi_settlement_eval.py \
    --mode fit \
    --models-base-dir "$BTC_KALSHI_ROOT/models" \
    --cache-dir "$CACHE_DIR"
else
  echo "Fit skipped (SETTLEMENT_FIT_ENABLE=${SETTLEMENT_FIT_ENABLE}). Re-run with SETTLEMENT_FIT_ENABLE=1 after reviewing gate_pass."
fi
