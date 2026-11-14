# Progress

## Current status (2026-11-14)

- Plan **`kxbtc15m-decision-engine`**: **APPROVED** — implementing on
  `feature/21-kxbtc15m-decision-engine` (issue [#21](https://github.com/loganware05/bitcoin-data-collector/issues/21))
- Rollback: `rollback/pre-kxbtc15m-decision-engine` @ `addc982`
- Worktree: `/Users/loganware/bitcoin-data-collector-kxbtc15m`
- Live execution: **DENIED**
- Hourly paper strategy: **`paper_buy_no_v1`** (untouched; separate clock)
- New paper candidate: **`paper_kxbtc15m_v1`** (separate state dir)
- Evidence: `.agent/evidence/kxbtc15m-decision-engine/`

## Phase scoreboard

| Phase | Status |
|---|---|
| A CPCV/DSR (`paper_buy_no_v1`) | **PASS** (prior) |
| B Live paper hourly | Continues on host LaunchAgent — do not reset |
| KXBTC15M Wave A–D | Implemented on feature branch; pytest green |
| D Security/packet | Live still denied; `approved_for_execution=false` |
| Agensi promo | Merged (#20) |

## Next

- [ ] Open / merge PR for #21
- [ ] Optional Captain-local live `KXBTC15M` read-only smoke
- [ ] Let hourly `paper_buy_no_v1` ticks continue to 30d
- [ ] Keep live money denied

## Commands

```bash
python3 -m pytest tests/ -q
python3 kxbtc15m_decision_engine.py --fixture tests/fixtures/kxbtc15m/market_pack.json
python3 kxbtc15m_monitor.py --once --spot-proxy 65000 --output-dir live_outputs/kxbtc15m
python3 kxbtc15m_ml.py --labels tests/fixtures/kxbtc15m/settlement_labels.json
python3 scripts/execution-gate/phase_b_kxbtc15m_paper_tick.py
./scripts/execution-gate/paper_tick_daily.sh   # hourly paper_buy_no_v1 only
```
