#!/usr/bin/env bash
set -euo pipefail
source "$(dirname "$0")/env.sh"
cd "$REPO_ROOT"

echo "=== Snapshot daemon starting: $(date -u +%Y-%m-%dT%H:%M:%SZ) ==="
exec "$PY" snapshot_daemon.py --data-root "$BTC_KALSHI_ROOT" --interval-seconds 900
