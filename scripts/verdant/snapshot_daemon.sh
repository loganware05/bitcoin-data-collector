#!/usr/bin/env bash
set -euo pipefail
source "$(dirname "$0")/env.sh"
# shellcheck source=verdant_staging.sh
source "$(dirname "$0")/verdant_staging.sh"
cd "$REPO_ROOT"

if ! verdant_remote_mounted; then
  echo "=== Snapshot daemon skip: $(date -u +%Y-%m-%dT%H:%M:%SZ) ==="
  echo "Verdant volume not mounted at $BTC_KALSHI_REMOTE_ROOT — snapshots require external drive."
  exit 0
fi

export BTC_KALSHI_ROOT="$BTC_KALSHI_REMOTE_ROOT"
echo "=== Snapshot daemon starting: $(date -u +%Y-%m-%dT%H:%M:%SZ) ==="
exec "$PY" snapshot_daemon.py --data-root "$BTC_KALSHI_ROOT" --interval-seconds 900
