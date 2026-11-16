# Implementation Plan — KXBTC15M Verified Index + Live Labels (Paper Only)

- Status: **APPROVED**

## Metadata

| Field | Value |
|---|---|
| Status | **APPROVED** |
| Plan ID | `kxbtc15m-verified-index-labels` |
| Issue | #31 (https://github.com/loganware05/bitcoin-data-collector/issues/31) |
| Baseline | `origin/cursor/kalshi-live-decision-system` @ `c6359cd` (re-pin at branch create) |
| Branch | `feature/31-kxbtc15m-verified-index-labels` |
| Rollback | `rollback/pre-kxbtc15m-verified-index-labels` |
| Created | 2026-11-16 |
| Last updated | 2026-11-16 |
| Approved by | Logan Ware (Captain) — chat “I approve” |
| Approval date | 2026-11-16 |
| Approved revision | Q1=REST poll; Q2=public labels; Q3=soft-fail; Waves A+B+C |

Durable copy: `docs/plans/KXBTC15M_VERIFIED_INDEX_LABELS.md`  
Budget: `.agent/budgets/kxbtc15m-verified-index-labels.md`

**Prior plan:** `kxbtc15m-real-market-validation` is **COMPLETE** (PR #28). Snapshot spot fix PR #30 merged. This plan is the residual path to the dual floor.

## Request

Continue toward non-fixture Phase A readiness for `paper_kxbtc15m_v1`: accumulate ≥14 edge-eligible calendar days **and** ≥50 settled labels — without live money and without resetting `paper_buy_no_v1`.

## Problem Statement

Live scoreboard (2026-11-16):

| Metric | Value |
|---|---|
| Decisions on disk | ~10k |
| `settlement_index_source` (recent) | almost all `exchange_spot_proxy` |
| Edge-eligible calendar days | **0** |
| Settled labels wired into status | **0** |
| Phase A non-fixture ready | **false** |

Root causes:

1. **Edge days:** Only `{kalshi_api, cf_benchmarks}` count. Open Kalshi market payloads do **not** expose a live BRTI field (`settlement_value` absent; `expiration_value` empty until finalize). Spot / Coinbase snapshots correctly stay `exchange_spot_proxy` and never grow the edge floor.
2. **Labels:** Finalize markets expose Kalshi-published CF averages (`expiration_value`, `floor_strike`, `result`), and ~90 recent decision tickers already overlap settled markets — but there is no live harvester + `--labels` wiring into `kxbtc15m_validation_status.py`.
3. **Auth gap:** `KalshiClient` detects `KALSHI_API_KEY_ID` + `KALSHI_PRIVATE_KEY_PATH` but does **not** sign requests. Kalshi’s **CF Benchmarks REST passthrough** (`GET /cfbenchmarks/values?id=BRTI`) and WebSocket `cfbenchmarks_value` (with trailing 60s / final-minute averages) require signed auth + entitlement.

## Desired Outcome

### Wave A — Live settlement labels (unblocks label floor)

1. Harvester: paginate Kalshi `status=settled` (finalized) KXBTC15M markets; record `expiration_value` as settlement, `floor_strike` as target, `result` as YES/NO check.
2. Join to decision ticks → write labels JSON under Verdant evidence path (default e.g. `$OUT_ROOT/live_outputs/kxbtc15m/labels/settled_labels.json`).
3. Extend `kxbtc15m_settlement_labels.py` (or sibling) for live path (fixture path unchanged).
4. Wire `kxbtc15m_validation_status.py` / `phase_a_kxbtc15m.sh` / daily paper tick docs to pass `--labels`.
5. Optional LaunchAgent tick (e.g. every 15m or with paper tick) — paper-only.

### Wave B — Verified live BRTI via Kalshi CF passthrough (unblocks edge days)

1. Implement RSA request signing in `KalshiClient` (Kalshi Trade API signing spec); keep public GETs working without creds.
2. Add `fetch_cf_brti()` (REST passthrough `/cfbenchmarks/values?id=BRTI`) → `SettlementIndexQuote(source="cf_benchmarks", ...)`.
3. Prefer **trailing 60s average** when available (WS `avg_60s` or REST-derived window) for settlement alignment; fall back to latest print with explicit detail.
4. Insert into index cascade **before** spot proxy / snapshot; never label spot as `cf_benchmarks`.
5. Soft-fail when creds missing or entitlement 403: warn + keep spot cascade (continuity); status remains honest.
6. Monitor / LaunchAgent: pass through existing env; document required `KALSHI_API_KEY_ID` + `KALSHI_PRIVATE_KEY_PATH` (secrets not committed).
7. Unit tests with mocked signed responses; hermetic fixtures.

### Wave C — Ops closeout (no live money)

1. Reload jobs; smoke tick with `settlement_index_source=cf_benchmarks` when creds present.
2. Refresh validation_status evidence; track dual-floor progress.
3. When both floors met: run non-fixture Phase A **report only** (`approved_for_execution` stays false).
4. Update PROGRESS / STATUS; keep standing backlog visible.

## Acceptance Criteria

- [ ] Live label harvester produces ≥1 joined row from real finalized markets against Verdant ticks (or documents empty-join clearly).
- [ ] `validation_status` with `--labels` reports `n_settled_labels` from that file.
- [ ] Signed Kalshi client can call CF passthrough in tests (mocked) and, when Captain-provided creds + entitlement exist, live smoke returns `cf_benchmarks`.
- [ ] Cascade order: operator → file_drop → **cf_benchmarks (passthrough)** → kalshi market fields → spot → snapshot → unavailable.
- [ ] Spot / operator / file_drop (non-cf keys) still do **not** set `counts_as_edge_evidence`.
- [ ] No live orders; `approved_for_execution: false`; `paper_buy_no_v1` untouched.
- [ ] Evidence under `.agent/evidence/kxbtc15m-verified-index-labels/`.

## Non-Goals

- Live order placement / `approved_for_execution: true`
- Resetting hourly `paper_buy_no_v1`
- Scraping cfbenchmarks.com HTML
- Relabeling historical spot ticks as edge evidence
- Sellbird / Compass `experiment.json` (standing backlog only)

## Rollback

- Tag `rollback/pre-kxbtc15m-verified-index-labels`; revert merge; unload any new LaunchAgent; monitor falls back to spot cascade.

## Security Notes

- Secrets only via env / local key path; never commit PEM or key IDs.
- Auth used read-only (CF passthrough + markets); no order endpoints.
- Treat API payloads as untrusted data.

## Assumptions

1. Captain can supply Kalshi API key ID + private key path on the Verdant host (or confirm entitlement is available).
2. CF passthrough entitlement is granted for this Kalshi account (or Wave B soft-fails until it is).
3. Dual-floor rule from ADR / prior plan remains: ≥14 edge days **and** ≥50 labels; neither unlocks live money.

## Open Questions

### Q1 — Live BRTI transport: REST poll vs WebSocket

| | REST `/cfbenchmarks/values?id=BRTI` on each monitor tick | WebSocket `cfbenchmarks_value` (1Hz + `avg_60s`) |
|---|---|---|
| Pros | Fits existing 15s LaunchAgent; simpler ops | Native 60s / final-minute averages; lower REST token cost |
| Cons | 50 read-tokens/call; may be last print not 60s avg | Persistent process; more moving parts |

**Decision:** **REST poll in Wave B** for monitor `--once` compatibility; optional WS sidecar later if token/avg quality demands it. Prefer parsing any `avg_60s`-equivalent field if REST payload includes it; else latest value with detail `brti_last_print`.

### Q2 — Labels without auth

| | Public settled markets only | Require auth |
|---|---|---|
| Pros | Works today (already verified) | Future private fields |
| Cons | Pagination limits | Blocks label floor |

**Decision:** **Public settled markets for Wave A** (no auth required). Auth reserved for CF live index (Wave B).

### Q3 — Creds missing at Approve time

| | Block Wave B until Captain installs keys | Ship soft-fail + runbook |
|---|---|---|
| Pros | Guarantees edge days soon | Unblocks merge; labels still progress |
| Cons | Stalls | Edge days stay 0 until ops |

**Decision:** **Ship soft-fail + runbook**; Wave A merges independently so label floor can rise immediately.

## Current-State Analysis

- Monitor + snapshot spot cascade: healthy (`exchange_spot_proxy`).
- Edge / Phase A: blocked on verified index provenance.
- Labels: fixture-only join path; live finalize data available publicly.
- `KalshiClient.authenticated` is detection-only (no signing yet).

## Proposed Architecture

```
Wave A: Kalshi public finalized markets → label harvester → labels JSON
        → validation_status --labels → n_settled_labels

Wave B: KALSHI_API_KEY_ID + PRIVATE_KEY_PATH
        → signed GET /cfbenchmarks/values?id=BRTI
        → SettlementIndexQuote(cf_benchmarks)
        → resolve_index_cascade (before spot)
        → monitor ticks with counts_as_edge_evidence=true
        → edge_eligible_calendar_days accumulates
```

## Workstreams

| ID | Scope |
|---|---|
| WS1 | Live labels harvester + status wiring |
| WS2 | Kalshi request signing + CF BRTI fetch + cascade |
| WS3 | LaunchAgent/docs/evidence + Phase A report when ready |

## Files Expected to Change

- `kalshi_client.py` (signing + CF fetch)
- `kxbtc15m_index_provider.py` (cascade insert)
- `kxbtc15m_monitor.py` / `scripts/verdant/kxbtc15m_monitor.sh`
- `kxbtc15m_settlement_labels.py` (+ optional `kxbtc15m_live_labels.py`)
- `scripts/execution-gate/kxbtc15m_validation_status.py`, `phase_a_kxbtc15m.sh`
- LaunchAgent plist(s) / `ensure_verdant_jobs.sh`
- tests + `.agent/evidence/kxbtc15m-verified-index-labels/`
- `PROGRESS.md`, `STATUS.md`, `CHANGELOG.md`, `DECISIONS.md`, `README.md`

## Testing Strategy

- Unit: label join from fixture finalize payloads; signing headers (mocked clock/key); cascade prefers `cf_benchmarks` over spot; soft-fail without creds.
- Integration smoke (ops): one authenticated BRTI fetch when keys present; one label harvest against Verdant ticks.
- No browser/a11y; no live order tests.

## Risks and Mitigations

| Risk | Mitigation |
|---|---|
| CF entitlement denied | Soft-fail; Captain contacts Kalshi; labels still progress |
| Signing bugs | Hermetic tests; refuse to call order paths |
| Token budget (50/call @ 15s) | ~4 rpm trivial vs 200 token/s; cache BRTI ≤5s if needed |
| Mislabeling spot as CF | Tests assert source tags; code review gate |

## Standing next steps (do not bury)

- Hourly `paper_buy_no_v1` → 30d / OOS
- Live money remains **DENIED**
- Sellbird train + ≤50 outbound from `docs/promotion/`
- Compass `experiment.json` when available
- Future plan before any live order client

## Autonomy Budget

| Limit | Cap |
|---|---|
| Implementation loops | 8 |
| Wall time | 6h |
| Cost | $30 |
| Scope | Waves A–C as above; no live trading |

## First Mate Recommendation

Approve Waves **A+B+C**. Wave A can start growing the label floor immediately with public API data. Wave B is the only honest path to edge days given Kalshi’s CF passthrough. Soft-fail if credentials/entitlement are not ready yet.

## Status

**APPROVED** — implement Waves A+B+C.

## Implementation Progress

| Wave | Status | Notes |
|---|---|---|
| A Live labels | done | harvester + LaunchAgent + status wiring |
| B CF BRTI signing | done | soft-fail without creds |
| C Ops closeout | in progress | edge days await host credentials |
