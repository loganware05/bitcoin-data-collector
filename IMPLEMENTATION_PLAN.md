# Implementation Plan — KXBTC15M Live-Readiness Pipeline (Paper Only)

- Status: **APPROVED**

## Metadata

| Field | Value |
|---|---|
| Status | **APPROVED** |
| Plan ID | `kxbtc15m-live-readiness` |
| Repo | `bitcoin-data-collector` only |
| Baseline | `cursor/kalshi-live-decision-system` @ `b4d9027` |
| Branch | `feature/24-kxbtc15m-live-readiness` |
| Issue | [#24](https://github.com/loganware05/bitcoin-data-collector/issues/24) |
| Rollback | `rollback/pre-kxbtc15m-live-readiness` @ `b4d9027` |
| Worktree | `/Users/loganware/bitcoin-data-collector-kxbtc15m` |
| Created | 2026-11-14 |
| Approved by | Logan Ware (Captain) — chat **"I approve"** |
| Approval date | 2026-11-14 |
| Approved revision | All waves 0–4 + open-question decisions below |

## Approval record

Captain approved 2026-11-14: **"I approve"** with instruction to defend both sides on open questions then decide.

### Open-question decisions

#### 1. Monitor: KeepAlive loop vs StartInterval + `--once`

| | KeepAlive in-process loop | StartInterval + `--once` |
|---|---|---|
| Pros | True ~10s cadence; one process; lower scheduling jitter | Crash isolation; matches existing Verdant LaunchAgents; laptop sleep/wake safer; launchd restarts cleanly |
| Cons | One hung process stalls all ticks; harder to reason about; atypical vs hourly/paper jobs | 15s floor coarser than 5–10s ideal; more process churn |

**Decision: StartInterval 15s calling `--once`.** Crash isolation and consistency with `ensure_verdant_jobs.sh` beat in-process KeepAlive on a laptop host. 15s still yields ~60 samples per 15m contract.

#### 2. Daily 15m paper tick at 23:50

| | 23:50 (after hourly 23:45) | Same minute / other time |
|---|---|---|
| Pros | Avoids disk/API contention with hourly tick; clear ops story | Slightly simpler single window |
| Cons | Two late-night jobs; if host asleep, both miss | Contention or confused logs if same minute |

**Decision: 23:50 local.** Soft-skip already protects missing feeds; separation from 23:45 is worth five minutes.

#### 3. Spot-proxy vs require CF/Kalshi index for edge evidence

| | Spot-proxy counts as edge | Index-only for edge |
|---|---|---|
| Pros | Unblocks paper clock immediately | Honest settlement-aligned evidence |
| Cons | Contaminates live-readiness claims | May stall if API lacks index |

**Decision: Dual-mode.** Always record `settlement_index_source`. Ticks with `exchange_spot_proxy` / `unavailable` still run paper continuity but set `counts_as_edge_evidence: false`. Phase A / readiness GO requires `kalshi_api` or `cf_benchmarks` (or fixture in hermetic tests only).

#### 4. Scope

**Decision: All waves 0–4** (Captain Approve).

## Non-Goals

- Live Kalshi orders; `approved_for_execution: true`
- Resetting `paper_buy_no_v1`
- Burying Sellbird / Compass experiment / hourly 30d standing steps

## Waves

See `docs/plans/KXBTC15M_LIVE_READINESS.md` for full acceptance criteria. Summary: W0 backlog+smoke → W1 monitor job → W2 daily 15m paper tick → W3 settlement+Phase A → W4 STATUS/docs.

## Approval Boundary

**Implementation may begin.** Live money remains DENIED.
