# Implementation Plan — KXBTC15M Live-Readiness Pipeline (Paper Only)

- Status: **COMPLETE** (merged PR #25)

## Metadata

| Field | Value |
|---|---|
| Status | **COMPLETE** (merged PR #25) |
| Plan ID | `kxbtc15m-live-readiness` |
| Repo | `bitcoin-data-collector` only |
| Goal | Reach Captain live-trading **eligibility** for 15m markets — **without** enabling live money in this plan |
| Baseline | `cursor/kalshi-live-decision-system` @ `b4d9027` (re-pin at branch create) |
| Branch | `feature/24-kxbtc15m-live-readiness` |
| Issue | [#24](https://github.com/loganware05/bitcoin-data-collector/issues/24) |
| Rollback | tag `rollback/pre-kxbtc15m-live-readiness` |
| Prior completed | `kxbtc15m-decision-engine` (#21 / PR #22) |
| Created | 2026-11-14 |
| Last updated | 2026-11-14 |
| Approved by | Logan Ware (Captain) — chat **I approve** |
| Approval date | 2026-11-14 |

Capability artifacts: `.agent/plans/kxbtc15m-live-readiness/`  
Durable copy: `docs/plans/KXBTC15M_LIVE_READINESS.md`  
Budget: `.agent/budgets/kxbtc15m-live-readiness.md`


## Approval record

Captain approved 2026-11-14. Open-question decisions: (1) StartInterval 15s + `--once`; (2) daily tick 23:50; (3) dual-mode edge evidence by `settlement_index_source`; (4) all waves 0–4.

## Request

Build a **seamless, automated paper pipeline** so `paper_kxbtc15m_v1` can accumulate uninterrupted evidence toward the Captain live-trading checklist, while **preserving** existing hourly paper continuity and other standing next steps. Live Kalshi orders remain **DENIED**.

## Problem Statement

The decision engine exists (#22), but readiness is blocked by operations gaps:

1. No continuous live read-only `KXBTC15M` monitor job (only manual/`--once`).
2. No daily LaunchAgent for `paper_kxbtc15m_v1` (hourly `paper_buy_no_v1` tick exists; 15m does not).
3. Settlement labeling / Phase A for **15m** is fixture-level only.
4. STATUS board still frames hourly paper; 15m readiness is easy to lose track of.
5. Prior next steps (Sellbird, hourly 30d, Compass `experiment.json`) must not be buried by the new goal.

## Desired Outcome

A working pipeline operators can leave running:

```
Kalshi KXBTC15M (read-only)
        │
        ▼
kxbtc15m_monitor (LaunchAgent)
        │  live_outputs/kxbtc15m/ + Verdant/local staging
        ▼
paper_kxbtc15m_daily_tick (LaunchAgent, daily)
        │  .agent/evidence/.../paper-kxbtc15m/  (SEPARATE from paper/)
        ▼
settlement label ingest → Phase A CPCV/DSR (15m)
        │
        ▼
STATUS + PROGRESS readiness board (15m + hourly + standing backlog)
```

When this plan completes, the repo can **run and measure** the path to live eligibility. A **separate** future plan is still required before any live order client or `approved_for_execution: true`.

## Standing backlog (must remain visible)

These stay in PROGRESS as **Standing next steps** and are **not** replaced by this plan:

| Item | Status | Owner track |
|---|---|---|
| Hourly `paper_buy_no_v1` → 30d / OOS floors (no calendar gaps) | In progress | Existing LaunchAgent |
| Keep live money **DENIED** | Standing rule | All plans |
| Sellbird train + first ≤50 outbound from `docs/promotion/` | Pending | Agensi / promo |
| Supply live Compass `experiment.json` when available | Blocked externally | AHF / Compass |
| Optional Captain-local live `KXBTC15M` read-only smoke | Starts in Wave 0 | This plan |

## Acceptance Criteria

### Wave 0 — Operator smoke + backlog hygiene

- [ ] PROGRESS has dual sections: **Primary goal** (this plan) + **Standing next steps**
- [ ] Documented one-shot live read-only smoke (or soft-skip evidence if series unavailable)
- [ ] Confirm hourly paper LaunchAgent still loaded (`ensure_verdant_jobs.sh --check`)
- [ ] Evidence under `.agent/evidence/kxbtc15m-live-readiness/wave-0/`

### Wave 1 — Continuous 15m monitor job (reuse existing modules)

- [ ] Wrapper `scripts/verdant/kxbtc15m_monitor.sh` → `kxbtc15m_monitor.py`
- [ ] LaunchAgent `com.verdant.btc-kalshi.kxbtc15m-monitor`
- [ ] Wired into `ensure_verdant_jobs.sh`
- [ ] ADR-003-compatible outputs; does not touch `paper_buy_no_v1` clock
- [ ] Soft-fail / backoff; logs under `~/Library/Logs/verdant/`
- [ ] Evidence: smoke tick + `--check` OK

### Wave 2 — Daily `paper_kxbtc15m_v1` continuity

- [ ] `scripts/execution-gate/paper_tick_kxbtc15m_daily.sh` (mirror `paper_tick_daily.sh`)
- [ ] Reuses `phase_b_kxbtc15m_paper_tick.py` + `paper_strategy_kxbtc15m_v1.json`
- [ ] LaunchAgent daily (default **23:50** local, after hourly 23:45)
- [ ] Soft-skip when no `kxbtc15m_tick_*.json`; refuse shared `paper/` dir
- [ ] Smoke tests for soft-skip path
- [ ] Evidence under `paper-kxbtc15m/` + wave-2

### Wave 3 — Settlement labels + Phase A for 15m

- [ ] Join decision ticks → settled outcomes (reuse settlement eval / label store patterns)
- [ ] Hermetic fixture path + optional live refresh
- [ ] `phase_a_cpcv_dsr.py` (or adapter) report for 15m paper returns
- [ ] Calibration via `kxbtc15m_ml.py` on growing labels
- [ ] Pass/fail recorded; **no** auto live unlock

### Wave 4 — Readiness STATUS board + docs

- [ ] `STATUS.md` dual tracks: hourly vs `KXBTC15M`
- [ ] TESTING.md / README operator section
- [ ] ADR for paper-only live-readiness pipeline
- [ ] Captain checklist with GO/NO-GO (live remains NO-GO)

## Non-Goals

- Live Kalshi order placement / trading client
- Setting `approved_for_execution: true`
- Resetting or pausing `paper_buy_no_v1`
- Replacing Sellbird / Agensi / Compass experiment backlog
- NorthStar control-repo product changes

## Reuse map

| Existing | Role |
|---|---|
| `kxbtc15m_monitor.py` / decision engine | Monitor + decisions |
| `phase_b_kxbtc15m_paper_tick.py` / strategy JSON | Paper fills |
| `paper_tick_daily.sh` + paper LaunchAgent | Template for 15m daily tick |
| `ensure_verdant_jobs.sh` | Install/reload |
| `phase_a_cpcv_dsr.py` / Phase C stubs | Gate evidence |
| `kalshi_settlement_eval.py` / `settlement_label_store.py` | Settlement join |
| `kxbtc15m_ml.py` | Calibration |
| Hourly paper path | Keep running in parallel |

## Workstreams

| ID | Focus | Depends |
|---|---|---|
| W0 | PROGRESS dual backlog + smoke | — |
| W1 | Monitor shell + LaunchAgent | W0 |
| W2 | Daily 15m paper tick + LaunchAgent | W1 |
| W3 | Settlement labels + Phase A 15m | W2 |
| W4 | STATUS + ADR + docs | W2, W3 |

## Autonomy budget

| Limit | Value |
|---|---|
| Max iterations | 6 |
| Max wall time | 4 hours without Captain check-in |
| Forbidden | Live orders; flip execution approval; reset hourly paper clock |

## Open Questions (Captain)

1. Monitor: KeepAlive loop vs StartInterval (e.g. 60s one-tick wrapper)?
2. Daily 15m paper tick at **23:50** local OK?
3. Count edge evidence with spot-proxy, or require Kalshi/CF index first?
4. Approve **all waves**, or **Wave 0–2 only** first?

## Risks

| Risk | Mitigation |
|---|---|
| Calendar gaps | Daily LaunchAgent + soft-skip alerts |
| Contaminating hourly paper | Separate dirs; refuse `paper/` |
| Rate limits | Existing backoff; ≥5s floor |
| Series unavailable | Soft-skip + STATUS blocker |
| Scope creep to live | Hard non-goals |

## Security Notes

Read-only market data; no order endpoints; `approved_for_execution` stays false.

## Rollback

Bootout new LaunchAgents; revert PR; hourly jobs and `paper_buy_no_v1` clock untouched.

## Approval Boundary

**Implementation must not begin until the Captain explicitly approves this plan.**

Reply: **Approve** | **Approve Wave 0–2 only** | **Revise** | **Reject**
