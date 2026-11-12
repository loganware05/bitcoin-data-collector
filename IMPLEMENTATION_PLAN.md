# Implementation Plan — XRV Pilot B Paper Continuity

- Status: APPROVED

## Metadata

| Field | Value |
|---|---|
| Status | APPROVED |
| Plan ID | `xrv-pilot-b-paper-continuity` |
| Parent | NorthStar XRV `xrv-release-integrity` (#261) |
| Repo | `bitcoin-data-collector` only |
| Baseline HEAD (pre-hardening) | `cursor/kalshi-live-decision-system` @ `8db4fcc8be352ab244863462f649f4c08cd63da0` (PR #16 merged) |
| Branch | `feature/17-xrv-pilot-b-paper-continuity` |
| Issue | [#17](https://github.com/loganware05/bitcoin-data-collector/issues/17) |
| Rollback | tag `rollback/pre-xrv-pilot-b-paper-continuity` @ `8db4fcc` |
| Prior plan | `execution-gate-evidence` (APPROVED 2026-10-08; PR #12/#14/#15/#16 merged) |

## Authority boundary

**Approved:** restore uninterrupted **paper** validation continuity (simulated fills), LaunchAgent install evidence, local-staging fallback, docs/evidence. Live money remains DENIED.

**Still DENIED until separate written Captain approval for live money:**

- Live Kalshi orders
- Production execution flags / Compass “execution allowed”
- `approved_for_execution: true`

## Desired Outcome

Restore an uninterrupted daily paper-validation workflow so the 30-day day clock can accumulate without calendar-gap resets, with Captain-visible evidence that the LaunchAgent is loaded and ticking.

## Non-Goals

- Live Kalshi orders / real money
- Setting `approved_for_execution: true`
- Production-wiring Phase C into a live order path
- Claiming 30d OOS complete in this implementation window
- Unblocking Compass main `experiment.json` (orthogonal)

## Workstreams

| ID | Focus | Status |
|---|---|---|
| W1 | Land daily paper-tick scheduler (PR #16) | **DONE** (merged 2026-11-12 → `8db4fcc`) |
| W2 | Harden hourly fallback + soft-skip evidence | **DONE** |
| W3 | Captain host deploy + smoke tick + clock restart doc | **DONE** |
| W4 | PROGRESS/STATUS/TESTING + XRV evidence packet | **DONE** |

## Acceptance Criteria

- [x] Plan APPROVED with Captain utterance + date
- [x] Daily paper-tick script + plist merged to default (PR #16)
- [x] Host LaunchAgent loaded (`ensure_verdant_jobs.sh --check` evidence)
- [x] Successful post-merge smoke tick with `approved_for_execution: false`
- [x] `day_clock.json` documents post-gap restart with reason (`calendar_gap_days=26`)
- [x] Soft-skip / local-fallback behavior documented and smoke-tested
- [x] No live order path introduced; strategy JSON still `approved_for_execution: false`
- [x] PROGRESS/STATUS/TESTING updated; XRV evidence packet present
- [ ] 30d completion remains in progress (not claimed) — wall-clock ongoing

## Rollback

```bash
git checkout cursor/kalshi-live-decision-system
git reset --hard rollback/pre-xrv-pilot-b-paper-continuity
launchctl bootout gui/$(id -u)/com.verdant.btc-kalshi.execution-gate-paper-tick || true
rm -f ~/Library/LaunchAgents/com.verdant.btc-kalshi.execution-gate-paper-tick.plist
```

## Autonomy Budget

| Limit | Value |
|---|---|
| Maximum iterations | 8 |
| Maximum failed validation cycles | 3 |
| Maximum estimated cost (USD) | 75 |
| Maximum elapsed minutes | 180 active (excludes 30d wall clock) |
| Ledger | `.agent/budgets/xrv-pilot-b-paper-continuity.md` |

## Approval Record

| Field | Value |
|---|---|
| Approved by | Captain (Logan Ware) |
| Approval date | 2026-11-11 |
| Approved revision | `xrv-pilot-b-paper-continuity` — paper continuity only; live money DENIED |
| Utterance | "I approve, and I've merged PR #13" (PR #16 merged; daily tick for #13) |
