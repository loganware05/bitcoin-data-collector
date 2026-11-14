# Progress

## Current status (2026-11-14)

- Plan **`kxbtc15m-real-market-validation`**: **DONE** (code) — PR [#28](https://github.com/loganware05/bitcoin-data-collector/pull/28) @ `e05a415`; issue [#27](https://github.com/loganware05/bitcoin-data-collector/issues/27) closed
- Rollback retained: `rollback/pre-kxbtc15m-real-market-validation` @ `778156d`
- Live execution: **DENIED**
- Ops remaining: verified settlement index → edge-eligible days (≥14) + settled labels (≥50)

## Phase scoreboard

| Track | Status |
|---|---|
| Hourly `paper_buy_no_v1` | 30d paper in progress |
| KXBTC15M validation code | **Merged** (#28) |
| KXBTC15M dual floor | Not met (need live index for edge days) |
| Live money | **DENIED** |

## Primary next (ops / follow-on)

- [ ] Supply CF/Kalshi index or `KXBTC15M_INDEX_FILE` / ensure snapshots feed spot cascade
- [ ] Confirm monitor ticks with non-`unavailable` source
- [ ] Accumulate dual floor; then non-fixture Phase A
- [ ] Keep LaunchAgents loaded (`ensure_verdant_jobs.sh --check`)

## Standing next steps (do not bury)

- [ ] Hourly `paper_buy_no_v1` → 30d / OOS
- [ ] Keep live money denied
- [ ] Sellbird train + ≤50 outbound from `docs/promotion/`
- [ ] Compass `experiment.json` when available
- [ ] Future plan before any live order client

## Commands

```bash
./scripts/verdant/ensure_verdant_jobs.sh --check
./scripts/verdant/kxbtc15m_monitor.sh
python3 scripts/execution-gate/kxbtc15m_validation_status.py \
  --decision-dir /Volumes/Verdant_AI/btc_kalshi/live_outputs/kxbtc15m \
  --out .agent/evidence/kxbtc15m-real-market-validation/validation_status.json
```
