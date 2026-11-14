"""Settlement-aligned probability for Kalshi KXBTC15M markets.

Kalshi 15-minute BTC markets settle against a CF Benchmarks-style reference
index. Operationally we treat UP/YES as:

    final 60-second average of the settlement index >= target_price

When the live CF index is unavailable, callers may supply a proxy
(`settlement_index`) with an explicit `settlement_index_source` so reports
never imply CF Benchmarks provenance they do not have.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Literal

from signal_engine import norm_cdf

SettlementIndexSource = Literal[
    "cf_benchmarks",
    "kalshi_api",
    "exchange_spot_proxy",
    "fixture",
    "unavailable",
]


@dataclass(frozen=True)
class SettlementModelConfig:
    fee_per_contract: float = 0.02  # dollars on $1 payout contract
    min_horizon_seconds: float = 5.0
    annualized_vol_floor: float = 0.20
    annualized_vol_default: float = 0.55


def _clamp01(x: float) -> float:
    return max(0.0, min(1.0, float(x)))


def estimate_p_up_settlement(
    *,
    settlement_index: float | None,
    target_price: float | None,
    time_remaining_seconds: float | None,
    annualized_volatility: float | None = None,
    directional_bias: float = 0.0,
    cfg: SettlementModelConfig | None = None,
) -> tuple[float | None, list[str]]:
    """Estimate P(final 60s settlement average >= target).

    Uses a lognormal short-horizon CDF on the settlement index level. This is
    settlement-aligned in *target*, not a generic 15m spot direction model.
    """
    cfg = cfg or SettlementModelConfig()
    drivers: list[str] = []
    if settlement_index is None or settlement_index <= 0:
        return None, ["settlement_index unavailable"]
    if target_price is None or target_price <= 0:
        return None, ["target_price unavailable"]
    if time_remaining_seconds is None:
        return None, ["time_remaining_seconds unavailable"]

    t_sec = max(float(time_remaining_seconds), cfg.min_horizon_seconds)
    vol = max(
        float(annualized_volatility)
        if annualized_volatility is not None
        else cfg.annualized_vol_default,
        cfg.annualized_vol_floor,
    )
    # Convert to horizon sigma: vol * sqrt(t / seconds_per_year)
    seconds_per_year = 365.0 * 24.0 * 3600.0
    sigma_h = vol * math.sqrt(t_sec / seconds_per_year)
    if sigma_h <= 1e-12:
        p = 1.0 if settlement_index >= target_price else 0.0
        drivers.append("degenerate_vol_horizon; step function vs target")
        return p, drivers

    # Mild drift from directional bias (bounded)
    mu_h = max(-2.0, min(2.0, float(directional_bias))) * sigma_h
    z = (math.log(target_price / settlement_index) - mu_h) / sigma_h
    # P(S_T >= K) = 1 - Phi(z) for lognormal S_T
    p_up = _clamp01(1.0 - norm_cdf(z))
    drivers.append(
        f"lognormal_cdf settlement_index={settlement_index:.2f} target={target_price:.2f} "
        f"tte_s={t_sec:.1f} sigma_h={sigma_h:.6f}"
    )
    return p_up, drivers


def net_edge_yes(
    *,
    model_p_up: float,
    yes_ask: float | None,
    fee_per_contract: float = 0.02,
) -> float | None:
    """Net expected value for buying YES at ask on a $1 payout contract."""
    if yes_ask is None:
        return None
    ask = _clamp01(yes_ask)
    # EV = p*(1-ask) - (1-p)*ask - fee = p - ask - fee
    return float(model_p_up) - ask - float(fee_per_contract)


def net_edge_no(
    *,
    model_p_up: float,
    no_ask: float | None,
    fee_per_contract: float = 0.02,
) -> float | None:
    """Net expected value for buying NO at ask on a $1 payout contract."""
    if no_ask is None:
        return None
    ask = _clamp01(no_ask)
    model_p_down = 1.0 - float(model_p_up)
    return model_p_down - ask - float(fee_per_contract)


def label_settlement_outcome(
    *,
    settlement_value: float,
    target_price: float,
) -> dict[str, Any]:
    """Binary label for contract-specific training/eval."""
    up = float(settlement_value) >= float(target_price)
    return {
        "settlement_value": float(settlement_value),
        "target_price": float(target_price),
        "outcome_up": up,
        "outcome_down": not up,
        "label": "UP" if up else "DOWN",
    }


def time_ordered_calibration(
    rows: list[dict[str, Any]],
    *,
    prob_key: str = "model_probability_up",
    label_key: str = "outcome_up",
) -> dict[str, Any]:
    """Simple time-ordered reliability summary (no shuffle)."""
    ordered = sorted(rows, key=lambda r: str(r.get("timestamp") or r.get("close_time") or ""))
    n = len(ordered)
    if n == 0:
        return {"n": 0, "brier": None, "mean_prob": None, "mean_outcome": None}
    brier = 0.0
    mean_p = 0.0
    mean_y = 0.0
    for r in ordered:
        p = float(r[prob_key])
        y = 1.0 if r[label_key] else 0.0
        brier += (p - y) ** 2
        mean_p += p
        mean_y += y
    return {
        "n": n,
        "brier": brier / n,
        "mean_prob": mean_p / n,
        "mean_outcome": mean_y / n,
        "calibration_gap": abs(mean_p / n - mean_y / n),
    }


__all__ = [
    "SettlementIndexSource",
    "SettlementModelConfig",
    "estimate_p_up_settlement",
    "net_edge_yes",
    "net_edge_no",
    "label_settlement_outcome",
    "time_ordered_calibration",
]
