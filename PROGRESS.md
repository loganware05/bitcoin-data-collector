# Progress

## Current status (2026-10-17)

- Plan **`execution-gate-evidence`**: APPROVED; PR #12, #14, #15 **merged**
- Branch: `feature/13-execution-gate-daily-paper-tick`
- Live execution: **DENIED**
- Paper strategy: **`paper_buy_no_v1`**
- Paper day clock: day **1/30** (post gap-reset); **daily LaunchAgent** added to prevent further resets

## Phase scoreboard

| Phase | Status |
|---|---|
| A CPCV/DSR | **PASS** on `paper_buy_no_v1` |
| B Live paper | Day 1/30 + durable daily tick job |
| C Risk drills | Drill pass; gates on paper ticks |
| D Security/packet | Live still denied |
| Jev | Fixture only; live `experiment.json` still absent on Compass main |

## Next

- [ ] **Captain Mac:** `./scripts/verdant/ensure_verdant_jobs.sh` (agent cannot write LaunchAgents)
- [ ] Confirm: `./scripts/verdant/ensure_verdant_jobs.sh --check` shows paper-tick loaded
- [ ] Let daily ticks accumulate toward 30d / OOS floors
- [ ] Supply live Compass `experiment.json` when available
- [ ] Keep live money denied

## Commands

```bash
./scripts/execution-gate/paper_tick_daily.sh
./scripts/verdant/ensure_verdant_jobs.sh
./scripts/verdant/ensure_verdant_jobs.sh --check
```
