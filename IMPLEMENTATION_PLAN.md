# Implementation Plan — KXBTC15M Decision Engine

- Status: **APPROVED**

## Metadata

| Field | Value |
|---|---|
| Status | **APPROVED** |
| Plan ID | `kxbtc15m-decision-engine` |
| Repo | `bitcoin-data-collector` only |
| Source brief | ChatGPT assessment *Assess Kalshi Decisions* (2026-11-14) |
| Baseline | `cursor/kalshi-live-decision-system` @ `addc982` |
| Branch | `feature/21-kxbtc15m-decision-engine` |
| Issue | [#21](https://github.com/loganware05/bitcoin-data-collector/issues/21) |
| Rollback | tag `rollback/pre-kxbtc15m-decision-engine` @ `addc982` |
| Worktree | `/Users/loganware/bitcoin-data-collector-kxbtc15m` |
| Created | 2026-11-14 |
| Last updated | 2026-11-14 |
| Approved by | Logan Ware (Captain) — chat **"Approve"** |
| Approval date | 2026-11-14 |
| Approved revision | All waves A–D; defaults for open questions below |

## Approval record

Captain approved on 2026-11-14 with utterance: **"Approve"** (all waves A–D).

### Open-question defaults (Captain did not override)

| Question | Default locked at approval |
|---|---|
| Series ticker | `KXBTC15M` (probe/document if API differs) |
| Poll interval | **10s** (within 5–15s band) |
| Paper filters | Dual-side with strict edges (`min_edge=0.20`, `min_confidence=0.65`) |
| Live GETs in Wave A | Fixtures for CI; optional Captain-local live read-only smoke |
| Scope | All waves A–D |

## Request

Build a dedicated **Kalshi BTC 15-minute (`KXBTC15M`) decision engine** so the repo can produce calibrated BUY YES / BUY NO / NO TRADE recommendations for contracts like “BTC 15min Target 65,586.65 UP/DOWN”, without enabling live-money trading.

## Problem Statement

The repo can collect BTC data, score hourly `KXBTCD` contracts, and run paper continuity under `paper_buy_no_v1`. It cannot yet responsibly decide a Kalshi **15-minute** UP/DOWN market because:

1. Series discovery defaults to `KXBTC` / `KXBTCD` only — **no `KXBTC15M` first-class support**.
2. Event parsing and hourly scan paths assume hourly tickers, not 15-minute slots.
3. Probability models forecast spot / strike CDFs — **not** Kalshi’s CF Benchmarks settlement rule.
4. Monitoring cadence is too coarse for a 15-minute contract life.
5. ML labels are generic horizon up/down, not **contract-settlement outcomes** for `KXBTC15M`.
6. Live execution remains correctly **DENIED**; any new 15m strategy must be a **separate** paper candidate.

## Desired Outcome

Full Wave A–D acceptance criteria, architecture, and risks are in `docs/plans/KXBTC15M_DECISION_ENGINE.md`.

### Waves (summary)

- **A** Discovery + JSON decision report (fail → NO TRADE)
- **B** Settlement-aligned P(UP)/P(DOWN) + fee/spread edge
- **C** 10s monitor loop (separate from hourly/`paper_buy_no_v1`)
- **D** Settlement-labeled ML + `paper_kxbtc15m_v1` paper strategy

## Non-Goals

- Live-money Kalshi orders or flipping `approved_for_execution` to true
- Resetting `paper_buy_no_v1` / its 30-day clock
- Claiming UP/DOWN from an illustrative target alone
- NorthStar control-repo product changes

## Approval Boundary

**Implementation may begin.** Live money remains denied. Stop at autonomy budget limits.
