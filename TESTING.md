# Testing

## Test commands

```bash
python3 -m pytest tests/ -q
python3 -m pytest tests/test_settlement_eval_cache.py tests/test_fair_value_engine.py -q
python3 kalshi_settlement_eval.py --help
bash -n scripts/verdant/weekly_retrain.sh
bash -n scripts/verdant/settlement_aug28_window.sh
bash -n scripts/verdant/settlement_aug28_actionable.sh
bash -n scripts/verdant/settlement_sep13_oct2_replay.sh
bash -n scripts/verdant/verdant_staging.sh
./scripts/verdant/sync_verdant_staging.sh --check
./scripts/verdant/ensure_hourly_scan_schedule.sh --check
```

## Unit tests

- Confidence / fair-value / orderbook guards (`tests/test_fair_value_engine.py`) including BUY NO OTM floor 0.5%
- Probability calibrator slices
- Settlement label cache, `--since`/`--until` filter, eval/fit mode separation (`tests/test_settlement_eval_cache.py`)

## Integration tests

- Verdant path helpers / pipeline preflight (`tests/test_verdant_pipeline.py`)

## End-to-end / manual — Sep 13–Oct 2 postfix replay

1. Mount Verdant (`/Volumes/Verdant_AI/btc_kalshi`).
2. `./scripts/verdant/sync_verdant_staging.sh --pull` (models + recent snapshots).
3. `./scripts/verdant/settlement_sep13_oct2_replay.sh`
4. Copy report into `.agent/evidence/postfix-buy-no-calibration/`
5. Keep `SETTLEMENT_FIT_ENABLE=0` unless Captain enables fit after gate_pass.

## Manual checks — offline staging (ADR-003/005)

1. With drive connected: `./scripts/verdant/sync_verdant_staging.sh --pull` → `Local model cache: OK` and `Local snapshot cache: OK`
2. Unplug drive (or simulate): `BTC_KALSHI_REMOTE_ROOT=/nonexistent ./scripts/verdant/hourly_scan.sh` → scan writes to `~/.local/share/verdant-btc-kalshi/hourly_outputs/`
3. Offline snapshots: `BTC_KALSHI_REMOTE_ROOT=/nonexistent ./scripts/verdant/snapshot_daemon.sh` → writes under local `snapshots/` when model cache present
4. Reconnect drive: `./scripts/verdant/sync_verdant_staging.sh` → pending scans/snapshots appear on Verdant

## Evidence location

`.agent/evidence/postfix-buy-no-calibration/`, `.agent/evidence/settlement-retrain-oom/`, `.agent/evidence/kalshi-predictive-roadmap/`, `.agent/evidence/execution-gate-evidence/`

## Execution-gate harnesses (non-execution)

```bash
# Plumbing demo (not edge evidence)
python3 scripts/execution-gate/phase_a_cpcv_dsr.py \
  --out .agent/evidence/execution-gate-evidence/analysis/phase_a_report.json

# Verdant non-fixture research bar (requires Verdant mount)
python3 scripts/execution-gate/export_verdant_actionable_returns.py \
  --out-csv .agent/evidence/execution-gate-evidence/analysis/verdant_actionable_returns.csv \
  --out-meta .agent/evidence/execution-gate-evidence/analysis/verdant_actionable_returns_meta.json
python3 scripts/execution-gate/phase_a_cpcv_dsr.py \
  --returns .agent/evidence/execution-gate-evidence/analysis/verdant_actionable_returns.csv \
  --data-class verdant_staging \
  --out .agent/evidence/execution-gate-evidence/analysis/phase_a_verdant.json

# Live-forward paper tick (simulated fills only; advances day clock)
python3 scripts/execution-gate/phase_b_live_scan_tick.py \
  --state-dir .agent/evidence/execution-gate-evidence/paper

python3 scripts/execution-gate/phase_c_breaker_stubs.py --drill \
  --out .agent/evidence/execution-gate-evidence/risk-drills/phase_c_drill_post_approval.json

python3 -m pytest tests/test_execution_gate_phase_a.py -q
```

These scripts must never enable live orders or set `approved_for_execution: true`.
Phase A must pass on non-fixture data before paper trades count as edge evidence.
