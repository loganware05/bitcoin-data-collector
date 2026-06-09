from __future__ import annotations

from hourly_probability_model import _orderflow_adjustment


def test_orderflow_uses_buy_sell_pressure_ratio():
    snapshot = {"liquidity_data": {"buy_sell_pressure_ratio": 1.5}}
    adj = _orderflow_adjustment(snapshot)
    assert adj > 0


def test_orderflow_falls_back_to_bid_ask_volume_ratio():
    snapshot = {"liquidity_data": {"bid_ask_volume_ratio": 0.5}}
    adj = _orderflow_adjustment(snapshot)
    assert adj < 0
