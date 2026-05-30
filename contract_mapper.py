from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Literal

from kalshi_client import NormalizedMarket, is_btc_related_text

TargetType = Literal[
    "above_threshold",
    "below_threshold",
    "range_bound",
    "daily_close",
    "weekly_close",
    "unknown",
]

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
RANGE_RE = re.compile(
    r"\b(between|range|within)\b",
    re.IGNORECASE,
)
DAILY_RE = re.compile(
    r"\b(daily|end of day|eod|close of day|4\s*pm|market close)\b",
    re.IGNORECASE,
)
WEEKLY_RE = re.compile(
    r"\b(weekly|week ending|week of)\b",
    re.IGNORECASE,
)


@dataclass
class ParsedContract:
    ticker: str
    target_type: TargetType
    threshold_price: float | None
    threshold_price_high: float | None
    direction: Literal["yes", "no", "neutral"] | None
    expiration_time: datetime | None
    horizon_hours: float | None
    compatible_probability_key: str
    mapping_confidence: float
    parse_warnings: list[str] = field(default_factory=list)
    contract_title: str = ""


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


def _is_year_like(val: float) -> bool:
    return 2015 <= val <= 2035 and val == int(val)


def _strike_from_ticker(ticker: str) -> float | None:
    m = re.search(r"-T([\d.]+)$", ticker, re.IGNORECASE)
    if not m:
        return None
    try:
        val = float(m.group(1))
    except ValueError:
        return None
    if val > 1000:
        return val
    return None


def _extract_prices(text: str, *, ticker: str = "") -> list[float]:
    prices: list[float] = []
    strike = _strike_from_ticker(ticker)
    if strike is not None:
        prices.append(strike)

    for m in PRICE_RE.finditer(text):
        raw = m.group(0)
        p = _parse_price_token(m.group(1), raw)
        if p is not None and p > 100 and not _is_year_like(p):
            prices.append(p)
    return prices


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


def _horizon_hours(expiration: datetime | None) -> float | None:
    if expiration is None:
        return None
    now = datetime.now(UTC)
    return max(0.0, (expiration - now).total_seconds() / 3600.0)


def _pick_horizon_key(horizon_hours: float | None, target_type: TargetType) -> str:
    h = horizon_hours if horizon_hours is not None else 24.0
    use_12h = abs(h - 12.0) < abs(h - 24.0)
    if target_type == "range_bound":
        return "range_bound_12h" if use_12h else "range_bound_24h"
    if target_type == "below_threshold":
        return "down_move_12h" if use_12h else "down_move_24h"
    return "up_move_12h" if use_12h else "up_move_24h"


def is_btc_market(market: NormalizedMarket | dict[str, Any]) -> bool:
    if isinstance(market, NormalizedMarket):
        raw = market.raw or {}
        return is_btc_related_text(
            market.title,
            market.ticker,
            market.event_ticker,
            raw.get("subtitle"),
            raw.get("yes_sub_title"),
            raw.get("no_sub_title"),
        )
    return is_btc_related_text(
        market.get("title"),
        market.get("subtitle"),
        market.get("yes_sub_title"),
        market.get("ticker"),
        market.get("event_ticker"),
    )


def parse_contract(
    market: NormalizedMarket,
    *,
    spot_price_usd: float | None = None,
) -> ParsedContract | None:
    if not is_btc_market(market):
        return None

    raw = market.raw or {}
    text_parts = [
        market.title,
        str(raw.get("yes_sub_title", "")),
        str(raw.get("no_sub_title", "")),
        str(raw.get("rules_primary", "")),
        str(raw.get("rules_secondary", "")),
    ]
    text = " ".join(p for p in text_parts if p).strip()
    prices = _extract_prices(text, ticker=market.ticker)
    expiration = _parse_dt(market.close_time)
    horizon = _horizon_hours(expiration)
    warnings: list[str] = []

    target_type: TargetType = "unknown"
    threshold: float | None = None
    threshold_high: float | None = None
    direction: Literal["yes", "no", "neutral"] | None = "yes"
    confidence = 0.35

    if RANGE_RE.search(text) and len(prices) >= 2:
        target_type = "range_bound"
        threshold, threshold_high = min(prices[0], prices[1]), max(prices[0], prices[1])
        confidence = 0.75
    elif ABOVE_RE.search(text) and prices:
        target_type = "above_threshold"
        threshold = prices[0]
        direction = "yes"
        confidence = 0.8
    elif BELOW_RE.search(text) and prices:
        target_type = "below_threshold"
        threshold = prices[0]
        direction = "yes"
        confidence = 0.8
    elif WEEKLY_RE.search(text):
        target_type = "weekly_close"
        if prices:
            threshold = prices[0]
        warnings.append("weekly close contract mapped to coarse 24h move proxy")
        confidence = 0.55
    elif DAILY_RE.search(text):
        target_type = "daily_close"
        if prices:
            threshold = prices[0]
        confidence = 0.65
    elif prices:
        target_type = "above_threshold"
        threshold = prices[0]
        warnings.append("inferred above-threshold from price in title without explicit direction")
        confidence = 0.5
    else:
        warnings.append("could not parse contract semantics from title")

    prob_key = _pick_horizon_key(horizon, target_type)
    if target_type == "daily_close":
        prob_key = _pick_horizon_key(horizon, "above_threshold")
    if target_type == "weekly_close":
        prob_key = "up_move_24h"

    if spot_price_usd and threshold and spot_price_usd > 0:
        rel = abs(threshold - spot_price_usd) / spot_price_usd
        if rel > 0.05:
            warnings.append(
                f"strike ${threshold:,.0f} is {rel:.1%} from spot ${spot_price_usd:,.0f}; "
                "model band semantics may not match contract"
            )
            confidence *= 0.85

    if target_type == "unknown":
        confidence = min(confidence, 0.4)

    return ParsedContract(
        ticker=market.ticker,
        target_type=target_type,
        threshold_price=threshold,
        threshold_price_high=threshold_high,
        direction=direction,
        expiration_time=expiration,
        horizon_hours=horizon,
        compatible_probability_key=prob_key,
        mapping_confidence=float(max(0.0, min(1.0, confidence))),
        parse_warnings=warnings,
        contract_title=market.title,
    )


def target_label(parsed: ParsedContract) -> str:
    parts = [parsed.target_type]
    if parsed.threshold_price is not None:
        parts.append(f"{parsed.threshold_price:.0f}")
    if parsed.threshold_price_high is not None:
        parts.append(f"to_{parsed.threshold_price_high:.0f}")
    if parsed.horizon_hours is not None:
        parts.append(f"{parsed.horizon_hours:.0f}h")
    return "_".join(parts)


def model_probability_for_contract(
    parsed: ParsedContract,
    *,
    rule_probs: dict[str, float],
    p_ml: dict[str, float] | None,
    fused: dict[str, float],
    spot_price_usd: float,
    w_rule: float = 0.55,
    w_ml: float = 0.45,
) -> tuple[float, list[str]]:
    """Return model YES probability for this Kalshi contract and explanatory warnings."""
    warnings = list(parsed.parse_warnings)

    key = parsed.compatible_probability_key
    p_from_rule = rule_probs.get(key)
    if p_from_rule is not None:
        p_rule_val = float(p_from_rule)
    else:
        p_rule_val = None

    # Fused directional proxy by target type
    if parsed.target_type == "below_threshold":
        p_fused = float(fused.get("down", 1 / 3))
        warnings.append("using fused down probability as YES proxy for below-threshold contract")
    elif parsed.target_type == "range_bound":
        p_fused = float(fused.get("range", 1 / 3))
        warnings.append("rule range band is ±0.5%; ML labels use ±1% — not exact Kalshi range match")
    elif parsed.target_type in ("above_threshold", "daily_close", "weekly_close"):
        p_fused = float(fused.get("up", 1 / 3))
        if parsed.target_type != "above_threshold":
            warnings.append(f"{parsed.target_type} mapped to fused up-move proxy")
        else:
            warnings.append("Kalshi strike contract uses fused up-move proxy (not exact strike probability)")
    else:
        p_fused = max(fused.values()) if fused else 1 / 3
        warnings.append("unknown contract type; using max fused outcome as weak proxy")

    if p_rule_val is not None and p_ml is not None:
        p_ml_key = _ml_key_for_rule_key(key)
        p_ml_val = float(p_ml.get(p_ml_key, p_fused)) if p_ml_key else p_fused
        wr, wm = w_rule, w_ml
        s = wr + wm
        if s > 0:
            wr, wm = wr / s, wm / s
        model_p = wr * p_rule_val + wm * p_ml_val
    elif p_rule_val is not None:
        model_p = p_rule_val
    else:
        model_p = p_fused

    return float(max(0.0, min(1.0, model_p))), warnings


def _ml_key_for_rule_key(rule_key: str) -> str:
    if "up" in rule_key:
        return "up"
    if "down" in rule_key:
        return "down"
    if "range" in rule_key:
        return "range"
    return "up"


__all__ = [
    "ParsedContract",
    "TargetType",
    "is_btc_market",
    "parse_contract",
    "target_label",
    "model_probability_for_contract",
]
