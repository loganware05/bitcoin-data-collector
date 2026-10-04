from __future__ import annotations

import json
import logging
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from verdant_paths import VerdantLayout, ensure_layout_dirs, resolve_layout

logger = logging.getLogger(__name__)

DEFAULT_INTERVAL_SECONDS = 900


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _append_health(path: Path, record: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, sort_keys=False) + "\n")


def _candles_bar_count(snapshot: dict[str, Any]) -> int:
    candles = (snapshot.get("market_data") or {}).get("candles_15m") or []
    return len(candles) if isinstance(candles, list) else 0


def collect_once(
    layout: VerdantLayout,
    *,
    repo_root: Path | None = None,
) -> dict[str, Any]:
    """Run collector once into layout.snapshots_dir; return health record."""
    repo_root = repo_root or Path(__file__).resolve().parent
    ensure_layout_dirs(layout)
    snap_dir = layout.snapshots_dir
    snap_dir.mkdir(parents=True, exist_ok=True)

    cmd = [
        sys.executable,
        str(repo_root / "btc_market_intel_collector.py"),
        "--output-dir",
        str(snap_dir),
        "--no-csv",
    ]
    started = _now_iso()
    proc = subprocess.run(cmd, capture_output=True, text=True, cwd=str(repo_root))
    candidates = sorted(snap_dir.glob("btc_market_intel_*.json"))
    record: dict[str, Any] = {
        "timestamp": started,
        "success": proc.returncode == 0 and bool(candidates),
        "returncode": proc.returncode,
        "snapshots_dir": str(snap_dir),
    }
    if proc.returncode != 0:
        record["stderr_tail"] = (proc.stderr or "")[-500:]
    if candidates:
        latest = candidates[-1]
        record["snapshot_file"] = latest.name
        try:
            with latest.open("r", encoding="utf-8") as f:
                snap = json.load(f)
            record["snapshot_timestamp"] = snap.get("timestamp")
            record["candles_15m_bars"] = _candles_bar_count(snap)
            record["spot_price_usd"] = (snap.get("price_data") or {}).get("spot_price_usd")
        except (json.JSONDecodeError, OSError) as exc:
            record["parse_error"] = str(exc)
            record["success"] = False
    else:
        record["error"] = "collector produced no snapshot JSON"
        record["success"] = False

    _append_health(layout.health_log, record)
    return record


def run_daemon(
    layout: VerdantLayout,
    *,
    interval_seconds: int = DEFAULT_INTERVAL_SECONDS,
    repo_root: Path | None = None,
) -> None:
    """Collect snapshots on a fixed interval until interrupted."""
    repo_root = repo_root or Path(__file__).resolve().parent
    interval = max(60, int(interval_seconds))
    logger.info(
        "Snapshot daemon: dir=%s interval=%ds health=%s",
        layout.snapshots_dir,
        interval,
        layout.health_log,
    )
    while True:
        record = collect_once(layout, repo_root=repo_root)
        if record.get("success"):
            logger.info(
                "Collected %s (candles=%s)",
                record.get("snapshot_file"),
                record.get("candles_15m_bars"),
            )
        else:
            logger.warning("Collection failed: %s", record.get("error") or record.get("stderr_tail"))
        time.sleep(interval)


def main(argv: list[str] | None = None) -> int:
    import argparse

    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    parser = argparse.ArgumentParser(
        description="Scheduled BTC snapshot collector for Verdant storage."
    )
    parser.add_argument(
        "--data-root",
        type=Path,
        default=None,
        help="Verdant data root (default: BTC_KALSHI_ROOT env or /Volumes/Verdant_AI/btc_kalshi)",
    )
    parser.add_argument(
        "--snapshots-dir",
        type=Path,
        default=None,
        help="Override snapshots directory (default: {data_root}/snapshots)",
    )
    parser.add_argument(
        "--interval-seconds",
        type=int,
        default=DEFAULT_INTERVAL_SECONDS,
        help="Collection interval (default: 900 = 15 minutes)",
    )
    parser.add_argument("--once", action="store_true", help="Collect one snapshot and exit")
    args = parser.parse_args(argv)

    layout = resolve_layout(args.data_root)
    if args.snapshots_dir:
        layout = VerdantLayout(
            data_root=layout.data_root,
            snapshots_dir=args.snapshots_dir.expanduser().resolve(),
            models_dir=layout.models_dir,
            hourly_outputs_dir=layout.hourly_outputs_dir,
            datasets_dir=layout.datasets_dir,
            health_log=layout.health_log,
        )

    if args.once:
        record = collect_once(layout)
        print(json.dumps(record, indent=2))
        return 0 if record.get("success") else 1

    try:
        run_daemon(layout, interval_seconds=args.interval_seconds)
    except KeyboardInterrupt:
        logger.info("Snapshot daemon stopped.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
