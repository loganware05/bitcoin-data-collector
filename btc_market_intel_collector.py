#!/usr/bin/env python3
"""
Bitcoin Market Intelligence Collector

Collects multi-layer Bitcoin signals (price, liquidity, derivatives, on-chain,
sentiment, and macro) from practical public APIs with graceful degradation.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from io import StringIO
from pathlib import Path
from typing import Any, TypedDict

import httpx
import numpy as np
import pandas as pd
from dotenv import load_dotenv


class SourceHealth(TypedDict, total=False):
    status: str
    message: str
    latency_ms: float
    last_updated: str


@dataclass
class AppConfig:
    timeout_seconds: float = 12.0
    max_retries: int = 3
    retry_backoff_seconds: float = 0.9
    """If set, requests bail out when monotonic clock exceeds this (soft global budget)."""
    run_deadline_monotonic: float | None = None
    output_dir: Path = Path("outputs")
    save_csv: bool = True
    log_level: str = "INFO"
    ohlc_interval: str = "1h"
    ohlc_limit: int = 240
    candles_15m_limit: int = 800
    depth_limit: int = 100
    trades_limit: int = 500
    liquidations_limit: int = 100
    rolling_vol_window: int = 30
    correlation_window: int = 60
    high_open_interest_threshold: float = 1_000_000_000.0
    extreme_funding_abs_threshold: float = 0.0008
    low_liquidity_spread_threshold_pct: float = 0.08
    slippage_notional_usd: float = 250_000.0


def setup_logging(level: str) -> None:
    """Configure application logging."""
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s | %(levelname)s | %(message)s",
    )


def now_iso() -> str:
    """Return current UTC timestamp in ISO format."""
    return datetime.now(UTC).isoformat()


def init_category_schema() -> dict[str, Any]:
    """Initialize schema with stable keys and nullable fields."""
    return {
        "timestamp": now_iso(),
        "market_data": {
            "candles_15m": [],
            "candles_15m_source": None,
            "candles_15m_as_of": None,
        },
        "price_data": {
            "spot_price_usd": None,
            "ohlc_interval": None,
            "ohlc_last_close_usd": None,
            "rolling_volatility_annualized": None,
            "market_cap_usd": None,
            "fdv_usd": None,
            "source": None,
            "as_of": None,
        },
        "volume_data": {
            "volume_24h_usd": None,
            "volume_change_pct_vs_prev_window": None,
            "pair_volumes_usd": {},
            "volume_spike_detected": None,
            "source": None,
            "as_of": None,
        },
        "liquidity_data": {
            "best_bid": None,
            "best_ask": None,
            "spread_abs": None,
            "spread_pct": None,
            "order_book_depth_usd": None,
            "buy_wall_usd_top10": None,
            "sell_wall_usd_top10": None,
            "buy_sell_pressure_ratio": None,
            "slippage_pct_for_notional": None,
            "real_time_trade_flow_note": None,
            "source": None,
            "as_of": None,
        },
        "derivatives_data": {
            "open_interest_usd": None,
            "funding_rate": None,
            "recent_liquidations_usd": None,
            "options_implied_volatility": None,
            "put_call_ratio": None,
            "max_pain": None,
            "source": None,
            "as_of": None,
        },
        "on_chain_data": {
            "transaction_count": None,
            "active_addresses": None,
            "hash_rate": None,
            "circulating_supply_btc": None,
            "exchange_inflow_btc": None,
            "exchange_outflow_btc": None,
            "dormant_supply_ratio": None,
            "whale_movement_note": None,
            "source": None,
            "as_of": None,
        },
        "sentiment_data": {
            "fear_greed_value": None,
            "fear_greed_classification": None,
            "social_sentiment_score": None,
            "social_volume": None,
            "news_sentiment_score": None,
            "source": None,
            "as_of": None,
        },
        "macro_data": {
            "corr_btc_spx": None,
            "corr_btc_gold": None,
            "corr_btc_qqq": None,
            "etf_net_flow_usd": None,
            "etf_flow_note": None,
            "source": None,
            "as_of": None,
        },
        "signals": {
            "high_open_interest": None,
            "extreme_funding": None,
            "exchange_outflow_bullish": None,
            "low_liquidity_warning": None,
            "volume_spike": None,
        },
        "source_health": {},
    }


def update_source_health(
    source_health: dict[str, SourceHealth],
    source: str,
    status: str,
    message: str,
    latency_ms: float | None = None,
) -> None:
    """Store per-source health information."""
    payload: SourceHealth = {
        "status": status,
        "message": message,
        "last_updated": now_iso(),
    }
    if latency_ms is not None:
        payload["latency_ms"] = round(latency_ms, 2)
    source_health[source] = payload


def parse_float(value: Any) -> float | None:
    """Safely parse nullable numeric values."""
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _is_transient_http_status(status_code: int) -> bool:
    """Statuses worth retrying: rate limit, timeout, server errors."""
    if status_code in (408, 429):
        return True
    return 500 <= status_code <= 599


def _deadline_exceeded(config: AppConfig) -> bool:
    if config.run_deadline_monotonic is None:
        return False
    return time.monotonic() > config.run_deadline_monotonic


def request_json(
    client: httpx.Client,
    url: str,
    source: str,
    source_health: dict[str, SourceHealth],
    params: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
    config: AppConfig | None = None,
) -> dict[str, Any] | list[Any] | None:
    """Fetch JSON with retries (transient HTTP + network only) and source health tracking."""
    cfg = config or AppConfig()
    last_error = "unknown error"
    for attempt in range(1, cfg.max_retries + 1):
        if _deadline_exceeded(cfg):
            msg = "skipped: max runtime exceeded before request"
            update_source_health(source_health, source, "error", msg)
            return None
        start = time.perf_counter()
        try:
            response = client.get(url, params=params, headers=headers, timeout=cfg.timeout_seconds)
            latency_ms = (time.perf_counter() - start) * 1000
            code = response.status_code
            if 200 <= code < 300:
                try:
                    data = response.json()
                except ValueError as exc:
                    last_error = f"invalid JSON: {exc}"
                    update_source_health(source_health, source, "error", last_error, latency_ms)
                    return None
                update_source_health(source_health, source, "ok", "fetched successfully", latency_ms)
                return data
            if _is_transient_http_status(code):
                last_error = f"HTTP {code}"
                if attempt < cfg.max_retries and not _deadline_exceeded(cfg):
                    time.sleep(cfg.retry_backoff_seconds * attempt)
                continue
            last_error = f"HTTP {code} (no retry)"
            update_source_health(source_health, source, "error", last_error, latency_ms)
            return None
        except httpx.HTTPStatusError as exc:
            last_error = str(exc)
            code = exc.response.status_code if exc.response is not None else 0
            if _is_transient_http_status(code) and attempt < cfg.max_retries and not _deadline_exceeded(cfg):
                time.sleep(cfg.retry_backoff_seconds * attempt)
                continue
            update_source_health(source_health, source, "error", last_error)
            return None
        except httpx.RequestError as exc:
            last_error = str(exc)
            if attempt < cfg.max_retries and not _deadline_exceeded(cfg):
                time.sleep(cfg.retry_backoff_seconds * attempt)
                continue
    update_source_health(source_health, source, "error", last_error)
    return None


def request_text(
    client: httpx.Client,
    url: str,
    source: str,
    source_health: dict[str, SourceHealth],
    params: dict[str, Any] | None = None,
    config: AppConfig | None = None,
) -> str | None:
    """Fetch text with retries (transient HTTP + network only) and source health tracking."""
    cfg = config or AppConfig()
    last_error = "unknown error"
    for attempt in range(1, cfg.max_retries + 1):
        if _deadline_exceeded(cfg):
            msg = "skipped: max runtime exceeded before request"
            update_source_health(source_health, source, "error", msg)
            return None
        start = time.perf_counter()
        try:
            response = client.get(url, params=params, timeout=cfg.timeout_seconds)
            latency_ms = (time.perf_counter() - start) * 1000
            code = response.status_code
            if 200 <= code < 300:
                update_source_health(source_health, source, "ok", "fetched successfully", latency_ms)
                return response.text
            if _is_transient_http_status(code):
                last_error = f"HTTP {code}"
                if attempt < cfg.max_retries and not _deadline_exceeded(cfg):
                    time.sleep(cfg.retry_backoff_seconds * attempt)
                continue
            last_error = f"HTTP {code} (no retry)"
            update_source_health(source_health, source, "error", last_error, latency_ms)
            return None
        except httpx.HTTPStatusError as exc:
            last_error = str(exc)
            code = exc.response.status_code if exc.response is not None else 0
            if _is_transient_http_status(code) and attempt < cfg.max_retries and not _deadline_exceeded(cfg):
                time.sleep(cfg.retry_backoff_seconds * attempt)
                continue
            update_source_health(source_health, source, "error", last_error)
            return None
        except httpx.RequestError as exc:
            last_error = str(exc)
            if attempt < cfg.max_retries and not _deadline_exceeded(cfg):
                time.sleep(cfg.retry_backoff_seconds * attempt)
                continue
    update_source_health(source_health, source, "error", last_error)
    return None


def fetch_binance_spot_market(
    client: httpx.Client,
    config: AppConfig,
    source_health: dict[str, SourceHealth],
) -> dict[str, Any]:
    """Fetch spot ticker, OHLC, depth, and trades from Binance."""
    base = "https://api.binance.com"
    symbol = "BTCUSDT"

    ticker = request_json(
        client,
        f"{base}/api/v3/ticker/24hr",
        "binance_spot_ticker",
        source_health,
        params={"symbol": symbol},
        config=config,
    )
    klines = request_json(
        client,
        f"{base}/api/v3/klines",
        "binance_spot_klines",
        source_health,
        params={"symbol": symbol, "interval": config.ohlc_interval, "limit": config.ohlc_limit},
        config=config,
    )
    klines_15m = request_json(
        client,
        f"{base}/api/v3/klines",
        "binance_spot_klines_15m",
        source_health,
        params={"symbol": symbol, "interval": "15m", "limit": config.candles_15m_limit},
        config=config,
    )
    depth = request_json(
        client,
        f"{base}/api/v3/depth",
        "binance_spot_depth",
        source_health,
        params={"symbol": symbol, "limit": config.depth_limit},
        config=config,
    )
    trades = request_json(
        client,
        f"{base}/api/v3/trades",
        "binance_spot_trades",
        source_health,
        params={"symbol": symbol, "limit": config.trades_limit},
        config=config,
    )
    return {"ticker": ticker, "klines": klines, "klines_15m": klines_15m, "depth": depth, "trades": trades}


def fetch_coinbase_spot_market(
    client: httpx.Client,
    config: AppConfig,
    source_health: dict[str, SourceHealth],
) -> dict[str, Any]:
    """Fetch spot market fallback metrics from Coinbase Exchange public API."""
    base = "https://api.exchange.coinbase.com/products/BTC-USD"
    ticker = request_json(client, f"{base}/ticker", "coinbase_spot_ticker", source_health, config=config)
    candles = request_json(
        client,
        f"{base}/candles",
        "coinbase_spot_candles",
        source_health,
        params={"granularity": 3600},
        config=config,
    )
    candles_15m = request_json(
        client,
        f"{base}/candles",
        "coinbase_spot_candles_15m",
        source_health,
        params={"granularity": 900},
        config=config,
    )
    book = request_json(
        client, f"{base}/book", "coinbase_spot_book", source_health, params={"level": 2}, config=config
    )
    trades = request_json(client, f"{base}/trades", "coinbase_spot_trades", source_health, config=config)
    return {"ticker": ticker, "klines": candles, "klines_15m": candles_15m, "depth": book, "trades": trades}


def _to_candle_rows_from_binance_klines(klines: Any) -> list[dict[str, Any]]:
    """
    Convert Binance kline arrays into a stable JSON-friendly candle list.
    Each row: {timestamp, open, high, low, close, volume}.
    """
    if not isinstance(klines, list):
        return []
    out: list[dict[str, Any]] = []
    for row in klines:
        if not isinstance(row, list) or len(row) < 6:
            continue
        ts_ms = row[0]
        o, h, l, c, v = row[1], row[2], row[3], row[4], row[5]
        ts = pd.to_datetime(ts_ms, unit="ms", utc=True, errors="coerce")
        if ts is pd.NaT:
            continue
        out.append(
            {
                "timestamp": ts.isoformat(),
                "open": parse_float(o),
                "high": parse_float(h),
                "low": parse_float(l),
                "close": parse_float(c),
                "volume": parse_float(v),
            }
        )
    return [r for r in out if all(r.get(k) is not None for k in ("open", "high", "low", "close", "volume"))]


def _to_candle_rows_from_coinbase_candles(candles: Any) -> list[dict[str, Any]]:
    """
    Convert Coinbase candle rows [time, low, high, open, close, volume] into stable candle dicts.
    """
    if not isinstance(candles, list):
        return []
    out: list[dict[str, Any]] = []
    for row in candles:
        if not isinstance(row, list) or len(row) < 6:
            continue
        ts_s, low, high, open_, close, volume = row[:6]
        ts = pd.to_datetime(ts_s, unit="s", utc=True, errors="coerce")
        if ts is pd.NaT:
            continue
        out.append(
            {
                "timestamp": ts.isoformat(),
                "open": parse_float(open_),
                "high": parse_float(high),
                "low": parse_float(low),
                "close": parse_float(close),
                "volume": parse_float(volume),
            }
        )
    out = [r for r in out if all(r.get(k) is not None for k in ("open", "high", "low", "close", "volume"))]
    # Coinbase returns newest-first; normalize ascending for downstream calculations.
    out.sort(key=lambda r: r["timestamp"])
    return out


def fetch_binance_pair_volumes(
    client: httpx.Client,
    config: AppConfig,
    source_health: dict[str, SourceHealth],
) -> dict[str, float]:
    """Fetch USD quote volumes for popular BTC trading pairs from Binance."""
    base = "https://api.binance.com"
    payload = request_json(client, f"{base}/api/v3/ticker/24hr", "binance_pair_volumes", source_health, config=config)
    if not isinstance(payload, list):
        return {}
    result: dict[str, float] = {}
    for item in payload:
        sym = str(item.get("symbol", ""))
        if not sym.startswith("BTC"):
            continue
        quote_vol = parse_float(item.get("quoteVolume"))
        if quote_vol is not None:
            result[sym] = quote_vol
    return dict(sorted(result.items(), key=lambda kv: kv[1], reverse=True)[:10])


def fetch_coingecko_market(
    client: httpx.Client,
    config: AppConfig,
    source_health: dict[str, SourceHealth],
) -> dict[str, Any]:
    """Fetch aggregated market metrics from CoinGecko."""
    base = "https://api.coingecko.com/api/v3"
    headers: dict[str, str] = {}
    api_key = os.getenv("COINGECKO_API_KEY")
    if api_key:
        headers["x-cg-demo-api-key"] = api_key

    market_data = request_json(
        client,
        f"{base}/coins/markets",
        "coingecko_markets",
        source_health,
        params={"vs_currency": "usd", "ids": "bitcoin"},
        headers=headers or None,
        config=config,
    )
    return {"market_data": market_data}


def fetch_binance_derivatives(
    client: httpx.Client,
    config: AppConfig,
    source_health: dict[str, SourceHealth],
) -> dict[str, Any]:
    """Fetch derivatives metrics from Binance Futures public endpoints."""
    base = "https://fapi.binance.com"
    symbol = "BTCUSDT"
    oi = request_json(
        client,
        f"{base}/fapi/v1/openInterest",
        "binance_futures_open_interest",
        source_health,
        params={"symbol": symbol},
        config=config,
    )
    funding = request_json(
        client,
        f"{base}/fapi/v1/fundingRate",
        "binance_futures_funding",
        source_health,
        params={"symbol": symbol, "limit": 1},
        config=config,
    )
    liquidations = request_json(
        client,
        f"{base}/fapi/v1/allForceOrders",
        "binance_futures_liquidations",
        source_health,
        params={"symbol": symbol, "limit": config.liquidations_limit},
        config=config,
    )
    return {"open_interest": oi, "funding": funding, "liquidations": liquidations}


def fetch_blockchain_com_onchain(
    client: httpx.Client,
    config: AppConfig,
    source_health: dict[str, SourceHealth],
) -> dict[str, Any]:
    """Fetch on-chain metrics from Blockchain.com charts API."""
    base = "https://api.blockchain.info/charts"
    tx_count = request_json(
        client,
        f"{base}/n-transactions",
        "blockchaincom_transactions",
        source_health,
        params={"timespan": "30days", "format": "json"},
        config=config,
    )
    hash_rate = request_json(
        client,
        f"{base}/hash-rate",
        "blockchaincom_hashrate",
        source_health,
        params={"timespan": "30days", "format": "json"},
        config=config,
    )
    return {"tx_count": tx_count, "hash_rate": hash_rate}


def fetch_fear_greed(
    client: httpx.Client,
    config: AppConfig,
    source_health: dict[str, SourceHealth],
) -> dict[str, Any]:
    """Fetch Fear & Greed Index from Alternative.me."""
    payload = request_json(
        client,
        "https://api.alternative.me/fng/",
        "alternative_fng",
        source_health,
        params={"limit": 1, "format": "json"},
        config=config,
    )
    return {"fear_greed": payload}


def fetch_stooq_series(
    client: httpx.Client,
    symbol: str,
    source_tag: str,
    config: AppConfig,
    source_health: dict[str, SourceHealth],
) -> pd.Series:
    """Fetch daily close series from Stooq CSV endpoint."""
    url = "https://stooq.com/q/d/l/"
    text = request_text(client, url, source_tag, source_health, params={"s": symbol, "i": "d"}, config=config)
    if not text:
        return pd.Series(dtype=float)
    try:
        df = pd.read_csv(StringIO(text))
        if "Date" not in df.columns or "Close" not in df.columns:
            return pd.Series(dtype=float)
        df["Date"] = pd.to_datetime(df["Date"], errors="coerce", utc=True)
        df["Close"] = pd.to_numeric(df["Close"], errors="coerce")
        clean = df.dropna(subset=["Date", "Close"]).set_index("Date")["Close"].sort_index()
        return clean.astype(float)
    except Exception as exc:  # noqa: BLE001
        update_source_health(source_health, source_tag, "error", f"parse failed: {exc}")
        return pd.Series(dtype=float)


def fetch_yahoo_series(
    client: httpx.Client,
    symbol: str,
    source_tag: str,
    config: AppConfig,
    source_health: dict[str, SourceHealth],
) -> pd.Series:
    """Fetch close series from Yahoo chart API as macro correlation fallback."""
    payload = request_json(
        client,
        f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}",
        source_tag,
        source_health,
        params={"range": "2y", "interval": "1d"},
        config=config,
    )
    if not isinstance(payload, dict):
        return pd.Series(dtype=float)
    try:
        result = payload.get("chart", {}).get("result", [])
        if not result:
            return pd.Series(dtype=float)
        row = result[0]
        timestamps = row.get("timestamp", [])
        closes = row.get("indicators", {}).get("quote", [{}])[0].get("close", [])
        if not timestamps or not closes:
            return pd.Series(dtype=float)
        idx = pd.to_datetime(pd.Series(timestamps), unit="s", utc=True, errors="coerce")
        vals = pd.to_numeric(pd.Series(closes), errors="coerce")
        series = pd.Series(vals.values, index=idx).dropna().sort_index()
        return series.astype(float)
    except Exception as exc:  # noqa: BLE001
        update_source_health(source_health, source_tag, "error", f"parse failed: {exc}")
        return pd.Series(dtype=float)


def fetch_fred_series(
    client: httpx.Client,
    series_id: str,
    source_tag: str,
    config: AppConfig,
    source_health: dict[str, SourceHealth],
) -> pd.Series:
    """Fetch market series from FRED CSV graph endpoint (no API key required)."""
    text = request_text(
        client,
        "https://fred.stlouisfed.org/graph/fredgraph.csv",
        source_tag,
        source_health,
        params={"id": series_id},
        config=config,
    )
    if not text:
        return pd.Series(dtype=float)
    try:
        df = pd.read_csv(StringIO(text))
        if df.shape[1] < 2:
            return pd.Series(dtype=float)
        date_col, val_col = df.columns[0], df.columns[1]
        df[date_col] = pd.to_datetime(df[date_col], errors="coerce", utc=True)
        df[val_col] = pd.to_numeric(df[val_col], errors="coerce")
        series = df.dropna(subset=[date_col, val_col]).set_index(date_col)[val_col].sort_index()
        return series.astype(float)
    except Exception as exc:  # noqa: BLE001
        update_source_health(source_health, source_tag, "error", f"parse failed: {exc}")
        return pd.Series(dtype=float)


def fetch_coingecko_btc_series(
    client: httpx.Client,
    config: AppConfig,
    source_health: dict[str, SourceHealth],
) -> pd.Series:
    """Fetch BTC daily price history from CoinGecko for macro correlations."""
    headers: dict[str, str] = {}
    api_key = os.getenv("COINGECKO_API_KEY")
    if api_key:
        headers["x-cg-demo-api-key"] = api_key
    payload = request_json(
        client,
        "https://api.coingecko.com/api/v3/coins/bitcoin/market_chart",
        "coingecko_btc_series",
        source_health,
        params={"vs_currency": "usd", "days": 365, "interval": "daily"},
        headers=headers or None,
        config=config,
    )
    if not isinstance(payload, dict):
        return pd.Series(dtype=float)
    prices = payload.get("prices")
    if not isinstance(prices, list) or not prices:
        return pd.Series(dtype=float)
    rows: list[tuple[pd.Timestamp, float]] = []
    for pair in prices:
        if not isinstance(pair, list) or len(pair) < 2:
            continue
        ts_ms, val = pair[0], pair[1]
        ts = pd.to_datetime(ts_ms, unit="ms", utc=True, errors="coerce")
        close = parse_float(val)
        if ts is pd.NaT or close is None:
            continue
        rows.append((ts, close))
    if not rows:
        return pd.Series(dtype=float)
    index = [r[0] for r in rows]
    values = [r[1] for r in rows]
    return pd.Series(values, index=index, dtype=float).sort_index()


def compute_rolling_volatility(klines: list[Any], window: int) -> float | None:
    """Compute annualized rolling volatility from OHLC close prices."""
    if not isinstance(klines, list) or len(klines) < max(window + 1, 3):
        return None
    closes = pd.to_numeric(pd.Series([row[4] for row in klines]), errors="coerce").dropna()
    if len(closes) < max(window + 1, 3):
        return None
    returns = np.log(closes / closes.shift(1)).dropna()
    rolling_std = returns.rolling(window).std().dropna()
    if rolling_std.empty:
        return None
    return float(rolling_std.iloc[-1] * np.sqrt(24 * 365))


def compute_volume_change_pct(klines: list[Any]) -> float | None:
    """Compare latest half-window quote volume against previous half-window."""
    if not isinstance(klines, list) or len(klines) < 30:
        return None
    qvol = pd.to_numeric(pd.Series([row[7] for row in klines]), errors="coerce").dropna()
    if len(qvol) < 30:
        return None
    half = len(qvol) // 2
    prev = qvol.iloc[:half].sum()
    latest = qvol.iloc[half:].sum()
    if prev <= 0:
        return None
    return float((latest - prev) / prev * 100.0)


def compute_volume_spike(klines: list[Any], z_threshold: float = 2.0) -> bool | None:
    """Detect quote-volume spike using simple z-score on recent candles."""
    if not isinstance(klines, list) or len(klines) < 30:
        return None
    qvol = pd.to_numeric(pd.Series([row[7] for row in klines]), errors="coerce").dropna()
    if len(qvol) < 30:
        return None
    mean = float(qvol.iloc[:-1].mean())
    std = float(qvol.iloc[:-1].std(ddof=0))
    latest = float(qvol.iloc[-1])
    if std <= 0:
        return None
    z = (latest - mean) / std
    return bool(z >= z_threshold)


def estimate_order_book_metrics(depth: dict[str, Any], slippage_notional: float) -> dict[str, float | None]:
    """Compute spread/depth/walls/slippage proxies from order book snapshots."""
    bids_raw = depth.get("bids", []) if isinstance(depth, dict) else []
    asks_raw = depth.get("asks", []) if isinstance(depth, dict) else []
    bids = [(parse_float(x[0]), parse_float(x[1])) for x in bids_raw if len(x) >= 2]
    asks = [(parse_float(x[0]), parse_float(x[1])) for x in asks_raw if len(x) >= 2]
    bids = [(p, q) for p, q in bids if p and q]
    asks = [(p, q) for p, q in asks if p and q]
    if not bids or not asks:
        return {
            "best_bid": None,
            "best_ask": None,
            "spread_abs": None,
            "spread_pct": None,
            "depth_usd": None,
            "buy_wall_top10": None,
            "sell_wall_top10": None,
            "slippage_pct": None,
        }

    best_bid = bids[0][0]
    best_ask = asks[0][0]
    spread_abs = best_ask - best_bid
    spread_pct = (spread_abs / best_ask) * 100 if best_ask else None
    depth_usd = sum(p * q for p, q in bids[:20]) + sum(p * q for p, q in asks[:20])
    buy_wall_top10 = sum(p * q for p, q in bids[:10])
    sell_wall_top10 = sum(p * q for p, q in asks[:10])

    consumed = 0.0
    weighted_cost = 0.0
    for price, qty in asks:
        level_usd = price * qty
        take = min(level_usd, slippage_notional - consumed)
        if take <= 0:
            break
        weighted_cost += take * (price / best_ask - 1.0)
        consumed += take
        if consumed >= slippage_notional:
            break
    slippage_pct = (weighted_cost / consumed * 100.0) if consumed > 0 else None

    return {
        "best_bid": best_bid,
        "best_ask": best_ask,
        "spread_abs": spread_abs,
        "spread_pct": spread_pct,
        "depth_usd": depth_usd,
        "buy_wall_top10": buy_wall_top10,
        "sell_wall_top10": sell_wall_top10,
        "slippage_pct": slippage_pct,
    }


def estimate_order_book_metrics_coinbase(
    depth: dict[str, Any], slippage_notional: float
) -> dict[str, float | None]:
    """Compute order book metrics from Coinbase level-2 format."""
    bids_raw = depth.get("bids", []) if isinstance(depth, dict) else []
    asks_raw = depth.get("asks", []) if isinstance(depth, dict) else []
    bids = [(parse_float(x[0]), parse_float(x[1])) for x in bids_raw if len(x) >= 2]
    asks = [(parse_float(x[0]), parse_float(x[1])) for x in asks_raw if len(x) >= 2]
    bids = [(p, q) for p, q in bids if p and q]
    asks = [(p, q) for p, q in asks if p and q]
    if not bids or not asks:
        return estimate_order_book_metrics({}, slippage_notional)
    return estimate_order_book_metrics({"bids": bids_raw, "asks": asks_raw}, slippage_notional)


def estimate_trade_pressure(trades: list[Any]) -> float | None:
    """
    Estimate buy/sell pressure ratio from Binance trade side indicator.
    isBuyerMaker=True means aggressive side was sell.
    """
    if not isinstance(trades, list) or not trades:
        return None
    buy_notional = 0.0
    sell_notional = 0.0
    for trade in trades:
        price = parse_float(trade.get("price"))
        qty = parse_float(trade.get("qty"))
        if price is None or qty is None:
            continue
        notional = price * qty
        is_buyer_maker = bool(trade.get("isBuyerMaker"))
        if is_buyer_maker:
            sell_notional += notional
        else:
            buy_notional += notional
    if sell_notional <= 0:
        return None if buy_notional <= 0 else float("inf")
    return buy_notional / sell_notional


def estimate_trade_pressure_coinbase(trades: list[Any]) -> float | None:
    """Estimate buy/sell pressure ratio from Coinbase trade side field."""
    if not isinstance(trades, list) or not trades:
        return None
    buy_notional = 0.0
    sell_notional = 0.0
    for trade in trades:
        if not isinstance(trade, dict):
            continue
        price = parse_float(trade.get("price"))
        size = parse_float(trade.get("size"))
        side = trade.get("side")
        if price is None or size is None:
            continue
        notional = price * size
        if side == "buy":
            buy_notional += notional
        elif side == "sell":
            sell_notional += notional
    if sell_notional <= 0:
        return None if buy_notional <= 0 else float("inf")
    return buy_notional / sell_notional


def convert_coinbase_candles_to_binance_like(candles: list[Any]) -> list[list[Any]]:
    """Convert Coinbase candle format to a kline-like shape used by metric helpers."""
    converted: list[list[Any]] = []
    if not isinstance(candles, list):
        return converted
    for row in candles:
        if not isinstance(row, list) or len(row) < 6:
            continue
        ts, low, high, open_, close, volume = row[:6]
        quote_volume = (parse_float(close) or 0.0) * (parse_float(volume) or 0.0)
        converted.append([ts, open_, high, low, close, volume, None, quote_volume])
    converted.sort(key=lambda x: x[0])
    return converted


def extract_last_chart_value(chart_payload: dict[str, Any] | None) -> float | None:
    """Extract latest y value from Blockchain.com chart response."""
    if not isinstance(chart_payload, dict):
        return None
    values = chart_payload.get("values")
    if not isinstance(values, list) or not values:
        return None
    last = values[-1]
    if not isinstance(last, dict):
        return None
    return parse_float(last.get("y"))


def compute_correlation(a: pd.Series, b: pd.Series, window: int) -> float | None:
    """Compute rolling return correlation between two close series."""
    if a.empty or b.empty:
        return None
    df = pd.concat([a.rename("a"), b.rename("b")], axis=1).dropna()
    if len(df) < window + 2:
        return None
    returns = np.log(df / df.shift(1)).dropna()
    if len(returns) < window:
        return None
    corr = returns["a"].tail(window).corr(returns["b"].tail(window))
    return None if pd.isna(corr) else float(corr)


def normalize_and_compute(
    result: dict[str, Any],
    binance_market: dict[str, Any],
    pair_volumes: dict[str, float],
    coingecko: dict[str, Any],
    derivatives: dict[str, Any],
    onchain: dict[str, Any],
    sentiment: dict[str, Any],
    macro_series: dict[str, pd.Series],
    config: AppConfig,
) -> None:
    """Normalize source payloads into unified schema and derive metrics/signals."""
    ticker = binance_market.get("ticker")
    klines = binance_market.get("klines")
    klines_15m = binance_market.get("klines_15m")
    depth = binance_market.get("depth")
    trades = binance_market.get("trades")

    if isinstance(ticker, dict):
        result["price_data"]["spot_price_usd"] = parse_float(ticker.get("lastPrice"))
        result["volume_data"]["volume_24h_usd"] = parse_float(ticker.get("quoteVolume"))
        result["price_data"]["source"] = "binance_spot_ticker"
        result["volume_data"]["source"] = "binance_spot_ticker"
        result["price_data"]["as_of"] = now_iso()
        result["volume_data"]["as_of"] = now_iso()

    if isinstance(klines, list) and klines:
        last_close = parse_float(klines[-1][4]) if len(klines[-1]) > 4 else None
        result["price_data"]["ohlc_interval"] = config.ohlc_interval
        result["price_data"]["ohlc_last_close_usd"] = last_close
        result["price_data"]["rolling_volatility_annualized"] = compute_rolling_volatility(
            klines, config.rolling_vol_window
        )
        result["volume_data"]["volume_change_pct_vs_prev_window"] = compute_volume_change_pct(klines)
        result["volume_data"]["volume_spike_detected"] = compute_volume_spike(klines)

    # Persist candle history (15m) for reproducible feature engineering / indicators.
    # Prefer Binance; fallback to Coinbase.
    candles_15m_rows: list[dict[str, Any]] = _to_candle_rows_from_binance_klines(klines_15m)
    if candles_15m_rows:
        result["market_data"]["candles_15m"] = candles_15m_rows
        result["market_data"]["candles_15m_source"] = "binance_spot_klines_15m"
        result["market_data"]["candles_15m_as_of"] = now_iso()
    else:
        cb_15m = binance_market.get("coinbase_klines_15m")
        cb_rows = _to_candle_rows_from_coinbase_candles(cb_15m)
        result["market_data"]["candles_15m"] = cb_rows
        result["market_data"]["candles_15m_source"] = "coinbase_spot_candles_15m" if cb_rows else None
        result["market_data"]["candles_15m_as_of"] = now_iso() if cb_rows else None

    result["volume_data"]["pair_volumes_usd"] = pair_volumes

    book_metrics = estimate_order_book_metrics(depth if isinstance(depth, dict) else {}, config.slippage_notional_usd)
    pressure_ratio = estimate_trade_pressure(trades if isinstance(trades, list) else [])
    result["liquidity_data"]["best_bid"] = book_metrics["best_bid"]
    result["liquidity_data"]["best_ask"] = book_metrics["best_ask"]
    result["liquidity_data"]["spread_abs"] = book_metrics["spread_abs"]
    result["liquidity_data"]["spread_pct"] = book_metrics["spread_pct"]
    result["liquidity_data"]["order_book_depth_usd"] = book_metrics["depth_usd"]
    result["liquidity_data"]["buy_wall_usd_top10"] = book_metrics["buy_wall_top10"]
    result["liquidity_data"]["sell_wall_usd_top10"] = book_metrics["sell_wall_top10"]
    result["liquidity_data"]["buy_sell_pressure_ratio"] = pressure_ratio
    result["liquidity_data"]["slippage_pct_for_notional"] = book_metrics["slippage_pct"]
    result["liquidity_data"]["real_time_trade_flow_note"] = (
        "Estimated from recent Binance trades; proxy only."
    )
    result["liquidity_data"]["source"] = "binance_spot_depth+trades"
    result["liquidity_data"]["as_of"] = now_iso()

    if result["price_data"]["spot_price_usd"] is None:
        cb_ticker = binance_market.get("coinbase_ticker")
        if isinstance(cb_ticker, dict):
            result["price_data"]["spot_price_usd"] = parse_float(cb_ticker.get("price"))
            result["volume_data"]["volume_24h_usd"] = parse_float(cb_ticker.get("volume")) * (
                result["price_data"]["spot_price_usd"] or 0.0
            )
            result["price_data"]["source"] = "coinbase_spot_ticker"
            result["volume_data"]["source"] = "coinbase_spot_ticker"
            result["price_data"]["as_of"] = now_iso()
            result["volume_data"]["as_of"] = now_iso()

    if (result["price_data"]["rolling_volatility_annualized"] is None) or (
        result["volume_data"]["volume_change_pct_vs_prev_window"] is None
    ):
        cb_klines = convert_coinbase_candles_to_binance_like(binance_market.get("coinbase_klines"))
        if cb_klines:
            result["price_data"]["ohlc_interval"] = "1h"
            result["price_data"]["ohlc_last_close_usd"] = parse_float(cb_klines[-1][4])
            result["price_data"]["rolling_volatility_annualized"] = compute_rolling_volatility(
                cb_klines, config.rolling_vol_window
            )
            result["volume_data"]["volume_change_pct_vs_prev_window"] = compute_volume_change_pct(cb_klines)
            result["volume_data"]["volume_spike_detected"] = compute_volume_spike(cb_klines)

    if result["liquidity_data"]["spread_pct"] is None:
        cb_depth = binance_market.get("coinbase_depth")
        cb_trades = binance_market.get("coinbase_trades")
        cb_book = estimate_order_book_metrics_coinbase(
            cb_depth if isinstance(cb_depth, dict) else {}, config.slippage_notional_usd
        )
        cb_pressure = estimate_trade_pressure_coinbase(cb_trades if isinstance(cb_trades, list) else [])
        result["liquidity_data"]["best_bid"] = cb_book["best_bid"]
        result["liquidity_data"]["best_ask"] = cb_book["best_ask"]
        result["liquidity_data"]["spread_abs"] = cb_book["spread_abs"]
        result["liquidity_data"]["spread_pct"] = cb_book["spread_pct"]
        result["liquidity_data"]["order_book_depth_usd"] = cb_book["depth_usd"]
        result["liquidity_data"]["buy_wall_usd_top10"] = cb_book["buy_wall_top10"]
        result["liquidity_data"]["sell_wall_usd_top10"] = cb_book["sell_wall_top10"]
        result["liquidity_data"]["buy_sell_pressure_ratio"] = cb_pressure
        result["liquidity_data"]["slippage_pct_for_notional"] = cb_book["slippage_pct"]
        result["liquidity_data"]["source"] = "coinbase_spot_book+trades"
        result["liquidity_data"]["as_of"] = now_iso()

    market_data = coingecko.get("market_data")
    if isinstance(market_data, list) and market_data:
        btc = market_data[0]
        if isinstance(btc, dict):
            result["price_data"]["market_cap_usd"] = parse_float(btc.get("market_cap"))
            result["price_data"]["fdv_usd"] = parse_float(btc.get("fully_diluted_valuation"))
            result["on_chain_data"]["circulating_supply_btc"] = parse_float(btc.get("circulating_supply"))
            result["on_chain_data"]["source"] = "coingecko_markets"
            result["on_chain_data"]["as_of"] = now_iso()

    oi = derivatives.get("open_interest")
    if isinstance(oi, dict):
        result["derivatives_data"]["open_interest_usd"] = parse_float(oi.get("openInterest"))
    funding = derivatives.get("funding")
    if isinstance(funding, list) and funding:
        row = funding[-1]
        if isinstance(row, dict):
            result["derivatives_data"]["funding_rate"] = parse_float(row.get("fundingRate"))
    liq = derivatives.get("liquidations")
    if isinstance(liq, list):
        total_liq = 0.0
        for row in liq:
            if not isinstance(row, dict):
                continue
            qty = parse_float(row.get("origQty")) or 0.0
            price = parse_float(row.get("avgPrice")) or parse_float(row.get("price")) or 0.0
            total_liq += qty * price
        result["derivatives_data"]["recent_liquidations_usd"] = total_liq if total_liq > 0 else None
    result["derivatives_data"]["options_implied_volatility"] = None
    result["derivatives_data"]["put_call_ratio"] = None
    result["derivatives_data"]["max_pain"] = None
    result["derivatives_data"]["source"] = "binance_futures_public"
    result["derivatives_data"]["as_of"] = now_iso()

    result["on_chain_data"]["transaction_count"] = extract_last_chart_value(onchain.get("tx_count"))
    result["on_chain_data"]["hash_rate"] = extract_last_chart_value(onchain.get("hash_rate"))
    result["on_chain_data"]["active_addresses"] = None
    result["on_chain_data"]["exchange_inflow_btc"] = None
    result["on_chain_data"]["exchange_outflow_btc"] = None
    result["on_chain_data"]["dormant_supply_ratio"] = None
    result["on_chain_data"]["whale_movement_note"] = (
        "TODO: integrate Glassnode/CryptoQuant/Santiment for exchange flows, dormant supply, whale movements."
    )

    fng = sentiment.get("fear_greed")
    if isinstance(fng, dict):
        rows = fng.get("data")
        if isinstance(rows, list) and rows and isinstance(rows[0], dict):
            result["sentiment_data"]["fear_greed_value"] = parse_float(rows[0].get("value"))
            result["sentiment_data"]["fear_greed_classification"] = rows[0].get("value_classification")
    result["sentiment_data"]["social_sentiment_score"] = None
    result["sentiment_data"]["social_volume"] = None
    result["sentiment_data"]["news_sentiment_score"] = None
    result["sentiment_data"]["source"] = "alternative_fng"
    result["sentiment_data"]["as_of"] = now_iso()

    btc_series = macro_series.get("btc", pd.Series(dtype=float))
    spx_series = macro_series.get("spx", pd.Series(dtype=float))
    gld_series = macro_series.get("gld", pd.Series(dtype=float))
    qqq_series = macro_series.get("qqq", pd.Series(dtype=float))
    result["macro_data"]["corr_btc_spx"] = compute_correlation(btc_series, spx_series, config.correlation_window)
    result["macro_data"]["corr_btc_gold"] = compute_correlation(btc_series, gld_series, config.correlation_window)
    result["macro_data"]["corr_btc_qqq"] = compute_correlation(btc_series, qqq_series, config.correlation_window)
    result["macro_data"]["etf_net_flow_usd"] = None
    result["macro_data"]["etf_flow_note"] = (
        "TODO: integrate reliable ETF flow feed (e.g., issuer reports/paid aggregators) for robust daily net flows."
    )
    result["macro_data"]["source"] = "coingecko+fred"
    result["macro_data"]["as_of"] = now_iso()

    oi_val = result["derivatives_data"]["open_interest_usd"]
    funding_val = result["derivatives_data"]["funding_rate"]
    spread_pct = result["liquidity_data"]["spread_pct"]
    outflow = result["on_chain_data"]["exchange_outflow_btc"]
    inflow = result["on_chain_data"]["exchange_inflow_btc"]
    result["signals"]["high_open_interest"] = (
        bool(oi_val > config.high_open_interest_threshold) if isinstance(oi_val, float) else None
    )
    result["signals"]["extreme_funding"] = (
        bool(abs(funding_val) > config.extreme_funding_abs_threshold) if isinstance(funding_val, float) else None
    )
    result["signals"]["exchange_outflow_bullish"] = (
        bool(outflow > inflow) if isinstance(outflow, float) and isinstance(inflow, float) else None
    )
    result["signals"]["low_liquidity_warning"] = (
        bool(spread_pct > config.low_liquidity_spread_threshold_pct) if isinstance(spread_pct, float) else None
    )
    result["signals"]["volume_spike"] = result["volume_data"]["volume_spike_detected"]


def render_console_summary(result: dict[str, Any]) -> None:
    """Print a concise human-readable summary for operators."""
    print("\n=== Bitcoin Market Intelligence Summary ===")
    print(f"Timestamp: {result['timestamp']}")
    print(f"BTC Price: {result['price_data']['spot_price_usd']}")
    print(f"24h Volume (USD): {result['volume_data']['volume_24h_usd']}")
    print(f"Spread (%): {result['liquidity_data']['spread_pct']}")
    print(f"Open Interest: {result['derivatives_data']['open_interest_usd']}")
    print(f"Funding Rate: {result['derivatives_data']['funding_rate']}")
    print(f"Recent Liquidations (USD): {result['derivatives_data']['recent_liquidations_usd']}")
    print(
        "Exchange Flow Signal: "
        f"{result['signals']['exchange_outflow_bullish']} (None means unavailable source)"
    )
    print(f"Hash Rate: {result['on_chain_data']['hash_rate']}")
    print(
        "Fear & Greed: "
        f"{result['sentiment_data']['fear_greed_value']} ({result['sentiment_data']['fear_greed_classification']})"
    )
    print(
        "ETF Flow Summary: "
        f"{result['macro_data']['etf_net_flow_usd']} ({result['macro_data']['etf_flow_note']})"
    )
    print("Interpretation notes:")
    print(
        f"- Liquidity warning: {result['signals']['low_liquidity_warning']}, "
        f"volume spike: {result['signals']['volume_spike']}, "
        f"extreme funding: {result['signals']['extreme_funding']}."
    )


def save_outputs(result: dict[str, Any], output_dir: Path, save_csv: bool) -> tuple[Path, Path | None]:
    """
    Write timestamped JSON and optional flattened CSV (same UTC stem for both).
    Logs paths before writing; raises on failure so callers can log via exception handler.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    json_path = output_dir / f"btc_market_intel_{ts}.json"
    csv_path: Path | None = output_dir / f"btc_market_intel_{ts}.csv" if save_csv else None

    result["output_file_timestamp_utc"] = ts
    logging.info("Writing JSON snapshot: %s", json_path.resolve())
    with json_path.open("w", encoding="utf-8") as fp:
        json.dump(result, fp, indent=2, ensure_ascii=True)
    logging.info("Wrote JSON (%s bytes)", json_path.stat().st_size)

    if save_csv and csv_path is not None:
        try:
            logging.info("Writing CSV snapshot: %s", csv_path.resolve())
            flat = pd.json_normalize(result, sep=".")
            flat.to_csv(csv_path, index=False)
            logging.info("Wrote CSV (%s rows, %s bytes)", len(flat), csv_path.stat().st_size)
        except Exception as exc:
            logging.exception("CSV write failed (JSON already saved): %s", exc)
            csv_path = None
    return json_path, csv_path


def parse_args() -> argparse.Namespace:
    """Parse CLI arguments."""
    parser = argparse.ArgumentParser(description="Collect multi-layer BTC market intelligence.")
    parser.add_argument("--output-dir", default="outputs", help="Directory for JSON/CSV outputs.")
    parser.add_argument("--no-csv", action="store_true", help="Disable CSV output.")
    parser.add_argument("--log-level", default="INFO", help="Logging level, e.g. INFO or DEBUG.")
    parser.add_argument(
        "--timeout-seconds",
        type=float,
        default=12.0,
        help="Per-request HTTP timeout (default: 12).",
    )
    parser.add_argument(
        "--retry-count",
        type=int,
        default=3,
        help="Max attempts per URL for transient errors (429/5xx/network); default 3.",
    )
    parser.add_argument(
        "--max-runtime-seconds",
        type=float,
        default=None,
        help="Optional soft cap: stop issuing new HTTP requests after this many seconds.",
    )
    return parser.parse_args()


def main() -> None:
    """Program entrypoint."""
    load_dotenv()
    args = parse_args()
    deadline: float | None = None
    if args.max_runtime_seconds is not None and args.max_runtime_seconds > 0:
        deadline = time.monotonic() + float(args.max_runtime_seconds)

    config = AppConfig(
        output_dir=Path(args.output_dir),
        save_csv=not args.no_csv,
        log_level=args.log_level,
        timeout_seconds=float(args.timeout_seconds),
        max_retries=max(1, int(args.retry_count)),
        run_deadline_monotonic=deadline,
    )
    setup_logging(config.log_level)
    logging.info("Starting Bitcoin Market Intelligence Collector")
    if deadline is not None:
        logging.info("Soft max runtime: %.1fs from start", args.max_runtime_seconds)

    result = init_category_schema()
    source_health: dict[str, SourceHealth] = result["source_health"]

    binance_market: dict[str, Any] = {}
    pair_volumes: dict[str, float] = {}
    coingecko: dict[str, Any] = {}
    derivatives: dict[str, Any] = {}
    onchain: dict[str, Any] = {}
    sentiment: dict[str, Any] = {}
    macro_series: dict[str, pd.Series] = {
        "btc": pd.Series(dtype=float),
        "spx": pd.Series(dtype=float),
        "gld": pd.Series(dtype=float),
        "qqq": pd.Series(dtype=float),
    }

    try:
        with httpx.Client() as client:
            binance_market = fetch_binance_spot_market(client, config, source_health)
            coinbase_market = fetch_coinbase_spot_market(client, config, source_health)
            binance_market["coinbase_ticker"] = coinbase_market.get("ticker")
            binance_market["coinbase_klines"] = coinbase_market.get("klines")
            binance_market["coinbase_klines_15m"] = coinbase_market.get("klines_15m")
            binance_market["coinbase_depth"] = coinbase_market.get("depth")
            binance_market["coinbase_trades"] = coinbase_market.get("trades")
            pair_volumes = fetch_binance_pair_volumes(client, config, source_health)
            coingecko = fetch_coingecko_market(client, config, source_health)
            derivatives = fetch_binance_derivatives(client, config, source_health)
            onchain = fetch_blockchain_com_onchain(client, config, source_health)
            sentiment = fetch_fear_greed(client, config, source_health)

            macro_series = {
                "btc": fetch_coingecko_btc_series(client, config, source_health),
                "spx": fetch_fred_series(client, "SP500", "fred_sp500", config, source_health),
                "gld": fetch_fred_series(client, "GOLDPMGBD228NLBM", "fred_gold", config, source_health),
                "qqq": fetch_fred_series(client, "NASDAQCOM", "fred_nasdaq", config, source_health),
            }

        normalize_and_compute(
            result=result,
            binance_market=binance_market,
            pair_volumes=pair_volumes,
            coingecko=coingecko,
            derivatives=derivatives,
            onchain=onchain,
            sentiment=sentiment,
            macro_series=macro_series,
            config=config,
        )

        # Optional interpretation layer: trading signal engine
        try:
            from signal_engine import SignalEngineConfig, generate_signal

            result["signal_engine_output"] = generate_signal(result, SignalEngineConfig())
        except Exception as exc:  # noqa: BLE001
            result["signal_engine_error"] = str(exc)

        for source_name, health in source_health.items():
            if health.get("status") == "error":
                logging.warning("Source failed: %s - %s", source_name, health.get("message"))
    except Exception as exc:
        logging.exception("Collection or compute failed: %s", exc)
        result["run_error"] = str(exc)

    finally:
        try:
            json_path, csv_path = save_outputs(result, config.output_dir, config.save_csv)
            logging.info("Outputs: JSON=%s", json_path.resolve())
            if csv_path is not None:
                logging.info("Outputs: CSV=%s", csv_path.resolve())
            else:
                logging.warning("CSV not written (disabled, failed, or skipped).")
        except Exception as exc:
            logging.exception("Failed to write JSON output: %s", exc)
        try:
            render_console_summary(result)
        except Exception as exc:
            logging.exception("Console summary failed: %s", exc)
        logging.info("Collection complete")


if __name__ == "__main__":
    main()
