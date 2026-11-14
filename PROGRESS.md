# Progress

## Current status (2026-11-14)

- Plan **`kxbtc15m-live-readiness`**: **DONE** — merged PR [#25](https://github.com/loganware05/bitcoin-data-collector/pull/25) @ `b93740d`; issue [#24](https://github.com/loganware05/bitcoin-data-collector/issues/24) closed
- Rollback retained: `rollback/pre-kxbtc15m-live-readiness` @ `b4d9027`
- Prior **`kxbtc15m-decision-engine`**: DONE (PR #22 / docs #23)
- Live execution: **DENIED**
- Hourly paper: **`paper_buy_no_v1`** (keep accumulating)
- 15m paper: **`paper_kxbtc15m_v1`** — jobs shipped; load LaunchAgents on host

## Phase scoreboard

| Track | Phase | Status |
|---|---|---|
| Hourly | A CPCV/DSR | **PASS** (`paper_buy_no_v1`) |
| Hourly | B Live paper 30d | In progress (LaunchAgent @ 23:45) |
| KXBTC15M | Decision engine | Merged (#22) |
| KXBTC15M | Live-readiness pipeline | **Merged** (#25) |
| Security | Live money | **DENIED** |

## Primary next (ops on host)

- [ ] `./scripts/verdant/ensure_verdant_jobs.sh` then `--check` (load kxbtc15m-monitor + kxbtc15m-paper-tick)
- [ ] Captain-local live read-only `KXBTC15M` smoke (prefer kalshi/CF index for edge)
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
./scripts/verdant/ensure_verdant_jobs.sh
./scripts/verdant/ensure_verdant_jobs.sh --check
./scripts/execution-gate/paper_tick_daily.sh
./scripts/execution-gate/paper_tick_kxbtc15m_daily.sh
./scripts/verdant/kxbtc15m_monitor.sh
./scripts/execution-gate/phase_a_kxbtc15m.sh
python3 -m pytest tests/ -q
```
