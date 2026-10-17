# STATUS — Execution Gate Evidence

**Updated:** 2026-10-11  
**Live execution authority:** **DENIED**

## Repo inventory

| Repo | Path | Notes |
|---|---|---|
| bitcoin-data-collector | this workspace | `feature/local-execution-gate-evidence`; PR #12 merged upstream |
| captains-compass-cursor (**main**) | `.repos/compass-run/captains-compass-cursor-main` (from GitHub zip; gitignored) | https://github.com/loganware05/captains-compass-cursor.git |
| Vorssaint Compass copy | do not use for AHF evidence | project-local only |

## experiment.json

| Artifact | Status |
|---|---|
| `.agent/evidence/ahf-p05-portfolio-experiment/exp-20261007T211148Z-23fa367a/experiment.json` on **main** | **MISSING** (404 / not in tree) |
| Same dir `CAPTAIN_LOCAL.md` | Present — states file is Captain-local only |
| Fixture `experiment_outcome_sample.json` | Present — coupling re-run 2026-10-11 → still deny execution |

## Session progress

| Item | Status |
|---|---|
| PR #12 merged | YES |
| Strategy revision `paper_buy_no_v1` | YES — Phase A **pass** |
| Paper clock reset on strategy adopt | YES — day 1/30 |
| Fixture coupling from main Compass | YES — `analysis/compass-coupling-20261011/` |
| Live Jev experiment.json | BLOCKED — not in main repo |
| `gh auth refresh` | BLOCKED — device login required |

## Safety locks

- No live Kalshi orders
- No `approved_for_execution: true`
- Paper = simulated fills under revised filters only for edge counting

## Update 2026-10-17

- PR #14 merged.
- Paper clock gap reset: `calendar_gap_days=6` → consecutive_days back to **1**.
- Cloud agent handoff superseded; live execution still DENIED.

## Update 2026-10-17 (daily paper LaunchAgent)

- Added `scripts/execution-gate/paper_tick_daily.sh`
- LaunchAgent `com.verdant.btc-kalshi.execution-gate-paper-tick` @ local 23:45 daily
- Wired into `ensure_verdant_jobs.sh`
- Live execution remains DENIED

