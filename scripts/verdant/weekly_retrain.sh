#!/usr/bin/env bash
set -euo pipefail
source "$(dirname "$0")/env.sh"
cd "$REPO_ROOT"

# Settlement fit is opt-in until the post-guard Aug 28+ calibration gate passes.
# Eval always runs in its own process; fit (if enabled) runs in a second process.
SETTLEMENT_FIT_ENABLE="${SETTLEMENT_FIT_ENABLE:-0}"
SETTLEMENT_SINCE="${SETTLEMENT_SINCE:-}"
SETTLEMENT_BATCH_SIZE="${SETTLEMENT_BATCH_SIZE:-25}"
CACHE_DIR="${SETTLEMENT_CACHE_DIR:-$BTC_KALSHI_ROOT/settlement_cache}"
REPORT_DIR="${SETTLEMENT_REPORT_DIR:-$BTC_KALSHI_ROOT/logs}"
mkdir -p "$CACHE_DIR" "$REPORT_DIR"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
REPORT_OUT="$REPORT_DIR/settlement_eval_${STAMP}.json"

echo "=== Weekly retrain: $STAMP ==="
"$PY" pipeline_preflight.py --data-root "$BTC_KALSHI_ROOT"
"$PY" examples/run_verdant_pipeline.py \
  --data-root "$BTC_KALSHI_ROOT" \
  --skip-collect \
  --skip-scan

echo "=== Dataset export ==="
"$PY" dataset_builder.py "$BTC_KALSHI_ROOT/snapshots" \
  --output-dir "$BTC_KALSHI_ROOT/datasets" \
  --market-probs-csv "$BTC_KALSHI_ROOT/market_probs/market_probs.csv" \
  --horizon-hours 24

SINCE_ARGS=()
if [[ -n "$SETTLEMENT_SINCE" ]]; then
  SINCE_ARGS=(--since "$SETTLEMENT_SINCE")
fi

echo "=== Settlement EVAL (process A; no calibrator write) ==="
"$PY" kalshi_settlement_eval.py \
  --mode eval \
  --scan-dir "$BTC_KALSHI_ROOT/hourly_outputs" \
  --models-base-dir "$BTC_KALSHI_ROOT/models" \
  --cache-dir "$CACHE_DIR" \
  --batch-size "$SETTLEMENT_BATCH_SIZE" \
  --report-out "$REPORT_OUT" \
  "${SINCE_ARGS[@]}"

if [[ "$SETTLEMENT_FIT_ENABLE" == "1" ]]; then
  echo "=== Settlement FIT (process B; from labeled cache only) ==="
  "$PY" kalshi_settlement_eval.py \
    --mode fit \
    --models-base-dir "$BTC_KALSHI_ROOT/models" \
    --cache-dir "$CACHE_DIR" \
    --batch-size "$SETTLEMENT_BATCH_SIZE"
else
  echo "=== Settlement FIT skipped (SETTLEMENT_FIT_ENABLE=${SETTLEMENT_FIT_ENABLE}) ==="
  echo "    Eval report: $REPORT_OUT"
fi

echo "=== Weekly retrain complete ==="
