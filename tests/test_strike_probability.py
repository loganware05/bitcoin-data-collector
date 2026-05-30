from __future__ import annotations

from hourly_probability_model import estimate_probability_above_strike, fuse_hourly_probability


def test_spot_above_strike_higher_prob():
    p_above, _ = estimate_probability_above_strike(
        current_price=80_000,
        strike_price=75_000,
        horizon_minutes=60,
        annualized_volatility=0.50,
        directional_bias=0.2,
        rule_probability_up=0.55,
        ml_probability_up=0.55,
        orderflow_adjustment=0.0,
    )
    assert p_above > 0.5


def test_spot_below_strike_lower_prob():
    p_above, _ = estimate_probability_above_strike(
        current_price=70_000,
        strike_price=75_000,
        horizon_minutes=60,
        annualized_volatility=0.50,
        directional_bias=-0.2,
        rule_probability_up=0.45,
        ml_probability_up=0.45,
        orderflow_adjustment=0.0,
    )
    assert p_above < 0.5


def test_higher_vol_increases_tail_probability():
    """With spot below strike, higher vol raises P(above strike)."""
    p_low_vol, _ = estimate_probability_above_strike(
        current_price=74_000,
        strike_price=75_000,
        horizon_minutes=60,
        annualized_volatility=0.20,
        directional_bias=0.0,
        rule_probability_up=0.5,
        ml_probability_up=0.5,
        orderflow_adjustment=0.0,
    )
    p_high_vol, _ = estimate_probability_above_strike(
        current_price=74_000,
        strike_price=75_000,
        horizon_minutes=60,
        annualized_volatility=0.80,
        directional_bias=0.0,
        rule_probability_up=0.5,
        ml_probability_up=0.5,
        orderflow_adjustment=0.0,
    )
    assert p_high_vol > p_low_vol


def test_fuse_above_contract():
    yes, no, _ = fuse_hourly_probability(
        p_strike_above=0.60,
        p_rule_up=0.55,
        p_ml_up=0.52,
        ob_adjustment=0.0,
        direction="above",
    )
    assert abs(yes + no - 1.0) < 1e-6
    assert yes > 0.5


def test_fuse_below_contract():
    yes, no, drivers = fuse_hourly_probability(
        p_strike_above=0.60,
        p_rule_up=0.55,
        p_ml_up=0.52,
        ob_adjustment=0.0,
        direction="below",
    )
    assert yes < 0.5
    assert any("below" in d.lower() for d in drivers)
