# Progress

## Current status (2026-10-11)

- Plan **`execution-gate-evidence`**: APPROVED; PR #12 **merged** into `cursor/kalshi-live-decision-system`
- Branch: `feature/local-execution-gate-evidence` (post-merge follow-on)
- Live execution: **DENIED**
- Main Compass: https://github.com/loganware05/captains-compass-cursor.git (not Vorssaint fork)
- Paper strategy: **`paper_buy_no_v1`** adopted after Phase A pass; day clock reset to **1/30**

## Phase scoreboard

| Phase | Status |
|---|---|
| A CPCV/DSR | **PASS** on revised strategy (`phase_a_revised_v1.json`, n=51, DSR n_trials=324) |
| A baseline (unfiltered) | FAIL (historical) — do not count |
| B Live paper | Day **1/30** under `paper_buy_no_v1` filters |
| C Risk drills | Drill pass; gates on paper ticks |
| D Security/packet | Updated; live still denied |
| Jev coupling | Fixture re-run OK from main Compass zip extract; **live `experiment.json` still absent on main** (only `CAPTAIN_LOCAL.md`) |

## Captain decisions (2026-10-11)

1. Revise strategy before counting paper edge — **done** (`paper_buy_no_v1`)
2. Use main `captains-compass-cursor` — **done** (zip extract under `.repos/`; gitignored)
3. Retry `gh auth refresh` — **blocked** on device login (invalid keyring token); Captain must complete browser device flow

## Next

- [ ] Captain: complete `gh auth refresh` device login (see chat for one-time code)
- [ ] Captain: place live `experiment.json` into main Compass evidence path (file not on GitHub main)
- [ ] Continue daily paper ticks under `paper_buy_no_v1`
- [ ] Keep live money denied until remaining gates + written approval

## Commands

```bash
# Phase A revised
python3 scripts/execution-gate/phase_a_cpcv_dsr.py \
  --returns .agent/evidence/execution-gate-evidence/analysis/verdant_returns_revised_v1.csv \
  --data-class verdant_staging --n-trials 324 \
  --out .agent/evidence/execution-gate-evidence/analysis/phase_a_revised_v1.json

# Paper tick (edge-counting under revised strategy)
python3 scripts/execution-gate/phase_b_live_scan_tick.py \
  --strategy scripts/execution-gate/paper_strategy_v1.json \
  --state-dir .agent/evidence/execution-gate-evidence/paper

# Compass coupling (from local main extract)
cd .repos/compass-run/captains-compass-cursor-main
PYTHONPATH=. COMPASS_AHF_BEHAVIOR_COUPLING_ENABLED=1 ./scripts/ahf-behavioral-coupling.sh \
  orchestrator/integrations/ai_hedge_fund/fixtures/experiment_outcome_sample.json
```
