#!/usr/bin/env bash
# Daily paper tick for paper_kxbtc15m_v1 (simulated fills only).
# Separate state dir from paper_buy_no_v1. Never places live Kalshi orders.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
if [[ -f "$REPO_ROOT/scripts/verdant/env.sh" ]]; then
  # shellcheck source=/dev/null
  source "$REPO_ROOT/scripts/verdant/env.sh"
fi

export BTC_KALSHI_REMOTE_ROOT="${BTC_KALSHI_REMOTE_ROOT:-/Volumes/Verdant_AI/btc_kalshi}"
export BTC_KALSHI_LOCAL_ROOT="${BTC_KALSHI_LOCAL_ROOT:-$HOME/.local/share/verdant-btc-kalshi}"
STATE_DIR="${KXBTC15M_PAPER_STATE_DIR:-$REPO_ROOT/.agent/evidence/execution-gate-evidence/paper-kxbtc15m}"
STRATEGY="${KXBTC15M_PAPER_STRATEGY:-$REPO_ROOT/scripts/execution-gate/paper_strategy_kxbtc15m_v1.json}"
LOG_DIR="${HOME}/Library/Logs/verdant"
PY="${PY:-$(command -v python3)}"
ALERT_PATH="${KXBTC15M_CONTINUITY_ALERT:-$STATE_DIR/continuity_alert.json}"

# Hard separation from hourly paper clock.
if [[ "$(basename "$STATE_DIR")" == "paper" ]]; then
  echo "ERROR: refusing shared paper/ state dir (protects paper_buy_no_v1)" >&2
  exit 2
fi

mkdir -p "$STATE_DIR" "$LOG_DIR"
cd "$REPO_ROOT"

ts="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
echo "=== kxbtc15m paper tick $ts ==="
echo "state=$STATE_DIR"
echo "strategy=$STRATEGY"
echo "approved_for_execution=false"

has_ticks() {
  local dir="$1"
  [[ -d "$dir" ]] || return 1
  [[ -n "$(find "$dir" -maxdepth 1 -name 'kxbtc15m_tick_*.json' -print -quit 2>/dev/null)" ]]
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
    "schema": "bdc.execution_gate.kxbtc15m_paper_continuity_alert.v1",
    "created_at": created_at,
    "event": "soft_skip_no_kxbtc15m_feed",
    "reason": reason,
    "strategy_id": "paper_kxbtc15m_v1",
    "approved_for_execution": False,
    "day_clock_advanced": False,
    "remote_decision_dir": remote_dir,
    "local_decision_dir": local_dir,
    "note": "Soft-skip avoids false continuity; does not touch paper_buy_no_v1.",
}
Path(path).write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
print(f"wrote continuity alert: {path}", file=sys.stderr)
PY
}

DECISION_DIR=""
DECISION_SOURCE=""
REMOTE_DIR="${BTC_KALSHI_REMOTE_ROOT}/live_outputs/kxbtc15m"
LOCAL_DIR="${BTC_KALSHI_LOCAL_ROOT}/live_outputs/kxbtc15m"
REPO_DIR="$REPO_ROOT/live_outputs/kxbtc15m"

if [[ -n "${KXBTC15M_DECISION_DIR:-}" ]]; then
  # Explicit override: never fall through to other roots (keeps soft-skip tests honest).
  if has_ticks "$KXBTC15M_DECISION_DIR"; then
    DECISION_DIR="$KXBTC15M_DECISION_DIR"
    DECISION_SOURCE="explicit"
  else
    echo "WARN: KXBTC15M_DECISION_DIR set but no kxbtc15m_tick_*.json under $KXBTC15M_DECISION_DIR" >&2
    write_soft_skip_alert "explicit_dir_empty" "$KXBTC15M_DECISION_DIR" "$LOCAL_DIR"
    exit 0
  fi
fi

if [[ -z "$DECISION_DIR" ]] && has_ticks "$REMOTE_DIR"; then
  DECISION_DIR="$REMOTE_DIR"
  DECISION_SOURCE="remote"
fi
if [[ -z "$DECISION_DIR" ]] && has_ticks "$LOCAL_DIR"; then
  DECISION_DIR="$LOCAL_DIR"
  DECISION_SOURCE="local_staging"
fi
if [[ -z "$DECISION_DIR" ]] && has_ticks "$REPO_DIR"; then
  DECISION_DIR="$REPO_DIR"
  DECISION_SOURCE="repo"
fi

echo "decision_dir=${DECISION_DIR:-MISSING}"
echo "decision_source=${DECISION_SOURCE:-none}"

if [[ -z "$DECISION_DIR" ]]; then
  echo "WARN: no kxbtc15m ticks; day clock not advanced — soft skip" >&2
  write_soft_skip_alert "no_kxbtc15m_tick_json" "$REMOTE_DIR" "$LOCAL_DIR"
  exit 0
fi

rm -f "$ALERT_PATH"

"$PY" "$REPO_ROOT/scripts/execution-gate/phase_b_kxbtc15m_paper_tick.py" \
  --decision-dir "$DECISION_DIR" \
  --state-dir "$STATE_DIR" \
  --strategy "$STRATEGY"

echo "=== kxbtc15m paper tick done $(date -u +%Y-%m-%dT%H:%M:%SZ) source=$DECISION_SOURCE ==="
