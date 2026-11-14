"""Parse Kalshi KXBTC15M (15-minute BTC) markets into structured targets."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from kalshi_client import NormalizedMarket

SERIES = "KXBTC15M"

# Common Kalshi 15m ticker shapes, e.g. KXBTC15M-26NOV141530-T65586.65
TICKER_STRIKE_RE = re.compile(r"-T([\d.]+)$", re.IGNORECASE)
TICKER_SLOT_RE = re.compile(
    r"^KXBTC15M-(\d{2})([A-Z]{3})(\d{2})(\d{2})(\d{2})",
    re.IGNORECASE,
)
TARGET_IN_TITLE_RE = re.compile(
    r"(?:target|strike|at|above|≥|>=)\s*\$?\s*([\d,]+(?:\.\d+)?)",
    re.IGNORECASE,
)
PRICE_RE = re.compile(r"\$\s*([\d,]+(?:\.\d+)?)")
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
class ParsedKxbtc15mMarket:
    series: str
    contract_ticker: str
    event_ticker: str | None
    title: str
    target_price: float | None
    close_time_utc: datetime | None
    open_time_utc: datetime | None
    time_remaining_seconds: float | None
    mapping_confidence: float
    parse_warnings: list[str] = field(default_factory=list)
    raw: dict[str, Any] | None = None


def _parse_iso_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    s = str(value).strip()
    if not s:
        return None
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(s)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)


def _strike_from_ticker(ticker: str) -> float | None:
    m = TICKER_STRIKE_RE.search(ticker)
    if not m:
        return None
    try:
        return float(m.group(1))
    except ValueError:
        return None


def _strike_from_text(*texts: str | None) -> float | None:
    for text in texts:
        if not text:
            continue
        m = TARGET_IN_TITLE_RE.search(text)
        if m:
            try:
                return float(m.group(1).replace(",", ""))
            except ValueError:
                pass
        m2 = PRICE_RE.search(text)
        if m2:
            try:
                return float(m2.group(1).replace(",", ""))
            except ValueError:
                pass
    return None


def _slot_open_close_from_ticker(ticker: str) -> tuple[datetime | None, datetime | None]:
    """Infer 15m window from ticker date+HHMM when present (close = slot end)."""
    m = TICKER_SLOT_RE.match(ticker)
    if not m:
        return None, None
    yy, mon, dd, hh, mm = m.groups()
    month = MONTH_MAP.get(mon.upper())
    if month is None:
        return None, None
    try:
        year = 2000 + int(yy)
        close = datetime(year, month, int(dd), int(hh), int(mm), tzinfo=UTC)
    except ValueError:
        return None, None
    from datetime import timedelta

    open_dt = close - timedelta(minutes=15)
    return open_dt, close


def is_kxbtc15m_market(market: NormalizedMarket | dict[str, Any]) -> bool:
    if isinstance(market, NormalizedMarket):
        ticker = market.ticker
        event = market.event_ticker or ""
        raw = market.raw or {}
    else:
        ticker = str(market.get("ticker") or "")
        event = str(market.get("event_ticker") or "")
        raw = market
    series = str(raw.get("series_ticker") or "")
    return (
        ticker.upper().startswith(f"{SERIES}-")
        or event.upper().startswith(f"{SERIES}-")
        or series.upper() == SERIES
    )


def parse_kxbtc15m_market(
    market: NormalizedMarket,
    *,
    now: datetime | None = None,
) -> ParsedKxbtc15mMarket:
    """Parse a normalized KXBTC15M market into a decision-ready target."""
    now = now or datetime.now(UTC)
    warnings: list[str] = []
    raw = market.raw or {}

    target = _strike_from_ticker(market.ticker)
    if target is None:
        target = _strike_from_text(market.title, raw.get("subtitle"), raw.get("yes_sub_title"))
    if target is None:
        # floor_strike / cap_strike style fields when present
        for key in ("floor_strike", "cap_strike", "strike_price", "yes_strike"):
            if raw.get(key) is not None:
                try:
                    target = float(raw[key])
                    break
                except (TypeError, ValueError):
                    continue
    conf = 0.55
    if target is not None:
        conf = 0.85

    open_from_ticker, close_from_ticker = _slot_open_close_from_ticker(market.ticker)
    close_dt = _parse_iso_dt(market.close_time) or close_from_ticker
    open_dt = _parse_iso_dt(
        str(raw.get("open_time") or raw.get("expected_expiration_time") or "") or None
    ) or open_from_ticker

    if close_dt is None:
        warnings.append("missing close_time; time_remaining unknown")
        conf = min(conf, 0.45)
    if target is None:
        warnings.append("missing target_price; cannot score UP/DOWN vs strike")
        conf = min(conf, 0.35)

    tte: float | None = None
    if close_dt is not None:
        tte = max(0.0, (close_dt - now).total_seconds())

    if not is_kxbtc15m_market(market):
        warnings.append("ticker/event does not look like KXBTC15M")
        conf = min(conf, 0.40)

    return ParsedKxbtc15mMarket(
        series=SERIES,
        contract_ticker=market.ticker,
        event_ticker=market.event_ticker,
        title=market.title,
        target_price=target,
        close_time_utc=close_dt,
        open_time_utc=open_dt,
        time_remaining_seconds=tte,
        mapping_confidence=conf,
        parse_warnings=warnings,
        raw=raw,
    )


__all__ = [
    "SERIES",
    "ParsedKxbtc15mMarket",
    "is_kxbtc15m_market",
    "parse_kxbtc15m_market",
]
