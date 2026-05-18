from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from metrics import (
    calibration_table_binary,
    confusion_matrix_3way,
    multiclass_brier_score,
    multiclass_log_loss,
    predicted_class,
    precision_recall_for_label,
)
from signal_engine import SignalEngineConfig, generate_signal, load_snapshot


def _is_nan(x: Any) -> bool:
    try:
        return bool(pd.isna(x))
    except Exception:
        return False


def _undot_row(row: Mapping[str, Any]) -> dict[str, Any]:
    """
    Convert a flattened dict with dotted keys into the nested collector snapshot format.
    Handles `source_health.<name>.<field>` into nested objects.
    """
    out: dict[str, Any] = {}
    for k, v in row.items():
        if k is None:
            continue
        if _is_nan(v):
            v = None
        if not isinstance(k, str) or not k:
            continue

        parts = k.split(".")
        cur: dict[str, Any] = out
        for p in parts[:-1]:
            nxt = cur.get(p)
            if not isinstance(nxt, dict):
                nxt = {}
                cur[p] = nxt
            cur = nxt
        cur[parts[-1]] = v
    return out


def load_time_series(input_path: str | Path) -> pd.DataFrame:
    """
    Load a historical time series from:
    - a CSV with dotted columns (collector CSV)
    - a JSON list of snapshots
    - a directory containing many `btc_market_intel_*.json` snapshots
    - a single snapshot JSON (treated as length-1 series)
    Returns a DataFrame with at least:
      - timestamp (datetime64[ns, UTC])
      - snapshot (dict) nested in collector schema
      - spot_price_usd (float)
    """
    p = Path(input_path)
    if not p.exists():
        raise FileNotFoundError(str(p))

    snapshots: list[dict[str, Any]] = []
    if p.is_dir():
        for fp in sorted(p.glob("*.json")):
            try:
                snap = load_snapshot(fp)
            except Exception:
                continue
            if isinstance(snap, dict) and "timestamp" in snap:
                snapshots.append(snap)
    elif p.suffix.lower() == ".csv":
        df = pd.read_csv(p)
        rows = df.to_dict(orient="records")
        snapshots = [_undot_row(r) for r in rows]
    elif p.suffix.lower() == ".json":
        with p.open("r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, list):
            snapshots = [x for x in data if isinstance(x, dict)]
        elif isinstance(data, dict):
            snapshots = [data]
        else:
            raise ValueError("Unsupported JSON structure for time series input.")
    else:
        raise ValueError(f"Unsupported input type: {p}")

    if not snapshots:
        raise ValueError("No snapshots found/loaded.")

    ts = []
    spot = []
    for s in snapshots:
        ts.append(s.get("timestamp"))
        spot.append(((s.get("price_data") or {}).get("spot_price_usd")) if isinstance(s.get("price_data"), dict) else None)

    out = pd.DataFrame({"timestamp": ts, "spot_price_usd": spot, "snapshot": snapshots})
    out["timestamp"] = pd.to_datetime(out["timestamp"], utc=True, errors="coerce")
    out["spot_price_usd"] = pd.to_numeric(out["spot_price_usd"], errors="coerce")
    out = out.dropna(subset=["timestamp"]).sort_values("timestamp").reset_index(drop=True)
    return out


@dataclass(frozen=True)
class BacktestConfig:
    horizon: pd.Timedelta = pd.Timedelta(hours=24)
    range_threshold_pct: float = 0.01  # ±1%
    high_confidence_prob_threshold: float = 0.65
    strong_signal_score_threshold: int = 65  # |score-50| >= 15 -> stronger-than-neutral
    calibration_bins: int = 10


def label_outcome(current_price: float, future_price: float, range_threshold_pct: float) -> str:
    if not np.isfinite(current_price) or not np.isfinite(future_price) or current_price == 0:
        return "unknown"
    ret = (future_price - current_price) / current_price
    if abs(ret) < range_threshold_pct:
        return "range"
    if ret > 0:
        return "up"
    if ret < 0:
        return "down"
    return "range"


def _find_future_index(timestamps: pd.Series, horizon: pd.Timedelta) -> np.ndarray:
    """
    For each timestamp t_i, find the smallest j such that ts_j >= t_i + horizon.
    Returns array of indices (or -1 if none).
    """
    ts = pd.to_datetime(timestamps, utc=True, errors="coerce").values.astype("datetime64[ns]")
    target = (pd.to_datetime(timestamps, utc=True, errors="coerce") + horizon).values.astype("datetime64[ns]")
    idx = np.searchsorted(ts, target, side="left")
    idx = idx.astype(int)
    idx[idx >= len(ts)] = -1
    return idx


def run_backtest(
    df: pd.DataFrame,
    cfg: BacktestConfig | None = None,
    signal_cfg: SignalEngineConfig | None = None,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    cfg = cfg or BacktestConfig()
    signal_cfg = signal_cfg or SignalEngineConfig()

    if df.empty:
        raise ValueError("Empty time series.")

    df = df.copy()
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True, errors="coerce")
    df = df.dropna(subset=["timestamp"]).sort_values("timestamp").reset_index(drop=True)

    future_idx = _find_future_index(df["timestamp"], cfg.horizon)
    df["future_index"] = future_idx
    df = df[df["future_index"] >= 0].copy()
    df["future_index"] = df["future_index"].astype(int)
    if df.empty:
        raise ValueError(
            "No rows have a valid future window for the configured horizon. "
            "Provide more history or reduce `horizon`."
        )

    # Compute signal/probabilities at each t (replay-style)
    sig_out = []
    for snap in df["snapshot"].tolist():
        if not isinstance(snap, Mapping):
            snap = {}
        sig_out.append(generate_signal(snap, signal_cfg))

    df["signal_score"] = [x["signal_score"] for x in sig_out]
    df["direction"] = [x["direction"] for x in sig_out]
    df["confidence"] = [x["confidence"] for x in sig_out]
    df["p_up"] = [x["probabilities"].get("up_move_24h", np.nan) for x in sig_out]
    df["p_down"] = [x["probabilities"].get("down_move_24h", np.nan) for x in sig_out]
    df["p_range"] = [x["probabilities"].get("range_bound", np.nan) for x in sig_out]

    # Outcome labeling
    future_prices = df["future_index"].map(lambda j: float(df.loc[j, "spot_price_usd"]) if j in df.index else np.nan)
    df["future_price"] = pd.to_numeric(future_prices, errors="coerce")
    df["return"] = (df["future_price"] - df["spot_price_usd"]) / df["spot_price_usd"]
    df["y_true"] = [
        label_outcome(float(cp), float(fp), cfg.range_threshold_pct)
        for cp, fp in zip(df["spot_price_usd"].astype(float), df["future_price"].astype(float))
    ]

    # Drop any rows we couldn't label or couldn't score probabilistically
    df = df[df["y_true"].isin(["up", "down", "range"])].copy()
    df = df.dropna(subset=["p_up", "p_down", "p_range"])
    if df.empty:
        raise ValueError("After filtering missing labels/probabilities, no rows remain for evaluation.")

    # Predicted class via max probability
    df["y_pred"] = predicted_class(df["p_up"], df["p_down"], df["p_range"])

    # Metrics
    cm = confusion_matrix_3way(df["y_true"], df["y_pred"])
    acc = float((df["y_true"] == df["y_pred"]).mean())
    pr_up = precision_recall_for_label(df["y_true"], df["y_pred"], "up")
    pr_down = precision_recall_for_label(df["y_true"], df["y_pred"], "down")

    brier = multiclass_brier_score(df["y_true"], df["p_up"], df["p_down"], df["p_range"])
    logloss = multiclass_log_loss(df["y_true"], df["p_up"], df["p_down"], df["p_range"])

    # Edge detection slices
    df["max_prob"] = df[["p_up", "p_down", "p_range"]].max(axis=1)
    df["abs_score_from_neutral"] = (df["signal_score"].astype(float) - 50.0).abs()

    high_conf = df[df["max_prob"] >= cfg.high_confidence_prob_threshold]
    strong_signal = df[df["abs_score_from_neutral"] >= (cfg.strong_signal_score_threshold - 50)]

    high_conf_acc = float((high_conf["y_true"] == high_conf["y_pred"]).mean()) if len(high_conf) else float("nan")
    strong_signal_acc = (
        float((strong_signal["y_true"] == strong_signal["y_pred"]).mean()) if len(strong_signal) else float("nan")
    )

    edge_detected = (
        (np.isfinite(high_conf_acc) and high_conf_acc >= acc + 0.03)
        or (np.isfinite(strong_signal_acc) and strong_signal_acc >= acc + 0.03)
    )

    # Buckets
    bins = [-0.1, 20, 40, 60, 80, 100.1]
    labels = ["strong_bearish", "weak_bearish", "neutral", "weak_bullish", "strong_bullish"]
    df["signal_bucket"] = pd.cut(df["signal_score"], bins=bins, labels=labels)

    tmp = df.assign(correct=(df["y_true"] == df["y_pred"]).astype(float))
    bucket_perf = (
        tmp.groupby("signal_bucket", observed=False)
        .agg(n=("correct", "size"), accuracy=("correct", "mean"))
        .reset_index()
    )

    # Calibration tables (binary view per class)
    calib_up = calibration_table_binary(df["p_up"], df["y_true"] == "up", n_bins=cfg.calibration_bins)
    calib_down = calibration_table_binary(df["p_down"], df["y_true"] == "down", n_bins=cfg.calibration_bins)
    calib_range = calibration_table_binary(df["p_range"], df["y_true"] == "range", n_bins=cfg.calibration_bins)

    summary = {
        "n": int(len(df)),
        "horizon": str(cfg.horizon),
        "range_threshold_pct": float(cfg.range_threshold_pct),
        "accuracy": float(acc),
        "brier_score": float(brier),
        "log_loss": float(logloss),
        "precision_up": float(pr_up.precision),
        "recall_up": float(pr_up.recall),
        "precision_down": float(pr_down.precision),
        "recall_down": float(pr_down.recall),
        "high_confidence_n": int(len(high_conf)),
        "high_confidence_accuracy": float(high_conf_acc),
        "strong_signal_n": int(len(strong_signal)),
        "strong_signal_accuracy": float(strong_signal_acc),
        "edge_detected": bool(edge_detected),
        "confusion_matrix": cm.to_dict(),
        "bucket_performance": bucket_perf.to_dict(orient="records"),
        "calibration": {
            "up": calib_up.to_dict(orient="records"),
            "down": calib_down.to_dict(orient="records"),
            "range": calib_range.to_dict(orient="records"),
        },
    }

    return df, summary


def plot_outputs(results: pd.DataFrame, out_dir: str | Path) -> dict[str, str]:
    outp = Path(out_dir)
    outp.mkdir(parents=True, exist_ok=True)

    paths: dict[str, str] = {}

    # Calibration curve (Up and Down as separate binary reliability curves)
    fig, ax = plt.subplots()
    for name, p_col, y_mask in [
        ("up", "p_up", results["y_true"] == "up"),
        ("down", "p_down", results["y_true"] == "down"),
        ("range", "p_range", results["y_true"] == "range"),
    ]:
        tab = calibration_table_binary(results[p_col], y_mask, n_bins=10)
        if not tab.empty:
            ax.plot(tab["mean_pred"], tab["frac_pos"], marker="o", label=name)
    ax.plot([0, 1], [0, 1], linestyle="--", label="perfect")
    ax.set_xlabel("Predicted probability")
    ax.set_ylabel("Empirical frequency")
    ax.set_title("Calibration (reliability curves)")
    ax.legend()
    p1 = outp / "calibration_curve.png"
    fig.tight_layout()
    fig.savefig(p1, dpi=150)
    plt.close(fig)
    paths["calibration_curve"] = str(p1)

    # Cumulative accuracy over time
    fig, ax = plt.subplots()
    ok = (results["y_true"] == results["y_pred"]).astype(float)
    cum = ok.cumsum() / np.arange(1, len(ok) + 1)
    ax.plot(results["timestamp"], cum)
    ax.set_xlabel("Time")
    ax.set_ylabel("Cumulative accuracy")
    ax.set_title("Cumulative accuracy over time")
    fig.autofmt_xdate()
    p2 = outp / "cumulative_accuracy.png"
    fig.tight_layout()
    fig.savefig(p2, dpi=150)
    plt.close(fig)
    paths["cumulative_accuracy"] = str(p2)

    # Signal vs actual outcome (scatter: score vs realized return)
    fig, ax = plt.subplots()
    ax.scatter(results["signal_score"], results["return"], alpha=0.7)
    ax.set_xlabel("Signal score (0-100)")
    ax.set_ylabel(f"Forward return ({results.attrs.get('horizon', 'horizon')})")
    ax.set_title("Signal score vs realized forward return")
    p3 = outp / "signal_vs_outcome.png"
    fig.tight_layout()
    fig.savefig(p3, dpi=150)
    plt.close(fig)
    paths["signal_vs_outcome"] = str(p3)

    return paths


def main(argv: Sequence[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Backtest BTC signal engine as probability forecasts (Kalshi-style).")
    parser.add_argument("input", help="CSV time series, JSON list, directory of snapshots, or single snapshot JSON.")
    parser.add_argument("--horizon-hours", type=float, default=24.0, help="Prediction horizon in hours (default 24).")
    parser.add_argument(
        "--range-threshold-pct",
        type=float,
        default=0.01,
        help="Range-bound threshold as fraction (default 0.01 = ±1%).",
    )
    parser.add_argument("--out-json", default="backtest_summary.json", help="Where to write summary JSON.")
    parser.add_argument("--plot-dir", default="backtest_plots", help="Directory for matplotlib PNG outputs.")
    args = parser.parse_args(list(argv) if argv is not None else None)

    df = load_time_series(args.input)
    bt_cfg = BacktestConfig(
        horizon=pd.Timedelta(hours=float(args.horizon_hours)),
        range_threshold_pct=float(args.range_threshold_pct),
    )
    results, summary = run_backtest(df, cfg=bt_cfg)
    results.attrs["horizon"] = str(bt_cfg.horizon)

    plot_paths = plot_outputs(results, args.plot_dir)
    summary["plots"] = plot_paths

    with Path(args.out_json).open("w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2, sort_keys=False)

    print(json.dumps(summary, indent=2, sort_keys=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

