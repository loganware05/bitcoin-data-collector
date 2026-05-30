#!/usr/bin/env python3
"""
Run one full Kalshi BTC market scan (recommendation only — no trade execution).

Usage:
  python examples/run_kalshi_scan.py
  python examples/run_kalshi_scan.py --snapshot outputs/btc_market_intel_*.json
  python examples/run_kalshi_scan.py --no-collect --snapshot outputs/btc_market_intel_20260526T233055Z.json
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from contract_mapper import parse_contract  # noqa: E402
from decision_utils import combined_model_confidence, extract_rule_probs  # noqa: E402
from feature_engineering import FeatureConfig, build_features  # noqa: E402
from kalshi_client import KalshiClient  # noqa: E402
from kalshi_mapper import FusionConfig, fuse_probabilities  # noqa: E402
from live_runner import load_snapshot_json  # noqa: E402
from ml_model import load_artifact  # noqa: E402
from signal_engine import SignalEngineConfig, generate_signal  # noqa: E402
from strategy_ranker import rank_opportunities  # noqa: E402


def _now_stamp() -> str:
    return datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")


def _collect_snapshot(output_dir: Path) -> dict:
    output_dir.mkdir(parents=True, exist_ok=True)
    cmd = [
        sys.executable,
        str(REPO_ROOT / "btc_market_intel_collector.py"),
        "--output-dir",
        str(output_dir),
        "--no-csv",
    ]
    subprocess.run(cmd, check=False, capture_output=True, text=True, cwd=str(REPO_ROOT))
    candidates = sorted(output_dir.glob("btc_market_intel_*.json"))
    if not candidates:
        raise RuntimeError("Collector did not produce a snapshot JSON.")
    return load_snapshot_json(candidates[-1])


def _load_latest_model(models_dir: Path) -> object | None:
    if not models_dir.exists():
        return None
    candidates = sorted(models_dir.glob("model_*.joblib"))
    if not candidates:
        return None
    return load_artifact(candidates[-1])


def _print_table(result: dict, top: int) -> None:
    rows = result.get("ranked_opportunities") or []
    if not rows:
        print("No ranked opportunities (no BTC markets or all filtered).")
        meta = result.get("scan_meta") or {}
        for w in meta.get("kalshi_warnings") or []:
            print(f"  warning: {w}")
        return

    header = f"{'ticker':<22} {'target':<28} {'model':>6} {'mkt':>6} {'edge':>7} {'rec':<10} {'conf':>5} {'liq':>5}"
    print(header)
    print("-" * len(header))
    for row in rows[:top]:
        mkt = row.get("market_implied_probability")
        edge = row.get("edge")
        print(
            f"{str(row.get('ticker', ''))[:22]:<22} "
            f"{str(row.get('target', ''))[:28]:<28} "
            f"{row.get('model_probability', 0):>6.3f} "
            f"{(mkt if mkt is not None else float('nan')):>6.3f} "
            f"{(edge if edge is not None else float('nan')):>+7.3f} "
            f"{str(row.get('recommendation', '')):<10} "
            f"{row.get('confidence', 0):>5.2f} "
            f"{row.get('liquidity_score', 0):>5.2f}"
        )


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Scan Kalshi BTC markets and rank recommendation opportunities (no execution)."
    )
    parser.add_argument("--snapshot", type=str, default=None, help="Path to existing snapshot JSON")
    parser.add_argument("--no-collect", action="store_true", help="Require --snapshot; do not run collector")
    parser.add_argument("--models-dir", type=Path, default=REPO_ROOT / "models")
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="JSON output path (default: live_outputs/kalshi_scans/scan_<UTC>.json)",
    )
    parser.add_argument("--top", type=int, default=15, help="Rows to print in summary table")
    parser.add_argument("--min-edge", type=float, default=None, help="Override FusionConfig.min_edge")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Alias for clarity: this tool never places trades",
    )
    args = parser.parse_args()

    if args.dry_run:
        print("dry-run: recommendation-only scan (no trade execution).")

    fusion_cfg = FusionConfig()
    if args.min_edge is not None:
        fusion_cfg = FusionConfig(
            w_rule=fusion_cfg.w_rule,
            w_ml=fusion_cfg.w_ml,
            min_confidence=fusion_cfg.min_confidence,
            min_edge=float(args.min_edge),
            max_range_prob_for_directional=fusion_cfg.max_range_prob_for_directional,
        )

    if args.snapshot:
        snapshot = load_snapshot_json(Path(args.snapshot))
    elif args.no_collect:
        print("error: --no-collect requires --snapshot", file=sys.stderr)
        return 2
    else:
        snap_dir = REPO_ROOT / "live_outputs" / "snapshots"
        snapshot = _collect_snapshot(snap_dir)

    rule_out = generate_signal(snapshot, SignalEngineConfig())
    p_rule = extract_rule_probs(rule_out)
    rule_conf = float(rule_out.get("confidence", 0.0))

    warnings: list[str] = []
    p_ml = None
    model = _load_latest_model(args.models_dir)
    if model is None:
        warnings.append("no saved ML model; using rule engine only")
    else:
        try:
            x_row, meta = build_features(snapshot, cfg=FeatureConfig())
            warnings.extend(list(meta.get("warnings", [])))
            p_ml = model.predict_proba(x_row)
        except Exception as exc:  # noqa: BLE001
            warnings.append(f"ml_inference_failed: {exc}")

    fused = fuse_probabilities(
        p_rule=p_rule,
        p_ml=p_ml,
        w_rule=fusion_cfg.w_rule,
        w_ml=fusion_cfg.w_ml,
    )
    combined_conf = combined_model_confidence(rule_conf, ml_available=p_ml is not None)

    client = KalshiClient()
    fetch = client.fetch_btc_markets()
    warnings.extend(fetch.warnings)

    parsed = []
    spot = float((snapshot.get("price_data") or {}).get("spot_price_usd") or 0.0)
    for m in fetch.markets:
        pc = parse_contract(m, spot_price_usd=spot if spot > 0 else None)
        if pc is not None:
            parsed.append(pc)

    result = rank_opportunities(
        snapshot=snapshot,
        rule_out=rule_out,
        p_rule=p_rule,
        p_ml=p_ml,
        fused=fused,
        model_confidence=combined_conf,
        markets=fetch.markets,
        parsed_contracts=parsed,
        fusion_cfg=fusion_cfg,
        kalshi_warnings=warnings,
    )
    result["model_summary"] = {
        "rule_probabilities": p_rule,
        "ml_probabilities": p_ml,
        "fused_probabilities": fused,
        "rule_confidence": rule_conf,
        "combined_confidence": combined_conf,
        "pipeline_warnings": warnings,
    }

    out_path = args.output
    if out_path is None:
        out_dir = REPO_ROOT / "live_outputs" / "kalshi_scans"
        out_dir.mkdir(parents=True, exist_ok=True)
        out_path = out_dir / f"scan_{_now_stamp()}.json"
    else:
        out_path = Path(out_path)
        out_path.parent.mkdir(parents=True, exist_ok=True)

    with out_path.open("w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, sort_keys=False)

    print(f"BTC spot: {result.get('btc_price')}")
    print(f"Markets fetched: {len(fetch.markets)} | Ranked: {len(result.get('ranked_opportunities', []))}")
    print(f"Saved: {out_path}\n")
    _print_table(result, args.top)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
