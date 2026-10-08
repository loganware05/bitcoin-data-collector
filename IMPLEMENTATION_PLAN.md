# Implementation Plan — Execution Gate Evidence (AHF-P06 follow-on)

## Metadata

| Field | Value |
|---|---|
| Status | **EVIDENCE SESSION AUTHORIZED** (production breaker merge: **AWAITING APPROVAL**) |
| Plan ID | `execution-gate-evidence` |
| Product | `bitcoin-data-collector` (coordination) + Compass assessor + sandbox paper path |
| Baseline | `cursor/kalshi-live-decision-system` @ `e4be26c` |
| Branch | `cursor/execution-gate-evidence-1043` |
| Upstream | Compass PR #192 / AHF-P06 v1.54.0 |
| Issue | placeholder — cloud tandem “Execution Gate Evidence” (create GitHub/Linear issue on Captain request) |

## Authority boundary

Captain mission (2026-10-08) authorizes **first-session evidence + non-execution
harnesses + stubs/design** immediately.

**Not authorized without further written approval:**

- Live Kalshi orders
- Production execution flags / `approved_for_execution: true`
- Merging risk-breaker production behavior into live order paths

## Desired Outcome

Flesh pending AHF-P06 readiness gates with real evidence so the Captain can
evaluate whether to grant written live-execution approval. Keep
`recommend_approved_for_execution: false` until bars are met.

## Workstreams

1. **Inventory + prior runs** — three-repo STATUS; P05/P06 artifacts; coupling re-run
2. **Phase A** — CPCV + DSR + IS/OOS reject harness; run on available data; document Verdant blockers
3. **Phase B** — sandbox paper loop design (real-time in, simulated fills out); day clock
4. **Phase C** — breaker interfaces + drill stubs (pre-approval)
5. **Phase D** — security checklist + Captain evaluation packet
6. **Docs handoff** — PROGRESS.md for local First Mate

## Acceptance Criteria (session 1)

- [x] STATUS.md with paths/SHAs/branches
- [x] Evidence tree + packet with `approved_for_execution: false`
- [x] Phase A script + run record (or precise blocker)
- [x] Phase B design + schema (no 30d claim)
- [x] Phase C stubs + drill plan/results
- [x] Phase D checklist
- [x] PROGRESS handoff

## Non-Goals

- Flipping execution readiness to approved
- Weakening tests
- Committing secrets
- Claiming fixture/demo CPCV as non-fixture backtest evidence

## Rollback

- Branch-only evidence/harness; revert by discarding branch or reverting commits
- Checkpoint: `e4be26c` on `cursor/kalshi-live-decision-system`

## Approval Record

| Scope | Status | Source |
|---|---|---|
| Evidence docs, harness scripts, packet, stubs/drills | **Authorized** | Captain mission 2026-10-08 “First session deliverables… Start immediately” |
| Production breaker merge / live execution | **AWAITING APPROVAL** | Explicit written approval required |
