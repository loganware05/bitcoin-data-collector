#!/usr/bin/env bash
# Ensure the Verdant hourly-scan LaunchAgent stays loaded on the approved schedule.
#
# Usage:
#   ./scripts/verdant/ensure_hourly_scan_schedule.sh           # check + repair schedule
#   ./scripts/verdant/ensure_hourly_scan_schedule.sh --check   # report only (exit 1 if unhealthy)
#   ./scripts/verdant/ensure_hourly_scan_schedule.sh --kick    # also kickstart one run now
#
# Schedule (UTC): daily 12:00–23:00 at :00; Mon–Fri also 14:00–20:00 at :30 (119 fires/week).
# Safe to run manually, from cron, or after reboot / Verdant remount.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=env.sh
source "$SCRIPT_DIR/env.sh"

LABEL="com.verdant.btc-kalshi.hourly-scan"
PLIST_SRC="$REPO_ROOT/scripts/verdant/launchd/${LABEL}.plist"
PLIST_DST="$HOME/Library/LaunchAgents/${LABEL}.plist"
LOCAL_LOG_DIR="$HOME/Library/Logs/verdant"
DOMAIN="gui/$(id -u)"
EXPECTED_INTERVALS=119
STALE_HOURS="${STALE_HOURS:-6}"

CHECK_ONLY=0
KICK=0
for arg in "$@"; do
  case "$arg" in
    --check) CHECK_ONLY=1 ;;
    --kick) KICK=1 ;;
    -h|--help)
      sed -n '2,14p' "$0"
      exit 0
      ;;
    *)
      echo "Unknown arg: $arg" >&2
      exit 2
      ;;
  esac
done

mkdir -p "$LOCAL_LOG_DIR" "$HOME/Library/LaunchAgents"
chmod +x "$SCRIPT_DIR/"*.sh

now_utc="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
echo "=== ensure hourly-scan schedule: $now_utc ==="
echo "Repo: $REPO_ROOT"
echo "Data remote: $BTC_KALSHI_REMOTE_ROOT"
echo "Data local:  $BTC_KALSHI_LOCAL_ROOT"

issues=0
warn() { echo "WARN: $*" >&2; issues=$((issues + 1)); }
ok() { echo "OK: $*"; }

# --- Verdant mount ---
if [[ -d "$BTC_KALSHI_REMOTE_ROOT" ]]; then
  ok "Verdant remote data root mounted"
else
  warn "Verdant remote not mounted at $BTC_KALSHI_REMOTE_ROOT (hourly scans use local cache if available)"
fi

# --- Expected interval count in repo template ---
repo_intervals="$(
  /usr/bin/python3 - <<PY
import plistlib, pathlib
p = plistlib.loads(pathlib.Path(r"""$PLIST_SRC""").read_bytes())
print(len(p.get("StartCalendarInterval") or []))
PY
)"
if [[ "$repo_intervals" -eq "$EXPECTED_INTERVALS" ]]; then
  ok "Repo plist has $repo_intervals calendar intervals"
else
  warn "Repo plist intervals=$repo_intervals (expected $EXPECTED_INTERVALS)"
fi

install_plist() {
  sed -e "s|REPO_ROOT_PLACEHOLDER|$REPO_ROOT|g" \
      -e "s|HOME_PLACEHOLDER|$HOME|g" \
      "$PLIST_SRC" > "$PLIST_DST"
  # Prefer /bin/bash + $HOME cwd so launchd avoids Documents getcwd TCC noise.
  /usr/bin/python3 - <<PY
import plistlib
from pathlib import Path
path = Path(r"""$PLIST_DST""")
plist = plistlib.loads(path.read_bytes())
script = plist["ProgramArguments"][0]
plist["ProgramArguments"] = ["/bin/bash", script]
plist["WorkingDirectory"] = str(Path.home())
path.write_bytes(plistlib.dumps(plist))
PY
  echo "Installed $PLIST_DST (bash + HOME working directory)"
}

reload_job() {
  launchctl bootout "$DOMAIN/$LABEL" 2>/dev/null || true
  launchctl bootstrap "$DOMAIN" "$PLIST_DST"
  launchctl enable "$DOMAIN/$LABEL" 2>/dev/null || true
  echo "Reloaded $DOMAIN/$LABEL"
}

installed_intervals() {
  /usr/bin/python3 - <<PY
import plistlib, pathlib
p = plistlib.loads(pathlib.Path(r"""$PLIST_DST""").read_bytes())
print(len(p.get("StartCalendarInterval") or []))
PY
}

job_loaded() {
  launchctl print "$DOMAIN/$LABEL" >/dev/null 2>&1
}

last_exit_code() {
  launchctl print "$DOMAIN/$LABEL" 2>/dev/null \
    | awk -F'= ' '/last exit code/ {gsub(/;.*/,"",$2); print $2; exit}' \
    || echo "unknown"
}

tcc_blocked() {
  [[ -f "$LOCAL_LOG_DIR/hourly_scan.stderr.log" ]] \
    && grep -q "Operation not permitted" "$LOCAL_LOG_DIR/hourly_scan.stderr.log" 2>/dev/null
}

newest_scan_age_hours() {
  /usr/bin/python3 - <<PY
from pathlib import Path
import time

def newest(root: Path):
    files = sorted((root / "hourly_outputs").glob("scan_*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    if not files:
        return None
    age_h = (time.time() - files[0].stat().st_mtime) / 3600.0
    return files[0].name, age_h

remote = Path(r"""$BTC_KALSHI_REMOTE_ROOT""")
local_ = Path(r"""$BTC_KALSHI_LOCAL_ROOT""")
best = None
for label, root in [("remote", remote), ("local", local_)]:
    if not (root / "hourly_outputs").is_dir():
        continue
    hit = newest(root)
    if hit is None:
        continue
    name, age = hit
    if best is None or age < best[2]:
        best = (label, name, age)
if best is None:
    print("none")
else:
    print(f"{best[0]}:{best[1]}|{best[2]:.2f}")
PY
}

# --- Repair path ---
if [[ "$CHECK_ONLY" -eq 0 ]]; then
  install_plist
  reload_job
fi

# --- Verify installed schedule ---
if [[ ! -f "$PLIST_DST" ]]; then
  warn "Installed plist missing: $PLIST_DST (run without --check)"
else
  got="$(installed_intervals)"
  if [[ "$got" -eq "$EXPECTED_INTERVALS" ]]; then
    ok "Installed LaunchAgent has $got calendar intervals"
  else
    warn "Installed intervals=$got (expected $EXPECTED_INTERVALS)"
  fi
fi

if job_loaded; then
  ok "LaunchAgent loaded: $DOMAIN/$LABEL"
  exit_code="$(last_exit_code)"
  echo "Last exit code: $exit_code"
  if [[ "$exit_code" == "(never exited)" || "$exit_code" == "-" || "$exit_code" == "unknown" || -z "$exit_code" ]]; then
    ok "No completed exit yet (calendar agent idle or freshly reloaded)"
  elif [[ "$exit_code" == "0" ]]; then
    ok "Last exit was success"
  elif [[ "$exit_code" == "126" ]] || [[ "$exit_code" == "127" ]]; then
    warn "Last exit $exit_code — script could not execute (often macOS TCC / Full Disk Access)"
  elif [[ "$exit_code" == "78" ]]; then
    warn "Last exit 78 (EX_CONFIG) — usually log path / config issue"
  else
    warn "Non-zero last exit: $exit_code (see $LOCAL_LOG_DIR/hourly_scan.stderr.log)"
  fi
else
  warn "LaunchAgent NOT loaded"
fi

if tcc_blocked; then
  # Only treat as active if stderr was touched in the last 48h
  if [[ -f "$LOCAL_LOG_DIR/hourly_scan.stderr.log" ]] \
    && find "$LOCAL_LOG_DIR/hourly_scan.stderr.log" -mtime -2 | grep -q .; then
    warn "Recent stderr shows 'Operation not permitted' — launchd cannot run scripts under Documents/"
    cat <<EOF >&2

REMEDIATION (required for the timer to actually fire successfully):
  1. Open System Settings → Privacy & Security → Full Disk Access
  2. Unlock, click +, enable /bin/bash (and/or Terminal)
  3. Re-run: $SCRIPT_DIR/ensure_hourly_scan_schedule.sh --kick
  Alternative: move/clone the repo outside ~/Documents (e.g. ~/src/...) and re-run
  install_launchd.sh + this ensure script so ProgramArguments point at the new path.

EOF
  fi
fi

# --- Scan freshness ---
scan_info="$(newest_scan_age_hours)"
if [[ "$scan_info" == "none" ]]; then
  warn "No scan_*.json under remote or local staging hourly_outputs"
else
  scan_src="${scan_info%%:*}"
  rest="${scan_info#*:}"
  scan_name="${rest%%|*}"
  scan_age="${rest##*|}"
  echo "Newest scan: [$scan_src] $scan_name (${scan_age}h ago)"
  hour_utc="$(date -u +%H)"
  hour_utc=$((10#$hour_utc))
  if (( hour_utc >= 12 && hour_utc <= 23 )); then
    if awk -v a="$scan_age" -v lim="$STALE_HOURS" 'BEGIN { exit !(a > lim) }'; then
      warn "Scan older than ${STALE_HOURS}h during active UTC hours — timer may be failing"
    else
      ok "Scan fresh within ${STALE_HOURS}h during active hours"
    fi
  else
    ok "Outside peak UTC window; scan age ${scan_age}h (staleness not enforced)"
  fi
fi

if [[ "$KICK" -eq 1 ]]; then
  echo "Kickstarting one hourly-scan run..."
  if launchctl kickstart -k "$DOMAIN/$LABEL" 2>/dev/null; then
    ok "kickstart issued"
  else
    warn "kickstart failed; running hourly_scan.sh directly"
    "$SCRIPT_DIR/hourly_scan.sh"
  fi
fi

echo
echo "Logs: $LOCAL_LOG_DIR/hourly_scan.stdout.log | hourly_scan.stderr.log"
echo "Manual scan: $SCRIPT_DIR/hourly_scan.sh"
echo "Staging sync: $SCRIPT_DIR/sync_verdant_staging.sh [--pull|--push|--check]"
echo "=== ensure complete (issues=$issues) ==="
exit "$([[ "$issues" -eq 0 ]] && echo 0 || echo 1)"
