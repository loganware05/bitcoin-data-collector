from __future__ import annotations

import argparse
import csv
import json
import logging
import subprocess
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from decision_utils import combined_model_confidence
from event_target_parser import is_hourly_btc_event, parse_hourly_target
from feature_engineering import FeatureConfig, build_features
from hourly_fair_value_engine import FairValueConfig, evaluate_contract, rank_evaluations
from hourly_probability_model import FusionWeights, build_hourly_model_probs
from kalshi_client import KalshiClient, NormalizedMarket
from kalshi_orderbook_features import extract_orderbook_features
from live_runner import load_snapshot_json
from ml_model import load_artifact
from signal_engine import SignalEngineConfig, generate_signal

logger = logging.getLogger(__name__)


@dataclass
class HourlyScanConfig:
    event_filter: str | None = None
    conservative: bool = True
    min_edge: float = 0.10
    min_confidence: float = 0.65
    max_spread: float = 0.08
    min_liquidity_score: float = 0.50
    max_expiry_hours: float = 24.0
    output_dir: Path = Path("hourly_outputs")
    snapshot_path: Path | None = None
    no_collect: bool = False
    collect_output_dir: Path = Path("live_outputs/snapshots")
    models_dir: Path = Path("models")
    fetch_orderbook: bool = True
    fusion_weights: FusionWeights | None = None
    repo_root: Path | None = None


def _now_stamp() -> str:
    return datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def collect_snapshot(output_dir: Path, repo_root: Path) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    cmd = [
        sys.executable,
        str(repo_root / "btc_market_intel_collector.py"),
        "--output-dir",
        str(output_dir),
        "--no-csv",
    ]
    subprocess.run(cmd, check=False, capture_output=True, text=True, cwd=str(repo_root))
    candidates = sorted(output_dir.glob("btc_market_intel_*.json"))
    if not candidates:
        raise RuntimeError("Collector did not produce a snapshot JSON.")
    return load_snapshot_json(candidates[-1])


def load_latest_model(models_dir: Path) -> object | None:
    if not models_dir.exists():
        return None
    candidates = sorted(models_dir.glob("model_*.joblib"))
    if not candidates:
        return None
    return load_artifact(candidates[-1])


def _fair_value_cfg(scan_cfg: HourlyScanConfig) -> FairValueConfig:
    if scan_cfg.conservative:
        return FairValueConfig(
            min_edge=scan_cfg.min_edge,
            min_confidence=scan_cfg.min_confidence,
            max_spread=scan_cfg.max_spread,
            min_liquidity_score=scan_cfg.min_liquidity_score,
        )
    return FairValueConfig(
        min_edge=scan_cfg.min_edge,
        min_confidence=scan_cfg.min_confidence,
        max_spread=scan_cfg.max_spread,
        min_liquidity_score=scan_cfg.min_liquidity_score,
    )


def filter_hourly_markets(
    markets: list[NormalizedMarket],
    *,
    event_filter: str | None = None,
    max_expiry_hours: float = 24.0,
) -> list[NormalizedMarket]:
    out: list[NormalizedMarket] = []
    for m in markets:
        if not is_hourly_btc_event(
            m.title,
            m.event_ticker,
            m.ticker,
            max_expiry_hours=max_expiry_hours,
            close_time=m.close_time,
        ):
            continue
        haystack = " ".join(
            t for t in (m.title, m.event_ticker, m.ticker) if t
        ).lower()
        if event_filter and event_filter.lower() not in haystack:
            continue
        out.append(m)
    return out


def run_hourly_scan(cfg: HourlyScanConfig) -> dict[str, Any]:
    """Orchestrate BTC snapshot + Kalshi hourly scan + fair value recommendations."""
    repo_root = cfg.repo_root or Path(__file__).resolve().parent
    warnings: list[str] = []

    if cfg.snapshot_path:
        snapshot = load_snapshot_json(cfg.snapshot_path)
    elif cfg.no_collect:
        raise RuntimeError("--no-collect requires --snapshot")
    else:
        snapshot = collect_snapshot(cfg.collect_output_dir, repo_root)

    rule_out = generate_signal(snapshot, SignalEngineConfig())
    rule_conf = float(rule_out.get("confidence", 0.0))

    p_ml = None
    model = load_latest_model(cfg.models_dir if cfg.models_dir.is_absolute() else repo_root / cfg.models_dir)
    if model is None:
        warnings.append("no saved ML model; using rule engine only")
    else:
        try:
            x_row, meta = build_features(snapshot, cfg=FeatureConfig())
            warnings.extend(list(meta.get("warnings", [])))
            p_ml = model.predict_proba(x_row)
        except Exception as exc:  # noqa: BLE001
            warnings.append(f"ml_inference_failed: {exc}")

    combined_conf = combined_model_confidence(rule_conf, ml_available=p_ml is not None)
    spot = float((snapshot.get("price_data") or {}).get("spot_price_usd") or 0.0)

    client = KalshiClient()
    fetch = client.fetch_btc_markets()
    warnings.extend(fetch.warnings)

    hourly_markets = filter_hourly_markets(
        fetch.markets,
        event_filter=cfg.event_filter,
        max_expiry_hours=cfg.max_expiry_hours,
    )

    fv_cfg = _fair_value_cfg(cfg)
    evaluations: list[dict[str, Any]] = []
    parse_skipped = 0

    for market in hourly_markets:
        parsed = parse_hourly_target(market, event_title=market.event_ticker)
        if parsed is None:
            parse_skipped += 1
            continue

        orderbook_raw = None
        if cfg.fetch_orderbook:
            orderbook_raw = client.fetch_market_orderbook(market.ticker)

        ob = extract_orderbook_features(market, parsed, orderbook_raw)
        model_probs = build_hourly_model_probs(
            snapshot=snapshot,
            parsed=parsed,
            rule_out=rule_out,
            p_ml=p_ml,
            ob_features=ob,
            weights=cfg.fusion_weights,
        )

        ev = evaluate_contract(
            parsed=parsed,
            ob=ob,
            model_yes=model_probs["model_yes_probability"],
            model_no=model_probs["model_no_probability"],
            confidence=model_probs["confidence"],
            selected_horizon=model_probs["selected_horizon"],
            current_btc_price=spot,
            model_drivers=model_probs["key_drivers"],
            cfg=fv_cfg,
            timestamp=_now_iso(),
        )
        evaluations.append(ev)

    ranked = rank_evaluations(evaluations)

    result: dict[str, Any] = {
        "timestamp": _now_iso(),
        "btc_price": spot,
        "scan_meta": {
            "markets_fetched": len(fetch.markets),
            "hourly_markets_matched": len(hourly_markets),
            "contracts_evaluated": len(evaluations),
            "parse_skipped": parse_skipped,
            "event_filter": cfg.event_filter,
            "conservative": cfg.conservative,
            "fair_value_config": {
                "min_edge": fv_cfg.min_edge,
                "min_confidence": fv_cfg.min_confidence,
                "max_spread": fv_cfg.max_spread,
                "min_liquidity_score": fv_cfg.min_liquidity_score,
            },
            "pipeline_warnings": warnings,
            "kalshi_api_available": fetch.api_available,
        },
        "ranked": ranked,
        "model_summary": {
            "rule_confidence": rule_conf,
            "combined_confidence": combined_conf,
            "ml_available": p_ml is not None,
        },
    }
    return result


def write_scan_outputs(result: dict[str, Any], output_dir: Path) -> tuple[Path, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    stamp = _now_stamp()
    json_path = output_dir / f"scan_{stamp}.json"
    csv_path = output_dir / f"scan_{stamp}.csv"

    with json_path.open("w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, sort_keys=False)

    rows = result.get("ranked", {}).get("all_contracts") or []
    if rows:
        fieldnames = list(rows[0].keys())
        with csv_path.open("w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
            writer.writeheader()
            for row in rows:
                out_row = dict(row)
                for key in ("key_drivers", "warnings"):
                    if key in out_row and isinstance(out_row[key], list):
                        out_row[key] = " | ".join(out_row[key])
                writer.writerow(out_row)
    else:
        csv_path.write_text("timestamp\n", encoding="utf-8")

    return json_path, csv_path


def print_summary_table(result: dict[str, Any], top: int = 10) -> None:
    ranked = result.get("ranked") or {}
    buy_yes = ranked.get("buy_yes") or []
    buy_no = ranked.get("buy_no") or []

    print(f"\nBTC spot: {result.get('btc_price')}")
    meta = result.get("scan_meta") or {}
    print(
        f"Hourly markets: {meta.get('hourly_markets_matched')} | "
        f"Evaluated: {meta.get('contracts_evaluated')} | "
        f"BUY YES: {ranked.get('counts', {}).get('buy_yes', 0)} | "
        f"BUY NO: {ranked.get('counts', {}).get('buy_no', 0)}"
    )

    if buy_yes:
        print("\n--- Top BUY YES ---")
        _print_rows(buy_yes[:top])
    if buy_no:
        print("\n--- Top BUY NO ---")
        _print_rows(buy_no[:top])
    if not buy_yes and not buy_no:
        print("\nNo BUY YES or BUY NO recommendations (conservative thresholds).")


def _print_rows(rows: list[dict[str, Any]]) -> None:
    header = f"{'ticker':<24} {'strike':>8} {'yes_e':>7} {'no_e':>7} {'rec':<10} {'conf':>5} {'hor':>4}"
    print(header)
    print("-" * len(header))
    for row in rows:
        print(
            f"{str(row.get('contract_ticker', ''))[:24]:<24} "
            f"{row.get('strike_price', 0):>8.0f} "
            f"{(row.get('yes_edge') or 0):>+7.3f} "
            f"{(row.get('no_edge') or 0):>+7.3f} "
            f"{str(row.get('recommendation', '')):<10} "
            f"{row.get('confidence', 0):>5.2f} "
            f"{str(row.get('selected_horizon', '')):>4}"
        )


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Kalshi BTC hourly event scanner (recommendation only — no trade execution)."
    )
    parser.add_argument(
        "--event-filter",
        type=str,
        default=None,
        help='Substring filter e.g. "BTC price today"',
    )
    parser.add_argument(
        "--conservative",
        action="store_true",
        default=True,
        help="Use conservative thresholds (default: on)",
    )
    parser.add_argument("--min-edge", type=float, default=0.10)
    parser.add_argument("--min-confidence", type=float, default=0.65)
    parser.add_argument("--max-spread", type=float, default=0.08)
    parser.add_argument("--min-liquidity-score", type=float, default=0.50)
    parser.add_argument("--output-dir", type=Path, default=Path("hourly_outputs"))
    parser.add_argument("--snapshot", type=Path, default=None)
    parser.add_argument("--no-collect", action="store_true")
    parser.add_argument("--once", action="store_true", help="Run one scan and exit (default behavior)")
    parser.add_argument("--no-orderbook", action="store_true", help="Skip orderbook API fetch")
    parser.add_argument("--models-dir", type=Path, default=Path("models"))
    parser.add_argument("--top", type=int, default=10, help="Rows to print per recommendation bucket")
    return parser


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    args = build_arg_parser().parse_args(argv)
    repo_root = Path(__file__).resolve().parent

    scan_cfg = HourlyScanConfig(
        event_filter=args.event_filter,
        conservative=args.conservative,
        min_edge=args.min_edge,
        min_confidence=args.min_confidence,
        max_spread=args.max_spread,
        min_liquidity_score=args.min_liquidity_score,
        output_dir=args.output_dir if args.output_dir.is_absolute() else repo_root / args.output_dir,
        snapshot_path=args.snapshot,
        no_collect=args.no_collect,
        models_dir=args.models_dir if args.models_dir.is_absolute() else repo_root / args.models_dir,
        fetch_orderbook=not args.no_orderbook,
        repo_root=repo_root,
    )

    try:
        result = run_hourly_scan(scan_cfg)
    except Exception as exc:  # noqa: BLE001
        logger.error("Scan failed: %s", exc)
        return 1

    json_path, csv_path = write_scan_outputs(result, scan_cfg.output_dir)
    print(f"Saved JSON: {json_path}")
    print(f"Saved CSV:  {csv_path}")
    print_summary_table(result, top=args.top)

    if not args.once:
        pass  # reserved for future loop mode; --once is default single-run

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
