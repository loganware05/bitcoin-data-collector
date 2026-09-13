# Phase 1–2 settlement roadmap status

Date: 2026-09-13  
Plan: `settlement-retrain-oom` (AWAITING APPROVAL)  
Issue: #4

## Captain-reported eval-only result

| Metric | Value |
|---|---|
| Scans | 298 |
| Settled rows | ~34.8k |
| Actionable rows | 6,939 |
| Raw calibration gap | ~81% (FAIL vs 12% gate) |
| Calibrator manifest | `20260828T003036Z` (unchanged) |
| Post-guard scan files | ~7 (insufficient) |

## Engineering next

Approve and implement settlement eval ⊥ fit + cache/batch (see root `IMPLEMENTATION_PLAN.md`).

## Ops next

Keep Verdant connected so hourly + sync jobs accumulate Aug 28+ post-guard scans; re-eval in ~2 weeks.
