#!/usr/bin/env bash
# Shared environment for Verdant BTC Kalshi pipeline jobs.
export BTC_KALSHI_ROOT="${BTC_KALSHI_ROOT:-/Volumes/Verdant_AI/btc_kalshi}"
export REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
export PY="${PY:-/opt/anaconda3/bin/python}"

if [[ ! -x "$PY" ]]; then
  PY="$(command -v python3)"
fi

if [[ ! -d "$BTC_KALSHI_ROOT" ]]; then
  echo "ERROR: Verdant data root not mounted: $BTC_KALSHI_ROOT" >&2
  exit 1
fi
