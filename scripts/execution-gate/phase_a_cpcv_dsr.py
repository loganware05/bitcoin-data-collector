#!/usr/bin/env python3
"""Phase A — CPCV + Deflated Sharpe + IS/OOS reject checks (non-execution).

Plumbing / research harness only. Does NOT place orders or enable live execution.
Passing this harness on fixture/demo series does NOT satisfy the
``non_fixture_backtests`` readiness gate.

Captain bars encoded:
- Combinatorial purged cross-validation (CPCV)
- Deflated Sharpe Ratio (DSR) before simulated trades count as evidence
- REJECT if IS/OOS Sharpe gap > ~1.5 OR IS/OOS ratio > 3.0
"""

from __future__ import annotations

import argparse
import json
import math
from dataclasses import dataclass
from datetime import datetime, timezone
from itertools import combinations
from pathlib import Path
from typing import Any

import numpy as np
from scipy import stats

# Captain acceptance bars (Phase A)
MAX_IS_OOS_SHARPE_GAP = 1.5
MAX_IS_OOS_SHARPE_RATIO = 3.0
DEFAULT_N_GROUPS = 6
DEFAULT_N_TEST_GROUPS = 2
DEFAULT_PURGE = 1
DEFAULT_EMBARGO = 1
DEFAULT_TRIALS = 25  # trials for DSR (strategy search multiplicity)


@dataclass
class SplitResult:
    train_idx: list[int]
    test_idx: list[int]
    train_sharpe: float
    test_sharpe: float
    gap: float
    ratio: float
    rejected: bool
    reject_reasons: list[str]


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def sharpe_ratio(returns: np.ndarray, eps: float = 1e-12) -> float:
    r = np.asarray(returns, dtype=float)
    r = r[np.isfinite(r)]
    if r.size < 2:
        return float("nan")
    mu = float(np.mean(r))
    sd = float(np.std(r, ddof=1))
    if sd < eps:
        return 0.0 if abs(mu) < eps else math.copysign(float("inf"), mu)
    return mu / sd * math.sqrt(r.size)  # per-sample t-stat style (not annualized)


def deflated_sharpe_ratio(
    observed_sharpe: float,
    n_obs: int,
    n_trials: int,
    skew: float = 0.0,
    kurt: float = 3.0,
) -> dict[str, float]:
    """Bailey & López de Prado Deflated Sharpe Ratio (simplified).

    Returns DSR probability that the true SR > 0 after adjusting for
    selection bias across ``n_trials`` independent trials.
    """
    if n_obs < 2 or not math.isfinite(observed_sharpe):
        return {"dsr": float("nan"), "sr_benchmark": float("nan"), "pass": 0.0}

    # Expected max SR under null of zero true SR (approx)
    e_max = (1.0 - np.euler_gamma) * stats.norm.ppf(1.0 - 1.0 / n_trials) + np.euler_gamma * stats.norm.ppf(
        1.0 - 1.0 / (n_trials * math.e)
    )
    # Variance of SR estimator
    sr_var = (
        1.0
        - skew * observed_sharpe
        + ((kurt - 1.0) / 4.0) * observed_sharpe**2
    ) / (n_obs - 1)
    sr_var = max(float(sr_var), 1e-12)
    sr_benchmark = float(e_max * math.sqrt(sr_var))
    # Prob(true SR > 0 | observed), vs selection-adjusted benchmark
    z = (observed_sharpe - sr_benchmark) / math.sqrt(sr_var)
    dsr = float(stats.norm.cdf(z))
    return {
        "dsr": dsr,
        "sr_benchmark": sr_benchmark,
        "z_score": float(z),
        "pass": 1.0 if dsr >= 0.95 else 0.0,
    }


def assign_groups(n: int, n_groups: int) -> np.ndarray:
    edges = np.linspace(0, n, n_groups + 1, dtype=int)
    groups = np.empty(n, dtype=int)
    for g in range(n_groups):
        groups[edges[g] : edges[g + 1]] = g
    return groups


def purged_train_mask(
    groups: np.ndarray,
    test_groups: set[int],
    purge: int,
    embargo: int,
) -> np.ndarray:
    """Drop train samples within purge/embargo distance of any test group."""
    n = groups.size
    is_test = np.isin(groups, list(test_groups))
    train = ~is_test
    # Expand test indices by purge+embargo on both sides (time-ordered)
    idx = np.where(is_test)[0]
    if idx.size == 0:
        return train
    ban = np.zeros(n, dtype=bool)
    radius = max(purge, 0) + max(embargo, 0)
    for i in idx:
        lo = max(0, i - radius)
        hi = min(n, i + radius + 1)
        ban[lo:hi] = True
    # Keep train only where not banned and not test
    return train & ~ban


def cpcv_splits(
    returns: np.ndarray,
    n_groups: int = DEFAULT_N_GROUPS,
    n_test_groups: int = DEFAULT_N_TEST_GROUPS,
    purge: int = DEFAULT_PURGE,
    embargo: int = DEFAULT_EMBARGO,
) -> list[SplitResult]:
    n = len(returns)
    groups = assign_groups(n, n_groups)
    results: list[SplitResult] = []
    for test_combo in combinations(range(n_groups), n_test_groups):
        test_set = set(test_combo)
        train_mask = purged_train_mask(groups, test_set, purge, embargo)
        test_mask = np.isin(groups, list(test_set))
        train_idx = np.where(train_mask)[0]
        test_idx = np.where(test_mask)[0]
        if train_idx.size < 2 or test_idx.size < 2:
            continue
        tr = sharpe_ratio(returns[train_idx])
        te = sharpe_ratio(returns[test_idx])
        gap = abs(tr - te) if math.isfinite(tr) and math.isfinite(te) else float("nan")
        if not math.isfinite(tr) or not math.isfinite(te) or abs(te) < 1e-12:
            ratio = float("inf")
        else:
            ratio = abs(tr / te)
        reasons: list[str] = []
        if math.isfinite(gap) and gap > MAX_IS_OOS_SHARPE_GAP:
            reasons.append(f"is_oos_gap>{MAX_IS_OOS_SHARPE_GAP}")
        if ratio > MAX_IS_OOS_SHARPE_RATIO:
            reasons.append(f"is_oos_ratio>{MAX_IS_OOS_SHARPE_RATIO}")
        results.append(
            SplitResult(
                train_idx=train_idx.tolist(),
                test_idx=test_idx.tolist(),
                train_sharpe=float(tr),
                test_sharpe=float(te),
                gap=float(gap) if math.isfinite(gap) else float("nan"),
                ratio=float(ratio) if math.isfinite(ratio) else float("inf"),
                rejected=bool(reasons),
                reject_reasons=reasons,
            )
        )
    return results


def load_returns_csv(path: Path, column: str = "return") -> np.ndarray:
    import csv

    vals: list[float] = []
    with path.open(newline="") as f:
        reader = csv.DictReader(f)
        if column not in (reader.fieldnames or []):
            # fall back to first numeric column
            for row in reader:
                for k, v in row.items():
                    try:
                        vals.append(float(v))
                        break
                    except (TypeError, ValueError):
                        continue
            return np.asarray(vals, dtype=float)
        for row in reader:
            try:
                vals.append(float(row[column]))
            except (TypeError, ValueError):
                continue
    return np.asarray(vals, dtype=float)


def load_returns_json(path: Path) -> np.ndarray:
    data = json.loads(path.read_text())
    if isinstance(data, list):
        if data and isinstance(data[0], dict):
            for key in ("return", "pnl", "r"):
                if key in data[0]:
                    return np.asarray([float(x[key]) for x in data], dtype=float)
            raise ValueError(f"JSON list objects missing return/pnl/r: {path}")
        return np.asarray([float(x) for x in data], dtype=float)
    if isinstance(data, dict):
        for key in ("returns", "pnl_series", "trade_returns"):
            if key in data:
                return np.asarray([float(x) for x in data[key]], dtype=float)
    raise ValueError(f"Unsupported JSON returns shape: {path}")


def demo_returns(n: int = 120, seed: int = 42) -> np.ndarray:
    """Synthetic series for harness smoke only — NOT edge evidence."""
    rng = np.random.default_rng(seed)
    # Mild positive drift + regime break mid-sample to exercise IS/OOS reject
    a = rng.normal(0.02, 0.08, size=n // 2)
    b = rng.normal(-0.01, 0.12, size=n - n // 2)
    return np.concatenate([a, b])


def evaluate(
    returns: np.ndarray,
    *,
    data_class: str,
    source: str,
    n_groups: int,
    n_test_groups: int,
    purge: int,
    embargo: int,
    n_trials: int,
) -> dict[str, Any]:
    splits = cpcv_splits(returns, n_groups, n_test_groups, purge, embargo)
    oos_sharpes = [s.test_sharpe for s in splits if math.isfinite(s.test_sharpe)]
    median_oos = float(np.median(oos_sharpes)) if oos_sharpes else float("nan")
    reject_rate = float(np.mean([s.rejected for s in splits])) if splits else 1.0
    skew = float(stats.skew(returns)) if returns.size >= 3 else 0.0
    kurt = float(stats.kurtosis(returns, fisher=False)) if returns.size >= 4 else 3.0
    full_sr = sharpe_ratio(returns)
    dsr = deflated_sharpe_ratio(full_sr, int(returns.size), n_trials, skew=skew, kurt=kurt)

    cpcv_pass = bool(splits) and reject_rate <= 0.5 and math.isfinite(median_oos) and median_oos > 0
    dsr_pass = bool(dsr.get("pass"))
    # Phase A overall: both CPCV and DSR must pass AND data must be non-fixture
    non_fixture = data_class in {"verdant_staging", "live_forward_paper", "non_fixture_market"}
    phase_a_pass = cpcv_pass and dsr_pass and non_fixture

    return {
        "schema": "bdc.execution_gate.phase_a.v1",
        "created_at": utc_now(),
        "approved_for_execution": False,
        "recommend_approved_for_execution": False,
        "data_class": data_class,
        "source": source,
        "n_obs": int(returns.size),
        "bars": {
            "max_is_oos_sharpe_gap": MAX_IS_OOS_SHARPE_GAP,
            "max_is_oos_sharpe_ratio": MAX_IS_OOS_SHARPE_RATIO,
            "dsr_pass_threshold": 0.95,
        },
        "config": {
            "n_groups": n_groups,
            "n_test_groups": n_test_groups,
            "purge": purge,
            "embargo": embargo,
            "n_trials": n_trials,
        },
        "full_sample_sharpe": full_sr if math.isfinite(full_sr) else None,
        "skew": skew,
        "kurtosis": kurt,
        "cpcv": {
            "n_splits": len(splits),
            "reject_rate": reject_rate,
            "median_oos_sharpe": median_oos if math.isfinite(median_oos) else None,
            "pass": cpcv_pass,
            "splits": [
                {
                    "train_sharpe": s.train_sharpe,
                    "test_sharpe": s.test_sharpe,
                    "gap": s.gap,
                    "ratio": s.ratio if math.isfinite(s.ratio) else None,
                    "rejected": s.rejected,
                    "reject_reasons": s.reject_reasons,
                    "n_train": len(s.train_idx),
                    "n_test": len(s.test_idx),
                }
                for s in splits
            ],
        },
        "dsr": {**dsr, "pass": dsr_pass},
        "phase_a_pass": phase_a_pass,
        "notes": [
            "Replay / settlement aggregate metrics are plumbing only — not edge proof.",
            "Simulated trade counts as evidence only after CPCV+DSR pass on non-fixture data.",
            "approved_for_execution remains false regardless of phase_a_pass.",
        ],
        "blocker_if_any": None
        if non_fixture
        else (
            f"data_class={data_class!r} cannot satisfy non_fixture_backtests gate; "
            "mount Verdant staging or supply --returns from live market series."
        ),
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--returns", type=Path, help="CSV or JSON returns series")
    ap.add_argument("--column", default="return")
    ap.add_argument(
        "--data-class",
        default="plumbing_demo",
        choices=[
            "plumbing_demo",
            "fixture",
            "settlement_replay",
            "verdant_staging",
            "live_forward_paper",
            "non_fixture_market",
        ],
    )
    ap.add_argument("--n-groups", type=int, default=DEFAULT_N_GROUPS)
    ap.add_argument("--n-test-groups", type=int, default=DEFAULT_N_TEST_GROUPS)
    ap.add_argument("--purge", type=int, default=DEFAULT_PURGE)
    ap.add_argument("--embargo", type=int, default=DEFAULT_EMBARGO)
    ap.add_argument("--n-trials", type=int, default=DEFAULT_TRIALS)
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args()

    if args.returns is None:
        returns = demo_returns()
        source = "synthetic:demo_returns(seed=42)"
        data_class = args.data_class
    else:
        path = args.returns
        if path.suffix.lower() == ".json":
            returns = load_returns_json(path)
        else:
            returns = load_returns_csv(path, args.column)
        source = str(path)
        data_class = args.data_class

    report = evaluate(
        returns,
        data_class=data_class,
        source=source,
        n_groups=args.n_groups,
        n_test_groups=args.n_test_groups,
        purge=args.purge,
        embargo=args.embargo,
        n_trials=args.n_trials,
    )
    args.out.parent.mkdir(parents=True, exist_ok=True)

    def _sanitize(obj: Any) -> Any:
        if isinstance(obj, float):
            if math.isnan(obj) or math.isinf(obj):
                return None
            return obj
        if isinstance(obj, dict):
            return {k: _sanitize(v) for k, v in obj.items()}
        if isinstance(obj, list):
            return [_sanitize(v) for v in obj]
        return obj

    clean = _sanitize(report)
    args.out.write_text(json.dumps(clean, indent=2) + "\n")
    summary = {
        "phase_a_pass": clean["phase_a_pass"],
        "data_class": clean["data_class"],
        "blocker_if_any": clean["blocker_if_any"],
        "cpcv_pass": clean["cpcv"]["pass"],
        "cpcv_reject_rate": clean["cpcv"]["reject_rate"],
        "dsr_pass": clean["dsr"]["pass"],
        "dsr": clean["dsr"].get("dsr"),
    }
    print(json.dumps(summary, indent=2))
    print("wrote", args.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
