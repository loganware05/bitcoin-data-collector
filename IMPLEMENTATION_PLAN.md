# Implementation Plan — KXBTC15M Real-Market Validation (Paper Only)

- Status: **COMPLETE** (merged PR #28)

## Metadata

| Field | Value |
|---|---|
| Status | **COMPLETE** (merged PR #28 @ `e05a415`) |
| Plan ID | `kxbtc15m-real-market-validation` |
| Baseline | `778156d` |
| Branch | `feature/27-kxbtc15m-real-market-validation` |
| Issue | [#27](https://github.com/loganware05/bitcoin-data-collector/issues/27) |
| Rollback | `rollback/pre-kxbtc15m-real-market-validation` @ `778156d` |
| Approved by | Logan Ware (Captain) — chat **"Approve"** |
| Approval date | 2026-11-14 |
| Approved revision | All waves 0–3 + open-question decisions below |

## Approval record

Captain approved 2026-11-14 with: apply same open-question logic as before (defend both sides, then decide).

### Open-question decisions

#### 1. Live index source

| | Kalshi metadata / API | Honest spot proxy | Captain file drop |
|---|---|---|---|
| Pros | Closest to settlement if present | Always available; unblocks ticks | Explicit operator control |
| Cons | May lack CF fields | Not settlement-aligned | Manual ops burden |

**Decision: cascade.** Try verified Kalshi/market fields → optional file drop (`KXBTC15M_INDEX_FILE`) → spot proxy from collector/env with `exchange_spot_proxy` → `unavailable`. Never label manual/env numeric as `kalshi_api`.

#### 2. Readiness sample size

| | 100 labeled actionables | 14 edge-eligible days |
|---|---|---|
| Pros | Stronger stats | Aligns with calendar continuity |
| Cons | Slow for thin markets | Weak n for CPCV |

**Decision: dual floor for non-fixture Phase A attempt:** ≥**14** edge-eligible calendar days **and** ≥**50** settled labeled rows. Report progress on both; neither alone unlocks live money.

#### 3. Scope

**All waves 0–3.**

## Non-Goals

Live orders; `approved_for_execution: true`; reset `paper_buy_no_v1`.

## Approval Boundary

Implementation may begin. Live money remains DENIED.


## Completion record

| Field | Value |
|---|---|
| Merged PR | [#28](https://github.com/loganware05/bitcoin-data-collector/pull/28) |
| Merge commit | `e05a415` |
| Issue | [#27](https://github.com/loganware05/bitcoin-data-collector/issues/27) closed |
| Completed | 2026-11-14 |
| Live execution | DENIED |
| Residual | Ops dual-floor accumulation (index feed) |
