# Progress

## Current status (2026-10-03)

- Branch: `cursor/postfix-buy-no-otm-cache-436f` (issue #9 / PR #10)
- Plan: `postfix-buy-no-calibration` — implemented; Sep13–Oct2 replay **complete**
- Replay: 246 scans → **207 settled BUY NO** (0 BUY YES); raw gap **0.323**; **gate_pass=false**
- `SETTLEMENT_FIT_ENABLE` stays **0**
- Evidence: `.agent/evidence/postfix-buy-no-calibration/sep13_oct2_replay_20261003T054308Z.json`

## Completed

- [x] Merge strike-guards into NorthStar tip
- [x] BUY NO min OTM floor 0.5% (ADR-005)
- [x] Offline snapshot cache pull/push + offline daemon path
- [x] Actionable-only Sep13–Oct2 replay with isolated cache
- [x] Unit tests 67 passed
- [x] Captain Mac Verdant replay report ingested

## Next

- [ ] Captain decide: iterate BUY NO guards further vs accumulate more post-floor scans
- [ ] Fit calibrator only if a future window hits `gate_pass`
- [ ] Phase 3 `min_confidence` defaults deferred
- [ ] Merge PR #10 when ready

## Commands

```bash
./scripts/verdant/settlement_sep13_oct2_replay.sh
./scripts/verdant/sync_verdant_staging.sh --check
```
