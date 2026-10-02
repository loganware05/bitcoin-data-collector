# Progress

## Current status (2026-10-02)

- Branch: `cursor/postfix-buy-no-otm-cache-436f` (issue #9)
- Plan: `postfix-buy-no-calibration` **APPROVED** — implementing / validating
- Base: NorthStar tip + merged `feature/buy-yes-strike-guards` product baseline
- Captain decisions: OTM floor **0.5%**, offline snapshot cache **yes**, replay **Sep 13–Oct 2**
- Cloud Sep13–Oct2 replay: **BLOCKED** (Verdant not mounted) — runbook in `.agent/evidence/postfix-buy-no-calibration/REPLAY.md`
- `SETTLEMENT_FIT_ENABLE` stays **0**

## Completed

- [x] PR #5 merge into `Kalshi-BTC-Hourly-Event-Scan`
- [x] BUY NO model-probability cap removal + ITM strike-guard fix (ADR-002)
- [x] Offline staging sync LaunchAgent (ADR-003)
- [x] Merge strike-guards into NorthStar tip for postfix work
- [x] BUY NO min OTM floor 0.5% (ADR-005)
- [x] Offline snapshot cache pull/push + offline snapshot daemon path
- [x] `--until` scan filter + `settlement_sep13_oct2_replay.sh`
- [x] Unit tests 66 passed (Cloud)

## Next

- [ ] Captain: mount Verdant → `./scripts/verdant/settlement_sep13_oct2_replay.sh` and attach report
- [ ] Open / merge PR #9 branch
- [ ] Fit calibrator only if gate_pass after post-floor window
- [ ] Phase 3 `min_confidence` defaults deferred until gate passes 2+ weeks

## Commands

```bash
./scripts/verdant/settlement_sep13_oct2_replay.sh
./scripts/verdant/settlement_aug28_actionable.sh
./scripts/verdant/sync_verdant_staging.sh --pull
./scripts/verdant/sync_verdant_staging.sh --check
./scripts/verdant/ensure_verdant_jobs.sh
```
