# KXBTC15M Phase A attempt — 2026-11-16

**Live money:** DENIED  
**approved_for_execution:** false  
**Readiness gate:** FAIL

## Dual floor

| Floor | Required | Observed | Met? |
|---|---:|---:|---|
| Edge-eligible calendar days | 14 | 1 | no |
| Settled labels | 50 | 10353 | yes |

## CPCV + DSR (exploratory)

### All actionable paper returns (n=2780)
- phase_a_pass: `False`
- cpcv_pass: `False` reject_rate=`0.9333333333333333`
- dsr_pass: `False` dsr=`0.0`

### Edge-only returns (n=18)
- phase_a_pass: `True`
- cpcv_pass: `True` reject_rate=`0.4666666666666667`
- dsr_pass: `True` dsr=`0.9856945787683616`

## Verdict

Dual floor not met: edge days 1/14 (labels 10353/50). CPCV/DSR numbers below are exploratory attempt only; do not unlock live trading.

Artifacts: `.agent/evidence/kxbtc15m-phase-a-attempt-20261116`

## Caveat

Edge-only CPCV/DSR pass is based on **n=18** returns — not durable evidence. Dual floor still fails (1/14 edge days).
