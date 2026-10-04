from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any


def _load_scan(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        raise ValueError("Scan JSON must be an object.")
    return data


def _classify_no_trade_reason(warnings: list[str]) -> str:
    text = " | ".join(warnings).lower()
    if "edge below minimum" in text:
        return "edge_below_min"
    if "confidence" in text and "below" in text:
        return "confidence_below_min"
    if "spread" in text and ("above" in text or "wide" in text or "exceeds" in text):
        return "spread_too_wide"
    if "liquidity" in text and "below" in text:
        return "liquidity_too_low"
    if "time to expiry" in text and "below" in text:
        return "expiry_too_soon"
    if "mapping confidence" in text and "below" in text:
        return "mapping_uncertain"
    if "no market yes" in text or "missing market" in text:
        return "missing_market_price"
    return "other_guardrail"


def analyze_scan(result: dict[str, Any]) -> dict[str, Any]:
    ranked = result.get("ranked") or {}
    all_contracts = ranked.get("all_contracts") or []
    meta = result.get("scan_meta") or {}
    model_summary = result.get("model_summary") or {}

    no_trade_reasons: Counter[str] = Counter()
    for row in all_contracts:
        if row.get("recommendation") != "NO TRADE":
            continue
        warnings = row.get("warnings") or []
        if isinstance(warnings, str):
            warnings = [warnings]
        no_trade_reasons[_classify_no_trade_reason(list(warnings))] += 1

    pipeline_warnings = meta.get("pipeline_warnings") or []
    ml_missing = sum(1 for w in pipeline_warnings if str(w).startswith("no_ml_model_for_horizon"))
    ml_inference_fail = sum(1 for w in pipeline_warnings if str(w).startswith("ml_inference_failed"))

    return {
        "btc_price": result.get("btc_price"),
        "timestamp": result.get("timestamp"),
        "counts": ranked.get("counts") or {},
        "horizons_available": model_summary.get("horizons_available") or [],
        "ml_any_available": model_summary.get("ml_any_available"),
        "kalshi_api_available": meta.get("kalshi_api_available"),
        "pipeline_warning_count": len(pipeline_warnings),
        "ml_model_missing_warnings": ml_missing,
        "ml_inference_failures": ml_inference_fail,
        "no_trade_reason_breakdown": dict(no_trade_reasons),
        "top_buy_yes": ranked.get("buy_yes") or [],
        "top_buy_no": ranked.get("buy_no") or [],
        "actionable_count": len(ranked.get("buy_yes") or []) + len(ranked.get("buy_no") or []),
    }


def print_interpretation(analysis: dict[str, Any], *, top: int = 5) -> None:
    counts = analysis.get("counts") or {}
    print(f"\n=== Scan interpretation ({analysis.get('timestamp')}) ===")
    print(f"BTC spot: {analysis.get('btc_price')}")
    print(
        f"Contracts: total={counts.get('total', 0)} | "
        f"BUY YES={counts.get('buy_yes', 0)} | "
        f"BUY NO={counts.get('buy_no', 0)} | "
        f"NO TRADE={counts.get('no_trade', 0)}"
    )
    print(f"ML horizons loaded: {analysis.get('horizons_available')} (any={analysis.get('ml_any_available')})")
    print(f"Kalshi API: {analysis.get('kalshi_api_available')}")

    if not analysis.get("ml_any_available"):
        print("\n⚠ No ML models loaded — expect heavy NO TRADE (rule-only fusion + confidence penalty).")
        print(f"  Missing-model warnings: {analysis.get('ml_model_missing_warnings', 0)}")

    breakdown = analysis.get("no_trade_reason_breakdown") or {}
    if breakdown:
        print("\nNO TRADE guardrail breakdown:")
        for reason, n in sorted(breakdown.items(), key=lambda x: -x[1]):
            print(f"  {reason}: {n}")

    buy_yes = analysis.get("top_buy_yes") or []
    buy_no = analysis.get("top_buy_no") or []
    if buy_yes:
        print(f"\n--- Actionable BUY YES (top {top}) ---")
        for row in buy_yes[:top]:
            print(
                f"  {row.get('contract_ticker')} strike={row.get('strike_price')} "
                f"yes_edge={row.get('yes_edge'):+.3f} conf={row.get('confidence'):.2f} "
                f"expiry={row.get('time_to_expiry_minutes'):.0f}m hor={row.get('selected_horizon')}"
            )
    if buy_no:
        print(f"\n--- Actionable BUY NO (top {top}) ---")
        for row in buy_no[:top]:
            print(
                f"  {row.get('contract_ticker')} strike={row.get('strike_price')} "
                f"no_edge={row.get('no_edge'):+.3f} conf={row.get('confidence'):.2f} "
                f"expiry={row.get('time_to_expiry_minutes'):.0f}m hor={row.get('selected_horizon')}"
            )
    if not buy_yes and not buy_no:
        print("\nNo actionable recommendations at current thresholds.")


def find_latest_scan(output_dir: Path) -> Path | None:
    candidates = sorted(output_dir.glob("scan_*.json"))
    return candidates[-1] if candidates else None


def main(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Interpret hourly scan JSON output.")
    parser.add_argument("scan_json", type=Path, nargs="?", default=None, help="Path to scan_*.json")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help="Directory to find latest scan_*.json if path omitted",
    )
    parser.add_argument("--data-root", type=Path, default=None)
    parser.add_argument("--top", type=int, default=5)
    parser.add_argument("--json", action="store_true", help="Print analysis as JSON")
    args = parser.parse_args(argv)

    from verdant_paths import resolve_layout

    layout = resolve_layout(args.data_root)
    scan_path = args.scan_json
    if scan_path is None:
        out_dir = args.output_dir or layout.hourly_outputs_dir
        scan_path = find_latest_scan(out_dir)
        if scan_path is None:
            print(f"No scan_*.json found in {out_dir}")
            return 1

    result = _load_scan(scan_path)
    analysis = analyze_scan(result)
    analysis["scan_path"] = str(scan_path)

    if args.json:
        print(json.dumps(analysis, indent=2))
    else:
        print(f"Scan file: {scan_path}")
        print_interpretation(analysis, top=args.top)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
