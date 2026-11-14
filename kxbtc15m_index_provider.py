"""Settlement-index acquisition with honest provenance (paper-only).

Cascade (approved plan):
1. Explicit operator value (caller-supplied) → operator_supplied
2. Index file drop → file_drop
3. Kalshi market / event metadata fields when present → kalshi_api
4. Spot proxy (env or latest snapshot) → exchange_spot_proxy
5. Else unavailable
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

SettlementIndexSource = Literal[
    "cf_benchmarks",
    "kalshi_api",
    "exchange_spot_proxy",
    "operator_supplied",
    "file_drop",
    "fixture",
    "unavailable",
]

# Production / readiness edge evidence (fixtures excluded unless test gate set)
LIVE_EDGE_SOURCES = frozenset({"kalshi_api", "cf_benchmarks"})


@dataclass(frozen=True)
class SettlementIndexQuote:
    value: float | None
    source: SettlementIndexSource
    detail: str = ""


def counts_as_edge_evidence(
    source: str,
    *,
    allow_fixture: bool | None = None,
) -> bool:
    if allow_fixture is None:
        allow_fixture = os.environ.get("COMPASS_KXBTC15M_ALLOW_FIXTURE_EDGE", "").strip() in {
            "1",
            "true",
            "TRUE",
            "yes",
        }
    if source in LIVE_EDGE_SOURCES:
        return True
    if allow_fixture and source == "fixture":
        return True
    return False


def _parse_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        v = float(value)
    except (TypeError, ValueError):
        return None
    if v <= 0:
        return None
    return v


def from_operator_value(value: float | None) -> SettlementIndexQuote:
    if value is None:
        return SettlementIndexQuote(None, "unavailable", "no operator value")
    return SettlementIndexQuote(float(value), "operator_supplied", "env_or_cli_numeric")


def from_index_file(path: Path | None) -> SettlementIndexQuote:
    if path is None or not path.is_file():
        return SettlementIndexQuote(None, "unavailable", "index_file_missing")
    try:
        raw = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        return SettlementIndexQuote(None, "unavailable", f"index_file_error:{exc}")
    if isinstance(raw, (int, float)):
        v = _parse_float(raw)
        return SettlementIndexQuote(v, "file_drop" if v else "unavailable", str(path))
    for key in ("settlement_index", "cf_benchmarks_index", "index", "value", "price"):
        v = _parse_float(raw.get(key) if isinstance(raw, dict) else None)
        if v is not None:
            src: SettlementIndexSource = (
                "cf_benchmarks" if "cf" in key.lower() else "file_drop"
            )
            return SettlementIndexQuote(v, src, f"file:{path.name}:{key}")
    return SettlementIndexQuote(None, "unavailable", f"index_file_no_value:{path}")


def from_kalshi_market_raw(raw: dict[str, Any] | None) -> SettlementIndexQuote:
    """Pull settlement-like fields from a Kalshi market payload when present."""
    if not raw:
        return SettlementIndexQuote(None, "unavailable", "no_market_raw")
    for key in (
        "settlement_value",
        "floor_strike",
        "cap_strike",
        "yes_ask_dollars",  # not an index — skip below
    ):
        if key == "yes_ask_dollars":
            continue
        v = _parse_float(raw.get(key))
        # floor/cap are strikes, not index — only settlement_value counts as kalshi
        if key == "settlement_value" and v is not None:
            return SettlementIndexQuote(v, "kalshi_api", "market.settlement_value")
    # Some payloads nest index hints under functional_strike / custom_strike
    for key in ("functional_strike", "strike_price", "custom_strike"):
        v = _parse_float(raw.get(key))
        if v is not None and v > 1000:  # crude BTC-level filter
            return SettlementIndexQuote(v, "kalshi_api", f"market.{key}")
    return SettlementIndexQuote(None, "unavailable", "no_kalshi_index_fields")


def from_spot_proxy(value: float | None, *, detail: str = "spot_proxy") -> SettlementIndexQuote:
    v = _parse_float(value)
    if v is None:
        return SettlementIndexQuote(None, "unavailable", detail)
    return SettlementIndexQuote(v, "exchange_spot_proxy", detail)


def from_latest_snapshot(snapshots_dir: Path | None) -> SettlementIndexQuote:
    if snapshots_dir is None or not snapshots_dir.is_dir():
        return SettlementIndexQuote(None, "unavailable", "no_snapshots_dir")
    candidates = sorted(snapshots_dir.glob("btc_market_intel_*.json"))
    if not candidates:
        return SettlementIndexQuote(None, "unavailable", "no_snapshots")
    try:
        raw = json.loads(candidates[-1].read_text())
    except (OSError, json.JSONDecodeError) as exc:
        return SettlementIndexQuote(None, "unavailable", f"snapshot_error:{exc}")
    price = None
    if isinstance(raw, dict):
        pd = raw.get("price_data")
        if isinstance(pd, dict):
            price = (
                pd.get("spot_price_usd")
                or pd.get("ohlc_last_close_usd")
                or pd.get("price_usd")
                or pd.get("spot")
            )
        md = raw.get("market_data")
        if price is None and isinstance(md, dict):
            price = md.get("price_usd") or md.get("spot") or md.get("btc_price")
        if price is None:
            price = raw.get("btc_price") or raw.get("price_usd")
    return from_spot_proxy(_parse_float(price), detail=f"snapshot:{candidates[-1].name}")


def resolve_index_cascade(
    *,
    operator_value: float | None = None,
    index_file: Path | None = None,
    market_raw: dict[str, Any] | None = None,
    spot_proxy: float | None = None,
    snapshots_dir: Path | None = None,
) -> SettlementIndexQuote:
    """Apply approved cascade; first non-unavailable wins."""
    steps = [
        from_operator_value(operator_value) if operator_value is not None else None,
        from_index_file(index_file) if index_file is not None else None,
        from_kalshi_market_raw(market_raw),
        from_spot_proxy(spot_proxy) if spot_proxy is not None else None,
        from_latest_snapshot(snapshots_dir),
    ]
    for quote in steps:
        if quote is None:
            continue
        if quote.value is not None and quote.source != "unavailable":
            return quote
    return SettlementIndexQuote(None, "unavailable", "cascade_exhausted")


__all__ = [
    "SettlementIndexSource",
    "SettlementIndexQuote",
    "LIVE_EDGE_SOURCES",
    "counts_as_edge_evidence",
    "resolve_index_cascade",
    "from_operator_value",
    "from_index_file",
    "from_kalshi_market_raw",
    "from_spot_proxy",
]
