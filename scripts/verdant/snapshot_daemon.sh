#!/usr/bin/env bash
# Collect BTC snapshots on a schedule.
# Prefer Verdant remote when mounted; when offline, write to local snapshot cache
# if models were previously pulled (Captain-approved offline snapshot cache).
set -euo pipefail
source "$(dirname "$0")/env.sh"
# shellcheck source=verdant_staging.sh
source "$(dirname "$0")/verdant_staging.sh"
cd "$REPO_ROOT"

verdant_ensure_local_dirs

if verdant_remote_mounted; then
  verdant_pull_cache
  export BTC_KALSHI_ROOT="$BTC_KALSHI_REMOTE_ROOT"
  echo "=== Snapshot daemon (remote): $(date -u +%Y-%m-%dT%H:%M:%SZ) ==="
elif verdant_local_has_scan_cache; then
  export BTC_KALSHI_ROOT="$BTC_KALSHI_LOCAL_ROOT"
  echo "=== Snapshot daemon (offline local cache): $(date -u +%Y-%m-%dT%H:%M:%SZ) ==="
  echo "Remote unmounted — writing snapshots to $BTC_KALSHI_ROOT/snapshots"
else
  echo "=== Snapshot daemon skip: $(date -u +%Y-%m-%dT%H:%M:%SZ) ==="
  echo "Verdant not mounted and no local model cache at $BTC_KALSHI_LOCAL_ROOT"
  echo "Connect drive and run: scripts/verdant/sync_verdant_staging.sh --pull"
  exit 0
fi

exec "$PY" snapshot_daemon.py --data-root "$BTC_KALSHI_ROOT" --interval-seconds 900
