# Design note — settlement eval ⊥ fit

Date: 2026-09-13  
Plan: `settlement-retrain-oom` (approved)

## Root cause

`kalshi_settlement_eval.py --fit-calibration` previously fit then **always** evaluated in one process, each path loading every `scan_*.json` and attaching Kalshi outcomes **per row**. Combined with weekly ML retrain, RSS blew up (~298 scans / ~35k rows).

## Fix

1. `settlement_label_store.py` — batch JSON load; unique-ticker outcome map; parquet/jsonl labeled table.
2. CLI `--mode eval|fit|refresh-cache` — mutually exclusive.
3. `weekly_retrain.sh` — eval process A, optional fit process B (`SETTLEMENT_FIT_ENABLE`, default 0).
4. `--since` for Aug 28+ post-guard window; helper `settlement_aug28_window.sh`.

## Validation

- `pytest tests/` → 59 passed (see `pytest.txt`).
- Live Verdant Aug 28+ retrain **not** run in Cloud (volume absent).
