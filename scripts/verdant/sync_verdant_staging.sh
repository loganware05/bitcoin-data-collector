#!/usr/bin/env bash
# Sync Verdant remote volume ↔ local laptop staging.
#
# Usage:
#   ./scripts/verdant/sync_verdant_staging.sh           # pull cache + push pending scans
#   ./scripts/verdant/sync_verdant_staging.sh --pull   # models/market_probs → local only
#   ./scripts/verdant/sync_verdant_staging.sh --push   # local scans → remote only
#   ./scripts/verdant/sync_verdant_staging.sh --check  # report mount + pending counts
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=env.sh
source "$SCRIPT_DIR/env.sh"
# shellcheck source=verdant_staging.sh
source "$SCRIPT_DIR/verdant_staging.sh"

MODE="sync"
for arg in "$@"; do
  case "$arg" in
    --pull) MODE="pull" ;;
    --push) MODE="push" ;;
    --sync) MODE="sync" ;;
    --check) MODE="check" ;;
    -h|--help)
      sed -n '2,10p' "$0"
      exit 0
      ;;
    *)
      echo "Unknown arg: $arg" >&2
      exit 2
      ;;
  esac
done

echo "=== Verdant staging sync: $(date -u +%Y-%m-%dT%H:%M:%SZ) ==="
echo "Remote: $BTC_KALSHI_REMOTE_ROOT"
echo "Local:  $BTC_KALSHI_LOCAL_ROOT"

if [[ "$MODE" == "check" ]]; then
  if verdant_remote_mounted; then
    echo "Remote: mounted"
  else
    echo "Remote: NOT mounted"
  fi
  local_scans=0
  if [[ -d "$BTC_KALSHI_LOCAL_ROOT/hourly_outputs" ]]; then
    local_scans="$(find "$BTC_KALSHI_LOCAL_ROOT/hourly_outputs" -maxdepth 1 -name 'scan_*.json' 2>/dev/null | wc -l | tr -d ' ')"
  fi
  echo "Local pending scans: $local_scans"
  if verdant_local_has_scan_cache; then
    echo "Local model cache: OK"
  else
    echo "Local model cache: missing (run --pull when drive connected)"
  fi
  exit 0
fi

case "$MODE" in
  pull) verdant_pull_cache ;;
  push) verdant_push_pending_scans ;;
  sync) verdant_sync_all ;;
esac

echo "=== Staging sync complete ==="
