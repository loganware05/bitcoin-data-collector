# Progress

## Current status (2026-11-14)

- **Primary goal:** Plan **`kxbtc15m-live-readiness`** — **APPROVED** / implementing
  on `feature/24-kxbtc15m-live-readiness` ([#24](https://github.com/loganware05/bitcoin-data-collector/issues/24))
- Rollback: `rollback/pre-kxbtc15m-live-readiness` @ `b4d9027`
- Prior **`kxbtc15m-decision-engine`**: DONE (PR #22 / docs #23)
- Live execution: **DENIED**

## Phase scoreboard

| Track | Phase | Status |
|---|---|---|
| Hourly | A CPCV/DSR | **PASS** (`paper_buy_no_v1`) |
| Hourly | B Live paper 30d | In progress (LaunchAgent @ 23:45) |
| KXBTC15M | Decision engine | Merged (#22) |
| KXBTC15M | Live-readiness pipeline | In progress (#24) |
| Security | Live money | **DENIED** |

## Primary next

- [ ] Merge #24 PR; run `./scripts/verdant/ensure_verdant_jobs.sh` on host to load new agents
- [ ] Captain-local live read-only `KXBTC15M` smoke (prefer kalshi index over spot-proxy for edge)
- [ ] Accumulate `paper_kxbtc15m_v1` days without calendar gaps
- [ ] Re-run Phase A on non-fixture returns when labels exist

## Standing next steps (do not bury)

- [ ] Let hourly `paper_buy_no_v1` ticks continue to 30d / OOS floors (no further calendar gaps)
- [ ] Keep live money denied
- [ ] Run Sellbird train + first ≤50 outbound cohort from `docs/promotion/`
- [ ] Supply live Compass `experiment.json` when available
- [ ] Separate future plan required before any live order client

## Commands

```bash
./scripts/verdant/ensure_verdant_jobs.sh --check
./scripts/verdant/ensure_verdant_jobs.sh          # install/reload including 15m jobs
./scripts/execution-gate/paper_tick_daily.sh      # hourly paper_buy_no_v1
./scripts/execution-gate/paper_tick_kxbtc15m_daily.sh
./scripts/verdant/kxbtc15m_monitor.sh
./scripts/execution-gate/phase_a_kxbtc15m.sh
python3 -m pytest tests/ -q
```
