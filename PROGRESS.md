# Progress

## Current status (2026-11-16)

- KXBTC15M verified index + labels: **shipped** (PRs #32–#35)
- CF BRTI edge ticks accruing (`cf_benchmarks`)
- Phase A **attempt** recorded: dual floor **FAIL** (edge days 1/14; labels met)
- Live execution: **DENIED**

## Dual floor

| Floor | Required | Observed |
|---|---:|---:|
| Edge-eligible calendar days | 14 | 1 |
| Settled labels | 50 | ≥10k |

Evidence: `.agent/evidence/kxbtc15m-phase-a-attempt-20261116/`

## Standing next steps (do not bury)

- [ ] Continue edge-day accrual to ≥14; re-run Phase A
- [ ] Hourly `paper_buy_no_v1` → 30d / OOS
- [ ] Keep live money denied
- [ ] Sellbird train + ≤50 outbound from `docs/promotion/`
- [ ] Compass `experiment.json` when available
- [ ] Future plan before any live order client
