from __future__ import annotations

import numpy as np
import pandas as pd

from probability_calibration import (
    CalibratorConfig,
    SettlementProbabilityCalibrator,
    evaluate_calibration_slices,
)


def test_calibrator_reduces_gap_on_skewed_probs() -> None:
    rng = np.random.default_rng(42)
    n = 200
    raw = rng.uniform(0.15, 0.55, size=n)
    # Empirical YES rate rises with raw prob but raw is systematically low
    y = (rng.random(n) < (raw + 0.25)).astype(int)

    df = pd.DataFrame(
        {
            "model_yes_probability": raw,
            "y_true": y,
            "recommendation": ["NO TRADE"] * n,
        }
    )

    calibrator = SettlementProbabilityCalibrator()
    meta = calibrator.fit(df, cfg=CalibratorConfig(min_samples=30))
    assert calibrator.fitted
    assert meta["fit_source"] == "all_settled"
    assert meta["calibrated_max_calibration_gap"] <= meta["raw_max_calibration_gap"]

    p_cal, _ = calibrator.calibrate_yes_no(0.4)
    assert 0.01 <= p_cal <= 0.99


def test_eval_slices_exclude_no_trade() -> None:
    df = pd.DataFrame(
        {
            "model_yes_probability": [0.2, 0.8, 0.3, 0.7],
            "y_true": [0, 1, 0, 1],
            "recommendation": ["NO TRADE", "BUY YES", "NO TRADE", "BUY NO"],
        }
    )
    out = evaluate_calibration_slices(df, cfg=CalibratorConfig(min_samples=2))
    assert out["all_settled"]["n"] == 4
    assert out["actionable"]["n"] == 2
    assert out["no_trade_excluded"]["n"] == 2
