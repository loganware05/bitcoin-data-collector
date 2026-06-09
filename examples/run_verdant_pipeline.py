#!/usr/bin/env python3
"""End-to-end Verdant multi-horizon pipeline: preflight → collect → train → scan → interpret."""

from __future__ import annotations

import json
import logging
import subprocess
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from hourly_event_scanner import (  # noqa: E402
    HourlyScanConfig,
    print_summary_table,
    run_hourly_scan,
    write_scan_outputs,
)
from pipeline_preflight import HORIZON_SPECS, print_preflight_report, run_preflight  # noqa: E402
from scan_interpreter import analyze_scan, print_interpretation  # noqa: E402
from snapshot_daemon import collect_once  # noqa: E402
from verdant_paths import ensure_layout_dirs, resolve_layout  # noqa: E402

logger = logging.getLogger(__name__)


def _run(cmd: list[str], *, cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    logger.info("Running: %s", " ".join(cmd))
    return subprocess.run(cmd, cwd=str(cwd or REPO_ROOT), capture_output=True, text=True)


def train_horizon(
    *,
    snapshots_dir: Path,
    models_subdir: Path,
    horizon_hours: float,
    range_threshold_pct: float,
    model_family: str = "logreg",
) -> dict[str, Any]:
    cmd = [
        sys.executable,
        str(REPO_ROOT / "ml_model.py"),
        str(snapshots_dir),
        "--model-family",
        model_family,
        "--horizon-hours",
        str(horizon_hours),
        "--range-threshold-pct",
        str(range_threshold_pct),
        "--models-dir",
        str(models_subdir),
        "--importance-dir",
        str(models_subdir / "importance_latest"),
    ]
    proc = _run(cmd)
    ok = proc.returncode == 0
    result: dict[str, Any] = {
        "horizon_hours": horizon_hours,
        "models_dir": str(models_subdir),
        "success": ok,
        "returncode": proc.returncode,
    }
    if ok:
        try:
            result["output"] = json.loads(proc.stdout)
        except json.JSONDecodeError:
            result["stdout"] = proc.stdout[-2000:]
    else:
        result["stderr"] = (proc.stderr or proc.stdout)[-2000:]
    return result


def main(argv: list[str] | None = None) -> int:
    import argparse

    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    parser = argparse.ArgumentParser(description="Verdant multi-horizon ML pipeline orchestrator.")
    parser.add_argument(
        "--data-root",
        type=Path,
        default=None,
        help="Verdant data root (default: BTC_KALSHI_ROOT or /Volumes/Verdant_AI/btc_kalshi)",
    )
    parser.add_argument("--skip-preflight", action="store_true")
    parser.add_argument("--skip-collect", action="store_true", help="Skip one-shot snapshot collection")
    parser.add_argument("--skip-train", action="store_true", help="Skip multi-horizon training")
    parser.add_argument("--skip-scan", action="store_true", help="Skip hourly event scanner")
    parser.add_argument(
        "--train-all",
        action="store_true",
        help="Attempt training all horizons even if preflight fails (default: train only OK horizons)",
    )
    parser.add_argument("--model-family", default="logreg", choices=["logreg", "decision_tree", "hgb"])
    parser.add_argument("--event-filter", default="BTC price today")
    parser.add_argument("--min-edge", type=float, default=0.10)
    parser.add_argument("--min-confidence", type=float, default=0.65)
    parser.add_argument("--no-collect-scan", action="store_true", help="Use latest snapshot for scan instead of collecting")
    parser.add_argument("--top", type=int, default=10)
    args = parser.parse_args(argv)

    layout = resolve_layout(args.data_root)
    ensure_layout_dirs(layout)
    train_only_ok = not args.train_all

    print(f"Verdant pipeline — data root: {layout.data_root}")

    # Phase 1: Preflight
    report: dict[str, Any] | None = None
    if not args.skip_preflight:
        print("\n=== Phase 1: Preflight ===")
        report = run_preflight(layout)
        print_preflight_report(report)
        if not report.get("mount_ok"):
            logger.error("Data root not mounted or missing: %s", layout.data_root)
            return 1

    # Phase 2: Collect one snapshot (optional)
    if not args.skip_collect:
        print("\n=== Phase 2: Collect snapshot ===")
        record = collect_once(layout, repo_root=REPO_ROOT)
        if record.get("success"):
            print(f"Collected {record.get('snapshot_file')} (candles={record.get('candles_15m_bars')})")
        else:
            logger.warning("Snapshot collection failed: %s", record.get("error") or record.get("stderr_tail"))

    # Phase 3: Train horizons
    train_results: list[dict[str, Any]] = []
    if not args.skip_train:
        print("\n=== Phase 3: Train multi-horizon models ===")
        if report is None:
            report = run_preflight(layout)
        ok_keys = {
            h["key"]
            for h in report.get("horizons") or []
            if h.get("ok")
        }
        for spec in HORIZON_SPECS:
            key = spec["key"]
            if train_only_ok and key not in ok_keys:
                logger.warning("Skipping %s — preflight not OK", key)
                train_results.append({"key": key, "skipped": True, "reason": "preflight_fail"})
                continue
            models_subdir = layout.models_dir / str(spec["models_subdir"])
            models_subdir.mkdir(parents=True, exist_ok=True)
            result = train_horizon(
                snapshots_dir=layout.snapshots_dir,
                models_subdir=models_subdir,
                horizon_hours=float(spec["horizon_hours"]),
                range_threshold_pct=float(spec["range_threshold_pct"]),
                model_family=args.model_family,
            )
            result["key"] = key
            train_results.append(result)
            if result.get("success"):
                logger.info("Trained %s → %s", key, models_subdir)
            else:
                logger.error("Training failed for %s: %s", key, result.get("stderr", "")[:200])

        trained = [r for r in train_results if r.get("success")]
        skipped = [r for r in train_results if r.get("skipped")]
        if not trained and skipped:
            print(
                "\nNo horizons trained — snapshot history is insufficient. "
                "Run the snapshot daemon for several days, then re-run:\n"
                f"  python snapshot_daemon.py --data-root {layout.data_root}"
            )

    # Phase 4: Hourly scan
    scan_result: dict[str, Any] | None = None
    json_path: Path | None = None
    if not args.skip_scan:
        print("\n=== Phase 4: Hourly event scan ===")
        snap_path: Path | None = None
        if args.no_collect_scan:
            candidates = sorted(layout.snapshots_dir.glob("btc_market_intel_*.json"))
            if candidates:
                snap_path = candidates[-1]
            else:
                logger.error("No snapshots in %s for --no-collect-scan", layout.snapshots_dir)
                return 1

        scan_cfg = HourlyScanConfig(
            event_filter=args.event_filter,
            conservative=True,
            min_edge=args.min_edge,
            min_confidence=args.min_confidence,
            output_dir=layout.hourly_outputs_dir,
            snapshot_path=snap_path,
            no_collect=args.no_collect_scan,
            collect_output_dir=layout.snapshots_dir,
            models_base_dir=layout.models_dir,
            repo_root=REPO_ROOT,
        )
        try:
            scan_result = run_hourly_scan(scan_cfg)
        except Exception as exc:  # noqa: BLE001
            logger.error("Scan failed: %s", exc)
            return 1
        json_path, csv_path = write_scan_outputs(scan_result, layout.hourly_outputs_dir)
        print(f"Saved JSON: {json_path}")
        print(f"Saved CSV:  {csv_path}")
        print_summary_table(scan_result, top=args.top)
        matched = (scan_result.get("scan_meta") or {}).get("hourly_markets_matched", 0)
        if matched == 0 and args.event_filter:
            print(
                f"\nNote: event filter {args.event_filter!r} matched 0 hourly markets. "
                "Try --event-filter '' or a broader filter if Kalshi titles differ."
            )

    # Phase 5: Interpret
    if scan_result is not None:
        print("\n=== Phase 5: Interpret scan ===")
        analysis = analyze_scan(scan_result)
        if json_path:
            analysis["scan_path"] = str(json_path)
        print_interpretation(analysis, top=args.top)

    summary = {
        "data_root": str(layout.data_root),
        "preflight": report,
        "train_results": train_results,
        "scan_json": str(json_path) if json_path else None,
    }
    print("\n=== Pipeline complete ===")
    print(json.dumps({k: v for k, v in summary.items() if k != "preflight"}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
