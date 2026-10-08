# Progress

## Current status (2026-10-08)

- Plan **`execution-gate-evidence`**: **APPROVED** (Captain) for evidence/paper/risk-on-paper
- Branch: `feature/local-execution-gate-evidence` (from cloud `docs/execution-gate-evidence-1043`)
- Live execution: **DENIED** (`approved_for_execution: false`)
- Evidence: `.agent/evidence/execution-gate-evidence/`
- Draft PR: https://github.com/loganware05/bitcoin-data-collector/pull/12
- Issue: `local/execution-gate-evidence` (`gh` auth broken on this host)

## Phase scoreboard

| Phase | Status |
|---|---|
| A CPCV/DSR Verdant | **FAIL** — 207 trades, Sharpe ≈ -1.05; research bar rejects |
| B Live paper | **Day 1/30** — `phase_b_live_scan_tick.py` against Verdant hourly scans |
| C Risk drills | Drill pass; gates consulted on paper ticks (not live-wired) |
| D Security/packet | Packet updated; execution denied recommendation |

## Completed

- [x] Cloud tandem harnesses + packet scaffold ([Execution Gate Evidence](bc-dcd1e50c-1985-422f-a94a-266e51971043))
- [x] Captain plan approval recorded
- [x] Verdant actionable returns export + Phase A non-fixture run
- [x] Paper day clock started (simulated fills only)
- [x] Phase C drill re-run post-approval

## Blockers

- Missing Compass live Jev `experiment.json`
- Phase A fail blocks counting paper trades as edge evidence until strategy revision
- `gh` token invalid — cannot open/update GitHub issue/PR from this host

## Next

- [ ] Captain: strategy revision vs CONTINUE_PAPER_ONLY plumbing
- [ ] Supply experiment.json → Compass coupling re-run
- [ ] Continue daily paper ticks (or LaunchAgent) without claiming edge until Phase A passes
- [ ] Refresh `gh auth` → sync PR #12 / create issue
- [ ] Keep live money denied

## Commands

```bash
python3 scripts/execution-gate/export_verdant_actionable_returns.py \
  --out-csv .agent/evidence/execution-gate-evidence/analysis/verdant_actionable_returns.csv \
  --out-meta .agent/evidence/execution-gate-evidence/analysis/verdant_actionable_returns_meta.json

python3 scripts/execution-gate/phase_a_cpcv_dsr.py \
  --returns .agent/evidence/execution-gate-evidence/analysis/verdant_actionable_returns.csv \
  --data-class verdant_staging \
  --out .agent/evidence/execution-gate-evidence/analysis/phase_a_verdant.json

python3 scripts/execution-gate/phase_b_live_scan_tick.py \
  --state-dir .agent/evidence/execution-gate-evidence/paper

python3 scripts/execution-gate/phase_c_breaker_stubs.py --drill \
  --out .agent/evidence/execution-gate-evidence/risk-drills/phase_c_drill_post_approval.json
```
