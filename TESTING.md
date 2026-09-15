# Testing

## Test commands

```bash
python3 -m pytest tests/ -q
python3 -m pytest tests/test_settlement_eval_cache.py tests/test_fair_value_engine.py -q
python3 kalshi_settlement_eval.py --help
bash -n scripts/verdant/weekly_retrain.sh
bash -n scripts/verdant/settlement_aug28_window.sh
bash -n scripts/verdant/settlement_aug28_actionable.sh
./scripts/verdant/sync_verdant_staging.sh --check
./scripts/verdant/ensure_hourly_scan_schedule.sh --check
```

## Unit tests

- Confidence / fair-value / orderbook guards (`tests/test_fair_value_engine.py`)
- Probability calibrator slices
- Settlement label cache, `--since` filter, eval/fit mode separation (`tests/test_settlement_eval_cache.py`)

## Integration tests

- Verdant path helpers / pipeline preflight (`tests/test_verdant_pipeline.py`)

## End-to-end / manual — settlement gate

1. Mount Verdant (`/Volumes/Verdant_AI/btc_kalshi`).
2. Prefer lean gate: `./scripts/verdant/settlement_aug28_actionable.sh`
3. Full-window (heavier): `./scripts/verdant/settlement_aug28_window.sh`
4. Only if `gate_pass` is true, re-run with `SETTLEMENT_FIT_ENABLE=1`.

## Manual checks — offline staging (ADR-003)

1. With drive connected: `./scripts/verdant/sync_verdant_staging.sh --pull` → `Local model cache: OK`
2. Unplug drive (or simulate): `BTC_KALSHI_REMOTE_ROOT=/nonexistent ./scripts/verdant/hourly_scan.sh` → scan writes to `~/.local/share/verdant-btc-kalshi/hourly_outputs/`
3. Reconnect drive: `./scripts/verdant/sync_verdant_staging.sh` → pending scans appear on Verdant

## Evidence location

`.agent/evidence/settlement-retrain-oom/` and `.agent/evidence/kalshi-predictive-roadmap/`
