from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Iterable, Literal

import numpy as np
import pandas as pd

Outcome = Literal["up", "down", "range"]
OUTCOMES: tuple[Outcome, Outcome, Outcome] = ("up", "down", "range")


def _as_outcome_series(y_true: Iterable[str]) -> pd.Series:
    if isinstance(y_true, pd.Series):
        s = y_true.astype("string").copy()
    else:
        s = pd.Series(list(y_true), dtype="string")
    # normalize common variants
    s = s.str.lower().str.strip()
    s = s.replace(
        {
            "up_move": "up",
            "up_move_24h": "up",
            "down_move": "down",
            "down_move_24h": "down",
            "range_bound": "range",
            "range_bound_24h": "range",
        }
    )
    return s


def confusion_matrix_3way(y_true: Iterable[str], y_pred: Iterable[str]) -> pd.DataFrame:
    yt = _as_outcome_series(y_true)
    yp = _as_outcome_series(y_pred)
    cm = pd.crosstab(yt, yp, rownames=["actual"], colnames=["pred"], dropna=False)
    for k in OUTCOMES:
        if k not in cm.index:
            cm.loc[k] = 0
        if k not in cm.columns:
            cm[k] = 0
    cm = cm.loc[list(OUTCOMES), list(OUTCOMES)]
    return cm.astype(int)


def accuracy(y_true: Iterable[str], y_pred: Iterable[str]) -> float:
    yt = _as_outcome_series(y_true)
    yp = _as_outcome_series(y_pred)
    ok = (yt == yp) & yt.notna() & yp.notna()
    denom = int(ok.shape[0])
    return float(ok.sum() / denom) if denom else float("nan")


@dataclass(frozen=True)
class BinaryPR:
    precision: float
    recall: float
    tp: int
    fp: int
    fn: int


def precision_recall_for_label(y_true: Iterable[str], y_pred: Iterable[str], positive: Outcome) -> BinaryPR:
    yt = _as_outcome_series(y_true)
    yp = _as_outcome_series(y_pred)
    yt_pos = yt == positive
    yp_pos = yp == positive

    tp = int((yt_pos & yp_pos).sum())
    fp = int((~yt_pos & yp_pos).sum())
    fn = int((yt_pos & ~yp_pos).sum())

    precision = tp / (tp + fp) if (tp + fp) else float("nan")
    recall = tp / (tp + fn) if (tp + fn) else float("nan")
    return BinaryPR(float(precision), float(recall), tp, fp, fn)


def multiclass_brier_score(
    y_true: Iterable[str],
    p_up: Iterable[float],
    p_down: Iterable[float],
    p_range: Iterable[float],
) -> float:
    yt = _as_outcome_series(y_true)
    p = pd.DataFrame({"up": p_up, "down": p_down, "range": p_range}).astype(float)
    p = p.clip(lower=0.0, upper=1.0)
    row_sum = p.sum(axis=1).replace(0.0, np.nan)
    p = p.div(row_sum, axis=0)

    y = pd.DataFrame(
        {
            "up": (yt == "up").astype(float),
            "down": (yt == "down").astype(float),
            "range": (yt == "range").astype(float),
        }
    )
    # mean over samples of sum_k (p_k - y_k)^2
    dif = (p - y) ** 2
    return float(dif.sum(axis=1).mean())


def multiclass_log_loss(
    y_true: Iterable[str],
    p_up: Iterable[float],
    p_down: Iterable[float],
    p_range: Iterable[float],
    eps: float = 1e-15,
) -> float:
    yt = _as_outcome_series(y_true)
    p = pd.DataFrame({"up": p_up, "down": p_down, "range": p_range}).astype(float)
    p = p.clip(lower=0.0, upper=1.0)
    row_sum = p.sum(axis=1).replace(0.0, np.nan)
    p = p.div(row_sum, axis=0)
    p = p.clip(lower=eps, upper=1.0 - eps)

    # vectorized: if any labels are missing/unknown, ignore those rows
    ll_parts: list[np.ndarray] = []
    for k in OUTCOMES:
        mask = (yt == k).to_numpy()
        if mask.any():
            ll_parts.append((-np.log(p[k].to_numpy()))[mask])
    if not ll_parts:
        return float("nan")
    return float(np.mean(np.concatenate(ll_parts)))


def predicted_class(p_up: Iterable[float], p_down: Iterable[float], p_range: Iterable[float]) -> pd.Series:
    p = pd.DataFrame({"up": p_up, "down": p_down, "range": p_range}).astype(float)
    return p.idxmax(axis=1).astype("string")


def calibration_table_binary(
    p: Iterable[float],
    y_true_binary: Iterable[bool],
    n_bins: int = 10,
) -> pd.DataFrame:
    """
    Returns a table with per-bin:
      - mean_pred: mean predicted probability in bin
      - frac_pos: empirical positive rate
      - count: samples
    """
    s_p = pd.Series(list(p), dtype="float64").clip(0.0, 1.0)
    s_y = pd.Series(list(y_true_binary), dtype="boolean")

    df = pd.DataFrame({"p": s_p, "y": s_y}).dropna()
    if df.empty:
        return pd.DataFrame(columns=["bin", "mean_pred", "frac_pos", "count"])

    # bins as [0,1] quantized (fixed), so comparisons are stable across runs
    edges = np.linspace(0.0, 1.0, n_bins + 1)
    df["bin"] = pd.cut(df["p"], bins=edges, include_lowest=True, right=True)
    out = (
        df.groupby("bin", observed=False)
        .agg(mean_pred=("p", "mean"), frac_pos=("y", "mean"), count=("y", "size"))
        .reset_index()
    )
    out["bin"] = out["bin"].astype("string")
    return out

