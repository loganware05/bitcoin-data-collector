"""Hermetic tests for KXBTC15M discovery, settlement edge, and fail-closed NO TRADE."""

from __future__ import annotations

import json
import sys
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from kalshi_client import (  # noqa: E402
    DEFAULT_BTC_SERIES_TICKERS,
    KXBTC15M_SERIES_TICKER,
    normalize_market,
)
from kxbtc15m_decision_engine import (  # noqa: E402
    Kxbtc15mDecisionConfig,
    build_decision_report,
    decide_from_raw_market,
)
from kxbtc15m_event_parser import is_kxbtc15m_market, parse_kxbtc15m_market  # noqa: E402
from kxbtc15m_ml import train_eval_time_ordered, load_labeled_rows  # noqa: E402
from kxbtc15m_monitor import _clamp_poll  # noqa: E402
from kxbtc15m_settlement_model import (  # noqa: E402
    estimate_p_up_settlement,
    label_settlement_outcome,
    net_edge_yes,
)

FIX = ROOT / "tests" / "fixtures" / "kxbtc15m"


def test_series_constant_and_hourly_defaults_unchanged():
    assert KXBTC15M_SERIES_TICKER == "KXBTC15M"
    assert "KXBTC15M" not in DEFAULT_BTC_SERIES_TICKERS
    assert DEFAULT_BTC_SERIES_TICKERS == ("KXBTC", "KXBTCD")


def test_parse_target_and_window():
    pack = json.loads((FIX / "market_pack.json").read_text())
    market = normalize_market(pack["markets"][0])
    assert is_kxbtc15m_market(market)
    now = datetime(2026, 11, 14, 15, 20, tzinfo=UTC)
    parsed = parse_kxbtc15m_market(market, now=now)
    assert parsed.target_price == 65586.65
    assert parsed.time_remaining_seconds == 600.0
    assert parsed.mapping_confidence >= 0.8


def test_decision_report_buy_yes_when_edge_strong():
    pack = json.loads((FIX / "market_pack.json").read_text())
    now = datetime(2026, 11, 14, 15, 20, tzinfo=UTC)
    report = decide_from_raw_market(
        pack["markets"][0],
        settlement_index=pack["settlement_index"],
        settlement_index_source="fixture",
        annualized_volatility=0.40,
        now=now,
        cfg=Kxbtc15mDecisionConfig(min_net_edge=0.02, min_confidence=0.50, min_liquidity_score=0.1),
        model_probability_up_override=0.72,
    )
    assert report["approved_for_execution"] is False
    assert report["series"] == "KXBTC15M"
    assert report["target_price"] == 65586.65
    assert report["model_probability_up"] == 0.72
    assert report["recommendation"] in {"BUY YES", "BUY NO", "NO TRADE"}
    # With 72% vs 54¢ ask and 2¢ fee → net edge ~0.16 → BUY YES under min_edge 0.02
    assert report["recommendation"] == "BUY YES"
    assert report["net_edge"] is not None and report["net_edge"] > 0


def test_missing_inputs_no_trade():
    raw = json.loads((FIX / "market_incomplete.json").read_text())
    report = decide_from_raw_market(
        raw,
        settlement_index=None,
        settlement_index_source="unavailable",
        now=datetime(2026, 11, 14, 15, 20, tzinfo=UTC),
    )
    assert report["recommendation"] == "NO TRADE"
    assert report["model_probability_up"] is None
    assert "Awaiting" in report["reason"] or "missing" in report["reason"].lower()


def test_settlement_label_and_edge_math():
    label = label_settlement_outcome(settlement_value=65600.0, target_price=65586.65)
    assert label["outcome_up"] is True
    p, drivers = estimate_p_up_settlement(
        settlement_index=65620.0,
        target_price=65586.65,
        time_remaining_seconds=600.0,
        annualized_volatility=0.55,
    )
    assert p is not None and 0.0 <= p <= 1.0
    assert drivers
    edge = net_edge_yes(model_p_up=0.68, yes_ask=0.54, fee_per_contract=0.02)
    assert edge is not None
    assert abs(edge - (0.68 - 0.54 - 0.02)) < 1e-9


def test_poll_clamp_band():
    assert _clamp_poll(1) == 5.0
    assert _clamp_poll(10) == 10.0
    assert _clamp_poll(30) == 15.0


def test_ml_time_ordered_train_eval():
    rows = load_labeled_rows(FIX / "settlement_labels.json")
    result = train_eval_time_ordered(rows)
    assert result.n_train >= 2
    assert result.n_eval >= 2
    assert result.eval_calibration["n"] == result.n_eval
    assert result.fitted_vol > 0


def test_build_decision_never_sets_execution_true():
    pack = json.loads((FIX / "market_pack.json").read_text())
    market = normalize_market(pack["markets"][0])
    cfg = Kxbtc15mDecisionConfig()
    assert cfg.approved_for_execution is False
    report = build_decision_report(
        market=market,
        settlement_index=65620.0,
        settlement_index_source="fixture",
        model_probability_up_override=0.9,
        now=datetime(2026, 11, 14, 15, 20, tzinfo=UTC),
        cfg=cfg,
    )
    assert report["approved_for_execution"] is False
