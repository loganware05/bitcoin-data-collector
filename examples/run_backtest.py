#!/usr/bin/env python3
"""
Example runner for the probability backtester.

This repo's `outputs/` folder contains point-in-time snapshots, not a full OHLCV history.
So this example backtests across the available snapshot files and uses a short horizon
by default to ensure some labeled outcomes exist.

Usage:
  python3 examples/run_backtest.py --input outputs --horizon-hours 1
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from backtester import BacktestConfig, load_time_series, plot_outputs, run_backtest  # noqa: E402


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Run a simple backtest over local snapshots.")
    parser.add_argument("--input", default="outputs", help="CSV, JSON, or directory of snapshot JSONs.")
    parser.add_argument("--horizon-hours", type=float, default=1.0, help="Default 1h for the small sample snapshots.")
    parser.add_argument("--range-threshold-pct", type=float, default=0.01, help="Default ±1% range band.")
    parser.add_argument("--plot-dir", default="backtest_plots_example", help="Where to write matplotlib PNGs.")
    args = parser.parse_args()

    df = load_time_series(args.input)
    cfg = BacktestConfig(
        horizon=pd.Timedelta(hours=float(args.horizon_hours)),
        range_threshold_pct=float(args.range_threshold_pct),
    )
    results, summary = run_backtest(df, cfg=cfg)
    results.attrs["horizon"] = str(cfg.horizon)
    summary["plots"] = plot_outputs(results, args.plot_dir)

    print(json.dumps(summary, indent=2, sort_keys=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

