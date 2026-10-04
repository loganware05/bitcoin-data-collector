from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Literal
from zoneinfo import ZoneInfo

from kalshi_client import NormalizedMarket, is_btc_related_text

ET = ZoneInfo("America/New_York")

Direction = Literal["above", "below"]

PRICE_RE = re.compile(
    r"\$?\s*([\d,]+(?:\.\d+)?)\s*(?:k|K|thousand|million|M)?",
    re.IGNORECASE,
)
ABOVE_RE = re.compile(
    r"\b(above|over|at or above|greater than|higher than|exceed|reach|hit)\b",
    re.IGNORECASE,
)
BELOW_RE = re.compile(
    r"\b(below|under|at or below|less than|lower than|drop to|fall to)\b",
    re.IGNORECASE,
)
HOURLY_TIME_RE = re.compile(
    r"\b(?:at\s+)?(\d{1,2})(?::(\d{2}))?\s*(am|pm)\b",
    re.IGNORECASE,
)
TODAY_RE = re.compile(r"\b(today|price today)\b", re.IGNORECASE)
TICKER_DATE_RE = re.compile(
    r"-(\d{2})([A-Z]{3})(\d{2})(\d{2})-",
    re.IGNORECASE,
)
TICKER_STRIKE_RE = re.compile(r"-T([\d.]+)$", re.IGNORECASE)
MONTH_MAP = {
    "JAN": 1,
    "FEB": 2,
    "MAR": 3,
    "APR": 4,
    "MAY": 5,
    "JUN": 6,
    "JUL": 7,
    "AUG": 8,
    "SEP": 9,
    "OCT": 10,
    "NOV": 11,
    "DEC": 12,
}


@dataclass
class ParsedHourlyTarget:
    event_ticker: str | None
    contract_ticker: str
    event_title: str
    contract_title: str
    target_time_edt: datetime
    settlement_time_utc: datetime
    strike_price: float
    direction: Direction
    time_to_expiry_minutes: float
    mapping_confidence: float
    parse_warnings: list[str] = field(default_factory=list)


def _parse_price_token(token: str, context: str = "") -> float | None:
    s = token.replace(",", "").strip()
    if not s:
        return None
    try:
        val = float(s)
    except ValueError:
        return None
    ctx = context.lower()
    if "k" in ctx and val < 10_000:
        val *= 1_000.0
    if "m" in ctx and val < 10_000:
        val *= 1_000_000.0
    if val < 1000 and ("btc" in ctx or "bitcoin" in ctx):
        val *= 1_000.0
    return val


def _extract_prices(text: str, *, ticker: str = "") -> list[float]:
    prices: list[float] = []
    strike = _strike_from_ticker(ticker)
    if strike is not None:
        prices.append(strike)
    for m in PRICE_RE.finditer(text):
        raw = m.group(0)
        p = _parse_price_token(m.group(1), raw)
        if p is not None and p > 100:
            prices.append(p)
    return prices


def _strike_from_ticker(ticker: str) -> float | None:
    m = TICKER_STRIKE_RE.search(ticker)
    if not m:
        return None
    try:
        val = float(m.group(1))
    except ValueError:
        return None
    return val if val > 1000 else None


def _parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=UTC)
        return dt
    except ValueError:
        return None


def _parse_ticker_datetime(ticker: str) -> datetime | None:
    """Parse KXBTCD-26MAY2717-T... → May 27, 2026 17:00 ET."""
    m = TICKER_DATE_RE.search(ticker)
    if not m:
        return None
    yy, mon, dd, hh = m.group(1), m.group(2).upper(), m.group(3), m.group(4)
    month = MONTH_MAP.get(mon)
    if month is None:
        return None
    try:
        year = 2000 + int(yy)
        day = int(dd)
        hour = int(hh)
    except ValueError:
        return None
    try:
        return datetime(year, month, day, hour, 0, 0, tzinfo=ET)
    except ValueError:
        return None


def _parse_title_time(text: str, *, reference: datetime | None = None) -> datetime | None:
    m = HOURLY_TIME_RE.search(text)
    if not m:
        return None
    hour = int(m.group(1))
    minute = int(m.group(2) or 0)
    ampm = m.group(3).lower()
    if ampm == "pm" and hour != 12:
        hour += 12
    elif ampm == "am" and hour == 12:
        hour = 0
    ref = reference or datetime.now(ET)
    if TODAY_RE.search(text):
        target_date = ref.date()
    else:
        target_date = ref.date()
    try:
        return datetime(
            target_date.year,
            target_date.month,
            target_date.day,
            hour,
            minute,
            0,
            tzinfo=ET,
        )
    except ValueError:
        return None


def _parse_direction(text: str) -> Direction | None:
    if BELOW_RE.search(text):
        return "below"
    if ABOVE_RE.search(text):
        return "above"
    return None


EVENT_FILTER_TODAY_ALIASES = frozenset(
    {"btc price today", "bitcoin price today", "price today"}
)


def market_search_text(market: NormalizedMarket) -> str:
    """Combined searchable text for market/event filters (API titles + subtitles)."""
    raw = market.raw or {}
    parts = [
        market.title,
        market.event_ticker,
        market.ticker,
        str(raw.get("subtitle", "")),
        str(raw.get("yes_sub_title", "")),
        str(raw.get("no_sub_title", "")),
        str(raw.get("rules_primary", ""))[:240],
    ]
    return " ".join(p for p in parts if p).strip()


def _ticker_contains_et_date(ticker: str, day: datetime) -> bool:
    """True when ticker embeds KXBTCD-style date e.g. 26MAY30 in KXBTCD-26MAY3018-..."""
    mon = day.strftime("%b").upper()
    dd = f"{day.day:02d}"
    yy = day.strftime("%y")
    return f"{yy}{mon}{dd}" in ticker.upper()


def is_today_btc_price_event(market: NormalizedMarket, *, now: datetime | None = None) -> bool:
    """Match Kalshi 'Bitcoin price on <today>' hourly events (documented CLI filter)."""
    ref = (now or datetime.now(ET)).astimezone(ET)
    hay = market_search_text(market).lower()
    if TODAY_RE.search(hay) or "price today" in hay:
        return True
    long_md = f"{ref.strftime('%B')} {ref.day}, {ref.year}".lower()
    short_md = f"{ref.strftime('%b')} {ref.day}, {ref.year}".lower()
    if long_md in hay or short_md in hay:
        return True
    md_no_year = f"{ref.strftime('%B')} {ref.day}".lower()
    md_no_year_short = f"{ref.strftime('%b')} {ref.day}".lower()
    if md_no_year in hay or md_no_year_short in hay:
        return True
    if _ticker_contains_et_date(market.ticker or "", ref):
        return True
    close = _parse_dt(market.close_time)
    if close is not None and close.astimezone(ET).date() == ref.date():
        return True
    return False


def matches_event_filter(
    market: NormalizedMarket,
    event_filter: str | None,
    *,
    now: datetime | None = None,
) -> bool:
    """Substring filter with aliases for documented values like 'BTC price today'."""
    if not event_filter:
        return True
    fl = event_filter.strip().lower()
    hay = market_search_text(market).lower()
    if fl in hay:
        return True
    if fl in EVENT_FILTER_TODAY_ALIASES:
        return is_today_btc_price_event(market, now=now)
    return False


def is_hourly_btc_event(
    title: str | None,
    event_title: str | None,
    ticker: str | None,
    *,
    max_expiry_hours: float = 24.0,
    close_time: str | None = None,
) -> bool:
    """True for hourly BTC threshold-style events within max_expiry_hours."""
    combined = " ".join(t for t in (title, event_title, ticker) if t)
    if not is_btc_related_text(combined):
        return False

    ticker_u = (ticker or "").upper()
    if ticker_u.startswith("KXBTCD") and TICKER_STRIKE_RE.search(ticker_u):
        if close_time:
            exp = _parse_dt(close_time)
            if exp is not None:
                hours = max(0.0, (exp - datetime.now(UTC)).total_seconds() / 3600.0)
                if hours > max_expiry_hours:
                    return False
        return True

    text = " ".join(t for t in (title, event_title) if t)
    if TODAY_RE.search(text) and HOURLY_TIME_RE.search(text):
        return True
    if HOURLY_TIME_RE.search(text) and (ABOVE_RE.search(text) or BELOW_RE.search(text)):
        return True
    if "price today" in text.lower() or "btc price" in text.lower():
        return True
    return False


def parse_hourly_target(
    market: NormalizedMarket,
    *,
    event_title: str | None = None,
    now: datetime | None = None,
) -> ParsedHourlyTarget | None:
    """Parse an hourly BTC Kalshi contract into strike, direction, and settlement time."""
    if not is_hourly_btc_event(
        market.title,
        event_title or market.event_ticker,
        market.ticker,
        close_time=market.close_time,
    ):
        return None

    raw = market.raw or {}
    text_parts = [
        market.title,
        str(raw.get("yes_sub_title", "")),
        str(raw.get("no_sub_title", "")),
        str(raw.get("rules_primary", "")),
        str(raw.get("rules_secondary", "")),
        event_title or "",
    ]
    text = " ".join(p for p in text_parts if p).strip()
    warnings: list[str] = []

    ticker_dt = _parse_ticker_datetime(market.ticker)
    title_dt = _parse_title_time(text)
    close_dt = _parse_dt(market.close_time)

    if close_dt is not None:
        settlement_utc = close_dt
    elif ticker_dt is not None:
        settlement_utc = ticker_dt.astimezone(UTC)
    elif title_dt is not None:
        settlement_utc = title_dt.astimezone(UTC)
    else:
        return None

    if ticker_dt is not None:
        target_edt = ticker_dt
    elif title_dt is not None:
        target_edt = title_dt
    else:
        target_edt = settlement_utc.astimezone(ET)

    prices = _extract_prices(text, ticker=market.ticker)
    strike = _strike_from_ticker(market.ticker)
    if strike is None and prices:
        strike = prices[0]
    if strike is None:
        warnings.append("could not determine strike price")
        return None

    direction = _parse_direction(text)
    if direction is None:
        if market.ticker.upper().startswith("KXBTCD"):
            direction = "above"
            warnings.append("inferred above-threshold from KXBTCD series")
        else:
            direction = "above"
            warnings.append("inferred above-threshold; no explicit direction in title")

    confidence = 0.85
    if ticker_dt is None:
        confidence -= 0.15
        warnings.append("could not parse settlement hour from ticker")
    if title_dt is None and not TODAY_RE.search(text):
        confidence -= 0.05
    if len(prices) > 1 and abs(prices[0] - prices[1]) > 1.0:
        confidence -= 0.10
        warnings.append("multiple prices in title; using first/strike match")

    now_utc = now or datetime.now(UTC)
    if now_utc.tzinfo is None:
        now_utc = now_utc.replace(tzinfo=UTC)
    tte_min = max(0.0, (settlement_utc - now_utc).total_seconds() / 60.0)

    return ParsedHourlyTarget(
        event_ticker=market.event_ticker,
        contract_ticker=market.ticker,
        event_title=event_title or market.title,
        contract_title=market.title,
        target_time_edt=target_edt,
        settlement_time_utc=settlement_utc,
        strike_price=float(strike),
        direction=direction,
        time_to_expiry_minutes=tte_min,
        mapping_confidence=max(0.0, min(1.0, confidence)),
        parse_warnings=warnings,
    )


def format_target_time_edt(dt: datetime) -> str:
    """Human-readable EDT/EST string for output."""
    local = dt.astimezone(ET)
    tz = local.strftime("%Z")
    return local.strftime(f"%Y-%m-%d %I:%M %p {tz}").replace(" 0", " ")


__all__ = [
    "ParsedHourlyTarget",
    "parse_hourly_target",
    "is_hourly_btc_event",
    "format_target_time_edt",
    "market_search_text",
    "matches_event_filter",
    "is_today_btc_price_event",
]
