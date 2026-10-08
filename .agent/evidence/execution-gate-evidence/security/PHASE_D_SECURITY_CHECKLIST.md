# Phase D — Security checklist (live-path design)

**Gate:** `security_review_live_path` — currently **FAIL** (fail closed; no live surface).  
**Authority:** `approved_for_execution` remains **false**.

## Checklist

| # | Control | Status | Evidence / links |
|---|---|---|---|
| 1 | Compass AHF remains proposal-only / research coupling | PASS (design) | Compass `orchestrator/integrations/ai_hedge_fund/behavioral.py` — never sets `approved_for_execution: true`; PR #192 |
| 2 | Env gate default-off for coupling | PASS | `COMPASS_AHF_BEHAVIOR_COUPLING_ENABLED` (default off in product docs; demo sets 1 for harness only) |
| 3 | Scoped API keys design: trading-only, no withdrawal | DESIGN | Document intended Kalshi key scopes; **do not commit keys**. Captain creates keys offline. |
| 4 | IP allowlist for trading keys | DESIGN | Captain ops: restrict key to known egress IPs |
| 5 | Secrets hygiene | PASS (repo) | `.gitignore` excludes `.env`, `.agent/evidence/private/`; no secrets in this evidence tree |
| 6 | Isolated order path / sandbox | PARTIAL | Sandbox repo present (`/home/ubuntu/repos/captain-compass-sandbox`); paper loop design in `../paper/PHASE_B_DESIGN.md`; no live broker wiring |
| 7 | Clock sync | DESIGN | Require NTP/chrony on any host that would eventually submit; log skew in paper loop |
| 8 | Metrics + alerts | DESIGN | Paper metrics schema + future alerts on breaker trips (`../risk-drills/PHASE_C_BREAKER_PLAN.md`) |
| 9 | Live execution path absent in AHF | PASS | Readiness gate `live_execution_path_absent` ok in P06 sample + re-run |
| 10 | Security review of proposed live surface | FAIL | No live surface to approve; keep fail-closed until designed + reviewed |

## Explicit prohibitions

- No withdrawal-capable keys in any environment used for paper
- No Verdant live trading secrets in git
- No enabling production execution flags in this workstream

## Captain evaluation

See `../packet/CAPTAIN_EVALUATION_PACKET.md`.
