# Prior AHF-P05 / P06 runs

## Found in Compass (`/home/ubuntu/repos/captains-compass-cursor`)

| Artifact | Path | Status |
|---|---|---|
| P06 EXECUTION_READINESS.md | `.agent/evidence/ahf-p06-behavioral-coupling/analysis/EXECUTION_READINESS.md` | FOUND → copied to `prior-runs/P06_EXECUTION_READINESS.md` |
| P06 readiness-sample.json | `.agent/evidence/ahf-p06-behavioral-coupling/analysis/readiness-sample.json` | FOUND → copied |
| P06 coupling script | `scripts/ahf-behavioral-coupling.sh` | FOUND; re-run 2026-10-08 |
| P05 TECH_DEV_AND_LIVE_JEV.md | `.agent/evidence/ahf-p05-portfolio-experiment/analysis/TECH_DEV_AND_LIVE_JEV.md` | FOUND → copied |
| P05 exp dir | `.agent/evidence/ahf-p05-portfolio-experiment/exp-20261007T211148Z-23fa367a/` | FOUND (placeholder only) |
| P05 `experiment.json` | `…/exp-20261007T211148Z-23fa367a/experiment.json` | **MISSING** (see CAPTAIN_LOCAL.md) |
| Fixture sample used for coupling | `orchestrator/integrations/ai_hedge_fund/fixtures/experiment_outcome_sample.json` | USED for demo re-run |

## Coupling re-run (this session)

```bash
cd /home/ubuntu/repos/captains-compass-cursor
COMPASS_AHF_BEHAVIOR_COUPLING_ENABLED=1 ./scripts/ahf-behavioral-coupling.sh
```

Outputs saved under `analysis/`:

- `ahf-behavioral-coupling-rerun.log`
- `readiness-rerun-20261008T183152Z.json`
- `coupling-rerun-20261008T183152Z.json`

### Verdict (unchanged)

- `recommend_approved_for_execution: false`
- `approved_for_execution: false`
- `confidence_band: research_operable`
- Failed: `non_fixture_backtests`, `paper_track_record`, `multiple_live_jev_runs`,
  `kill_switch_and_limits`, `security_review_live_path`, `captain_written_approval`
- Passing: `live_execution_path_absent`

## Captain ask

Provide `experiment.json` for `exp-20261007T211148Z-23fa367a` (Captain-local live Jev)
so coupling can be re-run against non-fixture experiment evidence.
