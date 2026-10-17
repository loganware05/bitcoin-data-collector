#!/usr/bin/env bash
# Daily live-forward paper tick (simulated fills only).
# Advances the execution-gate day clock under paper_buy_no_v1.
# Never places live Kalshi orders; never sets approved_for_execution.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
# Prefer Verdant env helpers when available
if [[ -f "$REPO_ROOT/scripts/verdant/env.sh" ]]; then
  # shellcheck source=/dev/null
  source "$REPO_ROOT/scripts/verdant/env.sh"
fi

export BTC_KALSHI_REMOTE_ROOT="${BTC_KALSHI_REMOTE_ROOT:-/Volumes/Verdant_AI/btc_kalshi}"
HOURLY_DIR="${PAPER_HOURLY_OUTPUTS:-$BTC_KALSHI_REMOTE_ROOT/hourly_outputs}"
STATE_DIR="${PAPER_STATE_DIR:-$REPO_ROOT/.agent/evidence/execution-gate-evidence/paper}"
STRATEGY="${PAPER_STRATEGY:-$REPO_ROOT/scripts/execution-gate/paper_strategy_v1.json}"
LOG_DIR="${PAPER_LOG_DIR:-$HOME/Library/Logs/verdant}"
PY="${PY:-$(command -v python3)}"

mkdir -p "$STATE_DIR" "$LOG_DIR"
cd "$REPO_ROOT"

ts="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
echo "=== execution-gate paper tick $ts ==="
echo "hourly=$HOURLY_DIR"
echo "state=$STATE_DIR"
echo "strategy=$STRATEGY"
echo "approved_for_execution=false"

if [[ ! -d "$HOURLY_DIR" ]]; then
  echo "WARN: hourly outputs missing ($HOURLY_DIR); day clock still needs a daily run — failing soft" >&2
  # Soft-fail: do not advance clock without a scan feed (avoids false continuity)
  exit 0
fi

"$PY" "$REPO_ROOT/scripts/execution-gate/phase_b_live_scan_tick.py" \
  --hourly-outputs "$HOURLY_DIR" \
  --state-dir "$STATE_DIR" \
  --strategy "$STRATEGY"

echo "=== paper tick done $(date -u +%Y-%m-%dT%H:%M:%SZ) ==="
