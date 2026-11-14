# Implementation Plan — KXBTC15M Decision Engine

- Status: **APPROVED**

## Metadata

| Field | Value |
|---|---|
| Status | **APPROVED** |
| Plan ID | `kxbtc15m-decision-engine` |
| Repo | `bitcoin-data-collector` only |
| Source brief | ChatGPT assessment *Assess Kalshi Decisions* (2026-11-14) — attach `assess-kalshi-decisions-6af89d8c.md` |
| Baseline | `cursor/kalshi-live-decision-system` @ `addc982` (re-pin at branch create) |
| Branch | `feature/21-kxbtc15m-decision-engine` |
| Issue | [#21](https://github.com/loganware05/bitcoin-data-collector/issues/21) |
| Rollback | tag `rollback/pre-kxbtc15m-decision-engine` at baseline SHA |
| Created | 2026-11-14 |
| Last updated | 2026-11-14 |
| Approved by | Logan Ware (Captain) — chat **Approve** |
| Approval date | 2026-11-14 |

Capability artifacts: `.agent/plans/kxbtc15m-decision-engine/`  
Durable copy: `docs/plans/KXBTC15M_DECISION_ENGINE.md`  
Budget ledger: `.agent/budgets/kxbtc15m-decision-engine.md`

## Prior plan note

Plan `agensi-promo-hygiene` (#19 / PR #20) is **merged and complete**. This plan **supersedes** it as the active product plan. It does **not** interrupt the in-flight `paper_buy_no_v1` 30-day paper clock (day **3/30** as of 2026-11-14).

## Request

Build a dedicated **Kalshi BTC 15-minute (`KXBTC15M`) decision engine** so the repo can produce calibrated BUY YES / BUY NO / NO TRADE recommendations for contracts like “BTC 15min Target 65,586.65 UP/DOWN”, without enabling live-money trading.

## Problem Statement

The repo can collect BTC data, score hourly `KXBTCD` contracts, and run paper continuity under `paper_buy_no_v1`. It cannot yet responsibly decide a Kalshi **15-minute** UP/DOWN market because:

1. Series discovery defaults to `KXBTC` / `KXBTCD` only — **no `KXBTC15M` first-class support** (`kalshi_client.DEFAULT_BTC_SERIES_TICKERS`).
2. Event parsing and hourly scan paths assume `KXBTCD-…-T{strike}` hourly tickers, not 15-minute slots.
3. Probability models forecast spot / strike CDFs — **not** Kalshi’s CF Benchmarks settlement rule (compare average in the minute before close vs minute before open).
4. Monitoring cadence is **~15 minutes** for snapshots and **~hourly** for decisions — too coarse for a 15-minute contract life.
5. ML labels are generic horizon up/down, not **contract-settlement outcomes** for `KXBTC15M`.
6. Live execution remains correctly **DENIED**; any new 15m strategy must be a **separate** paper candidate, not an automatic extension of `paper_buy_no_v1`.

## Desired Outcome

A research-stage **KXBTC15M Decision Engine** that:

1. Discovers live `KXBTC15M` markets and extracts target, expiry, YES/NO asks, and order book.
2. Estimates `P(UP)` / `P(DOWN)` under settlement-aligned rules (CF Benchmarks / final 60s averages where API-supported).
3. Computes net edge after fees/spread and emits `BUY YES` / `BUY NO` / `NO TRADE` with an explicit reason.
4. Runs a higher-frequency monitor loop (target **5–15s** quote poll with rate-limit backoff; event-driven updates preferred when available).
5. Trains/validates against historical `KXBTC15M` settlements with time-ordered OOS evaluation and calibration.
6. Registers a **separate** paper strategy (e.g. `paper_kxbtc15m_v1`) under the existing execution-gate pattern, with `approved_for_execution: false` hard-locked.
7. Emits decision reports shaped like:

```json
{
  "series": "KXBTC15M",
  "target_price": 65586.65,
  "time_remaining_seconds": null,
  "model_probability_up": null,
  "model_probability_down": null,
  "yes_ask": null,
  "no_ask": null,
  "net_edge": null,
  "recommendation": "NO TRADE",
  "reason": "Awaiting live contract data and validated model"
}
```

## Acceptance Criteria

### Wave A — Discovery + decision report (no ML retrain required)

- [ ] `KXBTC15M` is an explicit series ticker in client discovery (default list or documented opt-in that examples/CLI use by default for the 15m path)
- [ ] Parser extracts target price, open/close window, and UP/DOWN / YES/NO sides from live (or fixture) markets
- [ ] CLI or module entrypoint produces a JSON decision report with the fields above
- [ ] Missing quotes / time / model → **NO TRADE** with reason (never invent UP/DOWN)
- [ ] Hermetic fixture tests cover discovery + parse + NO TRADE fail-closed paths
- [ ] Evidence under `.agent/evidence/kxbtc15m-decision-engine/wave-a/`

### Wave B — Settlement-aligned probability + edge

- [ ] Settlement model documents and implements Kalshi 15m rule alignment (CF Benchmarks / last-60s averages via Kalshi-supported data; fixture path when live index unavailable)
- [ ] Edge calculator includes fees + spread; positive EV alone does not flip `approved_for_execution`
- [ ] Reuses fair-value / orderbook guard patterns where applicable; series-specific thresholds documented
- [ ] Unit tests for settlement labeling, edge math, and guard → NO TRADE
- [ ] Evidence under `.agent/evidence/kxbtc15m-decision-engine/wave-b/`

### Wave C — Higher-frequency monitor

- [ ] Monitor loop distinct from `snapshot_daemon` 900s default and hourly scan LaunchAgent
- [ ] Configurable poll interval (default in 5–15s band) with rate-limit backoff; no unbounded request storms
- [ ] Writes decision ticks to a dedicated output dir (Verdant + local staging compatible with ADR-003)
- [ ] Does **not** advance or reset the `paper_buy_no_v1` day clock
- [ ] Evidence under `.agent/evidence/kxbtc15m-decision-engine/wave-c/`

### Wave D — Contract-specific ML + separate paper strategy

- [ ] Training/eval pipeline uses `KXBTC15M` settlement outcomes (time-ordered OOS); calibration report recorded
- [ ] New strategy JSON (e.g. `paper_kxbtc15m_v1`) with `approved_for_execution: false`
- [ ] Separate day-clock state dir so hourly `paper_buy_no_v1` continuity is undisturbed
- [ ] Live Kalshi order placement remains impossible / denied in this plan’s scope
- [ ] `python3 -m pytest tests/ -q` green; TESTING.md updated
- [ ] ADR + PROGRESS/CHANGELOG/README updates; evidence under `.agent/evidence/kxbtc15m-decision-engine/wave-d/`

## Non-Goals

- Live-money Kalshi orders, API keys for trading, or flipping any `approved_for_execution` to true
- Replacing or resetting `paper_buy_no_v1` / its 30-day clock
- Claiming a specific UP/DOWN call for an illustrative target (e.g. $65,586.65) without live book + validated model
- Changing NorthStar control-repo product behavior
- Agensi / Sellbird promo work
- Automatic promotion from paper → live after 30 days (still Captain-gated, separate plan)

## Current behavior (evidence)

| Capability | State |
|---|---|
| BTC collection / indicators / ML horizons | Implemented |
| Hourly `KXBTCD` fair-value decisions | Implemented (`hourly_event_scanner` → `hourly_fair_value_engine`) |
| Kalshi client series defaults | `("KXBTC", "KXBTCD")` only |
| `KXBTC15M` string in repo | **Absent** |
| CF Benchmarks / 60s settlement forecast | **Not implemented** (settlement eval uses Kalshi `result`) |
| Snapshot / live cadence | 900s / 15m defaults |
| Paper strategy | `paper_buy_no_v1`, day 3/30, live denied |
| Execution authority | **DENIED** |

## Proposed architecture

```
KXBTC15M live market ──► series discovery + target/expiry parse
        │
        ├── BTC intelligence (price, vol, momentum, optional flows)
        ├── market intelligence (settlement index, spread, depth, TTE)
        └── 15m probability model (settlement-aligned)
                │
                ▼
        edge + risk gates ──► BUY YES / BUY NO / NO TRADE
                │
                ▼
        paper strategy `paper_kxbtc15m_v1` (separate clock; live denied)
```

### Suggested modules (names flexible at impl time)

| Module | Role |
|---|---|
| Extend `kalshi_client.py` | Discover `KXBTC15M` |
| `kxbtc15m_event_parser.py` (new) | Target / window / side parse |
| `kxbtc15m_settlement_model.py` (new) | CF/60s-aligned P(UP)/P(DOWN) |
| `kxbtc15m_decision_engine.py` (new) | Fuse quotes + model → report |
| `kxbtc15m_monitor.py` (new) or script | High-frequency loop |
| `scripts/execution-gate/paper_strategy_kxbtc15m_v1.json` | Separate paper candidate |
| Fixtures under `tests/fixtures/kxbtc15m/` | Hermetic markets + settlements |

Reuse: `kalshi_orderbook_features.py`, fair-value edge patterns, `settlement_label_store.py` cache pattern, execution-gate day-clock harness **as a template**.

## Workstreams

| ID | Focus | Depends | Parallelizable |
|---|---|---|---|
| W0 | Architecture brief + fixture contracts + ADR draft | — | no |
| W1 | Series discovery + parser + decision report CLI (Wave A) | W0 | no |
| W2 | Settlement-aligned probability + edge/guards (Wave B) | W1 | no |
| W3 | High-frequency monitor + staging paths (Wave C) | W1 | yes w/ W2 after W1 |
| W4 | Settlement-labeled ML train/eval + calibration report (Wave D) | W2 | no |
| W5 | Separate paper strategy + gate wiring (Wave D) | W3, W4 | no |
| W6 | Tests, evidence, docs, PR | W5 | no |

## Required Capabilities

Inferred for this Python/ML product objective (matcher also emitted React noise; **ignored** — no UI in scope):

- python-service-development
- ml-training / ml-evaluation / experiment-reproducibility
- unit-test-execution / integration-test-execution
- definition-of-done-validation / validation-evidence-capture
- github-issue-create / github-pr-create / pr-description-assembly
- security review (API keys, no live trading paths)

## Reusable Capabilities Found

| Skill | Notes |
|---|---|
| `python-ml` | Training/eval/calibration |
| `testing-validation` | pytest + evidence |
| `security-review` | Secrets / execution denial |
| `github-integration` | Issue + PR |
| `autonomy-budget` | Stop limits |
| `implementation-planning` / `capability-planning` | This plan |
| `repository-discovery` | Done for this plan |

### Capability Gaps

Matcher reported none for inferred caps. **Product gaps** (not Skill gaps) are the real work: `KXBTC15M` discovery, CF/60s settlement model, sub-minute monitoring, settlement-labeled ML, separate paper strategy.

## Technology Intelligence Candidates

> **NOT APPROVED FOR EXECUTION** — discovery signals only.

Stub provider; no external candidates queried. Optional later DISCOVERED refs (do not vendor): Kalshi Help Center settlement docs; starred `ryanfrigo/kalshi-ai-trading-bot` as research only.

## Task Graph (human-corrected)

Machine graph under `.agent/plans/kxbtc15m-decision-engine/task-graph.json` incorrectly included frontend tasks. **Authoritative graph:**

| Task ID | Objective | Dependencies | Parallelizable |
|---|---|---|---|
| `task-discovery` | Confirm series API shapes + fixture needs (read-only) | — | no |
| `task-architecture` | Contracts for parser, settlement model, decision JSON, paper strategy | task-discovery | no |
| `task-impl-discovery` | Client + parser + decision report (Wave A) | task-architecture (hard) | no |
| `task-impl-settlement` | Settlement-aligned probs + edge (Wave B) | task-impl-discovery (hard) | yes w/ monitor after discovery |
| `task-impl-monitor` | High-frequency monitor (Wave C) | task-impl-discovery (hard) | yes w/ settlement |
| `task-impl-ml` | Settlement-labeled train/eval (Wave D) | task-impl-settlement (hard) | no |
| `task-impl-paper` | Separate paper strategy + clock (Wave D) | task-impl-monitor, task-impl-ml | no |
| `task-validation` | pytest + evidence packs | task-impl-paper | no |
| `task-documentation` | ADR, PROGRESS, TESTING, README, CHANGELOG, PR | task-validation | no |

## Proposed Agent Configuration

| Task | Profile | Skills |
|---|---|---|
| discovery | `repository-scout` | `repository-discovery` |
| architecture | `architecture-agent` | `capability-planning`, `python-ml` |
| impl-* | `implementation-agent` | `python-ml`, `autonomy-budget`, `code-structure-cleanup` |
| validation | `test-engineer` | `testing-validation`, `security-review` |
| documentation | `documentation-agent` | `pull-request-preparation`, `github-integration` |

## Evaluation Strategy

- Wave A–D acceptance checklists above
- `python3 -m pytest tests/ -q` must pass; never weaken existing hourly/paper tests
- Hermetic fixtures for API/settlement; live Kalshi reads optional and Captain-local
- Security: confirm no order endpoints wired; strategy JSON stays `approved_for_execution: false`
- Adversarial review before merge
- Success metric: calibrated probabilities track settlement frequencies **and** paper EV after costs — not raw directional accuracy alone

## Learning Plan

Retain under `.agent/plans/kxbtc15m-decision-engine/` and evidence dirs. After paper OOS results exist, feed calibration gaps into a follow-on plan (not this one) before any live discussion.

## Autonomy budget

| Limit | Value |
|---|---|
| Max iterations | 8 (across waves; stop + Budget Stop Report if hit) |
| Max wall time | 6 hours agent time without Captain check-in |
| Cost ceiling | Captain-local; stop if unexpected paid API spend |
| Forbidden | Live orders; resetting `paper_buy_no_v1` clock; secrets in git |

Track in `.agent/budgets/kxbtc15m-decision-engine.md`.

## Assumptions

1. Kalshi still offers a `KXBTC15M` (or equivalent) 15-minute BTC series discoverable via Trade API; exact ticker confirmed in Wave A against live or documented API.
2. Settlement remains CF Benchmarks–style open/close minute averages per Kalshi Help Center; if rules differ, Wave B documents the actual rule from market metadata before coding.
3. Paper continuity for hourly `paper_buy_no_v1` must continue uninterrupted.
4. Verdant path `/Volumes/Verdant_AI/btc_kalshi/` + ADR-003 local staging remain the data roots.
5. Captain will not request live trading in this plan’s scope.

## Open Questions (Captain)

1. Confirm series ticker string (`KXBTC15M` vs current Kalshi naming) before Wave A locks fixtures.
2. Preferred default poll interval: **5s**, **10s**, or **15s**?
3. Should Wave D paper strategy prefer BUY NO–biased filters (like `paper_buy_no_v1`) or dual-side with stricter edges?
4. May Wave A use live read-only Kalshi market GETs during implementation, or fixtures-only until a later gate?
5. Approve all waves now, or **Wave A–B only** first (decision module before monitor/ML/paper)?

## Risks

| Risk | Mitigation |
|---|---|
| Series renamed / unavailable | Fail closed to NO TRADE; document ticker probe in evidence |
| Spot model mistaken for settlement model | Explicit settlement module + tests against labeled outcomes |
| Rate limits / ban risk on fast polling | Backoff, jitter, documented caps |
| Contaminating hourly paper clock | Separate strategy id + state directory |
| Overclaiming edge from uncalibrated probs | Default NO TRADE until calibration evidence exists |
| Accidental live trading | No order client; `approved_for_execution: false` const; security review |

## Security Notes

- No secrets in repo; Kalshi auth stays env-only if required for private endpoints
- Read-only market data preferred for Waves A–C
- Live execution remains DENIED; do not add place-order helpers in this plan
- Decision reports may include prices — treat evidence as sensitive operational data

## Rollback

1. Revert feature PR(s) or reset to `rollback/pre-kxbtc15m-decision-engine`.
2. Disable any new LaunchAgent/monitor scripts; leave hourly + `paper_buy_no_v1` jobs untouched.
3. Remove or ignore `paper_kxbtc15m_v1` state dir; hourly paper clock unchanged.
4. Document rollback SHA in PROGRESS.

## Review Domains

- python / Kalshi API client
- ML / calibration
- execution-gate / paper continuity
- security (no live trading)
- tests / evidence

## Approval Boundary

**Implementation must not begin until the Captain explicitly approves this plan.**

Reply with one of:

- **Approve** — all waves A–D
- **Approve Wave A–B only** — discovery + settlement decision module first
- **Revise** — with answers to Open Questions / scope edits
- **Reject**

Machine-generated capability matches and agent manifests are **proposals** only.
