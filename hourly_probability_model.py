from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

from event_target_parser import Direction, ParsedHourlyTarget
from kalshi_orderbook_features import OrderbookFeatures, orderbook_quality_adjustment
from signal_engine import SignalEngineConfig, compute_kalshi_probabilities, norm_cdf, sigmoid

HORIZON_MINUTES: dict[str, float] = {
    "15m": 15.0,
    "30m": 30.0,
    "60m": 60.0,
    "4h": 240.0,
    "24h": 1440.0,
}

HORIZON_BOUNDARIES = (22.5, 37.5, 150.0, 840.0)
MINUTES_PER_YEAR = 525_600.0  # 365 * 24 * 60


@dataclass(frozen=True)
class FusionWeights:
    strike_distance: float = 0.40
    ml: float = 0.30
    rule: float = 0.20
    orderbook: float = 0.10


def select_best_horizon(time_to_expiry_minutes: float) -> str:
    """
    Select model horizon from time remaining until settlement.

    Boundaries at midpoints: 22.5, 45, 150, 840 minutes.
    Examples: 12m→15m, 42m→60m, 192m→4h, 1080m→24h.
    """
    t = max(0.0, float(time_to_expiry_minutes))
    if t <= HORIZON_BOUNDARIES[0]:
        return "15m"
    if t <= HORIZON_BOUNDARIES[1]:
        return "30m"
    if t <= HORIZON_BOUNDARIES[2]:
        return "60m"
    if t <= HORIZON_BOUNDARIES[3]:
        return "4h"
    return "24h"


def horizon_minutes(horizon_key: str) -> float:
    return HORIZON_MINUTES.get(horizon_key, 60.0)


def estimate_probability_above_strike(
    current_price: float,
    strike_price: float,
    horizon_minutes: float,
    annualized_volatility: float,
    directional_bias: float,
    rule_probability_up: float,
    ml_probability_up: float,
    orderflow_adjustment: float,
    *,
    tilt_k: float = 2.5,
) -> tuple[float, list[str]]:
    """
    Transparent strike probability using lognormal CDF + directional blend.

    Steps:
    1. Scale annualized vol to horizon: sigma_h = vol * sqrt(horizon_minutes / 525600)
    2. Drift from composite bias: mu_h = tilt_k * directional_bias * sigma_h (bounded)
    3. P(S > K) = 1 - Phi((ln(K/S) - mu_h) / sigma_h)
    4. Blend with rule/ML directional probability when strike is near spot
    5. Apply small orderflow adjustment
    """
    drivers: list[str] = []
    s0 = max(current_price, 1e-9)
    k = max(strike_price, 1e-9)
    vol = max(annualized_volatility, 0.05)
    hm = max(horizon_minutes, 1.0)

    sigma_h = vol * math.sqrt(hm / MINUTES_PER_YEAR)
    sigma_h = max(sigma_h, 1e-6)

    bias = max(-1.0, min(1.0, directional_bias))
    mu_h = tilt_k * bias * sigma_h
    mu_h = max(-sigma_h, min(sigma_h, mu_h))

    z = (math.log(k / s0) - mu_h) / sigma_h
    cdf_prob = 1.0 - norm_cdf(z)

    rel_dist = abs(k - s0) / s0
    if rel_dist < 0.02:
        dir_prob = 0.5 * rule_probability_up + 0.5 * ml_probability_up
        p_strike = 0.7 * cdf_prob + 0.3 * dir_prob
        drivers.append(
            f"Strike within 2% of spot; blended CDF ({cdf_prob:.3f}) with directional ({dir_prob:.3f})."
        )
    else:
        p_strike = cdf_prob
        drivers.append(
            f"Lognormal CDF: spot ${s0:,.0f}, strike ${k:,.0f}, sigma_h={sigma_h:.4f}, P(above)={cdf_prob:.3f}."
        )

    p_strike += orderflow_adjustment
    p_strike = max(0.01, min(0.99, p_strike))
    if orderflow_adjustment != 0:
        drivers.append(f"Orderflow adjustment: {orderflow_adjustment:+.3f}.")

    return float(p_strike), drivers


def _orderflow_adjustment(snapshot: dict[str, Any]) -> float:
    """Map snapshot liquidity imbalance to [-0.05, 0.05] probability adjustment."""
    imb = snapshot.get("liquidity_data") or {}
    ratio = imb.get("bid_ask_volume_ratio")
    if ratio is None:
        imbalance = imb.get("order_book_imbalance")
        if imbalance is not None:
            try:
                return max(-0.05, min(0.05, float(imbalance) * 0.05))
            except (TypeError, ValueError):
                return 0.0
        return 0.0
    try:
        r = float(ratio)
    except (TypeError, ValueError):
        return 0.0
    if r > 1.0:
        return min(0.05, (r - 1.0) * 0.02)
    if r < 1.0:
        return max(-0.05, (r - 1.0) * 0.02)
    return 0.0


def _horizon_fit_score(selected_horizon: str, time_to_expiry_minutes: float) -> float:
    target = horizon_minutes(selected_horizon)
    return max(0.0, 1.0 - abs(time_to_expiry_minutes - target) / max(target, 1.0))


def compute_confidence(
    *,
    rule_confidence: float,
    ml_available: bool,
    mapping_confidence: float,
    ob_features: OrderbookFeatures,
    selected_horizon: str,
    time_to_expiry_minutes: float,
    ml_horizon_penalty: bool = False,
) -> float:
    """Combine rule, mapping, orderbook, and horizon-fit into [0, 1] confidence."""
    base = float(rule_confidence)
    if not ml_available:
        base *= 0.92
    if ml_horizon_penalty:
        base *= 0.85
    base *= mapping_confidence
    base *= orderbook_quality_adjustment(ob_features)
    base *= 0.5 + 0.5 * _horizon_fit_score(selected_horizon, time_to_expiry_minutes)
    return float(max(0.0, min(1.0, base)))


def fuse_hourly_probability(
    p_strike_above: float,
    p_rule_up: float,
    p_ml_up: float,
    ob_adjustment: float,
    direction: Direction,
    weights: FusionWeights | None = None,
) -> tuple[float, float, list[str]]:
    """
    Blend strike-distance, rule, ML, and orderbook into model YES/NO probabilities.

    For above contracts: YES = P(price above strike).
    For below contracts: YES = P(price below strike) = 1 - P(above).
    """
    weights = weights or FusionWeights()
    w_sum = weights.strike_distance + weights.ml + weights.rule + weights.orderbook
    if w_sum <= 0:
        ws = FusionWeights()
        w_sd, w_ml, w_rule, w_ob = ws.strike_distance, ws.ml, ws.rule, ws.orderbook
    else:
        w_sd = weights.strike_distance / w_sum
        w_ml = weights.ml / w_sum
        w_rule = weights.rule / w_sum
        w_ob = weights.orderbook / w_sum

    p_above = (
        w_sd * p_strike_above
        + w_rule * p_rule_up
        + w_ml * p_ml_up
        + w_ob * (0.5 + ob_adjustment)
    )
    p_above = max(0.01, min(0.99, p_above))

    if direction == "below":
        model_yes = 1.0 - p_above
        drivers = [
            f"Below contract: model YES = P(below strike) = {model_yes:.3f}.",
            f"Fusion weights: strike={w_sd:.0%}, rule={w_rule:.0%}, ML={w_ml:.0%}, OB={w_ob:.0%}.",
        ]
    else:
        model_yes = p_above
        drivers = [
            f"Above contract: model YES = P(above strike) = {model_yes:.3f}.",
            f"Fusion weights: strike={w_sd:.0%}, rule={w_rule:.0%}, ML={w_ml:.0%}, OB={w_ob:.0%}.",
        ]

    model_no = 1.0 - model_yes
    return float(model_yes), float(model_no), drivers


def build_hourly_model_probs(
    *,
    snapshot: dict[str, Any],
    parsed: ParsedHourlyTarget,
    rule_out: dict[str, Any],
    p_ml: dict[str, float] | None,
    ob_features: OrderbookFeatures,
    weights: FusionWeights | None = None,
    signal_cfg: SignalEngineConfig | None = None,
) -> dict[str, Any]:
    """Full pipeline: horizon select → strike prob → fuse → confidence."""
    signal_cfg = signal_cfg or SignalEngineConfig()
    selected = select_best_horizon(parsed.time_to_expiry_minutes)
    hm = horizon_minutes(selected)
    horizon_hours = hm / 60.0

    spot = float((snapshot.get("price_data") or {}).get("spot_price_usd") or 0.0)
    vol = float((snapshot.get("price_data") or {}).get("rolling_volatility_annualized") or 0.28)
    composite = float(rule_out.get("signal_score") or 0.0)
    rule_conf = float(rule_out.get("confidence") or 0.0)

    rule_horizon = compute_kalshi_probabilities(
        composite,
        snapshot,
        signal_cfg,
        rule_conf,
        hm / 60.0,
    )
    h_key = hm / 60.0
    key_up = f"up_move_{h_key}h"
    key_down = f"down_move_{h_key}h"
    p_rule_up = float(rule_horizon.get(key_up, rule_horizon.get("up_move_1h", 0.33)))
    p_rule_down = float(rule_horizon.get(key_down, rule_horizon.get("down_move_1h", 0.33)))

    p_ml_up = float((p_ml or {}).get("up", 0.33))
    ml_penalty = selected != "24h"
    orderflow_adj = _orderflow_adjustment(snapshot)
    ob_adj = max(-0.05, min(0.05, orderflow_adj))

    p_strike_above, strike_drivers = estimate_probability_above_strike(
        current_price=spot,
        strike_price=parsed.strike_price,
        horizon_minutes=hm,
        annualized_volatility=vol,
        directional_bias=composite,
        rule_probability_up=p_rule_up,
        ml_probability_up=p_ml_up,
        orderflow_adjustment=orderflow_adj,
        tilt_k=signal_cfg.tilt_k,
    )

    model_yes, model_no, fusion_drivers = fuse_hourly_probability(
        p_strike_above,
        p_rule_up,
        p_ml_up,
        ob_adj,
        parsed.direction,
        weights,
    )

    confidence = compute_confidence(
        rule_confidence=rule_conf,
        ml_available=p_ml is not None,
        mapping_confidence=parsed.mapping_confidence,
        ob_features=ob_features,
        selected_horizon=selected,
        time_to_expiry_minutes=parsed.time_to_expiry_minutes,
        ml_horizon_penalty=ml_penalty,
    )

    drivers = strike_drivers + fusion_drivers
    if ml_penalty and p_ml is not None:
        drivers.append("ML model trained at 24h; confidence penalized for shorter horizon.")

    return {
        "selected_horizon": selected,
        "horizon_minutes": hm,
        "model_yes_probability": model_yes,
        "model_no_probability": model_no,
        "p_strike_above": p_strike_above,
        "p_rule_up": p_rule_up,
        "p_rule_down": p_rule_down,
        "p_ml_up": p_ml_up,
        "confidence": confidence,
        "key_drivers": drivers,
        "ml_horizon_penalty": ml_penalty,
    }


__all__ = [
    "HORIZON_MINUTES",
    "FusionWeights",
    "select_best_horizon",
    "horizon_minutes",
    "estimate_probability_above_strike",
    "fuse_hourly_probability",
    "compute_confidence",
    "build_hourly_model_probs",
]
