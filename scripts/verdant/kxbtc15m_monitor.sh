#!/usr/bin/env bash
# One-shot KXBTC15M monitor tick for launchd StartInterval.
# Read-only market data; never places orders; does not touch paper_buy_no_v1.
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

# Spot proxy optional: used only when explicit index unset.
# Edge-counting readiness requires kalshi_api/cf_benchmarks (see decision engine flags).
SPOT_ARGS=()
if [[ -n "${KXBTC15M_SETTLEMENT_INDEX:-}" ]]; then
  SPOT_ARGS+=(--settlement-index "$KXBTC15M_SETTLEMENT_INDEX")
elif [[ -n "${KXBTC15M_SPOT_PROXY:-}" ]]; then
  SPOT_ARGS+=(--spot-proxy "$KXBTC15M_SPOT_PROXY")
fi

VOL_ARGS=()
if [[ -n "${KXBTC15M_VOL:-}" ]]; then
  VOL_ARGS+=(--vol "$KXBTC15M_VOL")
fi

cd "$REPO_ROOT"
echo "=== kxbtc15m monitor $(date -u +%Y-%m-%dT%H:%M:%SZ) out=$OUTPUT_DIR ==="
"$PY" "$REPO_ROOT/kxbtc15m_monitor.py" --once --output-dir "$OUTPUT_DIR" "${SPOT_ARGS[@]}" "${VOL_ARGS[@]}"
echo "=== kxbtc15m monitor done $(date -u +%Y-%m-%dT%H:%M:%SZ) ==="
