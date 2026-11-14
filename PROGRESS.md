# Progress

## Current status (2026-11-14)

- Plan **`kxbtc15m-real-market-validation`**: **APPROVED** / implementing on
  `feature/27-kxbtc15m-real-market-validation` ([#27](https://github.com/loganware05/bitcoin-data-collector/issues/27))
- Rollback: `rollback/pre-kxbtc15m-real-market-validation` @ `778156d`
- Monitor hotfix verified live: tick written; LaunchAgent `last_exit=0`
- Live execution: **DENIED**

## Phase scoreboard

| Track | Status |
|---|---|
| Hourly `paper_buy_no_v1` | Phase A pass; 30d in progress |
| KXBTC15M jobs | Loaded; monitor green after Wave 0 |
| KXBTC15M validation floors | 0 edge days / labels accumulating |
| Live money | **DENIED** |

## Primary next

- [ ] Merge #27 PR
- [ ] Provide CF/Kalshi index (or honest file drop) so edge-eligible ticks accumulate
- [ ] Hit dual floor (≥14 edge days + ≥50 settled labels) then non-fixture Phase A

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
  --decision-dir "$BTC_KALSHI_ROOT/live_outputs/kxbtc15m" \
  --out .agent/evidence/kxbtc15m-real-market-validation/wave-2/validation_status.json
python3 -m pytest tests/ -q
```
