# Autonomy Budget Ledger

## Metadata

- Plan ID: execution-gate-evidence
- Issue: local/execution-gate-evidence
- Branch: feature/local-execution-gate-evidence
- Created: 2026-10-08
- Last updated: 2026-10-08
- Status: ACTIVE (Captain approved 2026-10-08)

## Limits (from plan)

- Maximum iterations: 12
- Maximum failed validation cycles: 4
- Maximum estimated cost (USD): 150
- Maximum elapsed minutes: 480 (active agent-minutes; excludes 30-day paper wall clock)
- Stop on scope change: true
- Stop on destructive operation: true
- Stop on unresolved security high: true

## Usage

- Iterations used: 2
- Failed validation cycles: 1
- Estimated cost used (USD): 0
- Cost is estimate: true
- Elapsed minutes: 90

## Cycle log

| 2026-10-08 | 0 | plan draft + evidence scaffold | cloud tandem spawn |
| 2026-10-08 | 1 | cloud harness session | PR #12; plumbing_demo only |
| 2026-10-08 | 2 | local Verdant Phase A | phase_a_pass=false; paper day 1 |

## Stop condition

When any usage field meets or exceeds its limit, stop immediately and write
`.agent/evidence/execution-gate-evidence/BUDGET_STOP_REPORT.md`.
