from __future__ import annotations

from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

from event_target_parser import ParsedHourlyTarget
from hourly_probability_model import build_hourly_model_probs
from kalshi_orderbook_features import OrderbookFeatures


def _parsed(tte_minutes: float = 120.0) -> ParsedHourlyTarget:
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
        time_to_expiry_minutes=tte_minutes,
        mapping_confidence=0.85,
    )


def _ob() -> OrderbookFeatures:
    return OrderbookFeatures(
        yes_bid=0.35,
        yes_ask=0.40,
        no_bid=0.60,
        no_ask=0.65,
        bid_ask_spread=0.05,
        mid_price=0.375,
        implied_yes_probability=0.375,
        implied_no_probability=0.625,
        orderbook_depth=100.0,
        liquidity_score=0.75,
        volume=5000.0,
        open_interest=2000.0,
        yes_no_imbalance=0.0,
        recent_price_change=None,
        time_to_expiry_minutes=120.0,
    )


def _snapshot() -> dict:
    return {
        "price_data": {
            "spot_price_usd": 76448.91,
            "rolling_volatility_annualized": 0.28,
        },
        "liquidity_data": {},
    }


def _rule_out() -> dict:
    return {
        "signal_score": 0.15,
        "confidence": 0.72,
        "probabilities": {},
    }


def test_matched_horizon_no_ml_penalty():
    matched = build_hourly_model_probs(
        snapshot=_snapshot(),
        parsed=_parsed(),
        rule_out=_rule_out(),
        p_ml={"up": 0.55, "down": 0.25, "range": 0.20},
        ob_features=_ob(),
        ml_horizon_matched=True,
    )
    assert matched["ml_horizon_penalty"] is False
    assert matched["ml_horizon_matched"] is True
    assert not any("confidence penalized" in d for d in matched["key_drivers"])


def test_unmatched_horizon_applies_penalty():
    unmatched = build_hourly_model_probs(
        snapshot=_snapshot(),
        parsed=_parsed(),
        rule_out=_rule_out(),
        p_ml={"up": 0.55, "down": 0.25, "range": 0.20},
        ob_features=_ob(),
        ml_horizon_matched=False,
    )
    assert unmatched["ml_horizon_penalty"] is True
    assert any("confidence penalized" in d for d in unmatched["key_drivers"])


def test_matched_horizon_higher_confidence_than_unmatched():
    kwargs = dict(
        snapshot=_snapshot(),
        parsed=_parsed(),
        rule_out=_rule_out(),
        p_ml={"up": 0.55, "down": 0.25, "range": 0.20},
        ob_features=_ob(),
    )
    matched = build_hourly_model_probs(**kwargs, ml_horizon_matched=True)
    unmatched = build_hourly_model_probs(**kwargs, ml_horizon_matched=False)
    assert matched["confidence"] > unmatched["confidence"]


def test_no_ml_rule_only_no_horizon_penalty():
    out = build_hourly_model_probs(
        snapshot=_snapshot(),
        parsed=_parsed(),
        rule_out=_rule_out(),
        p_ml=None,
        ob_features=_ob(),
        ml_horizon_matched=False,
    )
    assert out["ml_horizon_penalty"] is False
    assert out["ml_horizon_matched"] is False
