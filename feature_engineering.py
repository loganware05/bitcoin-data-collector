from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd

from indicator_engine import IndicatorConfig, compute_indicator_features


@dataclass(frozen=True)
class FeatureConfig:
    # Candle-based returns from 15m closes
    ret_1h_bars: int = 4
    ret_4h_bars: int = 16
    ret_24h_bars: int = 96

    # Vol/volume windows in bars (15m)
    vol_windows: tuple[int, ...] = (16, 64, 256)  # 4h, 16h, ~2.7d
    volume_z_window: int = 64
    volume_roc_window: int = 16

    # Clipping / numeric safety
    clip_z: float = 8.0

    indicator_cfg: IndicatorConfig = IndicatorConfig()


def _safe_num(x: Any) -> float:
    try:
        if x is None:
            return float("nan")
        if isinstance(x, bool):
            return float("nan")
        return float(x)
    except (TypeError, ValueError):
        return float("nan")


def _get(snapshot: dict[str, Any], *path: str) -> Any:
    cur: Any = snapshot
    for p in path:
        if not isinstance(cur, dict):
            return None
        cur = cur.get(p)
    return cur


def _candles_df_from_snapshot(snapshot: dict[str, Any]) -> pd.DataFrame:
    candles = _get(snapshot, "market_data", "candles_15m")
    if not isinstance(candles, list):
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


def _log_returns(close: pd.Series) -> pd.Series:
    close = pd.to_numeric(close, errors="coerce")
    return np.log(close / close.shift(1))


def _rolling_z(x: pd.Series, window: int) -> pd.Series:
    mu = x.rolling(window, min_periods=max(3, window // 3)).mean()
    sd = x.rolling(window, min_periods=max(3, window // 3)).std(ddof=0)
    z = (x - mu) / sd.replace(0.0, np.nan)
    return z


def build_features(
    snapshot: dict[str, Any],
    candles_15m_df: pd.DataFrame | None = None,
    cfg: FeatureConfig | None = None,
) -> tuple[pd.Series, dict[str, Any]]:
    """
    Build a single ML-ready numeric feature row for the snapshot timestamp.
    Returns (X_row, meta) where:
      - X_row is a pandas Series of numeric scalars (NaNs allowed; caller may impute/drop).
      - meta contains warnings + a minimal trace for debugging.
    """
    cfg = cfg or FeatureConfig()
    warnings: list[str] = []

    if candles_15m_df is None:
        candles_15m_df = _candles_df_from_snapshot(snapshot)

    if candles_15m_df.empty or len(candles_15m_df) < max(cfg.ret_24h_bars + 5, 50):
        warnings.append("candles_15m missing or too short; candle-derived features degraded.")

    # Candle-derived features (use last bar)
    close = candles_15m_df["close"] if not candles_15m_df.empty else pd.Series(dtype=float)
    vol = candles_15m_df["volume"] if (not candles_15m_df.empty and "volume" in candles_15m_df.columns) else pd.Series(dtype=float)
    lr = _log_returns(close) if not candles_15m_df.empty else pd.Series(dtype=float)

    def last_shifted_logret(bars: int) -> float:
        if candles_15m_df.empty or len(close) <= bars:
            return float("nan")
        c0 = float(close.iloc[-1])
        c1 = float(close.iloc[-1 - bars])
        if not np.isfinite(c0) or not np.isfinite(c1) or c1 <= 0 or c0 <= 0:
            return float("nan")
        return float(np.log(c0 / c1))

    features: dict[str, float] = {
        "ret_log_1h": last_shifted_logret(cfg.ret_1h_bars),
        "ret_log_4h": last_shifted_logret(cfg.ret_4h_bars),
        "ret_log_24h": last_shifted_logret(cfg.ret_24h_bars),
    }

    # Rolling vol regimes: std of log returns
    if not candles_15m_df.empty and not lr.empty:
        for w in cfg.vol_windows:
            v = float(lr.rolling(w, min_periods=max(5, w // 3)).std(ddof=0).iloc[-1]) if len(lr) else float("nan")
            features[f"vol_logret_{w}"] = v
        # Regime flags based on in-sample quantiles of the longest window (causal at t)
        w_long = max(cfg.vol_windows)
        vol_long = lr.rolling(w_long, min_periods=max(5, w_long // 3)).std(ddof=0)
        if len(vol_long.dropna()) >= 30:
            q33 = float(vol_long.dropna().quantile(0.33))
            q66 = float(vol_long.dropna().quantile(0.66))
            cur = float(vol_long.iloc[-1]) if np.isfinite(vol_long.iloc[-1]) else float("nan")
            features["vol_regime_low"] = 1.0 if np.isfinite(cur) and cur <= q33 else 0.0
            features["vol_regime_high"] = 1.0 if np.isfinite(cur) and cur >= q66 else 0.0
        else:
            features["vol_regime_low"] = float("nan")
            features["vol_regime_high"] = float("nan")

    # Volume momentum
    if not candles_15m_df.empty and not vol.empty:
        vz = _rolling_z(np.log1p(vol), cfg.volume_z_window)
        features["volume_log_z"] = float(vz.iloc[-1]) if len(vz) else float("nan")
        roc_w = max(1, int(cfg.volume_roc_window))
        if len(vol) > roc_w and np.isfinite(vol.iloc[-1]) and np.isfinite(vol.iloc[-1 - roc_w]) and float(vol.iloc[-1 - roc_w]) >= 0:
            denom = float(vol.iloc[-1 - roc_w]) + 1e-9
            features["volume_roc"] = float((float(vol.iloc[-1]) - float(vol.iloc[-1 - roc_w])) / denom)
        else:
            features["volume_roc"] = float("nan")
    else:
        features["volume_log_z"] = float("nan")
        features["volume_roc"] = float("nan")

    # Snapshot orderbook / liquidity features
    features.update(
        {
            "spread_pct": _safe_num(_get(snapshot, "liquidity_data", "spread_pct")),
            "slippage_pct_for_notional": _safe_num(_get(snapshot, "liquidity_data", "slippage_pct_for_notional")),
            "order_book_depth_usd": _safe_num(_get(snapshot, "liquidity_data", "order_book_depth_usd")),
            "buy_wall_usd_top10": _safe_num(_get(snapshot, "liquidity_data", "buy_wall_usd_top10")),
            "sell_wall_usd_top10": _safe_num(_get(snapshot, "liquidity_data", "sell_wall_usd_top10")),
            "buy_sell_pressure_ratio": _safe_num(_get(snapshot, "liquidity_data", "buy_sell_pressure_ratio")),
        }
    )

    # Derived wall imbalance (bounded)
    bw = features["buy_wall_usd_top10"]
    sw = features["sell_wall_usd_top10"]
    if np.isfinite(bw) and np.isfinite(sw) and (bw + sw) > 0:
        features["wall_imbalance"] = float((bw - sw) / (bw + sw))
    else:
        features["wall_imbalance"] = float("nan")

    pr = features["buy_sell_pressure_ratio"]
    if np.isfinite(pr) and pr > 0:
        features["log_pressure_ratio"] = float(np.log(pr))
    else:
        features["log_pressure_ratio"] = float("nan")

    # Sentiment encoding
    fng = _safe_num(_get(snapshot, "sentiment_data", "fear_greed_value"))
    features["fear_greed_value"] = fng
    if np.isfinite(fng):
        features["fear_flag"] = 1.0 if fng < 30 else 0.0
        features["greed_flag"] = 1.0 if fng > 70 else 0.0
    else:
        features["fear_flag"] = float("nan")
        features["greed_flag"] = float("nan")

    # Macro regime
    features["corr_btc_spx"] = _safe_num(_get(snapshot, "macro_data", "corr_btc_spx"))
    features["corr_btc_qqq"] = _safe_num(_get(snapshot, "macro_data", "corr_btc_qqq"))
    for name in ("corr_btc_spx", "corr_btc_qqq"):
        v = features[name]
        if np.isfinite(v):
            features[f"{name}_abs"] = float(abs(v))
            features[f"{name}_high"] = 1.0 if abs(v) >= 0.35 else 0.0
        else:
            features[f"{name}_abs"] = float("nan")
            features[f"{name}_high"] = float("nan")

    # Simple liquidity stress composites / flags
    spread = features["spread_pct"]
    slip = features["slippage_pct_for_notional"]
    depth = features["order_book_depth_usd"]
    if np.isfinite(spread) and np.isfinite(slip):
        features["microstructure_stress"] = float(spread + 0.25 * slip)
    else:
        features["microstructure_stress"] = float("nan")
    if np.isfinite(depth):
        features["thin_book_flag"] = 1.0 if depth < 250_000 else 0.0
    else:
        features["thin_book_flag"] = float("nan")

    # Custom indicators (sweeps + IFVG)
    ind_df, ind_warn = compute_indicator_features(snapshot=snapshot, candles_15m=candles_15m_df, cfg=cfg.indicator_cfg)
    warnings.extend(ind_warn)
    if not ind_df.empty:
        last = ind_df.iloc[-1].to_dict()
        for k, v in last.items():
            if k == "timestamp":
                continue
            features[k] = _safe_num(v)
    else:
        # ensure stable columns exist
        for k in (
            "sweep_detected",
            "sweep_direction",
            "time_since_sweep_bars",
            "bars_since_bull_sweep",
            "bars_since_bear_sweep",
            "sweep_wick_size_atr",
            "sweep_reversal_body_pct",
            "ifvg_active",
            "ifvg_direction",
            "distance_to_ifvg_zone",
            "ifvg_mitigated",
            "bars_since_ifvg_confirmed",
            "bars_since_ifvg_mitigated",
        ):
            features[k] = float("nan")

    # Clip extreme values for numerical stability (training will still standardize)
    X = pd.Series(features, dtype="float64")
    for col in X.index:
        v = X[col]
        if not np.isfinite(v):
            continue
        if "z" in col or "log_pressure_ratio" in col:
            X[col] = float(np.clip(v, -cfg.clip_z, cfg.clip_z))
        if col.startswith("ret_log_") or col.startswith("vol_logret_"):
            X[col] = float(np.clip(v, -1.0, 1.0))
        if col.endswith("_pct") or col.endswith("_roc"):
            X[col] = float(np.clip(v, -10.0, 10.0))

    meta = {
        "snapshot_timestamp": _get(snapshot, "timestamp"),
        "candles_rows": int(len(candles_15m_df)) if candles_15m_df is not None else 0,
        "warnings": warnings,
    }
    return X, meta


__all__ = ["FeatureConfig", "build_features"]

