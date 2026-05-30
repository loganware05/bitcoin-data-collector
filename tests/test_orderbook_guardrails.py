from __future__ import annotations

from datetime import UTC, datetime
from zoneinfo import ZoneInfo

from event_target_parser import ParsedHourlyTarget
from hourly_fair_value_engine import FairValueConfig, evaluate_contract
from kalshi_orderbook_features import (
    OrderbookFeatures,
    OrderbookGuardrailConfig,
    orderbook_guardrails,
)


def _parsed() -> ParsedHourlyTarget:
    et = ZoneInfo("America/New_York")
    target = datetime(2026, 5, 27, 17, 0, tzinfo=et)
    return ParsedHourlyTarget(
        event_ticker="KXBTCD-26MAY2717",
        contract_ticker="KXBTCD-26MAY2717-T77000.99",
        event_title="BTC price today at 5 PM EDT",
        contract_title="Bitcoin above $77,000",
        target_time_edt=target,
        settlement_time_utc=target.astimezone(UTC),
        strike_price=77000.0,
        direction="above",
        time_to_expiry_minutes=120.0,
        mapping_confidence=0.85,
    )


def _ob(spread: float, liquidity: float) -> OrderbookFeatures:
    return OrderbookFeatures(
        yes_bid=0.40,
        yes_ask=0.40 + spread,
        no_bid=0.55,
        no_ask=0.55 + spread,
        bid_ask_spread=spread,
        mid_price=0.40 + spread / 2,
        implied_yes_probability=0.40 + spread / 2,
        implied_no_probability=0.60 - spread / 2,
        orderbook_depth=0.0,
        liquidity_score=liquidity,
        volume=100.0,
        open_interest=50.0,
        yes_no_imbalance=None,
        recent_price_change=None,
        time_to_expiry_minutes=120.0,
    )


def test_guardrail_wide_spread():
    ob = _ob(spread=0.15, liquidity=0.80)
    warnings = orderbook_guardrails(ob, OrderbookGuardrailConfig(max_spread=0.08))
    assert any("spread" in w.lower() for w in warnings)

    ev = evaluate_contract(
        parsed=_parsed(),
        ob=ob,
        model_yes=0.60,
        model_no=0.40,
        confidence=0.75,
        selected_horizon="60m",
        current_btc_price=76000.0,
        cfg=FairValueConfig(max_spread=0.08, min_edge=0.10, min_confidence=0.65),
    )
    assert ev["recommendation"] == "NO TRADE"


def test_guardrail_low_liquidity():
    ob = _ob(spread=0.03, liquidity=0.20)
    warnings = orderbook_guardrails(ob, OrderbookGuardrailConfig(min_liquidity_score=0.50))
    assert any("liquidity" in w.lower() for w in warnings)

    ev = evaluate_contract(
        parsed=_parsed(),
        ob=ob,
        model_yes=0.60,
        model_no=0.40,
        confidence=0.75,
        selected_horizon="60m",
        current_btc_price=76000.0,
        cfg=FairValueConfig(min_liquidity_score=0.50, min_edge=0.10, min_confidence=0.65),
    )
    assert ev["recommendation"] == "NO TRADE"


def test_guardrail_low_confidence():
    ob = _ob(spread=0.03, liquidity=0.80)
    ev = evaluate_contract(
        parsed=_parsed(),
        ob=ob,
        model_yes=0.60,
        model_no=0.40,
        confidence=0.55,
        selected_horizon="60m",
        current_btc_price=76000.0,
        cfg=FairValueConfig(min_confidence=0.65, min_edge=0.10),
    )
    assert ev["recommendation"] == "NO TRADE"
