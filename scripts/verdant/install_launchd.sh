#!/usr/bin/env bash
# Install launchd jobs for the Verdant BTC Kalshi pipeline.
# Usage: ./install_launchd.sh
#
# Hourly scan schedule (UTC, after active-hours expansion):
#   - Daily 12:00–23:00 at :00
#   - Mon–Fri also 14:00–20:00 at :30 (denser peak coverage)
# Job stdout/stderr: ~/Library/Logs/verdant/ (local; avoids launchd EX_CONFIG
# when Verdant volume log paths are unavailable). Data still writes to
# BTC_KALSHI_ROOT=/Volumes/Verdant_AI/btc_kalshi.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
LAUNCHD_SRC="$REPO_ROOT/scripts/verdant/launchd"
LAUNCHD_DST="$HOME/Library/LaunchAgents"
LOG_DIR="/Volumes/Verdant_AI/btc_kalshi/logs"
LOCAL_LOG_DIR="$HOME/Library/Logs/verdant"

chmod +x "$REPO_ROOT/scripts/verdant/"*.sh
mkdir -p "$LOCAL_LOG_DIR" "$LAUNCHD_DST"
# Best-effort Verdant log dir (may fail if volume unmounted / ACL-restricted).
mkdir -p "$LOG_DIR" 2>/dev/null || true

for plist in "$LAUNCHD_SRC"/*.plist; do
  name="$(basename "$plist")"
  dest="$LAUNCHD_DST/$name"
  sed -e "s|REPO_ROOT_PLACEHOLDER|$REPO_ROOT|g" \
      -e "s|HOME_PLACEHOLDER|$HOME|g" \
      "$plist" > "$dest"
  echo "Installed $dest"
done

echo ""
echo "Load jobs with:"
echo "  launchctl load ~/Library/LaunchAgents/com.verdant.btc-kalshi.snapshot-daemon.plist"
echo "  launchctl load ~/Library/LaunchAgents/com.verdant.btc-kalshi.weekly-retrain.plist"
echo "  launchctl load ~/Library/LaunchAgents/com.verdant.btc-kalshi.hourly-scan.plist"
echo ""
echo "Unload with launchctl unload <path>"
echo "Hourly scan logs: $LOCAL_LOG_DIR/hourly_scan.*.log"
