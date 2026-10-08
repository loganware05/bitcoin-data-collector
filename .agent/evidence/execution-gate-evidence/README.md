# Execution Gate Evidence

Coordination home for fleshing out AHF-P06 execution-readiness gates with
**real evidence**. Research remains operable; **live execution stays DENIED**.

Upstream: [captains-compass-cursor#192](https://github.com/loganware05/captains-compass-cursor/pull/192) (v1.54.0).

## Layout

| Path | Purpose |
|---|---|
| `STATUS.md` | Repo inventory, locks, handoff |
| `PRIOR_RUNS.md` | P05/P06 artifact index |
| `analysis/` | Coupling re-runs, Phase A reports, SHAs |
| `paper/` | Phase B paper loop design + metrics schema |
| `risk-drills/` | Phase C breaker interfaces + drill plan/results |
| `security/` | Phase D security checklist |
| `packet/CAPTAIN_EVALUATION_PACKET.md` | Scoreboard for Captain |

## Harness scripts (BDC)

```bash
# Phase A — CPCV + DSR + IS/OOS reject (non-execution)
./.venv/bin/python scripts/execution-gate/phase_a_cpcv_dsr.py \
  --out .agent/evidence/execution-gate-evidence/analysis/phase_a_report.json

# With Verdant / non-fixture returns CSV|JSON when available:
./.venv/bin/python scripts/execution-gate/phase_a_cpcv_dsr.py \
  --returns /path/to/returns.csv --data-class verdant_staging \
  --out .agent/evidence/execution-gate-evidence/analysis/phase_a_verdant.json

# Phase B — paper schema + dry-run tick (simulated fills)
./.venv/bin/python scripts/execution-gate/phase_b_paper_loop.py \
  --dry-run-tick \
  --out .agent/evidence/execution-gate-evidence/paper/phase_b_schema.json

# Phase C — breaker stub drills
./.venv/bin/python scripts/execution-gate/phase_c_breaker_stubs.py \
  --drill \
  --out .agent/evidence/execution-gate-evidence/risk-drills/phase_c_drill.json
```

## Captain acceptance bars (encoded)

### Phase A (before simulated trades count)

- Pass CPCV (combinatorial purged CV)
- Pass Deflated Sharpe Ratio
- REJECT if IS/OOS Sharpe gap > ~1.5 **or** IS/OOS ratio > 3.0
- Live forward paper PnL is the edge path; replay is plumbing only

### Phase B

- Continuous live paper; conservative fills; 30 calendar days
- Manual override → day clock = 0
- OOS floor: ≥14d, ≥50 closed trades, return > 0%, max DD < 15%,
  paper Sharpe (per-trade t-stat) ≥ 1.0, profit factor ≥ 1.2

### Phase C / D

- Breakers as gate functions + drills (stubs pre-approval)
- Security checklist + evaluation packet; scoped keys design

## Non-goals this session

- Live Kalshi orders
- Flipping `approved_for_execution` / `recommend_approved_for_execution` to true
- Merging production risk breakers into live paths
