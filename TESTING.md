# Testing

## Test commands

```bash
python3 -m pytest tests/ -q
python3 -m pytest tests/test_settlement_eval_cache.py tests/test_probability_calibration.py -q
python3 kalshi_settlement_eval.py --help
bash -n scripts/verdant/weekly_retrain.sh
bash -n scripts/verdant/settlement_aug28_window.sh
```

## Unit tests

- Confidence / fair-value / orderbook guards
- Probability calibrator slices
- Settlement label cache, `--since` filter, eval/fit mode separation (`tests/test_settlement_eval_cache.py`)

## Integration tests

- Verdant path helpers / pipeline preflight (when present)

## End-to-end tests

- Mac + Verdant: `./scripts/verdant/settlement_aug28_window.sh` against live `hourly_outputs`

## Manual checks

1. Mount Verdant (`/Volumes/Verdant_AI/btc_kalshi`).
2. Run Aug 28+ eval; confirm report JSON has `n`, `n_actionable`, `max_calibration_gap`, `gate_pass`.
3. Only if `gate_pass` is true, re-run with `SETTLEMENT_FIT_ENABLE=1`.

## Evidence location

`.agent/evidence/settlement-retrain-oom/`
