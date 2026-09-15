# Progress

## Current status (2026-09-15)

- Branch: `feature/buy-yes-strike-guards` (onto `Kalshi-BTC-Hourly-Event-Scan` after **PR #5 merged**)
- PR #5 (settlement OOM / Phase 1–2 cache): **MERGED**
- This branch adds: asymmetric BUY YES/NO guards (incl. BUY NO ITM fix), offline laptop staging (ADR-003), actionable gate helper
- Aug 28+ gate: **FAIL** raw gap 0.813 (pre–ITM-fix BUY NO mix); `SETTLEMENT_FIT_ENABLE` stays 0

## Completed

- [x] PR #5 merge into `Kalshi-BTC-Hourly-Event-Scan`
- [x] BUY NO model-probability cap removal + ITM strike-guard fix (ADR-002)
- [x] Offline staging sync LaunchAgent (ADR-003)
- [x] `settlement_aug28_actionable.sh` lean gate eval
- [x] Sep 13 multi-horizon retrain artifacts on Verdant

## Next

- [ ] Open / merge PR from this branch
- [ ] Accumulate post–ITM-fix scans → re-run `./scripts/verdant/settlement_aug28_actionable.sh`
- [ ] Fit calibrator only if `gate_pass`
- [ ] Phase 3 `min_confidence` defaults deferred until gate passes 2+ weeks

## Commands

```bash
./scripts/verdant/settlement_aug28_actionable.sh
./scripts/verdant/ensure_verdant_jobs.sh
./scripts/verdant/sync_verdant_staging.sh --check
```
