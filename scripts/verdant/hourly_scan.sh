#!/usr/bin/env bash
set -euo pipefail
source "$(dirname "$0")/env.sh"
cd "$REPO_ROOT"

# Phase 1 paper trial (Captain-approved 2026-08-05): lower confidence floor only.
# Defaults in code remain 0.65; omit these flags to roll back. Keep min-edge=0.10.
PAPER_MIN_CONFIDENCE="${PAPER_MIN_CONFIDENCE:-0.48}"
PAPER_MIN_EDGE="${PAPER_MIN_EDGE:-0.10}"

echo "=== Hourly scan: $(date -u +%Y-%m-%dT%H:%M:%SZ) ==="
echo "Paper trial guards: min_confidence=${PAPER_MIN_CONFIDENCE} min_edge=${PAPER_MIN_EDGE}"
"$PY" examples/run_verdant_pipeline.py \
  --data-root "$BTC_KALSHI_ROOT" \
  --skip-preflight \
  --skip-collect \
  --skip-train \
  --no-collect-scan \
  --min-confidence "$PAPER_MIN_CONFIDENCE" \
  --min-edge "$PAPER_MIN_EDGE"

echo "=== Hourly scan complete ==="
