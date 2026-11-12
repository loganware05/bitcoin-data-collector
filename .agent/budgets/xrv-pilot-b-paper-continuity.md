# Autonomy Budget Ledger

## Metadata

- Plan ID: xrv-pilot-b-paper-continuity
- Issue: #17
- Branch: feature/17-xrv-pilot-b-paper-continuity
- Created: 2026-11-11
- Last updated: 2026-11-12
- Status: ACTIVE (Captain approved 2026-11-11; W1–W4 implemented)

## Limits (from plan)

- Maximum iterations: 8
- Maximum failed validation cycles: 3
- Maximum estimated cost (USD): 75
- Maximum elapsed minutes: 180 (active agent-minutes; excludes 30-day paper wall clock)
- Stop on scope change: true
- Stop on destructive operation: true
- Stop on unresolved security high: true

## Usage

- Iterations used: 2
- Failed validation cycles: 0
- Estimated cost used (USD): 0
- Cost is estimate: true
- Elapsed minutes: 90

## Cycle log

| Date | Iter | Note |
|---|---|---|
| 2026-11-11 | 0 | Discovery + plan AWAITING APPROVAL |
| 2026-11-11 | 1 | Captain approved; PR #16 already merged; begin W2–W4 |
| 2026-11-12 | 2 | Fallback harden + LaunchAgent install + smoke + evidence |

## Stop condition

When any usage field meets or exceeds its limit, stop immediately and write
`.agent/evidence/xrv-pilot-b-paper-continuity/BUDGET_STOP_REPORT.md`.
