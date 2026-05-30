from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from contract_mapper import ParsedContract, model_probability_for_contract, parse_contract, target_label
from kalshi_client import NormalizedMarket
from kalshi_mapper import FusionConfig, map_to_kalshi_decision


@dataclass(frozen=True)
class RankConfig:
    w_edge: float = 0.40
    w_conf: float = 0.20
    w_liq: float = 0.20
    w_horizon: float = 0.10
    w_agree: float = 0.10
    max_spread: float = 0.05
    min_liquidity_score: float = 0.20
    stale_minutes: float = 15.0
    rule_ml_disagreement_threshold: float = 0.15
    min_mapping_confidence: float = 0.50
    horizon_mismatch_hours: float = 12.0


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


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


def _rule_ml_disagreement(p_rule: dict[str, float], p_ml: dict[str, float] | None) -> float:
    if not p_ml:
        return 0.0
    diffs = [
        abs(float(p_rule.get("up", 0)) - float(p_ml.get("up", 0))),
        abs(float(p_rule.get("down", 0)) - float(p_ml.get("down", 0))),
        abs(float(p_rule.get("range", 0)) - float(p_ml.get("range", 0))),
    ]
    return max(diffs) if diffs else 0.0


def _horizon_fit_score(parsed: ParsedContract) -> float:
    if parsed.horizon_hours is None:
        return 0.5
    h = parsed.horizon_hours
    if "12h" in parsed.compatible_probability_key:
        return max(0.0, 1.0 - abs(h - 12.0) / 24.0)
    return max(0.0, 1.0 - abs(h - 24.0) / 24.0)


def _synthetic_fused_for_decision(model_p: float, target_type: str) -> dict[str, float]:
    eps = 0.01
    rest = eps
    p = max(0.0, min(1.0, model_p))
    if target_type == "below_threshold":
        return {"up": rest, "down": p, "range": rest}
    if target_type == "range_bound":
        return {"up": rest, "down": rest, "range": p}
    return {"up": p, "down": rest, "range": rest}


def rank_opportunities(
    *,
    snapshot: dict[str, Any],
    rule_out: dict[str, Any],
    p_rule: dict[str, float],
    p_ml: dict[str, float] | None,
    fused: dict[str, float],
    model_confidence: float,
    markets: list[NormalizedMarket],
    parsed_contracts: list[ParsedContract] | None = None,
    fusion_cfg: FusionConfig | None = None,
    rank_cfg: RankConfig | None = None,
    kalshi_warnings: list[str] | None = None,
) -> dict[str, Any]:
    fusion_cfg = fusion_cfg or FusionConfig()
    rank_cfg = rank_cfg or RankConfig()

    spot = float((snapshot.get("price_data") or {}).get("spot_price_usd") or 0.0)
    rule_probs_full = dict(rule_out.get("probabilities") or {}) if isinstance(rule_out, dict) else {}

    if parsed_contracts is None:
        parsed_contracts = []
        for m in markets:
            pc = parse_contract(m, spot_price_usd=spot if spot > 0 else None)
            if pc is not None:
                parsed_contracts.append(pc)

    parsed_by_ticker = {p.ticker: p for p in parsed_contracts}
    disagreement = _rule_ml_disagreement(p_rule, p_ml)
    effective_conf = float(model_confidence)
    if disagreement > rank_cfg.rule_ml_disagreement_threshold:
        effective_conf *= 0.85

    opportunities: list[dict[str, Any]] = []

    for market in markets:
        parsed = parsed_by_ticker.get(market.ticker)
        if parsed is None:
            continue

        warnings: list[str] = list(parsed.parse_warnings)
        reasoning: list[str] = []

        model_p, model_warns = model_probability_for_contract(
            parsed,
            rule_probs=rule_probs_full,
            p_ml=p_ml,
            fused=fused,
            spot_price_usd=spot,
            w_rule=fusion_cfg.w_rule,
            w_ml=fusion_cfg.w_ml,
        )
        warnings.extend(model_warns)

        market_implied = market.implied_probability_mid
        edge: float | None = None
        if market_implied is not None:
            edge = float(model_p - market_implied)

        spread = 1.0
        if market.yes_bid is not None and market.yes_ask is not None:
            spread = max(0.0, market.yes_ask - market.yes_bid)
        if spread > rank_cfg.max_spread:
            warnings.append(f"wide spread ({spread:.3f}); liquidity penalty applied")

        updated = _parse_dt(market.updated_time)
        if updated is not None:
            age_min = (datetime.now(UTC) - updated).total_seconds() / 60.0
            if age_min > rank_cfg.stale_minutes:
                warnings.append(f"stale market data ({age_min:.0f} min since update)")

        if market.liquidity_score < rank_cfg.min_liquidity_score:
            warnings.append("liquidity below threshold")

        if parsed.mapping_confidence < rank_cfg.min_mapping_confidence:
            warnings.append("contract mapping confidence too low")

        if parsed.target_type == "unknown":
            warnings.append("unknown contract type")

        if parsed.horizon_hours is not None and "24h" in parsed.compatible_probability_key:
            if abs(parsed.horizon_hours - 24.0) > rank_cfg.horizon_mismatch_hours:
                warnings.append(
                    f"horizon mismatch: contract {parsed.horizon_hours:.0f}h vs 24h model key"
                )

        if disagreement > rank_cfg.rule_ml_disagreement_threshold:
            warnings.append("rule and ML models disagree materially")

        synth_fused = _synthetic_fused_for_decision(model_p, parsed.target_type)
        decision = map_to_kalshi_decision(
            fused_probs=synth_fused,
            model_confidence=effective_conf,
            market_implied_prob=market_implied,
            cfg=fusion_cfg,
            key_factors=list(rule_out.get("key_drivers", []))[:4] if isinstance(rule_out, dict) else [],
            ml_explanation=[],
            warnings=[],
        )

        recommendation = decision["recommendation"]
        if market_implied is None:
            recommendation = "NO TRADE"
            warnings.append("market implied probability missing")
        if parsed.mapping_confidence < rank_cfg.min_mapping_confidence or parsed.target_type == "unknown":
            recommendation = "NO TRADE"
        if market.liquidity_score < rank_cfg.min_liquidity_score:
            recommendation = "NO TRADE"
        if edge is not None and abs(edge) < fusion_cfg.min_edge:
            recommendation = "NO TRADE"
        if effective_conf < fusion_cfg.min_confidence:
            recommendation = "NO TRADE"

        horizon_score = _horizon_fit_score(parsed)
        agree_score = max(0.0, 1.0 - disagreement)
        rank_score = (
            rank_cfg.w_edge * (abs(edge) if edge is not None else 0.0)
            + rank_cfg.w_conf * effective_conf
            + rank_cfg.w_liq * market.liquidity_score
            + rank_cfg.w_horizon * horizon_score
            + rank_cfg.w_agree * agree_score
        ) * parsed.mapping_confidence

        if edge is not None:
            reasoning.append(f"model P(YES)={model_p:.3f} vs market={market_implied:.3f}")
            reasoning.append(f"edge={edge:+.3f}")
        else:
            reasoning.append("market implied probability unavailable")
        reasoning.append(f"horizon fit={horizon_score:.2f}, liquidity={market.liquidity_score:.2f}")
        drivers = rule_out.get("key_drivers") if isinstance(rule_out, dict) else []
        if drivers:
            reasoning.extend([str(d) for d in drivers[:2]])

        opportunities.append(
            {
                "ticker": market.ticker,
                "contract_title": parsed.contract_title or market.title,
                "target": target_label(parsed),
                "model_probability": round(model_p, 4),
                "market_implied_probability": None
                if market_implied is None
                else round(market_implied, 4),
                "edge": None if edge is None else round(edge, 4),
                "confidence": round(effective_conf, 4),
                "liquidity_score": round(market.liquidity_score, 4),
                "recommendation": recommendation,
                "reasoning": reasoning,
                "warnings": warnings,
                "rank_score": round(rank_score, 6),
            }
        )

    opportunities.sort(key=lambda x: float(x.get("rank_score", 0.0)), reverse=True)

    result: dict[str, Any] = {
        "timestamp": snapshot.get("timestamp") or _now_iso(),
        "btc_price": spot if spot > 0 else None,
        "ranked_opportunities": opportunities,
        "scan_meta": {
            "n_markets": len(markets),
            "n_ranked": len(opportunities),
            "rule_ml_disagreement": round(disagreement, 4),
            "kalshi_warnings": list(kalshi_warnings or []),
        },
    }
    return result


__all__ = ["RankConfig", "rank_opportunities"]
