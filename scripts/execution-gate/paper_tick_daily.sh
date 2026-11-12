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
export BTC_KALSHI_LOCAL_ROOT="${BTC_KALSHI_LOCAL_ROOT:-$HOME/.local/share/verdant-btc-kalshi}"
STATE_DIR="${PAPER_STATE_DIR:-$REPO_ROOT/.agent/evidence/execution-gate-evidence/paper}"
STRATEGY="${PAPER_STRATEGY:-$REPO_ROOT/scripts/execution-gate/paper_strategy_v1.json}"
LOG_DIR="${PAPER_LOG_DIR:-$HOME/Library/Logs/verdant}"
PY="${PY:-$(command -v python3)}"
ALERT_PATH="${PAPER_CONTINUITY_ALERT:-$STATE_DIR/continuity_alert.json}"

mkdir -p "$STATE_DIR" "$LOG_DIR"
cd "$REPO_ROOT"

ts="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
echo "=== execution-gate paper tick $ts ==="
echo "state=$STATE_DIR"
echo "strategy=$STRATEGY"
echo "approved_for_execution=false"

has_scans() {
  local dir="$1"
  [[ -d "$dir" ]] || return 1
  # Prefer scan_*.json presence over mere directory existence.
  [[ -n "$(find "$dir" -maxdepth 1 -name 'scan_*.json' -print -quit 2>/dev/null)" ]]
}

write_soft_skip_alert() {
  local reason="$1"
  local remote_dir="$2"
  local local_dir="$3"
  "$PY" - "$ALERT_PATH" "$ts" "$reason" "$remote_dir" "$local_dir" <<'PY'
import json, sys
from pathlib import Path
path, created_at, reason, remote_dir, local_dir = sys.argv[1:6]
payload = {
    "schema": "bdc.execution_gate.paper_continuity_alert.v1",
    "created_at": created_at,
    "event": "soft_skip_no_hourly_feed",
    "reason": reason,
    "approved_for_execution": False,
    "day_clock_advanced": False,
    "remote_hourly_outputs": remote_dir,
    "local_hourly_outputs": local_dir,
    "note": "Soft-skip avoids false continuity; schedule another tick once scans exist.",
}
Path(path).write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
print(f"wrote continuity alert: {path}", file=sys.stderr)
PY
}

# Resolve hourly feed: explicit override → remote → local staging (ADR-003).
HOURLY_DIR=""
HOURLY_SOURCE=""
if [[ -n "${PAPER_HOURLY_OUTPUTS:-}" ]]; then
  if has_scans "$PAPER_HOURLY_OUTPUTS"; then
    HOURLY_DIR="$PAPER_HOURLY_OUTPUTS"
    HOURLY_SOURCE="explicit"
  else
    echo "WARN: PAPER_HOURLY_OUTPUTS set but no scan_*.json under $PAPER_HOURLY_OUTPUTS" >&2
  fi
fi

REMOTE_HOURLY="${BTC_KALSHI_REMOTE_ROOT}/hourly_outputs"
LOCAL_HOURLY="${BTC_KALSHI_LOCAL_ROOT}/hourly_outputs"

if [[ -z "$HOURLY_DIR" ]] && has_scans "$REMOTE_HOURLY"; then
  HOURLY_DIR="$REMOTE_HOURLY"
  HOURLY_SOURCE="remote"
fi
if [[ -z "$HOURLY_DIR" ]] && has_scans "$LOCAL_HOURLY"; then
  HOURLY_DIR="$LOCAL_HOURLY"
  HOURLY_SOURCE="local_staging"
fi

echo "hourly=${HOURLY_DIR:-MISSING}"
echo "hourly_source=${HOURLY_SOURCE:-none}"

if [[ -z "$HOURLY_DIR" ]]; then
  reason="no_scan_json_under_remote_or_local"
  echo "WARN: hourly outputs missing (remote=$REMOTE_HOURLY local=$LOCAL_HOURLY); day clock not advanced — soft skip" >&2
  write_soft_skip_alert "$reason" "$REMOTE_HOURLY" "$LOCAL_HOURLY"
  # Soft-fail: do not advance clock without a scan feed (avoids false continuity)
  exit 0
fi

# Clear prior soft-skip alert on successful feed resolution.
rm -f "$ALERT_PATH"

"$PY" "$REPO_ROOT/scripts/execution-gate/phase_b_live_scan_tick.py" \
  --hourly-outputs "$HOURLY_DIR" \
  --state-dir "$STATE_DIR" \
  --strategy "$STRATEGY"

echo "=== paper tick done $(date -u +%Y-%m-%dT%H:%M:%SZ) source=$HOURLY_SOURCE ==="
