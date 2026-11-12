# Progress

## Current status (2026-11-12)

- Plan **`agensi-promo-hygiene`**: **APPROVED** (Captain: "Yes, do both"); issue [#19](https://github.com/loganware05/bitcoin-data-collector/issues/19)
- Branch: `feature/19-agensi-promo-hygiene` — README Agensi CTA + `docs/promotion/` Sellbird assets
- Prior plan **`xrv-pilot-b-paper-continuity`**: merged via PR [#18](https://github.com/loganware05/bitcoin-data-collector/pull/18) @ `59367ad`
- Live execution: **DENIED**
- Paper strategy: **`paper_buy_no_v1`**
- Paper day clock: day **1/30** after `calendar_gap_days=26` restart
- Host: `com.verdant.btc-kalshi.execution-gate-paper-tick` **loaded**
- Evidence: `.agent/evidence/xrv-pilot-b-paper-continuity/`

## Phase scoreboard

| Phase | Status |
|---|---|
| A CPCV/DSR | **PASS** on `paper_buy_no_v1` |
| B Live paper | Day **1/30** after documented gap restart; daily LaunchAgent installed |
| C Risk drills | Drill pass; gates on paper ticks |
| D Security/packet | Live still denied |
| Jev | Fixture only; live `experiment.json` still absent on Compass main |
| Agensi promo | Listing live; repo hygiene + Sellbird copy in flight (#19) |

## Next

- [ ] Merge Agensi promo hygiene PR (#19)
- [ ] Run Sellbird train + first ≤50 outbound cohort from `docs/promotion/`
- [ ] Let daily ticks accumulate toward 30d / OOS floors (no further calendar gaps)
- [ ] Supply live Compass `experiment.json` when available
- [ ] Keep live money denied

## Commands

```bash
./scripts/execution-gate/paper_tick_daily.sh
./scripts/verdant/ensure_verdant_jobs.sh --check
```
