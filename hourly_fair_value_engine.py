from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from event_target_parser import ParsedHourlyTarget, format_target_time_edt
from kalshi_orderbook_features import OrderbookFeatures, OrderbookGuardrailConfig, orderbook_guardrails

Recommendation = Literal["BUY YES", "BUY NO", "NO TRADE"]


@dataclass(frozen=True)
class FairValueConfig:
    min_edge: float = 0.10
    min_confidence: float = 0.65
    max_spread: float = 0.08
    min_liquidity_score: float = 0.50
    min_time_to_expiry_minutes: float = 5.0
    min_mapping_confidence: float = 0.60
    # Paper-trial guards: block miscalibrated far-OTM BUY YES despite low confidence floor.
    # Tuned 2026-08-27: 0.80/1.5% yielded 0% actionable for 8 days; loosen to 0.85/2%.
    # BUY NO uses strike-distance only — high model NO on far-above strikes is expected.
    max_buy_yes_model_probability: float = 0.85
    max_buy_yes_strike_distance_pct: float = 0.02
    max_buy_no_strike_distance_pct: float = 0.02


def _clamp(x: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, float(x)))


def _otm_strike_distance_pct(
    *,
    direction: str,
    strike_price: float,
    spot_price: float,
) -> float | None:
    """Positive when the YES side is out-of-the-money relative to spot."""
    if spot_price <= 0:
        return None
    if direction == "above":
        return (strike_price - spot_price) / spot_price
    if direction == "below":
        return (spot_price - strike_price) / spot_price
    return None


def _buy_yes_strike_guard_ok(
    *,
    parsed: ParsedHourlyTarget,
    spot_price: float,
    cfg: FairValueConfig,
) -> bool:
    dist = _otm_strike_distance_pct(
        direction=parsed.direction,
        strike_price=parsed.strike_price,
        spot_price=spot_price,
    )
    if dist is None:
        return True
    return dist <= cfg.max_buy_yes_strike_distance_pct


def _buy_no_strike_guard_ok(
    *,
    parsed: ParsedHourlyTarget,
    spot_price: float,
    cfg: FairValueConfig,
) -> bool:
    # BUY NO only when YES is OTM/ATM within max distance — never when YES is ITM.
    # (Earlier flip-direction logic allowed near-ITM YES, which settled YES ~82%.)
    dist = _otm_strike_distance_pct(
        direction=parsed.direction,
        strike_price=parsed.strike_price,
        spot_price=spot_price,
    )
    if dist is None:
        return True
    return 0.0 <= dist <= cfg.max_buy_no_strike_distance_pct


def evaluate_contract(
    *,
    parsed: ParsedHourlyTarget,
    ob: OrderbookFeatures,
    model_yes: float,
    model_no: float,
    confidence: float,
    selected_horizon: str,
    current_btc_price: float,
    model_drivers: list[str] | None = None,
    cfg: FairValueConfig | None = None,
    timestamp: str | None = None,
) -> dict[str, Any]:
    """Compute YES/NO edge and conservative recommendation."""
    cfg = cfg or FairValueConfig()
    ob_cfg = OrderbookGuardrailConfig(
        max_spread=cfg.max_spread,
        min_liquidity_score=cfg.min_liquidity_score,
    )

    market_yes = ob.implied_yes_probability
    market_no = ob.implied_no_probability
    if market_yes is None and market_no is not None:
        market_yes = 1.0 - market_no
    if market_no is None and market_yes is not None:
        market_no = 1.0 - market_yes

    yes_edge: float | None = None
    no_edge: float | None = None
    if market_yes is not None:
        yes_edge = model_yes - market_yes
    if market_no is not None:
        no_edge = model_no - market_no

    warnings: list[str] = list(parsed.parse_warnings)
    warnings.extend(orderbook_guardrails(ob, ob_cfg))

    guardrail_fail = False
    if parsed.time_to_expiry_minutes < cfg.min_time_to_expiry_minutes:
        warnings.append(
            f"time to expiry {parsed.time_to_expiry_minutes:.1f}m below min "
            f"{cfg.min_time_to_expiry_minutes:.1f}m"
        )
        guardrail_fail = True
    if parsed.mapping_confidence < cfg.min_mapping_confidence:
        warnings.append(
            f"mapping confidence {parsed.mapping_confidence:.2f} below min "
            f"{cfg.min_mapping_confidence:.2f}"
        )
        guardrail_fail = True
    if confidence < cfg.min_confidence:
        warnings.append(f"confidence {confidence:.2f} below threshold {cfg.min_confidence:.2f}")
    if market_yes is None:
        guardrail_fail = True

    rec: Recommendation = "NO TRADE"
    buy_yes_ok = (
        not guardrail_fail
        and yes_edge is not None
        and yes_edge > cfg.min_edge
        and confidence >= cfg.min_confidence
        and ob.bid_ask_spread <= cfg.max_spread
        and ob.liquidity_score >= cfg.min_liquidity_score
        and model_yes <= cfg.max_buy_yes_model_probability
        and _buy_yes_strike_guard_ok(parsed=parsed, spot_price=current_btc_price, cfg=cfg)
    )
    buy_no_ok = (
        not guardrail_fail
        and no_edge is not None
        and no_edge > cfg.min_edge
        and confidence >= cfg.min_confidence
        and ob.bid_ask_spread <= cfg.max_spread
        and ob.liquidity_score >= cfg.min_liquidity_score
        and _buy_no_strike_guard_ok(parsed=parsed, spot_price=current_btc_price, cfg=cfg)
    )

    if buy_yes_ok:
        rec = "BUY YES"
    elif buy_no_ok:
        rec = "BUY NO"
    else:
        if model_yes > cfg.max_buy_yes_model_probability:
            warnings.append(
                f"model YES {model_yes:.2f} above max for BUY YES "
                f"{cfg.max_buy_yes_model_probability:.2f}"
            )
        dist_yes = _otm_strike_distance_pct(
            direction=parsed.direction,
            strike_price=parsed.strike_price,
            spot_price=current_btc_price,
        )
        if dist_yes is not None and dist_yes > cfg.max_buy_yes_strike_distance_pct:
            warnings.append(
                f"strike OTM distance {dist_yes * 100:.2f}% exceeds BUY YES max "
                f"{cfg.max_buy_yes_strike_distance_pct * 100:.2f}%"
            )
        if rec == "NO TRADE" and not any("below threshold" in w for w in warnings):
            if yes_edge is not None and yes_edge <= cfg.min_edge and no_edge is not None and no_edge <= cfg.min_edge:
                warnings.append("edge below minimum threshold; defaulting to NO TRADE")

    key_drivers: list[str] = list(model_drivers or [])
    if yes_edge is not None and market_yes is not None:
        if yes_edge > 0:
            key_drivers.append(
                f"Model YES probability is {yes_edge * 100:.0f} percentage points above market YES price."
            )
        elif no_edge is not None and no_edge > 0:
            key_drivers.append(
                f"Model NO probability is {no_edge * 100:.0f} percentage points above market NO price."
            )
    if ob.liquidity_score >= cfg.min_liquidity_score and ob.bid_ask_spread <= cfg.max_spread:
        key_drivers.append("Liquidity is acceptable and spread is within threshold.")

    rank_score = 0.0
    if rec == "BUY YES" and yes_edge is not None:
        rank_score = abs(yes_edge) * confidence
    elif rec == "BUY NO" and no_edge is not None:
        rank_score = abs(no_edge) * confidence

    from datetime import UTC, datetime

    ts = timestamp or datetime.now(UTC).isoformat()

    return {
        "timestamp": ts,
        "event_title": parsed.event_title,
        "contract_ticker": parsed.contract_ticker,
        "contract_title": parsed.contract_title,
        "target_time_edt": format_target_time_edt(parsed.target_time_edt),
        "time_to_expiry_minutes": round(parsed.time_to_expiry_minutes, 1),
        "current_btc_price": round(current_btc_price, 2),
        "strike_price": round(parsed.strike_price, 2),
        "direction": parsed.direction,
        "selected_horizon": selected_horizon,
        "market_yes_probability": None if market_yes is None else round(_clamp(market_yes), 4),
        "market_no_probability": None if market_no is None else round(_clamp(market_no), 4),
        "model_yes_probability": round(_clamp(model_yes), 4),
        "model_no_probability": round(_clamp(model_no), 4),
        "yes_edge": None if yes_edge is None else round(yes_edge, 4),
        "no_edge": None if no_edge is None else round(no_edge, 4),
        "confidence": round(_clamp(confidence), 4),
        "recommendation": rec,
        "liquidity_score": round(ob.liquidity_score, 4),
        "bid_ask_spread": round(ob.bid_ask_spread, 4),
        "mapping_confidence": round(parsed.mapping_confidence, 4),
        "key_drivers": key_drivers,
        "warnings": warnings,
        "rank_score": round(rank_score, 6),
    }


def rank_evaluations(evaluations: list[dict[str, Any]]) -> dict[str, Any]:
    """Bucket and rank contract evaluations."""
    buy_yes = sorted(
        [e for e in evaluations if e.get("recommendation") == "BUY YES"],
        key=lambda x: float(x.get("rank_score") or 0),
        reverse=True,
    )
    buy_no = sorted(
        [e for e in evaluations if e.get("recommendation") == "BUY NO"],
        key=lambda x: float(x.get("rank_score") or 0),
        reverse=True,
    )
    no_trade = sorted(
        [e for e in evaluations if e.get("recommendation") == "NO TRADE"],
        key=lambda x: max(
            abs(float(x.get("yes_edge") or 0)),
            abs(float(x.get("no_edge") or 0)),
        ),
        reverse=True,
    )
    return {
        "buy_yes": buy_yes,
        "buy_no": buy_no,
        "no_trade": no_trade,
        "all_contracts": evaluations,
        "counts": {
            "buy_yes": len(buy_yes),
            "buy_no": len(buy_no),
            "no_trade": len(no_trade),
            "total": len(evaluations),
        },
    }


__all__ = ["FairValueConfig", "evaluate_contract", "rank_evaluations", "Recommendation"]
