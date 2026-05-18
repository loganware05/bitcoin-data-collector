#!/usr/bin/env python3
"""
Example runner for the BTC signal engine.

Usage:
  python3 examples/run_signal_engine.py outputs/btc_market_intel_*.json
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from signal_engine import SignalEngineConfig, generate_signal, load_snapshot  # noqa: E402


def main() -> int:
    if len(sys.argv) < 2:
        print("Usage: python3 examples/run_signal_engine.py <path/to/btc_market_intel_*.json>")
        return 2

    snapshot_path = Path(sys.argv[1])
    snap = load_snapshot(snapshot_path)

    cfg = SignalEngineConfig()
    out = generate_signal(snap, cfg)
    print(json.dumps(out, indent=2, sort_keys=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

