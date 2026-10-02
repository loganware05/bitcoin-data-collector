#!/usr/bin/env bash
# Install + reload all Verdant LaunchAgents with local logs and /bin/bash wrapper.
#
# Usage:
#   ./scripts/verdant/ensure_verdant_jobs.sh
#   ./scripts/verdant/ensure_verdant_jobs.sh --check
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=env.sh
source "$SCRIPT_DIR/env.sh"

DOMAIN="gui/$(id -u)"
LOCAL_LOG_DIR="$HOME/Library/Logs/verdant"
CHECK_ONLY=0
[[ "${1:-}" == "--check" ]] && CHECK_ONLY=1

mkdir -p "$LOCAL_LOG_DIR" "$HOME/Library/LaunchAgents"
chmod +x "$SCRIPT_DIR/"*.sh

install_plist() {
  local label="$1"
  local src="$REPO_ROOT/scripts/verdant/launchd/${label}.plist"
  local dst="$HOME/Library/LaunchAgents/${label}.plist"
  sed -e "s|REPO_ROOT_PLACEHOLDER|$REPO_ROOT|g" \
      -e "s|HOME_PLACEHOLDER|$HOME|g" \
      "$src" > "$dst"
  /usr/bin/python3 - <<PY
import plistlib
from pathlib import Path
path = Path(r"""$dst""")
plist = plistlib.loads(path.read_bytes())
script = plist["ProgramArguments"][0]
plist["ProgramArguments"] = ["/bin/bash", script]
plist["WorkingDirectory"] = str(Path.home())
path.write_bytes(plistlib.dumps(plist))
PY
  echo "Installed $dst"
}

reload_job() {
  local label="$1"
  launchctl bootout "$DOMAIN/$label" 2>/dev/null || true
  launchctl bootstrap "$DOMAIN" "$HOME/Library/LaunchAgents/${label}.plist"
  launchctl enable "$DOMAIN/$label" 2>/dev/null || true
  echo "Reloaded $label"
}

labels=(
  com.verdant.btc-kalshi.snapshot-daemon
  com.verdant.btc-kalshi.weekly-retrain
  com.verdant.btc-kalshi.hourly-scan
  com.verdant.btc-kalshi.sync-staging
)

echo "=== ensure Verdant jobs: $(date -u +%Y-%m-%dT%H:%M:%SZ) ==="
issues=0
for label in "${labels[@]}"; do
  if [[ "$CHECK_ONLY" -eq 0 ]]; then
    install_plist "$label"
    reload_job "$label"
  fi
  if launchctl print "$DOMAIN/$label" >/dev/null 2>&1; then
    code="$(launchctl print "$DOMAIN/$label" 2>/dev/null | awk -F'= ' '/last exit code/ {gsub(/;.*/,"",$2); print $2; exit}')"
    echo "OK: $label loaded (last_exit=$code)"
    if [[ "$code" == "78" || "$code" == "126" ]]; then
      echo "WARN: $label last_exit=$code" >&2
      issues=$((issues + 1))
    fi
  else
    echo "WARN: $label not loaded" >&2
    issues=$((issues + 1))
  fi
done

echo "Logs: $LOCAL_LOG_DIR/"
exit "$([[ "$issues" -eq 0 ]] && echo 0 || echo 1)"
