# Progress

## Current status (2026-11-14)

- Plan **`kxbtc15m-decision-engine`**: **DONE** — merged PR [#22](https://github.com/loganware05/bitcoin-data-collector/pull/22) @ `f14e8cd`; issue [#21](https://github.com/loganware05/bitcoin-data-collector/issues/21) closed
- Rollback retained: `rollback/pre-kxbtc15m-decision-engine` @ `addc982`
- Live execution: **DENIED**
- Hourly paper strategy: **`paper_buy_no_v1`** (untouched by 15m work)
- New paper candidate on default branch: **`paper_kxbtc15m_v1`** (separate state dir)
- Evidence: `.agent/evidence/kxbtc15m-decision-engine/`

## Phase scoreboard

| Phase | Status |
|---|---|
| A CPCV/DSR (`paper_buy_no_v1`) | **PASS** (prior) |
| B Live paper hourly | Continues on host LaunchAgent |
| KXBTC15M Wave A–D | **Merged** (#22) |
| D Security/packet | Live still denied |
| Agensi promo | Merged (#20) |

## Next

- [ ] Optional Captain-local live `KXBTC15M` read-only smoke
- [ ] Let hourly `paper_buy_no_v1` ticks continue to 30d
- [ ] Keep live money denied
- [ ] Evaluate `paper_kxbtc15m_v1` separately before any live discussion

## Commands

```bash
python3 -m pytest tests/ -q
python3 kxbtc15m_decision_engine.py --fixture tests/fixtures/kxbtc15m/market_pack.json
python3 kxbtc15m_monitor.py --once --spot-proxy 65000 --output-dir live_outputs/kxbtc15m
python3 scripts/execution-gate/phase_b_kxbtc15m_paper_tick.py
./scripts/execution-gate/paper_tick_daily.sh
```
