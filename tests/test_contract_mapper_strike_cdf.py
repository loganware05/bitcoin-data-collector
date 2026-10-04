from __future__ import annotations

from contract_mapper import ParsedContract, model_probability_for_contract


def _above_contract() -> ParsedContract:
    return ParsedContract(
        ticker="KXBTCD-TEST-T77000.99",
        target_type="above_threshold",
        threshold_price=77_000.0,
        threshold_price_high=None,
        direction="yes",
        expiration_time=None,
        horizon_hours=1.0,
        compatible_probability_key="up_move_1h",
        mapping_confidence=0.8,
        contract_title="Bitcoin above $77,000",
    )


def test_strike_cdf_above_spot_gives_higher_yes_prob():
    parsed = _above_contract()
    snapshot = {
        "price_data": {"spot_price_usd": 76_000.0, "rolling_volatility_annualized": 0.5},
        "liquidity_data": {"buy_sell_pressure_ratio": 1.0},
    }
    model_p, warns = model_probability_for_contract(
        parsed,
        rule_probs={"up_move_1h": 0.55},
        p_ml={"up": 0.6, "down": 0.2, "range": 0.2},
        fused={"up": 0.58, "down": 0.22, "range": 0.2},
        spot_price_usd=76_000.0,
        snapshot=snapshot,
        rule_composite=0.1,
    )
    assert 0.0 < model_p < 1.0
    assert any("strike CDF" in w for w in warns)
