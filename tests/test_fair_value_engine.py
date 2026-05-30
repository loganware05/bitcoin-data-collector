from __future__ import annotations

from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

from event_target_parser import ParsedHourlyTarget
from hourly_fair_value_engine import FairValueConfig, evaluate_contract
from kalshi_orderbook_features import OrderbookFeatures


def _parsed() -> ParsedHourlyTarget:
    et = ZoneInfo("America/New_York")
    target = datetime(2026, 5, 27, 17, 0, tzinfo=et)
    settlement = target.astimezone(UTC)
    return ParsedHourlyTarget(
        event_ticker="KXBTCD-26MAY2717",
        contract_ticker="KXBTCD-26MAY2717-T77000.99",
        event_title="BTC price today at 5 PM EDT",
        contract_title="Bitcoin above $77,000 at 5 PM EDT",
        target_time_edt=target,
        settlement_time_utc=settlement,
        strike_price=77000.0,
        direction="above",
        time_to_expiry_minutes=120.0,
        mapping_confidence=0.85,
    )


def _ob(
    yes_mid: float = 0.37,
    spread: float = 0.03,
    liquidity: float = 0.75,
) -> OrderbookFeatures:
    return OrderbookFeatures(
        yes_bid=yes_mid - spread / 2,
        yes_ask=yes_mid + spread / 2,
        no_bid=1 - yes_mid - spread / 2,
        no_ask=1 - yes_mid + spread / 2,
        bid_ask_spread=spread,
        mid_price=yes_mid,
        implied_yes_probability=yes_mid,
        implied_no_probability=1 - yes_mid,
        orderbook_depth=100.0,
        liquidity_score=liquidity,
        volume=5000.0,
        open_interest=2000.0,
        yes_no_imbalance=0.0,
        recent_price_change=None,
        time_to_expiry_minutes=120.0,
    )


def test_yes_edge_calculation():
    ev = evaluate_contract(
        parsed=_parsed(),
        ob=_ob(yes_mid=0.37),
        model_yes=0.51,
        model_no=0.49,
        confidence=0.72,
        selected_horizon="60m",
        current_btc_price=76448.91,
        cfg=FairValueConfig(),
    )
    assert ev["yes_edge"] == round(0.51 - 0.37, 4)
    assert ev["no_edge"] == round(0.49 - 0.63, 4)


def test_buy_yes_when_edge_and_confidence_met():
    ev = evaluate_contract(
        parsed=_parsed(),
        ob=_ob(yes_mid=0.37, spread=0.03, liquidity=0.75),
        model_yes=0.55,
        model_no=0.45,
        confidence=0.72,
        selected_horizon="60m",
        current_btc_price=76448.91,
        cfg=FairValueConfig(min_edge=0.10, min_confidence=0.65),
    )
    assert ev["recommendation"] == "BUY YES"


def test_buy_no_when_no_edge_met():
    ev = evaluate_contract(
        parsed=_parsed(),
        ob=_ob(yes_mid=0.80, spread=0.03, liquidity=0.75),
        model_yes=0.30,
        model_no=0.70,
        confidence=0.72,
        selected_horizon="60m",
        current_btc_price=76448.91,
        cfg=FairValueConfig(min_edge=0.10, min_confidence=0.65),
    )
    assert ev["recommendation"] == "BUY NO"


def test_no_trade_insufficient_edge():
    ev = evaluate_contract(
        parsed=_parsed(),
        ob=_ob(yes_mid=0.48),
        model_yes=0.51,
        model_no=0.49,
        confidence=0.72,
        selected_horizon="60m",
        current_btc_price=76448.91,
        cfg=FairValueConfig(min_edge=0.10),
    )
    assert ev["recommendation"] == "NO TRADE"


def test_no_trade_low_confidence():
    ev = evaluate_contract(
        parsed=_parsed(),
        ob=_ob(yes_mid=0.30),
        model_yes=0.55,
        model_no=0.45,
        confidence=0.50,
        selected_horizon="60m",
        current_btc_price=76448.91,
        cfg=FairValueConfig(min_edge=0.10, min_confidence=0.65),
    )
    assert ev["recommendation"] == "NO TRADE"
    assert any("confidence" in w.lower() for w in ev["warnings"])
