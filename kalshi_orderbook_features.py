from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

from event_target_parser import ParsedHourlyTarget
from kalshi_client import NormalizedMarket, liquidity_score, mid_prob


@dataclass(frozen=True)
class OrderbookGuardrailConfig:
    max_spread: float = 0.08
    min_liquidity_score: float = 0.50


@dataclass
class OrderbookFeatures:
    yes_bid: float | None
    yes_ask: float | None
    no_bid: float | None
    no_ask: float | None
    bid_ask_spread: float
    mid_price: float | None
    implied_yes_probability: float | None
    implied_no_probability: float | None
    orderbook_depth: float
    liquidity_score: float
    volume: float | None
    open_interest: float | None
    yes_no_imbalance: float | None
    recent_price_change: float | None
    time_to_expiry_minutes: float


def _sum_depth(orderbook_raw: dict[str, Any] | None, key: str, top_n: int = 5) -> float:
    if not orderbook_raw:
        return 0.0
    levels = orderbook_raw.get(key) or []
    total = 0.0
    for level in levels[:top_n]:
        if isinstance(level, (list, tuple)) and len(level) >= 2:
            try:
                total += float(level[1])
            except (TypeError, ValueError):
                continue
        elif isinstance(level, dict):
            try:
                total += float(level.get("quantity") or level.get("count") or 0)
            except (TypeError, ValueError):
                continue
    return total


def extract_orderbook_features(
    market: NormalizedMarket,
    parsed: ParsedHourlyTarget,
    orderbook_raw: dict[str, Any] | None = None,
) -> OrderbookFeatures:
    """Normalize Kalshi orderbook / top-of-book into decision features."""
    yes_bid = market.yes_bid
    yes_ask = market.yes_ask
    no_bid = market.no_bid
    no_ask = market.no_ask

    if orderbook_raw:
        yes_levels = orderbook_raw.get("yes") or []
        no_levels = orderbook_raw.get("no") or []
        if yes_levels and isinstance(yes_levels[0], (list, tuple)):
            try:
                yes_bid = float(yes_levels[0][0]) if yes_levels else yes_bid
            except (TypeError, ValueError, IndexError):
                pass
        if no_levels and isinstance(no_levels[0], (list, tuple)):
            try:
                no_bid = float(no_levels[0][0]) if no_levels else no_bid
            except (TypeError, ValueError, IndexError):
                pass

    if yes_bid is not None and yes_ask is not None:
        spread = max(0.0, yes_ask - yes_bid)
    else:
        spread = 1.0

    yes_mid = mid_prob(yes_bid, yes_ask, market.last_price)
    no_mid = mid_prob(no_bid, no_ask, None)
    if no_mid is None and yes_mid is not None:
        no_mid = max(0.0, min(1.0, 1.0 - yes_mid))
    elif yes_mid is None and no_mid is not None:
        yes_mid = max(0.0, min(1.0, 1.0 - no_mid))

    depth = _sum_depth(orderbook_raw, "yes") + _sum_depth(orderbook_raw, "no")
    base_liq = liquidity_score(
        yes_bid=yes_bid,
        yes_ask=yes_ask,
        volume=market.volume,
        open_interest=market.open_interest,
    )
    depth_bonus = min(0.10, math.log1p(depth) / math.log1p(1000.0)) if depth > 0 else 0.0
    liq = float(max(0.0, min(1.0, base_liq + depth_bonus)))

    imbalance: float | None = None
    if yes_bid is not None and no_bid is not None:
        imbalance = max(-1.0, min(1.0, yes_bid - no_bid))

    recent_change: float | None = None
    raw = market.raw or {}
    prev = raw.get("previous_price_dollars") or raw.get("previous_price")
    if prev is not None and market.last_price is not None:
        try:
            recent_change = float(market.last_price) - float(prev)
        except (TypeError, ValueError):
            recent_change = None

    return OrderbookFeatures(
        yes_bid=yes_bid,
        yes_ask=yes_ask,
        no_bid=no_bid,
        no_ask=no_ask,
        bid_ask_spread=spread,
        mid_price=yes_mid,
        implied_yes_probability=yes_mid,
        implied_no_probability=no_mid,
        orderbook_depth=depth,
        liquidity_score=liq,
        volume=market.volume,
        open_interest=market.open_interest,
        yes_no_imbalance=imbalance,
        recent_price_change=recent_change,
        time_to_expiry_minutes=parsed.time_to_expiry_minutes,
    )


def orderbook_quality_adjustment(
    features: OrderbookFeatures,
    cfg: OrderbookGuardrailConfig | None = None,
) -> float:
    """Return confidence multiplier in [0.85, 1.05] from spread and liquidity."""
    cfg = cfg or OrderbookGuardrailConfig()
    spread_penalty = max(0.0, features.bid_ask_spread - 0.03) / max(cfg.max_spread, 1e-9)
    liq_bonus = max(0.0, features.liquidity_score - cfg.min_liquidity_score)
    adj = 1.0 - 0.10 * min(1.0, spread_penalty) + 0.05 * min(1.0, liq_bonus / 0.5)
    return float(max(0.85, min(1.05, adj)))


def orderbook_guardrails(
    features: OrderbookFeatures,
    cfg: OrderbookGuardrailConfig | None = None,
) -> list[str]:
    """Return warnings when orderbook quality fails guardrails."""
    cfg = cfg or OrderbookGuardrailConfig()
    warnings: list[str] = []
    if features.implied_yes_probability is None and features.implied_no_probability is None:
        warnings.append("missing market quotes; cannot compute edge")
    if features.bid_ask_spread > cfg.max_spread:
        warnings.append(
            f"spread {features.bid_ask_spread:.3f} exceeds max {cfg.max_spread:.3f}"
        )
    if features.liquidity_score < cfg.min_liquidity_score:
        warnings.append(
            f"liquidity score {features.liquidity_score:.2f} below min {cfg.min_liquidity_score:.2f}"
        )
    return warnings


__all__ = [
    "OrderbookFeatures",
    "OrderbookGuardrailConfig",
    "extract_orderbook_features",
    "orderbook_quality_adjustment",
    "orderbook_guardrails",
]
