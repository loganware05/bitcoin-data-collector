from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class IndicatorConfig:
    swing_len: int = 5
    sweep_max_lookback_bars: int = 400
    atr_period: int = 14
    ifvg_vol_mult: float = 1.0
    ifvg_max_zones: int = 6


def _to_candles_df(candles: Any) -> pd.DataFrame:
    """
    Normalize snapshot `market_data.candles_15m` rows into a sorted DataFrame.
    Expected row keys: timestamp, open, high, low, close, volume.
    """
    if not isinstance(candles, list) or not candles:
        return pd.DataFrame(columns=["timestamp", "open", "high", "low", "close", "volume"])
    df = pd.DataFrame(candles)
    for col in ("timestamp", "open", "high", "low", "close", "volume"):
        if col not in df.columns:
            df[col] = np.nan
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True, errors="coerce")
    for col in ("open", "high", "low", "close", "volume"):
        df[col] = pd.to_numeric(df[col], errors="coerce")
    df = df.dropna(subset=["timestamp", "open", "high", "low", "close"]).sort_values("timestamp").reset_index(drop=True)
    return df


def _true_range(high: pd.Series, low: pd.Series, close: pd.Series) -> pd.Series:
    prev_close = close.shift(1)
    tr = pd.concat([(high - low).abs(), (high - prev_close).abs(), (low - prev_close).abs()], axis=1).max(axis=1)
    return tr


def compute_atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    if df.empty:
        return pd.Series(dtype=float)
    tr = _true_range(df["high"], df["low"], df["close"])
    atr = tr.rolling(period, min_periods=period).mean()
    return atr


def _confirmed_pivots(series: pd.Series, swing_len: int, mode: str) -> pd.Series:
    """
    Causal pivot detection with confirmation delay.
    A pivot at index i is only known at i+swing_len.
    Returns a series with pivot value placed at the confirmation index.
    """
    n = len(series)
    out = pd.Series(np.nan, index=series.index, dtype=float)
    if n == 0:
        return out
    L = max(1, int(swing_len))
    # For each center i, check window [i-L, i+L] and emit at i+L.
    for i in range(L, n - L):
        window = series.iloc[i - L : i + L + 1]
        if window.isna().any():
            continue
        val = float(series.iloc[i])
        if mode == "high":
            if val >= float(window.max()) - 1e-12:
                out.iloc[i + L] = val
        else:
            if val <= float(window.min()) + 1e-12:
                out.iloc[i + L] = val
    return out


def compute_liquidity_sweeps(candles_15m: pd.DataFrame, cfg: IndicatorConfig) -> pd.DataFrame:
    """
    Liquidity sweeps:
    - Detect confirmed swing highs/lows (pivot, with confirmation delay).
    - A bearish sweep happens when current high breaches last swing high, but closes back below it.
    - A bullish sweep happens when current low breaches last swing low, but closes back above it.
    Emits numeric features per bar (aligned to input).
    """
    if candles_15m.empty:
        return pd.DataFrame()

    df = candles_15m.copy()
    atr = compute_atr(df, period=cfg.atr_period)
    piv_hi_conf = _confirmed_pivots(df["high"], cfg.swing_len, mode="high")
    piv_lo_conf = _confirmed_pivots(df["low"], cfg.swing_len, mode="low")

    last_swing_high = np.nan
    last_swing_low = np.nan
    last_bull_sweep_idx = -1
    last_bear_sweep_idx = -1

    sweep_detected = np.zeros(len(df), dtype=float)
    sweep_direction = np.zeros(len(df), dtype=float)
    bars_since_sweep = np.full(len(df), np.nan, dtype=float)
    bars_since_bull = np.full(len(df), np.nan, dtype=float)
    bars_since_bear = np.full(len(df), np.nan, dtype=float)
    wick_size_atr = np.zeros(len(df), dtype=float)
    reversal_body_pct = np.zeros(len(df), dtype=float)

    max_lb = max(10, int(cfg.sweep_max_lookback_bars))

    for t in range(len(df)):
        piv_h = piv_hi_conf.iloc[t]
        if np.isfinite(piv_h):
            last_swing_high = float(piv_h)
        piv_l = piv_lo_conf.iloc[t]
        if np.isfinite(piv_l):
            last_swing_low = float(piv_l)

        high = float(df["high"].iloc[t])
        low = float(df["low"].iloc[t])
        open_ = float(df["open"].iloc[t])
        close = float(df["close"].iloc[t])

        atr_t = float(atr.iloc[t]) if t < len(atr) and np.isfinite(atr.iloc[t]) else np.nan
        body = abs(close - open_)
        rng = max(high - low, 1e-12)
        reversal_body_pct[t] = float(body / rng)

        did = False
        dir_ = 0.0
        wick = 0.0

        if np.isfinite(last_swing_high):
            if high > last_swing_high and close < last_swing_high:
                did = True
                dir_ = -1.0
                wick = max(high - max(open_, close), 0.0)
                last_bear_sweep_idx = t
        if (not did) and np.isfinite(last_swing_low):
            if low < last_swing_low and close > last_swing_low:
                did = True
                dir_ = +1.0
                wick = max(min(open_, close) - low, 0.0)
                last_bull_sweep_idx = t

        sweep_detected[t] = 1.0 if did else 0.0
        sweep_direction[t] = dir_
        if np.isfinite(atr_t) and atr_t > 0:
            wick_size_atr[t] = float(wick / atr_t)
        else:
            wick_size_atr[t] = 0.0

        last_any = max(last_bull_sweep_idx, last_bear_sweep_idx)
        if last_any >= 0:
            bars_since_sweep[t] = float(min(t - last_any, max_lb))
        if last_bull_sweep_idx >= 0:
            bars_since_bull[t] = float(min(t - last_bull_sweep_idx, max_lb))
        if last_bear_sweep_idx >= 0:
            bars_since_bear[t] = float(min(t - last_bear_sweep_idx, max_lb))

    out = pd.DataFrame(
        {
            "timestamp": df["timestamp"].values,
            "sweep_detected": sweep_detected,
            "sweep_direction": sweep_direction,
            "time_since_sweep_bars": np.nan_to_num(bars_since_sweep, nan=float(max_lb)),
            "bars_since_bull_sweep": np.nan_to_num(bars_since_bull, nan=float(max_lb)),
            "bars_since_bear_sweep": np.nan_to_num(bars_since_bear, nan=float(max_lb)),
            "sweep_wick_size_atr": wick_size_atr,
            "sweep_reversal_body_pct": reversal_body_pct,
        }
    )
    return out


@dataclass
class _IfvgZone:
    direction: int  # +1 bullish support, -1 bearish resistance
    top: float
    bottom: float
    confirmed_at: int
    mitigated_at: int | None = None


def _distance_to_zone(close: float, zone: _IfvgZone) -> float:
    if zone.bottom <= close <= zone.top:
        return 0.0
    # Signed: positive means price above zone, negative below zone.
    if close > zone.top:
        return float(close - zone.top)
    return float(close - zone.bottom)


def compute_ifvg_features(candles_15m: pd.DataFrame, cfg: IndicatorConfig) -> pd.DataFrame:
    """
    IFVG state machine:
    - Detect FVG candidates via 3-candle condition.
    - Apply ATR filter on gap size.
    - Confirm inversion later; then the inverted zone becomes an IFVG (support/resistance).
    - Track active IFVG zones (bounded FIFO).
    Emits numeric features per bar (aligned to input).
    """
    if candles_15m.empty:
        return pd.DataFrame()

    df = candles_15m.copy()
    atr = compute_atr(df, period=cfg.atr_period)

    # pending candidates: {"type": "bull_fvg"|"bear_fvg", "top":float, "bottom":float, "detected_at":int}
    pending: list[dict[str, Any]] = []
    zones: list[_IfvgZone] = []
    last_confirmed_idx = -1
    last_mitigated_idx = -1

    ifvg_active = np.zeros(len(df), dtype=float)
    ifvg_direction = np.zeros(len(df), dtype=float)
    distance_to_ifvg = np.zeros(len(df), dtype=float)
    ifvg_mitigated = np.zeros(len(df), dtype=float)
    bars_since_confirmed = np.full(len(df), np.nan, dtype=float)
    bars_since_mitigated = np.full(len(df), np.nan, dtype=float)

    max_z = max(1, int(cfg.ifvg_max_zones))

    for t in range(len(df)):
        close_t = float(df["close"].iloc[t])
        high_t = float(df["high"].iloc[t])
        low_t = float(df["low"].iloc[t])

        atr_t = float(atr.iloc[t]) if np.isfinite(atr.iloc[t]) else np.nan
        atr_thresh = (float(cfg.ifvg_vol_mult) * atr_t) if np.isfinite(atr_t) else np.nan

        # Detect new FVG candidates at t (needs t-2)
        if t >= 2:
            high_t2 = float(df["high"].iloc[t - 2])
            low_t2 = float(df["low"].iloc[t - 2])

            # Bull FVG candidate: low[t] > high[t-2] (gap up)
            if low_t > high_t2:
                gap = float(low_t - high_t2)
                if (not np.isfinite(atr_thresh)) or (gap > atr_thresh):
                    pending.append({"type": "bull_fvg", "top": float(low_t), "bottom": float(high_t2), "detected_at": t})

            # Bear FVG candidate: high[t] < low[t-2] (gap down)
            if high_t < low_t2:
                gap = float(low_t2 - high_t)
                if (not np.isfinite(atr_thresh)) or (gap > atr_thresh):
                    pending.append({"type": "bear_fvg", "top": float(low_t2), "bottom": float(high_t), "detected_at": t})

        # Confirm inversions for pending candidates
        still_pending: list[dict[str, Any]] = []
        for cand in pending:
            ctype = cand["type"]
            top = float(cand["top"])
            bottom = float(cand["bottom"])
            # Inversion confirmation:
            # - Bull FVG -> bearish IFVG if later close < bottom
            # - Bear FVG -> bullish IFVG if later close > top
            if ctype == "bull_fvg":
                if close_t < bottom:
                    zones.append(_IfvgZone(direction=-1, top=top, bottom=bottom, confirmed_at=t))
                    last_confirmed_idx = t
                else:
                    still_pending.append(cand)
            else:
                if close_t > top:
                    zones.append(_IfvgZone(direction=+1, top=top, bottom=bottom, confirmed_at=t))
                    last_confirmed_idx = t
                else:
                    still_pending.append(cand)
        pending = still_pending

        # Bound number of active zones (keep most recent by confirmation time)
        if len(zones) > max_z:
            zones = sorted(zones, key=lambda z: z.confirmed_at)[-max_z:]

        # Mitigation updates: remove zones when invalidated
        active_zones: list[_IfvgZone] = []
        mitigated_this_bar = False
        for z in zones:
            if z.mitigated_at is not None:
                continue
            if z.direction == +1:
                # bullish support mitigated if close < bottom
                if close_t < z.bottom:
                    z.mitigated_at = t
                    last_mitigated_idx = t
                    mitigated_this_bar = True
                    continue
            else:
                # bearish resistance mitigated if close > top
                if close_t > z.top:
                    z.mitigated_at = t
                    last_mitigated_idx = t
                    mitigated_this_bar = True
                    continue
            active_zones.append(z)

        zones = active_zones + [z for z in zones if z.mitigated_at is not None]

        # Choose nearest active zone for feature emission
        if active_zones:
            dists = [abs(_distance_to_zone(close_t, z)) for z in active_zones]
            k = int(np.argmin(dists))
            z = active_zones[k]
            ifvg_active[t] = 1.0
            ifvg_direction[t] = float(z.direction)
            distance_to_ifvg[t] = float(_distance_to_zone(close_t, z))
        else:
            ifvg_active[t] = 0.0
            ifvg_direction[t] = 0.0
            distance_to_ifvg[t] = 0.0

        ifvg_mitigated[t] = 1.0 if mitigated_this_bar else 0.0
        if last_confirmed_idx >= 0:
            bars_since_confirmed[t] = float(t - last_confirmed_idx)
        if last_mitigated_idx >= 0:
            bars_since_mitigated[t] = float(t - last_mitigated_idx)

    out = pd.DataFrame(
        {
            "timestamp": df["timestamp"].values,
            "ifvg_active": ifvg_active,
            "ifvg_direction": ifvg_direction,
            "distance_to_ifvg_zone": distance_to_ifvg,
            "ifvg_mitigated": ifvg_mitigated,
            "bars_since_ifvg_confirmed": np.nan_to_num(bars_since_confirmed, nan=float(len(df))),
            "bars_since_ifvg_mitigated": np.nan_to_num(bars_since_mitigated, nan=float(len(df))),
        }
    )
    return out


def compute_indicator_features(
    snapshot: dict[str, Any] | None = None,
    candles_15m: pd.DataFrame | None = None,
    cfg: IndicatorConfig | None = None,
) -> tuple[pd.DataFrame, list[str]]:
    """
    Main entrypoint.
    Provide either:
    - `snapshot` containing `market_data.candles_15m`, or
    - `candles_15m` DataFrame directly.

    Returns (features_df, warnings). `features_df` is aligned to candle timestamps.
    """
    cfg = cfg or IndicatorConfig()
    warnings: list[str] = []

    if candles_15m is None:
        candles = (snapshot or {}).get("market_data", {}).get("candles_15m") if isinstance(snapshot, dict) else None
        candles_15m = _to_candles_df(candles)

    if candles_15m.empty or len(candles_15m) < max(50, cfg.atr_period + 5):
        warnings.append("candles_15m missing or too short for indicators; skipping indicator features.")
        return pd.DataFrame(), warnings

    sweeps = compute_liquidity_sweeps(candles_15m, cfg)
    ifvg = compute_ifvg_features(candles_15m, cfg)
    out = sweeps.merge(ifvg, on="timestamp", how="left", validate="one_to_one")
    return out, warnings


__all__ = [
    "IndicatorConfig",
    "compute_indicator_features",
    "compute_liquidity_sweeps",
    "compute_ifvg_features",
]

