# Progress

## Current status (2026-11-12)

- Plan **`xrv-pilot-b-paper-continuity`**: **APPROVED**; issue [#17](https://github.com/loganware05/bitcoin-data-collector/issues/17)
- PR #16 (daily paper-tick LaunchAgent) **merged** @ `8db4fcc`
- Live execution: **DENIED**
- Paper strategy: **`paper_buy_no_v1`**
- Paper day clock: restarted to day **1/30** after `calendar_gap_days=26` (last active 2026-10-17 → smoke 2026-11-12)
- Host: `com.verdant.btc-kalshi.execution-gate-paper-tick` **loaded** via `ensure_verdant_jobs.sh`
- Evidence: `.agent/evidence/xrv-pilot-b-paper-continuity/`

## Phase scoreboard

| Phase | Status |
|---|---|
| A CPCV/DSR | **PASS** on `paper_buy_no_v1` |
| B Live paper | Day **1/30** after documented gap restart; daily LaunchAgent installed |
| C Risk drills | Drill pass; gates on paper ticks |
| D Security/packet | Live still denied |
| Jev | Fixture only; live `experiment.json` still absent on Compass main |

## Next

- [ ] Let daily ticks accumulate toward 30d / OOS floors (no further calendar gaps)
- [ ] Open PR for Pilot B hardening (`feature/17-xrv-pilot-b-paper-continuity`) when Captain requests
- [ ] Supply live Compass `experiment.json` when available
- [ ] Keep live money denied

## Commands

```bash
./scripts/execution-gate/paper_tick_daily.sh
./scripts/verdant/ensure_verdant_jobs.sh --check
```
