# Implementation Plan

## Metadata

- Status: APPROVED — PR READY
- Plan ID: buy-yes-strike-guards + offline staging (on top of merged `settlement-retrain-oom`)
- Issue: #4 (settlement; merged via PR #5) + local predictive roadmap
- Branch: `feature/buy-yes-strike-guards`
- Base: `Kalshi-BTC-Hourly-Event-Scan` (includes PR #5)
- Created: 2026-08-19
- Last updated: 2026-09-15
- Approved by: Captain

## Scope (this PR)

1. **Asymmetric fair-value guards (ADR-002)**
   - `max_buy_yes_model_probability=0.85`
   - Strike distance 2% OTM for BUY YES
   - BUY NO: no model-NO cap; YES must be OTM/ATM within 2% (never ITM)
2. **Offline laptop staging (ADR-003)**
   - Local cache `~/.local/share/verdant-btc-kalshi`
   - Sync LaunchAgent every 10 min; hourly scan writes local when drive offline
3. **Ops helpers**
   - `ensure_verdant_jobs.sh`, `settlement_aug28_actionable.sh`
   - Wire staging into `weekly_retrain.sh` / `settlement_aug28_window.sh`

## Already on base (PR #5)

Settlement eval/fit split, `settlement_label_store.py`, `SETTLEMENT_FIT_ENABLE=0` (ADR-004).

## Acceptance

- [x] PR #5 merged first
- [x] Unit tests for fair-value + settlement cache
- [x] Aug 28+ actionable gate evidence recorded (FAIL; no fit)
- [ ] This branch PR open for Captain review

## Rollback

Revert this branch merge; PR #5 settlement tooling remains on base.
