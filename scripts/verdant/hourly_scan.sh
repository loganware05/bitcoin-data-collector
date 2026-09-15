#!/usr/bin/env bash
set -euo pipefail
source "$(dirname "$0")/env.sh"
# shellcheck source=verdant_staging.sh
source "$(dirname "$0")/verdant_staging.sh"
cd "$REPO_ROOT"

# Phase 1 paper trial (Captain-approved 2026-08-05): lower confidence floor only.
# Defaults in code remain 0.65; omit these flags to roll back. Keep min-edge=0.10.
PAPER_MIN_CONFIDENCE="${PAPER_MIN_CONFIDENCE:-0.48}"
PAPER_MIN_EDGE="${PAPER_MIN_EDGE:-0.10}"

echo "=== Hourly scan: $(date -u +%Y-%m-%dT%H:%M:%SZ) ==="
echo "Paper trial guards: min_confidence=${PAPER_MIN_CONFIDENCE} min_edge=${PAPER_MIN_EDGE}"

if ! verdant_prepare_hourly_scan; then
  echo "SKIP: no data root (drive offline and no local model cache)"
  exit 0
fi

"$PY" examples/run_verdant_pipeline.py \
  --data-root "$BTC_KALSHI_ROOT" \
  --skip-preflight \
  --skip-collect \
  --skip-train \
  --no-collect-scan \
  --min-confidence "$PAPER_MIN_CONFIDENCE" \
  --min-edge "$PAPER_MIN_EDGE"

verdant_finalize_hourly_scan

echo "=== Hourly scan complete (data root: $BTC_KALSHI_ROOT) ==="
