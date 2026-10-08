"""Unit tests for execution-gate Phase A CPCV/DSR helpers."""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts" / "execution-gate"))

from phase_a_cpcv_dsr import (  # noqa: E402
    cpcv_splits,
    deflated_sharpe_ratio,
    evaluate,
    sharpe_ratio,
)


def test_sharpe_ratio_basic():
    r = np.array([0.01, 0.02, -0.005, 0.015, 0.0])
    s = sharpe_ratio(r)
    assert np.isfinite(s)


def test_cpcv_reject_on_regime_break():
    rng = np.random.default_rng(0)
    a = rng.normal(0.05, 0.02, size=60)
    b = rng.normal(-0.05, 0.02, size=60)
    returns = np.concatenate([a, b])
    splits = cpcv_splits(returns, n_groups=6, n_test_groups=2, purge=1, embargo=1)
    assert splits
    assert any(s.rejected for s in splits)


def test_evaluate_demo_not_phase_a_pass():
    rng = np.random.default_rng(1)
    returns = rng.normal(0.0, 0.1, size=100)
    report = evaluate(
        returns,
        data_class="plumbing_demo",
        source="unit-test",
        n_groups=6,
        n_test_groups=2,
        purge=1,
        embargo=1,
        n_trials=25,
    )
    assert report["approved_for_execution"] is False
    assert report["phase_a_pass"] is False
    assert report["blocker_if_any"]


def test_dsr_returns_keys():
    out = deflated_sharpe_ratio(0.5, n_obs=100, n_trials=25)
    assert "dsr" in out and "pass" in out
