#!/usr/bin/env bash
# Shared environment for Verdant BTC Kalshi pipeline jobs.
export BTC_KALSHI_REMOTE_ROOT="${BTC_KALSHI_REMOTE_ROOT:-/Volumes/Verdant_AI/btc_kalshi}"
export BTC_KALSHI_LOCAL_ROOT="${BTC_KALSHI_LOCAL_ROOT:-$HOME/.local/share/verdant-btc-kalshi}"
# Active root for the current job (may be remote or local staging).
export BTC_KALSHI_ROOT="${BTC_KALSHI_ROOT:-$BTC_KALSHI_REMOTE_ROOT}"
export REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
export PY="${PY:-/opt/anaconda3/bin/python}"

if [[ ! -x "$PY" ]]; then
  PY="$(command -v python3)"
fi

# Legacy scripts expect BTC_KALSHI_ROOT; hourly_scan resolves via verdant_staging.sh.
# Do not hard-exit when the external drive is unplugged.
