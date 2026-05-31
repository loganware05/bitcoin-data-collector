from __future__ import annotations

from datetime import UTC, datetime, timedelta

from event_target_parser import (
    ParsedHourlyTarget,
    format_target_time_edt,
    is_hourly_btc_event,
    is_today_btc_price_event,
    matches_event_filter,
    parse_hourly_target,
)
from kalshi_client import NormalizedMarket


def _market(
    ticker: str = "KXBTCD-26MAY2717-T77000.99",
    title: str = "Bitcoin above $77,000 at 5 PM EDT",
    close_time: str | None = None,
) -> NormalizedMarket:
    if close_time is None:
        close_time = (datetime.now(UTC) + timedelta(hours=2)).isoformat()
    return NormalizedMarket(
        ticker=ticker,
        title=title,
        close_time=close_time,
        yes_bid=0.35,
        yes_ask=0.40,
        no_bid=0.60,
        no_ask=0.65,
        last_price=0.37,
        volume=5000.0,
        open_interest=2000.0,
        implied_probability_mid=0.375,
        liquidity_score=0.7,
        updated_time=datetime.now(UTC).isoformat(),
        event_ticker="KXBTCD-26MAY2717",
        raw={"yes_sub_title": title},
    )


def test_is_hourly_btc_event_kxbtcd():
    m = _market()
    assert is_hourly_btc_event(m.title, m.event_ticker, m.ticker, close_time=m.close_time)


def test_is_hourly_btc_event_title_pattern():
    assert is_hourly_btc_event(
        "BTC price today at 3 PM EDT",
        None,
        None,
    )


def test_parse_hourly_target_above_strike():
    m = _market(title="BTC above $78,000 at 3 PM EDT")
    parsed = parse_hourly_target(m)
    assert parsed is not None
    assert parsed.strike_price == 77000.99 or parsed.strike_price == 78000.0
    assert parsed.direction == "above"
    assert parsed.mapping_confidence > 0.5
    assert parsed.time_to_expiry_minutes >= 0


def test_parse_hourly_target_below_strike():
    m = _market(title="BTC below $77,500 at 4 PM EDT", ticker="KXBTCD-26MAY2717-T77500.99")
    parsed = parse_hourly_target(m)
    assert parsed is not None
    assert parsed.direction == "below"


def test_parse_ticker_datetime_may_27_2026_17h():
    m = _market(ticker="KXBTCD-26MAY2717-T72999.99")
    parsed = parse_hourly_target(m)
    assert parsed is not None
    assert parsed.target_time_edt.year == 2026
    assert parsed.target_time_edt.month == 5
    assert parsed.target_time_edt.day == 27
    assert parsed.target_time_edt.hour == 17


def test_format_target_time_edt():
    from zoneinfo import ZoneInfo

    dt = datetime(2026, 5, 27, 15, 0, tzinfo=ZoneInfo("America/New_York"))
    s = format_target_time_edt(dt)
    assert "2026" in s
    assert "PM" in s or "pm" in s.lower()


def test_matches_event_filter_btc_price_today_alias():
    from zoneinfo import ZoneInfo

    ref = datetime(2026, 5, 30, 12, 0, tzinfo=ZoneInfo("America/New_York"))
    m = _market(
        ticker="KXBTCD-26MAY3018-T73599.99",
        title="Bitcoin price on May 30, 2026?",
    )
    assert matches_event_filter(m, "BTC price today", now=ref)
    assert is_today_btc_price_event(m, now=ref)


def test_matches_event_filter_rejects_other_day():
    from zoneinfo import ZoneInfo

    ref = datetime(2026, 5, 30, 12, 0, tzinfo=ZoneInfo("America/New_York"))
    m = _market(
        ticker="KXBTCD-26MAY3117-T73599.99",
        title="Bitcoin price on May 31, 2026?",
        close_time=datetime(2026, 5, 31, 21, 0, tzinfo=UTC).isoformat(),
    )
    m.event_ticker = "KXBTCD-26MAY3117"
    assert not matches_event_filter(m, "BTC price today", now=ref)


def test_low_confidence_without_strike():
    m = _market(ticker="KXBTCD-26MAY2717", title="BTC price today at 2 PM EDT")
    m = NormalizedMarket(
        ticker=m.ticker,
        title=m.title,
        close_time=m.close_time,
        yes_bid=m.yes_bid,
        yes_ask=m.yes_ask,
        no_bid=m.no_bid,
        no_ask=m.no_ask,
        last_price=m.last_price,
        volume=m.volume,
        open_interest=m.open_interest,
        implied_probability_mid=m.implied_probability_mid,
        liquidity_score=m.liquidity_score,
        updated_time=m.updated_time,
        event_ticker=m.event_ticker,
        raw={},
    )
    parsed = parse_hourly_target(m)
    assert parsed is None
