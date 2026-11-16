from __future__ import annotations

import base64
import logging
import math
import os
import re
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import httpx

try:
    from cryptography.hazmat.backends import default_backend
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import padding
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
except ImportError:  # pragma: no cover
    default_backend = None  # type: ignore[assignment,misc]
    hashes = None  # type: ignore[assignment,misc]
    serialization = None  # type: ignore[assignment,misc]
    padding = None  # type: ignore[assignment,misc]
    Ed25519PrivateKey = None  # type: ignore[assignment,misc]

try:
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover
    load_dotenv = None  # type: ignore[assignment,misc]

logger = logging.getLogger(__name__)

DEFAULT_BASE_URL = "https://api.elections.kalshi.com/trade-api/v2"
SIGN_PATH_PREFIX = "/trade-api/v2"
BTC_PATTERN = re.compile(r"\b(btc|bitcoin)\b", re.IGNORECASE)
DEFAULT_BTC_SERIES_TICKERS = ("KXBTC", "KXBTCD")
# 15-minute series is first-class via fetch_kxbtc15m_markets(); not merged into
# the hourly/general DEFAULT fetch to avoid extra API load on existing jobs.
KXBTC15M_SERIES_TICKER = "KXBTC15M"


@dataclass(frozen=True)
class KalshiClientConfig:
    base_url: str = DEFAULT_BASE_URL
    timeout_s: float = 30.0
    max_pages: int = 20
    page_limit: int = 200
    status: str = "open"
    max_retries: int = 3
    retry_backoff_s: float = 0.9


@dataclass
class NormalizedMarket:
    ticker: str
    title: str
    close_time: str | None
    yes_bid: float | None
    yes_ask: float | None
    no_bid: float | None
    no_ask: float | None
    last_price: float | None
    volume: float | None
    open_interest: float | None
    implied_probability_mid: float | None
    liquidity_score: float
    updated_time: str | None
    event_ticker: str | None = None
    raw: dict[str, Any] | None = None


@dataclass
class FetchResult:
    markets: list[NormalizedMarket]
    warnings: list[str] = field(default_factory=list)
    api_available: bool = True


def _load_env() -> None:
    if load_dotenv is not None:
        load_dotenv()


def _parse_dollar_prob(value: Any) -> float | None:
    """Parse Kalshi dollar price string to probability in [0, 1]."""
    if value is None:
        return None
    if isinstance(value, (int, float)):
        v = float(value)
        return max(0.0, min(1.0, v)) if v <= 1.0 else max(0.0, min(1.0, v / 100.0))
    s = str(value).strip()
    if not s:
        return None
    try:
        v = float(s)
    except ValueError:
        return None
    if v > 1.0:
        v = v / 100.0
    return max(0.0, min(1.0, v))


def _parse_fp_count(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(str(value).strip())
    except ValueError:
        return None


def _parse_iso(value: Any) -> str | None:
    if not value:
        return None
    return str(value)


def mid_prob(bid: float | None, ask: float | None, last: float | None) -> float | None:
    if bid is not None and ask is not None:
        return max(0.0, min(1.0, (bid + ask) / 2.0))
    if ask is not None:
        return ask
    if bid is not None:
        return bid
    return last


def liquidity_score(
    *,
    yes_bid: float | None,
    yes_ask: float | None,
    volume: float | None,
    open_interest: float | None,
) -> float:
    spread = 1.0
    if yes_bid is not None and yes_ask is not None:
        spread = max(0.0, yes_ask - yes_bid)
    spread_score = max(0.0, 1.0 - spread / 0.10)

    vol = volume or 0.0
    oi = open_interest or 0.0
    vol_score = min(1.0, math.log1p(vol) / math.log1p(10_000.0)) if vol > 0 else 0.0
    oi_score = min(1.0, math.log1p(oi) / math.log1p(5_000.0)) if oi > 0 else 0.0

    quote_score = 1.0 if (yes_bid is not None or yes_ask is not None) else 0.0
    return float(max(0.0, min(1.0, 0.45 * spread_score + 0.25 * vol_score + 0.20 * oi_score + 0.10 * quote_score)))


def _market_title(raw: dict[str, Any]) -> str:
    for key in ("title", "subtitle", "yes_sub_title"):
        v = raw.get(key)
        if v and str(v).strip():
            return str(v).strip()
    return str(raw.get("ticker", ""))


def is_btc_related_text(*texts: str | None) -> bool:
    combined = " ".join(t for t in texts if t)
    return bool(BTC_PATTERN.search(combined))


def normalize_market(raw: dict[str, Any]) -> NormalizedMarket:
    yes_bid = _parse_dollar_prob(raw.get("yes_bid_dollars") or raw.get("yes_bid"))
    yes_ask = _parse_dollar_prob(raw.get("yes_ask_dollars") or raw.get("yes_ask"))
    no_bid = _parse_dollar_prob(raw.get("no_bid_dollars") or raw.get("no_bid"))
    no_ask = _parse_dollar_prob(raw.get("no_ask_dollars") or raw.get("no_ask"))
    last_price = _parse_dollar_prob(raw.get("last_price_dollars") or raw.get("last_price"))

    volume = _parse_fp_count(raw.get("volume_24h_fp") or raw.get("volume_fp") or raw.get("volume"))
    open_interest = _parse_fp_count(raw.get("open_interest_fp") or raw.get("open_interest"))

    implied = mid_prob(yes_bid, yes_ask, last_price)
    liq = liquidity_score(
        yes_bid=yes_bid,
        yes_ask=yes_ask,
        volume=volume,
        open_interest=open_interest,
    )

    close_time = _parse_iso(
        raw.get("close_time") or raw.get("latest_expiration_time") or raw.get("expiration_time")
    )

    return NormalizedMarket(
        ticker=str(raw.get("ticker", "")),
        title=_market_title(raw),
        close_time=close_time,
        yes_bid=yes_bid,
        yes_ask=yes_ask,
        no_bid=no_bid,
        no_ask=no_ask,
        last_price=last_price,
        volume=volume,
        open_interest=open_interest,
        implied_probability_mid=implied,
        liquidity_score=liq,
        updated_time=_parse_iso(raw.get("updated_time")),
        event_ticker=raw.get("event_ticker"),
        raw=raw,
    )


def _load_private_key(path: str | Path) -> Any:
    if serialization is None:
        raise RuntimeError("cryptography package required for Kalshi request signing")
    pem = Path(path).expanduser().read_bytes()
    return serialization.load_pem_private_key(pem, password=None, backend=default_backend())


def sign_kalshi_request(private_key: Any, *, timestamp_ms: str, method: str, sign_path: str) -> str:
    """Sign timestamp+METHOD+path (no query) per Kalshi API key docs."""
    if hashes is None or padding is None:
        raise RuntimeError("cryptography package required for Kalshi request signing")
    message = f"{timestamp_ms}{method.upper()}{sign_path}".encode("utf-8")
    if Ed25519PrivateKey is not None and isinstance(private_key, Ed25519PrivateKey):
        signature = private_key.sign(message)
    else:
        signature = private_key.sign(
            message,
            padding.PSS(
                mgf=padding.MGF1(hashes.SHA256()),
                salt_length=padding.PSS.DIGEST_LENGTH,
            ),
            hashes.SHA256(),
        )
    return base64.b64encode(signature).decode("utf-8")


def parse_cf_brti_payload(payload: Any) -> tuple[float | None, str]:
    """Extract a BRTI numeric value from CF / Kalshi passthrough JSON shapes."""
    if payload is None:
        return None, "empty_payload"
    if isinstance(payload, (int, float)):
        v = float(payload)
        return (v, "numeric") if v > 0 else (None, "non_positive")
    if isinstance(payload, str):
        try:
            v = float(payload.strip())
        except ValueError:
            return None, "unparseable_string"
        return (v, "string") if v > 0 else (None, "non_positive")
    if not isinstance(payload, dict):
        return None, f"unsupported_type:{type(payload).__name__}"

    # Prefer explicit average fields when present (settlement-aligned).
    for key in (
        "avg_60s",
        "avg60s",
        "average_60s",
        "last_60s_windowed_average_15min",
        "value",
        "price",
        "index",
        "brti",
    ):
        if key in payload:
            v, detail = parse_cf_brti_payload(payload.get(key))
            if v is not None:
                return v, f"{key}:{detail}"

    for nest in ("payload", "data", "result", "values"):
        if nest in payload:
            inner = payload.get(nest)
            if isinstance(inner, list) and inner:
                # CF history/values often returns a list of {value, time}
                last = inner[-1]
                v, detail = parse_cf_brti_payload(last)
                if v is not None:
                    return v, f"{nest}[-1]:{detail}"
            else:
                v, detail = parse_cf_brti_payload(inner)
                if v is not None:
                    return v, f"{nest}:{detail}"
    return None, "no_brti_field"


class KalshiClient:
    """Fetch and normalize Kalshi market data; optional signed auth for CF passthrough."""

    def __init__(self, cfg: KalshiClientConfig | None = None) -> None:
        _load_env()
        self.cfg = cfg or KalshiClientConfig(
            base_url=os.getenv("KALSHI_API_BASE", DEFAULT_BASE_URL).rstrip("/"),
        )
        self.api_key_id = os.getenv("KALSHI_API_KEY_ID")
        self.private_key_path = os.getenv("KALSHI_PRIVATE_KEY_PATH")
        self.btc_series_ticker = os.getenv("KALSHI_BTC_SERIES_TICKER")
        self.authenticated = bool(self.api_key_id and self.private_key_path)
        self.warnings: list[str] = []
        self._private_key: Any | None = None

        if not self.authenticated:
            self.warnings.append("Kalshi API credentials not set; using public market data only.")
        else:
            try:
                self._private_key = _load_private_key(self.private_key_path)  # type: ignore[arg-type]
                logger.info("Kalshi credentials loaded for signed read endpoints.")
            except Exception as exc:  # noqa: BLE001
                self.authenticated = False
                self._private_key = None
                msg = f"Kalshi private key load failed: {exc}; using public market data only."
                logger.warning(msg)
                self.warnings.append(msg)

    def _sign_path(self, path: str) -> str:
        """Full Trade API path used for signatures (no query string)."""
        clean = path.split("?", 1)[0]
        if clean.startswith(SIGN_PATH_PREFIX):
            return clean
        # base_url may already end with /trade-api/v2
        base_path = urlsplit(self.cfg.base_url).path.rstrip("/") or SIGN_PATH_PREFIX
        if not clean.startswith("/"):
            clean = "/" + clean
        if base_path.endswith(SIGN_PATH_PREFIX) or base_path == SIGN_PATH_PREFIX:
            return f"{SIGN_PATH_PREFIX}{clean}"
        return f"{base_path}{clean}"

    def _auth_headers(self, *, method: str, path: str) -> dict[str, str]:
        if not self.authenticated or self._private_key is None or not self.api_key_id:
            return {}
        timestamp_ms = str(int(time.time() * 1000))
        sign_path = self._sign_path(path)
        signature = sign_kalshi_request(
            self._private_key,
            timestamp_ms=timestamp_ms,
            method=method,
            sign_path=sign_path,
        )
        return {
            "KALSHI-ACCESS-KEY": self.api_key_id,
            "KALSHI-ACCESS-TIMESTAMP": timestamp_ms,
            "KALSHI-ACCESS-SIGNATURE": signature,
        }

    def _get(
        self,
        path: str,
        params: dict[str, Any] | None = None,
        *,
        signed: bool = False,
    ) -> dict[str, Any]:
        url = f"{self.cfg.base_url}{path}"
        last_exc: Exception | None = None
        for attempt in range(self.cfg.max_retries):
            try:
                headers = self._auth_headers(method="GET", path=path) if signed else {}
                with httpx.Client(timeout=self.cfg.timeout_s) as client:
                    resp = client.get(url, params=params or {}, headers=headers)
                    resp.raise_for_status()
                    data = resp.json()
                    if isinstance(data, dict):
                        return data
                    return {"markets": data}
            except Exception as exc:  # noqa: BLE001
                last_exc = exc
                if attempt + 1 < self.cfg.max_retries:
                    time.sleep(self.cfg.retry_backoff_s * (attempt + 1))
        raise RuntimeError(f"Kalshi API request failed: {last_exc}") from last_exc

    def fetch_markets_page(
        self,
        *,
        cursor: str | None = None,
        series_ticker: str | None = None,
        status: str | None = None,
    ) -> tuple[list[dict[str, Any]], str | None]:
        params: dict[str, Any] = {
            "limit": self.cfg.page_limit,
            "status": status or self.cfg.status,
        }
        if cursor:
            params["cursor"] = cursor
        if series_ticker:
            params["series_ticker"] = series_ticker

        data = self._get("/markets", params=params)
        markets = data.get("markets") or []
        next_cursor = data.get("cursor") or None
        if next_cursor == "":
            next_cursor = None
        return list(markets), next_cursor

    def fetch_markets(
        self,
        *,
        series_ticker: str | None = None,
        status: str | None = None,
        max_pages: int | None = None,
    ) -> list[dict[str, Any]]:
        all_markets: list[dict[str, Any]] = []
        cursor: str | None = None
        series = series_ticker or self.btc_series_ticker
        pages = max_pages if max_pages is not None else self.cfg.max_pages

        for _ in range(pages):
            page, cursor = self.fetch_markets_page(
                cursor=cursor,
                series_ticker=series,
                status=status,
            )
            all_markets.extend(page)
            if not cursor or not page:
                break
        return all_markets

    def fetch_cf_brti(self) -> tuple[float | None, str, str]:
        """Fetch BTC Real-Time Index via Kalshi CF Benchmarks REST passthrough.

        Returns (value, source, detail). Soft-fails to (None, unavailable, ...) when
        credentials/entitlement are missing — never raises for ops continuity.
        """
        if not self.authenticated or self._private_key is None:
            return None, "unavailable", "cf_brti_auth_missing"
        try:
            data = self._get(
                "/cfbenchmarks/values",
                params={"id": "BRTI"},
                signed=True,
            )
        except Exception as exc:  # noqa: BLE001
            msg = f"cf_brti_fetch_failed:{exc}"
            logger.warning(msg)
            self.warnings.append(msg)
            return None, "unavailable", msg

        # Passthrough wraps upstream under `data`
        candidate: Any = data.get("data") if isinstance(data, dict) else data
        if candidate is None:
            candidate = data
        value, detail = parse_cf_brti_payload(candidate)
        if value is None:
            return None, "unavailable", f"cf_brti_parse:{detail}"
        return value, "cf_benchmarks", f"passthrough:BRTI:{detail}"

    def fetch_settled_kxbtc15m_markets(self, *, max_pages: int = 5) -> list[dict[str, Any]]:
        """Public finalized/settled KXBTC15M markets (no auth required)."""
        return self.fetch_markets(
            series_ticker=KXBTC15M_SERIES_TICKER,
            status="settled",
            max_pages=max_pages,
        )

    def filter_btc_markets(self, raw_markets: list[dict[str, Any]]) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        for m in raw_markets:
            if is_btc_related_text(
                m.get("title"),
                m.get("subtitle"),
                m.get("yes_sub_title"),
                m.get("no_sub_title"),
                m.get("event_ticker"),
                m.get("ticker"),
                (m.get("rules_primary") if isinstance(m.get("rules_primary"), str) else None),
            ):
                out.append(m)
        return out

    def _fetch_btc_series_markets(self) -> list[dict[str, Any]]:
        """Fetch markets from configured or default BTC series tickers."""
        if self.btc_series_ticker:
            return self.fetch_markets(series_ticker=self.btc_series_ticker)

        seen: set[str] = set()
        merged: list[dict[str, Any]] = []
        for series in DEFAULT_BTC_SERIES_TICKERS:
            for m in self.fetch_markets(series_ticker=series):
                ticker = str(m.get("ticker", ""))
                if ticker and ticker not in seen:
                    seen.add(ticker)
                    merged.append(m)
        return merged

    def fetch_btc_markets(self) -> FetchResult:
        warnings = list(self.warnings)
        try:
            raw = self._fetch_btc_series_markets()
            if not raw:
                warnings.append("No markets from BTC series tickers; scanning paginated /markets.")
                raw = self.fetch_markets(series_ticker=None)

            btc_raw = self.filter_btc_markets(raw)
            if not btc_raw and raw:
                # Series tickers are BTC-specific even if title lacks the word "bitcoin"
                btc_raw = raw

            normalized = [normalize_market(m) for m in btc_raw if m.get("ticker")]

            if not normalized:
                warnings.append("No BTC-related Kalshi markets found in API response.")

            return FetchResult(markets=normalized, warnings=warnings, api_available=True)
        except Exception as exc:  # noqa: BLE001
            msg = f"Kalshi API unavailable: {exc}"
            logger.warning(msg)
            warnings.append(msg)
            return FetchResult(markets=[], warnings=warnings, api_available=False)

    def fetch_market_orderbook(self, ticker: str) -> dict[str, Any] | None:
        """Fetch orderbook depth for a market (public endpoint). Returns None on failure."""
        try:
            data = self._get(f"/markets/{ticker}/orderbook")
            if isinstance(data, dict):
                return data.get("orderbook") or data
            return None
        except Exception as exc:  # noqa: BLE001
            logger.debug("Orderbook fetch failed for %s: %s", ticker, exc)
            return None

    def fetch_event_markets(self, event_ticker: str) -> list[NormalizedMarket]:
        """Return normalized open markets for a specific event ticker."""
        raw = self.fetch_markets(series_ticker=None)
        matched = [
            normalize_market(m)
            for m in raw
            if str(m.get("event_ticker", "")) == event_ticker and m.get("ticker")
        ]
        return matched


    def fetch_kxbtc15m_markets(self) -> FetchResult:
        """Fetch and normalize open KXBTC15M series markets (15-minute BTC)."""
        warnings = list(self.warnings)
        try:
            raw = self.fetch_markets(series_ticker=KXBTC15M_SERIES_TICKER)
            if not raw:
                warnings.append(f"No markets returned for series {KXBTC15M_SERIES_TICKER}.")
            normalized = [normalize_market(m) for m in raw if m.get("ticker")]
            return FetchResult(markets=normalized, warnings=warnings, api_available=True)
        except Exception as exc:  # noqa: BLE001
            msg = f"Kalshi API unavailable for {KXBTC15M_SERIES_TICKER}: {exc}"
            logger.warning(msg)
            warnings.append(msg)
            return FetchResult(markets=[], warnings=warnings, api_available=False)


__all__ = [
    "KalshiClient",
    "KalshiClientConfig",
    "NormalizedMarket",
    "FetchResult",
    "normalize_market",
    "is_btc_related_text",
    "mid_prob",
    "liquidity_score",
    "DEFAULT_BTC_SERIES_TICKERS",
    "KXBTC15M_SERIES_TICKER",
]
