# Progress

## Current status

| Item | Value |
|---|---|
| Active plan | `settlement-retrain-oom` — **AWAITING APPROVAL** |
| Issue | [#4](https://github.com/loganware05/bitcoin-data-collector/issues/4) |
| Branch | `cursor/settlement-retrain-oom-5182` |
| Production base | `Kalshi-BTC-Hourly-Event-Scan` |
| Prior plan | `kalshi-confidence-guards-ws-a` — CLOSED (archived `docs/plans/kalshi-confidence-guards-ws-a.md`) |

## Phase 1–2 roadmap (Captain 2026-09-13)

| Step | Status | Notes |
|---|---|---|
| Accumulate post-guard scans (BUY NO / guard fix) | **In progress (ops)** | ~7 post-guard files so far; need ~2 weeks; Captain plugs in Verdant drive for snapshots/retrain + local→Verdant sync |
| Settlement eval on Aug 28+ slice | **Blocked on data** | Full-history eval-only done: 298 scans / ~34.8k settled / 6,939 actionable; raw gap ~81% FAIL vs 12%; mostly pre-guard BUY YES flood; manifest `20260828T003036Z` unchanged |
| Fix weekly retrain OOM (eval ⊥ fit) | **Plan ready** | Awaiting Captain approval of `IMPLEMENTATION_PLAN.md` |

## Completed

- [x] Compass install + confidence-guard diagnosis + plan
- [x] Captain approval Phase 1 paper + Phase 2 soft-land; Phase 3 defaults deferred
- [x] Soft-land `_soft_mapping_factor`; paper flags in `hourly_scan.sh`
- [x] Settlement eval-only full run (Captain) — report only, no calibrator refit
- [x] Issue #4 + plan `settlement-retrain-oom` drafted

## Next (after plan approval)

- [ ] Implement settlement cache + batched load + eval/fit process split
- [ ] Wire `weekly_retrain.sh` two-step + `SETTLEMENT_FIT_ENABLE` gate
- [ ] Unit tests + evidence package
- [ ] ~2 weeks later: `--since 2026-08-28` eval; reconsider fit / Phase 3

## Blockers

- Verdant drive not mounted in Cloud — live OOM reproduction / full-scan smoke is Captain-side.
- GitHub default branch (`cursor/kalshi-live-decision-system`) lacks Verdant/settlement modules (follow-up hygiene).
