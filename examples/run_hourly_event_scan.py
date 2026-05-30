#!/usr/bin/env python3
"""
Run Kalshi BTC hourly event scan (recommendation only — no trade execution).

Usage:
  python examples/run_hourly_event_scan.py
  python examples/run_hourly_event_scan.py --conservative --once
  python examples/run_hourly_event_scan.py --event-filter "BTC price today" --snapshot outputs/btc_market_intel_*.json --no-collect
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from hourly_event_scanner import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main())
