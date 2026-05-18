from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal


Recommendation = Literal["BUY YES", "BUY NO", "NO TRADE"]
Outcome = Literal["up", "down", "range"]


@dataclass(frozen=True)
class FusionConfig:
    w_rule: float = 0.55
    w_ml: float = 0.45
    min_confidence: float = 0.55
    min_edge: float = 0.03
    max_range_prob_for_directional: float = 0.55


def _clamp(x: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, float(x)))


def _renorm(p: dict[Outcome, float]) -> dict[Outcome, float]:
    s = sum(float(v) for v in p.values())
    if s <= 0:
        return {"up": 1 / 3, "down": 1 / 3, "range": 1 / 3}
    return {k: float(v) / s for k, v in p.items()}


def fuse_probabilities(
    p_rule: dict[Outcome, float] | None,
    p_ml: dict[Outcome, float] | None,
    *,
    w_rule: float,
    w_ml: float,
) -> dict[Outcome, float]:
    p_rule = p_rule or {"up": 1 / 3, "down": 1 / 3, "range": 1 / 3}
    p_ml = p_ml or {"up": 1 / 3, "down": 1 / 3, "range": 1 / 3}
    p_rule = _renorm({k: _clamp(p_rule.get(k, 0.0)) for k in ("up", "down", "range")})  # type: ignore[misc]
    p_ml = _renorm({k: _clamp(p_ml.get(k, 0.0)) for k in ("up", "down", "range")})  # type: ignore[misc]
    wr = max(0.0, float(w_rule))
    wm = max(0.0, float(w_ml))
    s = wr + wm
    if s <= 0:
        wr, wm = 0.5, 0.5
    else:
        wr, wm = wr / s, wm / s
    out = {
        "up": wr * p_rule["up"] + wm * p_ml["up"],
        "down": wr * p_rule["down"] + wm * p_ml["down"],
        "range": wr * p_rule["range"] + wm * p_ml["range"],
    }
    return _renorm(out)  # type: ignore[return-value]


def _pick_contract(p: dict[Outcome, float]) -> Outcome:
    return max(p, key=lambda k: p[k])


def map_to_kalshi_decision(
    *,
    fused_probs: dict[Outcome, float],
    model_confidence: float,
    market_implied_prob: float | None,
    cfg: FusionConfig | None = None,
    key_factors: list[str] | None = None,
    ml_explanation: list[str] | None = None,
    warnings: list[str] | None = None,
) -> dict[str, Any]:
    """
    Produces a decision-grade object (recommendations only; no execution).
    If market_implied_prob is None, edge/recommendation are disabled.
    """
    cfg = cfg or FusionConfig()
    key_factors = key_factors or []
    ml_explanation = ml_explanation or []
    warnings = warnings or []

    fused = _renorm({k: _clamp(fused_probs.get(k, 0.0)) for k in ("up", "down", "range")})  # type: ignore[misc]
    contract = _pick_contract(fused)
    prob = float(fused[contract])

    edge: float | None = None
    rec: Recommendation = "NO TRADE"
    side: Literal["YES", "NO"] | None = None

    # Guardrails
    if model_confidence < cfg.min_confidence:
        warnings.append("confidence below threshold; forcing NO TRADE")
    if contract in ("up", "down") and fused["range"] > cfg.max_range_prob_for_directional:
        warnings.append("range probability too high for directional trade; forcing NO TRADE")

    if market_implied_prob is None:
        warnings.append("market implied probability missing; edge not computed; forcing NO TRADE")
    else:
        mkt = _clamp(market_implied_prob)
        edge = prob - mkt
        if (
            model_confidence >= cfg.min_confidence
            and abs(edge) >= cfg.min_edge
            and not (contract in ("up", "down") and fused["range"] > cfg.max_range_prob_for_directional)
        ):
            # If our prob > market, buy YES; else buy NO
            if edge > 0:
                rec = "BUY YES"
                side = "YES"
            else:
                rec = "BUY NO"
                side = "NO"
        else:
            rec = "NO TRADE"

    return {
        "contract": contract,
        "probability": float(round(prob, 4)),
        "market_implied_prob": None if market_implied_prob is None else float(round(_clamp(market_implied_prob), 4)),
        "edge": None if edge is None else float(round(edge, 4)),
        "confidence": float(round(_clamp(model_confidence), 4)),
        "recommendation": rec,
        "recommended_side": side,
        "key_factors": key_factors,
        "ml_explanation": ml_explanation,
        "warnings": warnings,
    }


__all__ = ["FusionConfig", "fuse_probabilities", "map_to_kalshi_decision"]

