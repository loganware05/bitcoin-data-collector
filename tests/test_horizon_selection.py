from __future__ import annotations

from hourly_probability_model import select_best_horizon


def test_horizon_12_minutes():
    assert select_best_horizon(12) == "15m"


def test_horizon_42_minutes():
    assert select_best_horizon(42) == "60m"


def test_horizon_192_minutes():
    assert select_best_horizon(192) == "4h"


def test_horizon_1080_minutes():
    assert select_best_horizon(1080) == "24h"


def test_horizon_boundaries():
    assert select_best_horizon(22.5) == "15m"
    assert select_best_horizon(22.6) == "30m"
    assert select_best_horizon(37.5) == "30m"
    assert select_best_horizon(37.6) == "60m"
    assert select_best_horizon(150) == "60m"
    assert select_best_horizon(150.1) == "4h"
    assert select_best_horizon(840) == "4h"
    assert select_best_horizon(840.1) == "24h"
