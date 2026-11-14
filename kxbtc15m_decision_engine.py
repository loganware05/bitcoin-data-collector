"""KXBTC15M decision engine — research-stage, paper-only recommendations."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from kalshi_client import NormalizedMarket, normalize_market
from kxbtc15m_event_parser import ParsedKxbtc15mMarket, parse_kxbtc15m_market
from kxbtc15m_settlement_model import (
    SettlementIndexSource,
    SettlementModelConfig,
    estimate_p_up_settlement,
    net_edge_no,
    net_edge_yes,
)

Recommendation = Literal["BUY YES", "BUY NO", "NO TRADE"]


@dataclass(frozen=True)
class Kxbtc15mDecisionConfig:
    min_net_edge: float = 0.10
    min_confidence: float = 0.65
    max_spread: float = 0.08
    min_liquidity_score: float = 0.50
    min_time_remaining_seconds: float = 30.0
    fee_per_contract: float = 0.02
    max_model_p_up_for_buy_yes: float = 0.90
    approved_for_execution: bool = False  # hard lock — live money denied


def _clamp01(x: float) -> float:
    return max(0.0, min(1.0, float(x)))


def _spread(yes_bid: float | None, yes_ask: float | None) -> float | None:
    if yes_bid is None or yes_ask is None:
        return None
    return max(0.0, yes_ask - yes_bid)


def build_decision_report(
    *,
    market: NormalizedMarket,
    settlement_index: float | None,
    settlement_index_source: SettlementIndexSource = "unavailable",
    annualized_volatility: float | None = None,
    directional_bias: float = 0.0,
    parsed: ParsedKxbtc15mMarket | None = None,
    now: datetime | None = None,
    cfg: Kxbtc15mDecisionConfig | None = None,
    model_probability_up_override: float | None = None,
) -> dict[str, Any]:
    """Produce a KXBTC15M decision report. Missing inputs → NO TRADE."""
    cfg = cfg or Kxbtc15mDecisionConfig()
    assert cfg.approved_for_execution is False
    now = now or datetime.now(UTC)
    parsed = parsed or parse_kxbtc15m_market(market, now=now)
    reasons: list[str] = list(parsed.parse_warnings)
    model_cfg = SettlementModelConfig(fee_per_contract=cfg.fee_per_contract)

    model_p_up: float | None = model_probability_up_override
    drivers: list[str] = []
    if model_p_up is None:
        model_p_up, drivers = estimate_p_up_settlement(
            settlement_index=settlement_index,
            target_price=parsed.target_price,
            time_remaining_seconds=parsed.time_remaining_seconds,
            annualized_volatility=annualized_volatility,
            directional_bias=directional_bias,
            cfg=model_cfg,
        )
    else:
        drivers.append("model_probability_up_override")

    model_p_down = None if model_p_up is None else _clamp01(1.0 - model_p_up)
    yes_ask = market.yes_ask
    no_ask = market.no_ask
    if no_ask is None and yes_ask is not None:
        no_ask = _clamp01(1.0 - yes_ask)
    if yes_ask is None and no_ask is not None:
        yes_ask = _clamp01(1.0 - no_ask)

    yes_edge = (
        None
        if model_p_up is None
        else net_edge_yes(
            model_p_up=model_p_up,
            yes_ask=yes_ask,
            fee_per_contract=cfg.fee_per_contract,
        )
    )
    no_edge = (
        None
        if model_p_up is None
        else net_edge_no(
            model_p_up=model_p_up,
            no_ask=no_ask,
            fee_per_contract=cfg.fee_per_contract,
        )
    )
    spread = _spread(market.yes_bid, market.yes_ask)
    liq = float(market.liquidity_score)

    confidence = parsed.mapping_confidence
    if model_p_up is not None:
        # Soft confidence from mapping + quote completeness
        quote_factor = 1.0 if (yes_ask is not None and no_ask is not None) else 0.7
        confidence = _clamp01(0.7 * parsed.mapping_confidence + 0.3 * quote_factor)

    rec: Recommendation = "NO TRADE"
    net_edge: float | None = None

    if model_p_up is None:
        reasons.append("Awaiting live contract data and validated model")
    if settlement_index is None:
        reasons.append("settlement_index missing")
    if parsed.target_price is None:
        reasons.append("target_price missing")
    if parsed.time_remaining_seconds is None:
        reasons.append("time_remaining_seconds missing")
    elif parsed.time_remaining_seconds < cfg.min_time_remaining_seconds:
        reasons.append(
            f"time_remaining_seconds {parsed.time_remaining_seconds:.1f} below min "
            f"{cfg.min_time_remaining_seconds:.1f}"
        )
    if yes_ask is None and no_ask is None:
        reasons.append("missing YES/NO ask quotes")
    if spread is not None and spread > cfg.max_spread:
        reasons.append(f"spread {spread:.4f} exceeds max {cfg.max_spread:.4f}")
    if liq < cfg.min_liquidity_score:
        reasons.append(f"liquidity_score {liq:.4f} below min {cfg.min_liquidity_score:.4f}")
    if confidence < cfg.min_confidence:
        reasons.append(f"confidence {confidence:.4f} below min {cfg.min_confidence:.4f}")

    hard_block = any(
        x in " ".join(reasons).lower()
        for x in (
            "missing",
            "unavailable",
            "awaiting",
            "below min",
            "exceeds max",
        )
    ) or model_p_up is None

    if not hard_block and model_p_up is not None:
        buy_yes = (
            yes_edge is not None
            and yes_edge >= cfg.min_net_edge
            and model_p_up <= cfg.max_model_p_up_for_buy_yes
            and confidence >= cfg.min_confidence
        )
        buy_no = (
            no_edge is not None
            and no_edge >= cfg.min_net_edge
            and confidence >= cfg.min_confidence
        )
        if buy_yes and (no_edge is None or yes_edge >= (no_edge or -1e9)):
            rec = "BUY YES"
            net_edge = yes_edge
        elif buy_no:
            rec = "BUY NO"
            net_edge = no_edge
        else:
            reasons.append("edge below minimum threshold; defaulting to NO TRADE")

    if rec != "NO TRADE":
        reasons.append(
            "Paper recommendation only; approved_for_execution=false; live money denied"
        )

    return {
        "series": parsed.series,
        "contract_ticker": parsed.contract_ticker,
        "event_ticker": parsed.event_ticker,
        "title": parsed.title,
        "target_price": parsed.target_price,
        "time_remaining_seconds": parsed.time_remaining_seconds,
        "close_time_utc": parsed.close_time_utc.isoformat() if parsed.close_time_utc else None,
        "open_time_utc": parsed.open_time_utc.isoformat() if parsed.open_time_utc else None,
        "settlement_index": settlement_index,
        "settlement_index_source": settlement_index_source,
        "model_probability_up": None if model_p_up is None else round(_clamp01(model_p_up), 6),
        "model_probability_down": None if model_p_down is None else round(model_p_down, 6),
        "yes_ask": yes_ask,
        "no_ask": no_ask,
        "yes_bid": market.yes_bid,
        "no_bid": market.no_bid,
        "yes_net_edge": None if yes_edge is None else round(yes_edge, 6),
        "no_net_edge": None if no_edge is None else round(no_edge, 6),
        "net_edge": None if net_edge is None else round(net_edge, 6),
        "bid_ask_spread": spread,
        "liquidity_score": liq,
        "confidence": round(confidence, 4),
        "mapping_confidence": round(parsed.mapping_confidence, 4),
        "recommendation": rec,
        "reason": "; ".join(dict.fromkeys(reasons)) if reasons else "ok",
        "drivers": drivers,
        "fee_per_contract": cfg.fee_per_contract,
        "approved_for_execution": False,
        "timestamp": now.isoformat(),
    }


def decide_from_raw_market(
    raw: dict[str, Any],
    *,
    settlement_index: float | None,
    settlement_index_source: SettlementIndexSource = "fixture",
    **kwargs: Any,
) -> dict[str, Any]:
    return build_decision_report(
        market=normalize_market(raw),
        settlement_index=settlement_index,
        settlement_index_source=settlement_index_source,
        **kwargs,
    )


def main(argv: list[str] | None = None) -> int:
    import argparse

    ap = argparse.ArgumentParser(description="KXBTC15M decision report (paper-only)")
    ap.add_argument("--fixture", type=Path, help="Path to fixture market JSON")
    ap.add_argument("--settlement-index", type=float, default=None)
    ap.add_argument(
        "--settlement-index-source",
        default="fixture",
        choices=[
            "cf_benchmarks",
            "kalshi_api",
            "exchange_spot_proxy",
            "fixture",
            "unavailable",
        ],
    )
    ap.add_argument("--vol", type=float, default=None, help="Annualized volatility")
    ap.add_argument("--out", type=Path, default=None)
    args = ap.parse_args(argv)

    if not args.fixture:
        ap.error("--fixture is required (use live client via monitor for API paths)")

    raw = json.loads(args.fixture.read_text())
    if "markets" in raw and isinstance(raw["markets"], list) and raw["markets"]:
        market_raw = raw["markets"][0]
        if args.settlement_index is None:
            args.settlement_index = raw.get("settlement_index")
    else:
        market_raw = raw

    report = decide_from_raw_market(
        market_raw,
        settlement_index=args.settlement_index,
        settlement_index_source=args.settlement_index_source,  # type: ignore[arg-type]
        annualized_volatility=args.vol,
    )
    text = json.dumps(report, indent=2, sort_keys=False)
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(text + "\n")
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
