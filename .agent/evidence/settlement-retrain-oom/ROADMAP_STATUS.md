# Phase 1–2 settlement roadmap status

Date: 2026-09-13
Plan: `settlement-retrain-oom` (**APPROVED / implemented in code**)
Issue: #4

## Code (this branch)

- Settlement label cache + batched scan load
- CLI modes `eval` / `fit` / `refresh-cache` (no dual load in one process)
- `weekly_retrain.sh` two-process settlement; `SETTLEMENT_FIT_ENABLE=0` default
- Helper `scripts/verdant/settlement_aug28_window.sh`
- Tests: 59 passed (see pytest.txt)

## Live Aug 28+ retrain

**Not executed in Cloud** — Verdant volume not mounted (`/Volumes/Verdant_AI` absent).
Captain should run on Mac with drive attached:

```bash
./scripts/verdant/settlement_aug28_window.sh
# if gate_pass:
SETTLEMENT_FIT_ENABLE=1 ./scripts/verdant/settlement_aug28_window.sh
```

## Prior full-history eval (Captain, pre-window)

| Metric | Value |
|---|---|
| Scans | 298 |
| Settled rows | ~34.8k |
| Actionable | 6,939 |
| Raw gap | ~81% FAIL vs 12% |
| Manifest | `20260828T003036Z` unchanged |
