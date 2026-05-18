#!/usr/bin/env python3
"""
BTC Trading Signal Engine (Prediction Market oriented)

Consumes the JSON output of `btc_market_intel_collector.py` and produces:
- a 0–100 signal score
- directional bias (BULLISH / BEARISH / NEUTRAL)
- confidence (0–1) with explicit data-quality adjustment
- Kalshi-style probability estimates (12h/24h; range band default ±0.5%)
- human-readable reasoning (key drivers + warnings + a trade insight)

This module is deterministic and explainable: no black-box ML, no external APIs.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Literal, Mapping, MutableMapping, Sequence, TypedDict

Direction = Literal["BULLISH", "BEARISH", "NEUTRAL"]


class SignalEngineOutput(TypedDict):
    signal_score: int  # 0..100
    direction: Direction
    confidence: float  # 0..1
    probabilities: dict[str, float]
    key_drivers: list[str]
    warnings: list[str]
    kalshi_trade_insight: str


@dataclass(frozen=True)
class SignalEngineConfig:
    """
    Configuration for scoring and probability mapping.

    Weights are category weights for the composite score. They are re-normalized
    (after accounting for missing categories) to sum to 1.
    """

    weights: dict[str, float] = field(
        default_factory=lambda: {
            "price_momentum": 0.20,
            "volume": 0.15,
            "liquidity_orderflow": 0.25,
            "sentiment": 0.15,
            "onchain": 0.10,
            "macro_corr": 0.07,
            "derivatives": 0.08,
        }
    )

    # Direction classification thresholds on composite score in [-1, 1]
    bullish_threshold: float = 0.25
    bearish_threshold: float = -0.25

    # Price-return saturation: tanh(ret / ret_scale)
    price_ret_scale: float = 0.0045  # ~0.45% per hour saturates around tanh(1)

    # Volume change saturation: tanh(vol_chg_pct / volume_chg_scale_pct)
    volume_chg_scale_pct: float = 25.0

    # Liquidity/orderflow: log pressure saturation: tanh(log(ratio) / pressure_log_scale)
    pressure_log_scale: float = 0.7

    # Wall imbalance scale already in [-1,1] but can be tempered
    wall_imbalance_scale: float = 1.0

    # Confidence haircuts based on microstructure (these are applied deterministically)
    max_spread_pct_good: float = 0.02  # <2 bps (note: spread_pct in your JSON is percent, not fraction)
    max_slippage_pct_good: float = 0.50  # <0.5% for configured notional
    min_book_depth_usd_good: float = 250_000.0

    # Volatility regime thresholds (annualized)
    vol_low: float = 0.15
    vol_high: float = 0.35
    vol_extreme: float = 0.55

    # Kalshi probability mapping
    range_band_pct: float = 0.005  # ±0.5%
    horizons_hours: tuple[int, int] = (12, 24)
    tilt_k: float = 3.0  # sigmoid slope for directional tilt

    # Breakout/chop adjustments to p_range (clamped)
    breakout_adjustment_max: float = 0.20  # max reduction in p_range
    chop_adjustment_max: float = 0.15  # max increase in p_range

    # Driver/warning formatting
    max_key_drivers: int = 6
    max_warnings: int = 8

    # Data-quality / source-health
    critical_sources: tuple[str, ...] = (
        "coinbase_spot_ticker",
        "coinbase_spot_book",
        "coinbase_spot_trades",
        "alternative_fng",
        "coingecko_markets",
        "blockchaincom_transactions",
        "blockchaincom_hashrate",
    )
    important_sources: tuple[str, ...] = (
        # Often blocked in your environment; still important if available.
        "binance_spot_ticker",
        "binance_spot_depth",
        "binance_spot_trades",
        "binance_futures_open_interest",
        "binance_futures_funding",
        "binance_futures_liquidations",
        "fred_sp500",
        "fred_nasdaq",
        "fred_gold",
    )


@dataclass
class CategorySignal:
    name: str
    value: float  # in [-1, 1]
    quality: float  # in [0, 1]
    drivers: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def clamp(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


def safe_float(x: Any) -> float | None:
    if x is None:
        return None
    try:
        if isinstance(x, bool):
            return None
        return float(x)
    except (TypeError, ValueError):
        return None


def safe_bool(x: Any) -> bool | None:
    if x is None:
        return None
    if isinstance(x, bool):
        return x
    if isinstance(x, (int, float)) and x in (0, 1):
        return bool(x)
    if isinstance(x, str):
        s = x.strip().lower()
        if s in ("true", "yes", "y", "1"):
            return True
        if s in ("false", "no", "n", "0"):
            return False
    return None


def get_path(d: Mapping[str, Any], path: Sequence[str]) -> Any:
    cur: Any = d
    for key in path:
        if not isinstance(cur, Mapping):
            return None
        cur = cur.get(key)
    return cur


def tanh_squash(x: float) -> float:
    return math.tanh(x)


def sigmoid(x: float) -> float:
    # numerically stable enough for our typical magnitudes
    return 1.0 / (1.0 + math.exp(-x))


def norm_cdf(x: float) -> float:
    # Phi(x) via erf
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def _fmt_pct(x: float, decimals: int = 2) -> str:
    return f"{x * 100:.{decimals}f}%"


def _fmt_num(x: float, decimals: int = 2) -> str:
    return f"{x:.{decimals}f}"


def _nonempty(xs: Iterable[str]) -> list[str]:
    return [x for x in xs if isinstance(x, str) and x.strip()]


def _renormalize_weights(weights: Mapping[str, float], present: set[str]) -> dict[str, float]:
    w = {k: float(v) for k, v in weights.items() if k in present and float(v) > 0}
    s = sum(w.values())
    if s <= 0:
        return {k: 1.0 / len(present) for k in sorted(present)} if present else {}
    return {k: v / s for k, v in w.items()}


def compute_price_signal(snapshot: Mapping[str, Any], cfg: SignalEngineConfig) -> CategorySignal:
    spot = safe_float(get_path(snapshot, ("price_data", "spot_price_usd")))
    last_close = safe_float(get_path(snapshot, ("price_data", "ohlc_last_close_usd")))
    vol_ann = safe_float(get_path(snapshot, ("price_data", "rolling_volatility_annualized")))

    drivers: list[str] = []
    warnings: list[str] = []

    q = 1.0
    if spot is None or last_close is None or last_close == 0:
        warnings.append("Price momentum unavailable (missing spot or last close).")
        return CategorySignal("price_momentum", 0.0, 0.0, drivers, warnings)

    ret_1h = (spot - last_close) / last_close
    ret_score = tanh_squash(ret_1h / max(cfg.price_ret_scale, 1e-9))
    ret_score = clamp(ret_score, -1.0, 1.0)
    drivers.append(f"1h ret: {_fmt_pct(ret_1h, 2)} → momentum {_fmt_num(ret_score, 2)}")

    # Vol regime: mostly affects confidence/quality; mild effect on score (avoid overfitting).
    vol_adj = 0.0
    if vol_ann is None:
        q *= 0.75
        warnings.append("Volatility regime missing; confidence reduced.")
    else:
        if vol_ann >= cfg.vol_extreme:
            q *= 0.70
            warnings.append(f"Extreme vol regime ({_fmt_pct(vol_ann, 1)} annualized); targets less reliable.")
            vol_adj = -0.05 * math.copysign(1.0, ret_score)  # small mean-reversion bias in chaos
        elif vol_ann >= cfg.vol_high:
            q *= 0.85
            drivers.append(f"High vol regime ({_fmt_pct(vol_ann, 1)} annualized).")
        elif vol_ann <= cfg.vol_low:
            drivers.append(f"Low vol regime ({_fmt_pct(vol_ann, 1)} annualized).")

    value = clamp(ret_score + vol_adj, -1.0, 1.0)
    return CategorySignal("price_momentum", value, clamp(q, 0.0, 1.0), drivers, warnings)


def compute_volume_signal(snapshot: Mapping[str, Any], cfg: SignalEngineConfig) -> CategorySignal:
    vol_chg = safe_float(get_path(snapshot, ("volume_data", "volume_change_pct_vs_prev_window")))
    spike = safe_bool(get_path(snapshot, ("volume_data", "volume_spike_detected")))

    drivers: list[str] = []
    warnings: list[str] = []
    q = 1.0

    if vol_chg is None:
        warnings.append("Volume change unavailable; confidence reduced.")
        return CategorySignal("volume", 0.0, 0.0, drivers, warnings)

    base = tanh_squash(vol_chg / max(cfg.volume_chg_scale_pct, 1e-9))
    base = clamp(base, -1.0, 1.0)
    drivers.append(f"Volume change vs prior window: {_fmt_num(vol_chg, 1)}% → {_fmt_num(base, 2)}")

    # A spike is interpreted as "activity / potential breakout". It doesn't pick direction by itself.
    if spike is True:
        drivers.append("Volume spike detected (breakout risk up).")
        # Increase magnitude slightly in the direction suggested by vol_chg (expansion => trend-following)
        base = clamp(base + 0.10 * math.copysign(1.0, base if base != 0 else 1.0), -1.0, 1.0)
    elif spike is False:
        drivers.append("No volume spike (less evidence of forced move).")
    else:
        q *= 0.9
        warnings.append("Volume spike flag missing.")

    return CategorySignal("volume", base, clamp(q, 0.0, 1.0), drivers, warnings)


def compute_liquidity_signal(snapshot: Mapping[str, Any], cfg: SignalEngineConfig) -> CategorySignal:
    spread_pct = safe_float(get_path(snapshot, ("liquidity_data", "spread_pct")))
    slippage_pct = safe_float(get_path(snapshot, ("liquidity_data", "slippage_pct_for_notional")))
    depth_usd = safe_float(get_path(snapshot, ("liquidity_data", "order_book_depth_usd")))
    buy_wall = safe_float(get_path(snapshot, ("liquidity_data", "buy_wall_usd_top10")))
    sell_wall = safe_float(get_path(snapshot, ("liquidity_data", "sell_wall_usd_top10")))
    pressure = safe_float(get_path(snapshot, ("liquidity_data", "buy_sell_pressure_ratio")))

    drivers: list[str] = []
    warnings: list[str] = []
    q = 1.0

    # Wall imbalance
    wall_score = 0.0
    if buy_wall is None or sell_wall is None or (buy_wall + sell_wall) <= 0:
        q *= 0.85
        warnings.append("Order book wall metrics missing; liquidity signal weakened.")
    else:
        wall_imb = (buy_wall - sell_wall) / (buy_wall + sell_wall)
        wall_score = clamp(wall_imb * cfg.wall_imbalance_scale, -1.0, 1.0)
        if wall_imb < 0:
            drivers.append(
                f"Sell wall dominates buy wall (imbalance {_fmt_num(wall_imb, 2)}): bearish pressure."
            )
        else:
            drivers.append(
                f"Buy wall dominates sell wall (imbalance {_fmt_num(wall_imb, 2)}): bullish support."
            )

    # Trade pressure ratio
    pressure_score = 0.0
    if pressure is None or pressure <= 0:
        q *= 0.85
        warnings.append("Buy/sell pressure ratio missing; order-flow confidence reduced.")
    else:
        logp = math.log(pressure)
        pressure_score = clamp(tanh_squash(logp / max(cfg.pressure_log_scale, 1e-9)), -1.0, 1.0)
        if pressure_score > 0:
            drivers.append(f"Buy pressure > sell pressure (ratio {_fmt_num(pressure, 2)}).")
        else:
            drivers.append(f"Sell pressure > buy pressure (ratio {_fmt_num(pressure, 2)}).")

    # Spread/slippage/depth primarily affect confidence, but also hint at fragility.
    if spread_pct is None:
        q *= 0.85
        warnings.append("Spread missing; liquidity quality reduced.")
    else:
        drivers.append(f"Spread: {_fmt_num(spread_pct, 4)}%")
        # If spread is wide, reduce quality
        if spread_pct > cfg.max_spread_pct_good:
            q *= clamp(cfg.max_spread_pct_good / max(spread_pct, 1e-9), 0.4, 1.0)
            warnings.append("Spread wider than 'good' threshold; microstructure risk up.")

    if slippage_pct is None:
        q *= 0.85
        warnings.append("Slippage missing; liquidity quality reduced.")
    else:
        drivers.append(f"Slippage for notional: {_fmt_num(slippage_pct, 3)}%")
        if slippage_pct > cfg.max_slippage_pct_good:
            q *= clamp(cfg.max_slippage_pct_good / max(slippage_pct, 1e-9), 0.4, 1.0)
            warnings.append("Slippage elevated; fills in size are harder (confidence haircut).")

    if depth_usd is None:
        q *= 0.9
        warnings.append("Order book depth missing; liquidity quality reduced.")
    else:
        drivers.append(f"Top-book depth (proxy): ${_fmt_num(depth_usd, 0)}")
        if depth_usd < cfg.min_book_depth_usd_good:
            q *= clamp(depth_usd / cfg.min_book_depth_usd_good, 0.4, 1.0)
            warnings.append("Order book depth looks thin; price can gap (confidence haircut).")

    # Combine: order-flow dominates walls slightly; clamp.
    value = clamp(0.55 * pressure_score + 0.45 * wall_score, -1.0, 1.0)
    return CategorySignal("liquidity_orderflow", value, clamp(q, 0.0, 1.0), drivers, warnings)


def compute_sentiment_signal(snapshot: Mapping[str, Any], cfg: SignalEngineConfig) -> CategorySignal:
    fng = safe_float(get_path(snapshot, ("sentiment_data", "fear_greed_value")))
    drivers: list[str] = []
    warnings: list[str] = []
    q = 1.0

    if fng is None:
        warnings.append("Fear & Greed missing; sentiment signal unavailable.")
        return CategorySignal("sentiment", 0.0, 0.0, drivers, warnings)

    # Contrarian logic by requirement:
    # - Fear < 30 -> bullish tilt
    # - Greed > 70 -> bearish tilt
    if fng < 30:
        value = clamp((30 - fng) / 30.0, 0.0, 1.0)
        drivers.append(f"Fear & Greed {int(fng)} (<30): contrarian bullish tilt.")
    elif fng > 70:
        value = -clamp((fng - 70) / 30.0, 0.0, 1.0)
        drivers.append(f"Fear & Greed {int(fng)} (>70): contrarian bearish tilt.")
    else:
        # Mid-range: near neutral, fade toward 0
        mid = (fng - 50.0) / 20.0  # -1 at 30, +1 at 70
        value = -0.25 * clamp(mid, -1.0, 1.0)  # keep weak & slightly contrarian
        drivers.append(f"Fear & Greed {int(fng)} (mid-range): weak/neutral sentiment signal.")

    return CategorySignal("sentiment", clamp(value, -1.0, 1.0), clamp(q, 0.0, 1.0), drivers, warnings)


def compute_onchain_signal(snapshot: Mapping[str, Any], cfg: SignalEngineConfig) -> CategorySignal:
    tx = safe_float(get_path(snapshot, ("on_chain_data", "transaction_count")))
    hr = safe_float(get_path(snapshot, ("on_chain_data", "hash_rate")))
    drivers: list[str] = []
    warnings: list[str] = []

    present = 0
    if tx is not None and tx > 0:
        present += 1
        drivers.append(f"On-chain tx count available: {_fmt_num(tx, 0)}")
    else:
        warnings.append("On-chain tx count missing.")
    if hr is not None and hr > 0:
        present += 1
        drivers.append(f"Hash rate available: {_fmt_num(hr, 0)}")
    else:
        warnings.append("Hash rate missing.")

    if present == 0:
        return CategorySignal("onchain", 0.0, 0.0, drivers, warnings)

    # With no trend info in a single snapshot, keep as mild supportive bias only.
    value = 0.10 if present == 2 else 0.05
    return CategorySignal("onchain", value, present / 2.0, drivers, warnings)


def compute_macro_signal(snapshot: Mapping[str, Any], cfg: SignalEngineConfig) -> CategorySignal:
    corr_spx = safe_float(get_path(snapshot, ("macro_data", "corr_btc_spx")))
    corr_qqq = safe_float(get_path(snapshot, ("macro_data", "corr_btc_qqq")))
    drivers: list[str] = []
    warnings: list[str] = []

    vals = [v for v in (corr_spx, corr_qqq) if isinstance(v, float)]
    if not vals:
        warnings.append("Macro correlation missing; macro signal unavailable.")
        return CategorySignal("macro_corr", 0.0, 0.0, drivers, warnings)

    avg = float(sum(vals) / len(vals))
    mag = float(sum(abs(v) for v in vals) / len(vals))

    drivers.append(f"Corr regime (avg SPX/QQQ): {_fmt_num(avg, 2)} (|corr|~{_fmt_num(mag, 2)})")

    # Macro correlation is primarily a regime indicator; keep direction weak.
    # If strongly risk-on (high positive corr), slight bearish contrarian (more macro fragility).
    # If strongly negative corr, slight bullish (diversifier bid), but keep small.
    if mag < 0.15:
        value = 0.05
        drivers.append("Low macro correlation: more idiosyncratic BTC regime (confidence slightly higher).")
    else:
        value = -0.05 * math.copysign(1.0, avg) if avg != 0 else 0.0
        drivers.append("High macro coupling: BTC more risk-on (macro headlines matter).")

    quality = clamp(len(vals) / 2.0, 0.0, 1.0)
    return CategorySignal("macro_corr", clamp(value, -1.0, 1.0), quality, drivers, warnings)


def compute_derivatives_signal(snapshot: Mapping[str, Any], cfg: SignalEngineConfig) -> CategorySignal:
    """
    Derivatives category is optional; if missing, it should reduce confidence
    (quality=0) and add an explicit warning rather than being imputed.
    """

    oi = safe_float(get_path(snapshot, ("derivatives_data", "open_interest_usd")))
    funding = safe_float(get_path(snapshot, ("derivatives_data", "funding_rate")))
    liq = safe_float(get_path(snapshot, ("derivatives_data", "recent_liquidations_usd")))

    drivers: list[str] = []
    warnings: list[str] = []

    present = 0
    if oi is not None:
        present += 1
        drivers.append(f"Open interest available: ${_fmt_num(oi, 0)}")
    if funding is not None:
        present += 1
        drivers.append(f"Funding rate available: {_fmt_num(funding, 5)}")
    if liq is not None:
        present += 1
        drivers.append(f"Recent liquidations (proxy): ${_fmt_num(liq, 0)}")

    if present == 0:
        warnings.append("Derivatives data missing (OI/funding/liquidations); confidence reduced.")
        return CategorySignal("derivatives", 0.0, 0.0, drivers, warnings)

    # Light-touch scoring:
    # - Very positive funding -> crowded longs -> contrarian bearish
    # - Very negative funding -> crowded shorts -> contrarian bullish
    value = 0.0
    if funding is not None:
        # Use a heuristic scale (funding is typically small); saturate quickly.
        value += clamp(-tanh_squash(funding / 0.0006), -0.5, 0.5)
    if liq is not None and liq > 0:
        # Liquidations imply stress; direction ambiguous; reduce magnitude slightly.
        value *= 0.9
        drivers.append("Liquidations present: stress up (range probability down).")

    quality = clamp(present / 3.0, 0.0, 1.0)
    return CategorySignal("derivatives", clamp(value, -1.0, 1.0), quality, drivers, warnings)


def combine_signals(parts: Sequence[CategorySignal], cfg: SignalEngineConfig) -> tuple[float, dict[str, float]]:
    """
    Combine category scores into a composite score in [-1, 1].
    Returns (composite, weights_used).
    """

    present = {p.name for p in parts if p.quality > 0}
    weights = _renormalize_weights(cfg.weights, present)
    if not weights:
        return 0.0, {}

    composite = 0.0
    for p in parts:
        w = weights.get(p.name)
        if w is None:
            continue
        composite += w * clamp(p.value, -1.0, 1.0)
    return clamp(composite, -1.0, 1.0), weights


def compute_source_health_factor(snapshot: Mapping[str, Any], cfg: SignalEngineConfig) -> tuple[float, list[str]]:
    """
    Convert collector `source_health` map into a multiplicative factor in [0,1].
    """

    sh = get_path(snapshot, ("source_health",))
    if not isinstance(sh, Mapping):
        return 0.85, ["source_health missing; confidence reduced."]

    warnings: list[str] = []

    def ok(name: str) -> bool | None:
        node = sh.get(name)
        if not isinstance(node, Mapping):
            return None
        return node.get("status") == "ok"

    critical_status = [ok(n) for n in cfg.critical_sources]
    crit_known = [s for s in critical_status if s is not None]
    crit_ok = [s for s in crit_known if s]
    crit_factor = (len(crit_ok) / len(crit_known)) if crit_known else 0.85

    # Important sources: smaller penalty (they are bonus reliability)
    important_status = [ok(n) for n in cfg.important_sources]
    imp_known = [s for s in important_status if s is not None]
    imp_ok = [s for s in imp_known if s]
    imp_factor = (len(imp_ok) / len(imp_known)) if imp_known else 0.85

    # Explicitly warn on missing/failed critical sources
    for n in cfg.critical_sources:
        if ok(n) is False:
            warnings.append(f"Critical source failed: {n}")
        elif ok(n) is None:
            warnings.append(f"Critical source status missing: {n}")

    # Penalize when derivatives are systematically failing (common in your environment)
    for n in ("binance_futures_open_interest", "binance_futures_funding", "binance_futures_liquidations"):
        if ok(n) is False:
            warnings.append(f"Derivatives source failed: {n}")

    # Combine: critical dominates.
    factor = clamp(0.70 * crit_factor + 0.30 * imp_factor, 0.0, 1.0)
    return factor, warnings


def compute_data_quality(parts: Sequence[CategorySignal], snapshot: Mapping[str, Any], cfg: SignalEngineConfig) -> tuple[float, list[str]]:
    """
    Compute overall confidence factor in [0,1] from:
    - category qualities (missing fields)
    - source health map
    - microstructure penalties (spread/slippage/depth) already embedded in liquidity quality
    """

    # Category availability factor (weighted by configured weights)
    weighted_q_num = 0.0
    weighted_q_den = 0.0
    for p in parts:
        w = cfg.weights.get(p.name, 0.0)
        if w <= 0:
            continue
        weighted_q_num += w * clamp(p.quality, 0.0, 1.0)
        weighted_q_den += w
    cat_factor = (weighted_q_num / weighted_q_den) if weighted_q_den > 0 else 0.85

    sh_factor, sh_warnings = compute_source_health_factor(snapshot, cfg)
    # Combine and clamp; keep some floor so output isn't unusable
    confidence = clamp(cat_factor * sh_factor, 0.05, 1.0)
    return confidence, sh_warnings


def _breakout_chop_adjustment(snapshot: Mapping[str, Any], cfg: SignalEngineConfig) -> tuple[float, list[str]]:
    """
    Compute deterministic adjustment to p_range in [-breakout_max, +chop_max].
    """

    drivers: list[str] = []

    vol_ann = safe_float(get_path(snapshot, ("price_data", "rolling_volatility_annualized")))
    spread_pct = safe_float(get_path(snapshot, ("liquidity_data", "spread_pct")))
    slippage_pct = safe_float(get_path(snapshot, ("liquidity_data", "slippage_pct_for_notional")))
    pressure = safe_float(get_path(snapshot, ("liquidity_data", "buy_sell_pressure_ratio")))
    buy_wall = safe_float(get_path(snapshot, ("liquidity_data", "buy_wall_usd_top10")))
    sell_wall = safe_float(get_path(snapshot, ("liquidity_data", "sell_wall_usd_top10")))
    vol_chg = safe_float(get_path(snapshot, ("volume_data", "volume_change_pct_vs_prev_window")))

    # Breakout score: high vol + strong imbalance/pressure
    breakout = 0.0
    if vol_ann is not None:
        breakout += clamp((vol_ann - cfg.vol_high) / max(cfg.vol_extreme - cfg.vol_high, 1e-9), 0.0, 1.0)
    if pressure is not None and pressure > 0:
        breakout += clamp(abs(math.log(pressure)) / 1.2, 0.0, 1.0)
    if buy_wall is not None and sell_wall is not None and (buy_wall + sell_wall) > 0:
        wall_imb = abs((buy_wall - sell_wall) / (buy_wall + sell_wall))
        breakout += clamp(wall_imb / 0.6, 0.0, 1.0)
    breakout = breakout / 3.0

    # Chop score: tight spread + contracting volume
    chop = 0.0
    if spread_pct is not None:
        chop += clamp((cfg.max_spread_pct_good - spread_pct) / max(cfg.max_spread_pct_good, 1e-9), 0.0, 1.0)
    if vol_chg is not None:
        # contraction -> chop
        chop += clamp((-vol_chg) / 30.0, 0.0, 1.0)
    if slippage_pct is not None:
        chop += clamp((cfg.max_slippage_pct_good - slippage_pct) / max(cfg.max_slippage_pct_good, 1e-9), 0.0, 1.0)
    chop = chop / 3.0

    adjustment = 0.0
    if breakout > chop:
        adjustment = -cfg.breakout_adjustment_max * clamp((breakout - chop) / max(1.0 - chop, 1e-9), 0.0, 1.0)
        drivers.append("Breakout conditions (vol/imbalance) reduce range probability.")
    elif chop > breakout:
        adjustment = cfg.chop_adjustment_max * clamp((chop - breakout) / max(1.0 - breakout, 1e-9), 0.0, 1.0)
        drivers.append("Chop/indecision conditions increase range probability.")

    return clamp(adjustment, -cfg.breakout_adjustment_max, cfg.chop_adjustment_max), drivers


def compute_kalshi_probabilities(
    composite: float,
    snapshot: Mapping[str, Any],
    cfg: SignalEngineConfig,
    confidence: float,
    horizon_hours: int,
) -> dict[str, float]:
    """
    Produce probabilities for up/down move vs a range band around spot.

    - Baseline range probability comes from normal approximation using annualized vol.
    - Direction tilt comes from sigmoid(k * composite).
    - Deterministic breakout/chop adjustments reallocate mass between range and tails.
    - Final probabilities are shrunk toward 0.5 using confidence.
    """

    vol_ann = safe_float(get_path(snapshot, ("price_data", "rolling_volatility_annualized")))
    if vol_ann is None or vol_ann <= 0:
        # degrade gracefully: assume moderate sigma, but shrink heavily via confidence
        vol_ann = 0.28

    sigma_h = vol_ann * math.sqrt(horizon_hours / (24.0 * 365.0))
    sigma_h = max(sigma_h, 1e-6)

    band = cfg.range_band_pct
    z = band / sigma_h
    p_range = clamp(2.0 * norm_cdf(z) - 1.0, 0.01, 0.98)

    adj, _adj_drivers = _breakout_chop_adjustment(snapshot, cfg)
    p_range = clamp(p_range + adj, 0.01, 0.98)

    tilt = sigmoid(cfg.tilt_k * clamp(composite, -1.0, 1.0))
    tail = 1.0 - p_range
    p_up = tail * tilt
    p_down = tail * (1.0 - tilt)

    # Convert up/down/range into "final" probs via confidence shrinkage.
    # Range is shrunk around its own base; up/down shrink toward 0.5 pairwise.
    # First ensure invariants.
    s = p_up + p_down + p_range
    if s <= 0:
        p_up, p_down, p_range = 0.25, 0.25, 0.50
    else:
        p_up, p_down, p_range = p_up / s, p_down / s, p_range / s

    # Shrink toward an uninformative baseline driven by vol only:
    # baseline tilt = 0.5, baseline range = p_range (already vol-based)
    base_up = (1.0 - p_range) * 0.5
    base_down = (1.0 - p_range) * 0.5
    p_up = base_up + confidence * (p_up - base_up)
    p_down = base_down + confidence * (p_down - base_down)
    # Range gets only mild shrinkage (it is already a vol-based estimate)
    p_range = p_range + clamp(0.6 * confidence, 0.0, 1.0) * (p_range - p_range)

    # Re-normalize
    s2 = p_up + p_down + p_range
    p_up, p_down, p_range = p_up / s2, p_down / s2, p_range / s2

    return {
        f"up_move_{horizon_hours}h": clamp(p_up, 0.0, 1.0),
        f"down_move_{horizon_hours}h": clamp(p_down, 0.0, 1.0),
        f"range_bound_{horizon_hours}h": clamp(p_range, 0.0, 1.0),
    }


def classify_direction(composite: float, cfg: SignalEngineConfig) -> Direction:
    if composite >= cfg.bullish_threshold:
        return "BULLISH"
    if composite <= cfg.bearish_threshold:
        return "BEARISH"
    return "NEUTRAL"


def to_signal_score(composite: float) -> int:
    return int(round(clamp(50.0 + 50.0 * composite, 0.0, 100.0)))


def generate_signal(snapshot: Mapping[str, Any], cfg: SignalEngineConfig | None = None) -> SignalEngineOutput:
    cfg = cfg or SignalEngineConfig()

    parts = [
        compute_price_signal(snapshot, cfg),
        compute_volume_signal(snapshot, cfg),
        compute_liquidity_signal(snapshot, cfg),
        compute_sentiment_signal(snapshot, cfg),
        compute_onchain_signal(snapshot, cfg),
        compute_macro_signal(snapshot, cfg),
        compute_derivatives_signal(snapshot, cfg),
    ]

    composite, weights_used = combine_signals(parts, cfg)
    direction = classify_direction(composite, cfg)
    score = to_signal_score(composite)

    confidence, sh_warnings = compute_data_quality(parts, snapshot, cfg)

    probs: dict[str, float] = {}
    for h in cfg.horizons_hours:
        probs.update(compute_kalshi_probabilities(composite, snapshot, cfg, confidence, h))

    # Required keys in the spec (24h) plus range_bound:
    # Provide aliases with the exact required names.
    probs["up_move_24h"] = probs.get("up_move_24h", probs.get("up_move_24h", 0.0))
    probs["down_move_24h"] = probs.get("down_move_24h", probs.get("down_move_24h", 0.0))
    probs["range_bound"] = probs.get("range_bound_24h", 0.0)

    # Build drivers/warnings
    drivers: list[str] = []
    warnings: list[str] = []
    for p in parts:
        drivers.extend(p.drivers)
        warnings.extend(p.warnings)
    warnings.extend(sh_warnings)

    # Prioritize: keep high-signal drivers first (liquidity, sentiment, momentum)
    priority = {"liquidity_orderflow": 0, "sentiment": 1, "price_momentum": 2, "volume": 3, "derivatives": 4, "onchain": 5, "macro_corr": 6}
    parts_sorted = sorted(parts, key=lambda x: priority.get(x.name, 99))
    prioritized_drivers: list[str] = []
    for p in parts_sorted:
        prioritized_drivers.extend(p.drivers[:3])
    key_drivers = prioritized_drivers[: cfg.max_key_drivers]

    warnings = _nonempty(warnings)
    # De-dupe while preserving order
    seen: set[str] = set()
    warnings_dedup: list[str] = []
    for w in warnings:
        if w in seen:
            continue
        seen.add(w)
        warnings_dedup.append(w)
    warnings = warnings_dedup[: cfg.max_warnings]

    # Desk-style insight
    p_range_12 = probs.get("range_bound_12h", probs.get("range_bound_24h", 0.0))
    p_range_24 = probs.get("range_bound_24h", 0.0)
    if direction == "NEUTRAL":
        play = "range-style contracts" if (p_range_12 + p_range_24) / 2.0 >= 0.45 else "conditional breakout contracts"
    else:
        play = "directional contracts" if confidence >= 0.55 else "small-size directional with hedged structure"

    kalshi_trade_insight = (
        f"Signal {score}/100 ({direction}), confidence {_fmt_num(confidence, 2)}. "
        f"12h range(±{_fmt_pct(cfg.range_band_pct, 2)})={_fmt_num(p_range_12, 2)}, "
        f"24h range={_fmt_num(p_range_24, 2)}. "
        f"Primary drivers: {', '.join(key_drivers[:3])}. "
        f"Best fit: {play}."
    )

    return {
        "signal_score": score,
        "direction": direction,
        "confidence": float(round(confidence, 4)),
        "probabilities": {k: float(round(v, 4)) for k, v in probs.items()},
        "key_drivers": key_drivers,
        "warnings": warnings,
        "kalshi_trade_insight": kalshi_trade_insight,
    }


def load_snapshot(path: str | Path) -> dict[str, Any]:
    p = Path(path)
    with p.open("r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        raise ValueError("Snapshot JSON must be an object.")
    return data


def main(argv: Sequence[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Generate trading signal from BTC market intel JSON.")
    parser.add_argument("snapshot_json", help="Path to btc_market_intel_*.json")
    parser.add_argument("--pretty", action="store_true", help="Pretty-print JSON.")
    args = parser.parse_args(list(argv) if argv is not None else None)

    snap = load_snapshot(args.snapshot_json)
    out = generate_signal(snap)
    if args.pretty:
        print(json.dumps(out, indent=2, sort_keys=False))
    else:
        print(json.dumps(out))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

