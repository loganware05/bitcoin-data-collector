from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from backtester import load_time_series
from ml_model import TrainConfig, build_labeled_dataset
from verdant_paths import VerdantLayout, resolve_layout

MIN_CANDLE_BARS = 101
DEFAULT_MIN_LABELED_ROWS = 150
SHORT_HORIZON_MIN_ROWS = 50

HORIZON_SPECS: tuple[dict[str, Any], ...] = (
    {"key": "15m", "horizon_hours": 0.25, "models_subdir": "15m", "range_threshold_pct": 0.003},
    {"key": "30m", "horizon_hours": 0.5, "models_subdir": "30m", "range_threshold_pct": 0.005},
    {"key": "60m", "horizon_hours": 1.0, "models_subdir": "60m", "range_threshold_pct": 0.007},
    {"key": "4h", "horizon_hours": 4.0, "models_subdir": "4h", "range_threshold_pct": 0.01},
    {"key": "24h", "horizon_hours": 24.0, "models_subdir": "24h", "range_threshold_pct": 0.01},
)


@dataclass(frozen=True)
class SnapshotAudit:
    snapshot_count: int
    date_range_start: str | None
    date_range_end: str | None
    span_hours: float
    median_spacing_minutes: float | None
    candles_ok_fraction: float
    mount_ok: bool
    snapshots_dir: str


@dataclass(frozen=True)
class HorizonReadiness:
    key: str
    horizon_hours: float
    labeled_rows: int
    span_hours: float
    class_balance: dict[str, int]
    ok: bool
    reason: str


def check_mount(data_root: Path) -> bool:
    return data_root.exists() and data_root.is_dir()


def _candles_bar_count(snapshot: dict[str, Any]) -> int:
    candles = (snapshot.get("market_data") or {}).get("candles_15m") or []
    return len(candles) if isinstance(candles, list) else 0


def audit_snapshots(snapshots_dir: Path, *, data_root: Path | None = None) -> SnapshotAudit:
    root = data_root or snapshots_dir.parent
    mount_ok = check_mount(root)
    if not snapshots_dir.exists():
        return SnapshotAudit(
            snapshot_count=0,
            date_range_start=None,
            date_range_end=None,
            span_hours=0.0,
            median_spacing_minutes=None,
            candles_ok_fraction=0.0,
            mount_ok=mount_ok,
            snapshots_dir=str(snapshots_dir),
        )

    files = sorted(snapshots_dir.glob("btc_market_intel_*.json"))
    if not files:
        return SnapshotAudit(
            snapshot_count=0,
            date_range_start=None,
            date_range_end=None,
            span_hours=0.0,
            median_spacing_minutes=None,
            candles_ok_fraction=0.0,
            mount_ok=mount_ok,
            snapshots_dir=str(snapshots_dir),
        )

    timestamps: list[pd.Timestamp] = []
    candles_ok = 0
    for fp in files:
        try:
            with fp.open("r", encoding="utf-8") as f:
                snap = json.load(f)
        except (json.JSONDecodeError, OSError):
            continue
        if not isinstance(snap, dict):
            continue
        ts = pd.to_datetime(snap.get("timestamp"), utc=True, errors="coerce")
        if pd.isna(ts):
            continue
        timestamps.append(ts)
        if _candles_bar_count(snap) >= MIN_CANDLE_BARS:
            candles_ok += 1

    if not timestamps:
        return SnapshotAudit(
            snapshot_count=len(files),
            date_range_start=None,
            date_range_end=None,
            span_hours=0.0,
            median_spacing_minutes=None,
            candles_ok_fraction=0.0,
            mount_ok=mount_ok,
            snapshots_dir=str(snapshots_dir),
        )

    timestamps = sorted(timestamps)
    span_hours = (timestamps[-1] - timestamps[0]).total_seconds() / 3600.0
    spacing: float | None = None
    if len(timestamps) >= 2:
        diffs = [(timestamps[i + 1] - timestamps[i]).total_seconds() / 60.0 for i in range(len(timestamps) - 1)]
        spacing = float(np.median(diffs))

    return SnapshotAudit(
        snapshot_count=len(timestamps),
        date_range_start=timestamps[0].isoformat(),
        date_range_end=timestamps[-1].isoformat(),
        span_hours=float(span_hours),
        median_spacing_minutes=spacing,
        candles_ok_fraction=float(candles_ok / len(timestamps)),
        mount_ok=mount_ok,
        snapshots_dir=str(snapshots_dir),
    )


def _min_rows_for_horizon(horizon_hours: float) -> int:
    if horizon_hours <= 1.0:
        return SHORT_HORIZON_MIN_ROWS
    return DEFAULT_MIN_LABELED_ROWS


def assess_horizon_readiness(
    snapshots_dir: Path,
    spec: dict[str, Any],
    *,
    min_labeled_rows: int | None = None,
) -> HorizonReadiness:
    key = str(spec["key"])
    horizon_hours = float(spec["horizon_hours"])
    range_pct = float(spec.get("range_threshold_pct", 0.01))
    min_rows = min_labeled_rows if min_labeled_rows is not None else _min_rows_for_horizon(horizon_hours)
    min_span_hours = horizon_hours + 0.5

    cfg = TrainConfig(horizon_hours=horizon_hours, range_threshold_pct=range_pct)
    try:
        dataset, _ = build_labeled_dataset(snapshots_dir, cfg=cfg)
    except (ValueError, FileNotFoundError) as exc:
        return HorizonReadiness(
            key=key,
            horizon_hours=horizon_hours,
            labeled_rows=0,
            span_hours=0.0,
            class_balance={},
            ok=False,
            reason=str(exc),
        )

    n = len(dataset)
    ts = pd.to_datetime(dataset["timestamp"], utc=True, errors="coerce")
    span = 0.0
    if len(ts) >= 2:
        span = (ts.max() - ts.min()).total_seconds() / 3600.0

    balance: dict[str, int] = {}
    if "y_true" in dataset.columns:
        for label, count in dataset["y_true"].value_counts().items():
            balance[str(label)] = int(count)

    if n < min_rows:
        return HorizonReadiness(
            key=key,
            horizon_hours=horizon_hours,
            labeled_rows=n,
            span_hours=span,
            class_balance=balance,
            ok=False,
            reason=f"need ≥{min_rows} labeled rows, have {n}",
        )
    if span < min_span_hours:
        return HorizonReadiness(
            key=key,
            horizon_hours=horizon_hours,
            labeled_rows=n,
            span_hours=span,
            class_balance=balance,
            ok=False,
            reason=f"need span ≥{min_span_hours:.1f}h, have {span:.1f}h",
        )
    return HorizonReadiness(
        key=key,
        horizon_hours=horizon_hours,
        labeled_rows=n,
        span_hours=span,
        class_balance=balance,
        ok=True,
        reason="OK",
    )


def run_preflight(
    layout: VerdantLayout | None = None,
    *,
    snapshots_dir: Path | None = None,
    horizon_specs: tuple[dict[str, Any], ...] = HORIZON_SPECS,
) -> dict[str, Any]:
    layout = layout or resolve_layout()
    snap_dir = snapshots_dir or layout.snapshots_dir
    audit = audit_snapshots(snap_dir, data_root=layout.data_root)
    horizons = [assess_horizon_readiness(snap_dir, spec) for spec in horizon_specs]
    return {
        "mount_ok": audit.mount_ok,
        "data_root": str(layout.data_root),
        "snapshots_audit": audit.__dict__,
        "horizons": [h.__dict__ for h in horizons],
        "all_horizons_ok": all(h.ok for h in horizons),
        "any_horizon_ok": any(h.ok for h in horizons),
    }


def print_preflight_report(report: dict[str, Any]) -> None:
    audit = report.get("snapshots_audit") or {}
    print(f"Data root: {report.get('data_root')} (mount_ok={report.get('mount_ok')})")
    print(
        f"Snapshots: {audit.get('snapshot_count', 0)} files | "
        f"span {audit.get('span_hours', 0):.1f}h | "
        f"candles_ok {100 * audit.get('candles_ok_fraction', 0):.0f}%"
    )
    if audit.get("date_range_start"):
        print(f"  Range: {audit['date_range_start']} → {audit['date_range_end']}")
    print("\nHorizon readiness:")
    for h in report.get("horizons") or []:
        status = "OK" if h.get("ok") else "FAIL"
        print(
            f"  {h.get('key'):>4}: {h.get('labeled_rows', 0):>4} labeled rows, "
            f"span {h.get('span_hours', 0):.1f}h — {status}"
            + (f" ({h.get('reason')})" if not h.get("ok") else "")
        )


def main(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Preflight checks for Verdant ML pipeline.")
    parser.add_argument(
        "--data-root",
        type=Path,
        default=None,
        help="Verdant data root (default: BTC_KALSHI_ROOT or /Volumes/Verdant_AI/btc_kalshi)",
    )
    parser.add_argument("--snapshots-dir", type=Path, default=None)
    parser.add_argument("--json", action="store_true", help="Print full report as JSON")
    args = parser.parse_args(argv)

    layout = resolve_layout(args.data_root)
    snap_dir = args.snapshots_dir or layout.snapshots_dir
    report = run_preflight(layout, snapshots_dir=snap_dir)

    if args.json:
        print(json.dumps(report, indent=2))
    else:
        print_preflight_report(report)
    return 0 if report.get("mount_ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
