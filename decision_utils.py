from __future__ import annotations

from typing import Any


def extract_rule_probs(sig: dict[str, Any]) -> dict[str, float]:
    """Map signal_engine 24h probability keys to {up, down, range}."""
    probs = (sig.get("probabilities") or {}) if isinstance(sig, dict) else {}
    p_up = float(probs.get("up_move_24h", 0.0))
    p_down = float(probs.get("down_move_24h", 0.0))
    p_range = float(probs.get("range_bound", 0.0))
    s = p_up + p_down + p_range
    if s <= 0:
        return {"up": 1 / 3, "down": 1 / 3, "range": 1 / 3}
    return {"up": p_up / s, "down": p_down / s, "range": p_range / s}


def combined_model_confidence(rule_conf: float, ml_available: bool) -> float:
    """Conservative confidence used by live_runner and dataset_builder."""
    rule_conf = float(rule_conf)
    if not ml_available:
        return rule_conf
    return float(min(rule_conf, 1.0))


__all__ = ["extract_rule_probs", "combined_model_confidence"]
