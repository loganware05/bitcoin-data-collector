# Implementation Plan — Execution Gate Evidence (AHF-P06 follow-on)

## Metadata

| Field | Value |
|---|---|
| Status | **APPROVED** |
| Plan ID | `execution-gate-evidence` |
| Product | `bitcoin-data-collector` (coordination) + Compass assessor + sandbox/paper path |
| Baseline | `cursor/kalshi-live-decision-system` @ `e4be26c` |
| Branch | `feature/local-execution-gate-evidence` (tracks cloud `docs/execution-gate-evidence-1043`) |
| Upstream | Compass [PR #192](https://github.com/loganware05/captains-compass-cursor/pull/192) / AHF-P06 v1.54.0 |
| Issue | `local/execution-gate-evidence` (GitHub issue blocked: local `gh` token invalid) |
| Draft PR | https://github.com/loganware05/bitcoin-data-collector/pull/12 |
| Rollback | tag `rollback/pre-execution-gate-evidence` @ `e4be26c` |

## Authority boundary

**Approved (Captain 2026-10-08):** evidence, non-execution harnesses, paper path (real-time in → simulated fills out), code-enforced risk gates on the **paper** path + drills, security checklist, Captain evaluation packet.

**Still DENIED until separate written Captain approval for live money:**

- Live Kalshi orders
- Production execution flags / Compass “execution allowed”
- `approved_for_execution: true`

## Desired Outcome

Close AHF-P06 failed readiness gates with real evidence; keep live authority denied until bars pass **and** Captain writes approval.

## Sequential phases

| Phase | Focus | Status (2026-10-08 local) |
|---|---|---|
| A | CPCV + DSR on non-fixture Verdant series | Harness + Verdant run done — **`phase_a_pass: false`** (negative SR; research bar correctly rejects) |
| B | 30d continuous live paper | Day clock **1/30**; tick harness wired to latest Verdant scan + risk gates |
| C | Kill switch / limits | Stub drills **pass**; gates evaluated on paper tick (not live-wired) |
| D | Security + packet | Checklist + packet updated; `approved_for_execution: false` |

## Acceptance Criteria

- [x] Evidence tree + packet with execution denied
- [x] Phase A harness; Verdant non-fixture run recorded (pass not required to ship harness)
- [x] Phase B live-scan paper tick + day clock (no 30d claim)
- [x] Phase C drills fire; paper path consults gates
- [x] Phase D checklist + evaluation packet
- [ ] 30d paper OOS floors (wall-clock)
- [ ] Live Jev `experiment.json` re-run (artifact still missing)
- [ ] Captain written live-execution approval (explicitly deferred)

## Non-Goals

- Flipping execution readiness to approved
- Using settlement replay as edge proof
- Committing secrets
- Live Kalshi order placement

## Rollback

```bash
git checkout cursor/kalshi-live-decision-system
git reset --hard rollback/pre-execution-gate-evidence   # or e4be26c
```

## Autonomy Budget

| Limit | Value |
|---|---|
| Maximum iterations | 12 |
| Maximum failed validation cycles | 4 |
| Maximum estimated cost (USD) | 150 |
| Maximum elapsed minutes | 480 active (excludes 30d paper wall clock) |
| Ledger | `.agent/budgets/execution-gate-evidence.md` |

## Approval Record

| Field | Value |
|---|---|
| Approved by | Captain (Logan Ware) |
| Approval date | 2026-10-08 |
| Approved revision | `execution-gate-evidence` — four sequential phases; evidence/harness + paper path + risk drills; live money still denied |
| Utterance | "I approve, the cloud agent has finished, so check its progress and proceed" |
