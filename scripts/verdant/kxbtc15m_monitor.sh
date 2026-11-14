#!/usr/bin/env bash
# One-shot KXBTC15M monitor tick for launchd StartInterval.
# Read-only market data; never places orders; does not touch paper_buy_no_v1.
#
# Note: macOS /bin/bash is 3.2 — empty arrays with set -u + "${arr[@]}" fail.
# Build a single non-empty cmd array instead.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=env.sh
source "$SCRIPT_DIR/env.sh"

LOG_DIR="${HOME}/Library/Logs/verdant"
mkdir -p "$LOG_DIR"

# Prefer Verdant remote when mounted; else local staging (ADR-003).
if [[ -d "$BTC_KALSHI_REMOTE_ROOT" ]]; then
  OUT_ROOT="$BTC_KALSHI_REMOTE_ROOT"
else
  OUT_ROOT="$BTC_KALSHI_LOCAL_ROOT"
  mkdir -p "$OUT_ROOT"
fi
OUTPUT_DIR="${KXBTC15M_OUTPUT_DIR:-$OUT_ROOT/live_outputs/kxbtc15m}"
mkdir -p "$OUTPUT_DIR"

cd "$REPO_ROOT"
echo "=== kxbtc15m monitor $(date -u +%Y-%m-%dT%H:%M:%SZ) out=$OUTPUT_DIR ==="

cmd=(
  "$PY"
  "$REPO_ROOT/kxbtc15m_monitor.py"
  --once
  --output-dir "$OUTPUT_DIR"
)

# Snapshot fallback for honest exchange_spot_proxy when no better index is configured.
SNAPSHOTS_DIR="${KXBTC15M_SNAPSHOTS_DIR:-$OUT_ROOT/snapshots}"
if [[ -d "$SNAPSHOTS_DIR" ]]; then
  cmd+=(--snapshots-dir "$SNAPSHOTS_DIR")
fi

# Provenance: numeric env is operator_supplied (NOT kalshi_api).
if [[ -n "${KXBTC15M_SETTLEMENT_INDEX:-}" ]]; then
  cmd+=(--settlement-index "$KXBTC15M_SETTLEMENT_INDEX" --settlement-index-source operator_supplied)
elif [[ -n "${KXBTC15M_INDEX_FILE:-}" ]]; then
  cmd+=(--index-file "$KXBTC15M_INDEX_FILE")
elif [[ -n "${KXBTC15M_SPOT_PROXY:-}" ]]; then
  cmd+=(--spot-proxy "$KXBTC15M_SPOT_PROXY")
fi

if [[ -n "${KXBTC15M_VOL:-}" ]]; then
  cmd+=(--vol "$KXBTC15M_VOL")
fi

"${cmd[@]}"
echo "=== kxbtc15m monitor done $(date -u +%Y-%m-%dT%H:%M:%SZ) ==="
