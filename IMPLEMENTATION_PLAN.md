# Implementation Plan

## Metadata

| Field | Value |
|---|---|
| Status | VALIDATING |
| Plan ID | postfix-buy-no-calibration |
| Issue | #9 |
| Branch | cursor/postfix-buy-no-otm-cache-436f |
| Created | 2026-10-02 |
| Last updated | 2026-10-03 |
| Approved by | Captain (Logan Ware) |
| Approval date | 2026-10-02 |
| Approved revision | Captain decisions: OTM floor 0.5%, offline snapshot cache yes, replay Sep13–Oct2 |
| Prior agent | ccb435ce-39ae-4e76-922e-86677a8f405c (transcript not accessible in this env; plan reconstructed from roadmap + Captain answers) |

## Request

Continue Kalshi predictive roadmap **post–BUY NO ITM fix** without waiting on calibrator fit: tighten BUY NO with a minimum OTM floor, extend offline staging to snapshot cache, and replay evaluation on existing Sep 13–Oct 2 scans.

## Problem Statement

1. ADR-002 BUY NO guard currently allows YES ATM through 2% OTM (`0.0 <= dist <= 0.02`). Near-ATM BUY NO still concentrates risk; Captain wants a **minimum OTM floor of 0.5%**.
2. Offline staging (ADR-003) caches models + market_probs but **snapshots stay Verdant-only**; laptop offline scans lack snapshot continuity.
3. Settlement calibrator fit remains gated (`SETTLEMENT_FIT_ENABLE=0`). Captain wants **postfix progress without calibration** — eval/replay only on the Sep 13–Oct 2 window.

## Desired Outcome

- BUY NO requires YES OTM distance in `[0.005, max_buy_no_strike_distance_pct]` (default max still 2%).
- Verdant local staging pulls/caches recent snapshots for offline use.
- Replay tooling evaluates actionable BUY YES/NO on Sep 13–Oct 2 scans (or reports blocker if Verdant data absent) without enabling fit.
- Strike-guards / settlement product base from `feature/buy-yes-strike-guards` is present on this NorthStar branch so postfix logic is not orphaned.

## Acceptance Criteria

- [ ] `FairValueConfig.min_buy_no_otm_pct = 0.005` enforced in `_buy_no_strike_guard_ok`
- [ ] Unit tests: BUY NO blocked when YES OTM &lt; 0.5%; allowed when 0.5% ≤ dist ≤ max; still blocked when ITM
- [ ] Offline snapshot cache: `verdant_staging.sh` pulls snapshots into local root; snapshot daemon can write local when remote offline **if** cache policy allows (prefer pull when mounted; local collect when offline + model cache present)
- [ ] Replay script for `SETTLEMENT_SINCE=2026-09-13` through `2026-10-02` (inclusive window) with actionable-only eval; fit remains disabled
- [ ] Evidence under `.agent/evidence/postfix-buy-no-calibration/`
- [ ] pytest green on touched tests
- [ ] DECISIONS / PROGRESS / TESTING / CHANGELOG updated
- [ ] PR opened vs base `cursor/kalshi-live-decision-system`

## Non-Goals

- Changing Phase 3 `min_confidence` defaults
- Enabling `SETTLEMENT_FIT_ENABLE=1` / refitting calibrator
- Trade execution / order placement
- Recreating Verdant history inside Cloud when drive data is unavailable (tooling + fixture tests still required)

## Rollback

- Revert merge commit / PR `#9` branch
- Or restore `min_buy_no_otm_pct` to `0.0` and remove snapshot pull from staging
- Tag: `rollback/pre-postfix-buy-no-calibration`

## Security Notes

- No secrets committed; Verdant paths remain local/env-configured
- Replay uses existing Kalshi public settlement APIs already used by settlement eval
- Offline cache is machine-local under `~/.local/share/verdant-btc-kalshi`

## Review Domains

- python
- tests
- security (paths / env only)

## Assumptions

- Captain approval of plan `postfix-buy-no-calibration` with answers: OTM floor **0.5%**, offline snapshot cache **include**, replay **Sep 13–Oct 2**
- Product baseline for strike guards + staging lives on `origin/feature/buy-yes-strike-guards` and must be merged into this NorthStar branch
- Cloud may lack Verdant mount; replay then documents blocker + ships CLI for Captain Mac run

## Open Questions

| Question | Captain answer |
|---|---|
| OTM floor value? | **0.5%** |
| Include offline snapshot cache? | **Yes** |
| Replay window? | **Existing Sep 13–Oct 2** |

## Current-State Analysis

- Branch `cursor/kalshi-live-decision-system`: NorthStar harness + pre–strike-guard fair value (no OTM guards)
- Branch `feature/buy-yes-strike-guards`: ADR-002 guards, ADR-003 staging, settlement eval/cache — **not yet merged** to NorthStar tip
- BUY NO guard today (on strike-guards): `0.0 <= dist <= 0.02`

## Proposed Architecture

1. Merge strike-guards product into feature branch (resolve docs in favor of NorthStar tip where needed).
2. Add `min_buy_no_otm_pct: float = 0.005` to `FairValueConfig`; update `_buy_no_strike_guard_ok` and warnings.
3. Extend `verdant_pull_cache` to rsync `snapshots/` (bounded recent window optional via env); allow snapshot daemon offline path to local root when model cache present.
4. Add `scripts/verdant/settlement_sep13_oct2_replay.sh` (or parameterized window script) wrapping actionable eval with `SETTLEMENT_SINCE`/`SETTLEMENT_UNTIL`.
5. Record evidence + memory docs.

## Files Expected to Change

- `hourly_fair_value_engine.py`
- `tests/test_fair_value_engine.py`
- `scripts/verdant/verdant_staging.sh`
- `scripts/verdant/snapshot_daemon.sh` (and/or `snapshot_daemon.py`)
- `scripts/verdant/settlement_sep13_oct2_replay.sh` (new)
- Possibly merge-introduced: settlement/staging modules from strike-guards
- `IMPLEMENTATION_PLAN.md`, `DECISIONS.md`, `PROGRESS.md`, `TESTING.md`, `CHANGELOG.md`
- `.agent/evidence/postfix-buy-no-calibration/*`
- `.agent/budgets/postfix-buy-no-calibration.md`

## Testing Strategy

- Unit: fair-value OTM floor / ITM / in-band
- Staging: shell syntax check; unit/doc of pull paths
- Replay: run against Verdant if mounted; else fixture-based dry path + Captain runbook evidence note
- Evidence matrix: backend / data-pipeline row → unit + integration evidence under `.agent/evidence/`

## Autonomy Budget

- Maximum iterations: 6
- Maximum failed validation cycles: 3
- Maximum estimated cost: n/a (Cloud Agent)
- Maximum elapsed time: single session
- Budget ledger path: `.agent/budgets/postfix-buy-no-calibration.md`
- On limit: write `.agent/evidence/postfix-buy-no-calibration/BUDGET_STOP_REPORT.md` and stop

## Definition of Done

Acceptance criteria above + PR opened with evidence. Plan → COMPLETE only after merge or Captain stop.

## Approval Boundary

**Implementation begins after this Captain approval record.**

## Approval Record

| Field | Value |
|---|---|
| Approved by | Captain (Logan Ware) |
| Approval date | 2026-10-02 |
| Approved revision | postfix-buy-no-calibration — OTM floor 0.5%; offline snapshot cache included; replay Sep 13–Oct 2 |
| Utterance | "I approve the existing postfix-buy-no-calibration implementation plan" + decisions 2–4 |
