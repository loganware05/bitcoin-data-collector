# Strategy revision v1 — `paper_buy_no_v1`

**Date:** 2026-10-11  
**Captain decision:** Revise strategy before counting paper edge.  
**Live execution:** DENIED.

## Filters

| Param | Value |
|---|---|
| side | BUY NO only |
| min_confidence | **0.65** |
| min_no_edge | **0.20** |
| max_spread | **0.03** |
| min_liquidity_score | **0.70** |
| OTM | [0%, 2%] |
| time_to_expiry_minutes | **[15, 180]** |
| fills | cross-spread + 7bps fee + 5bps slip |

## Phase A result (Verdant settled)

- n = 51
- full-sample Sharpe ≈ 2.1225
- median OOS Sharpe ≈ 1.3374
- CPCV reject_rate = 0.200
- DSR n_trials=324 pass = True
- **phase_a_pass = True**

Artifacts: `phase_a_revised_v1.json`, `verdant_returns_revised_v1.csv`, `strategy_revision_grid.json`.
