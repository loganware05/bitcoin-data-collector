#!/usr/bin/env bash
set -euo pipefail
source "$(dirname "$0")/env.sh"
cd "$REPO_ROOT"

echo "=== Weekly retrain: $(date -u +%Y-%m-%dT%H:%M:%SZ) ==="
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

echo "=== Settlement eval + fit probability calibrator ==="
"$PY" kalshi_settlement_eval.py \
  --scan-dir "$BTC_KALSHI_ROOT/hourly_outputs" \
  --models-base-dir "$BTC_KALSHI_ROOT/models" \
  --fit-calibration

echo "=== Weekly retrain complete ==="
