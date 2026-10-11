# Phase A run — CPCV + DSR + IS/OOS

## Cloud session (plumbing_demo)

- `phase_a_report.json` — synthetic demo; `phase_a_pass: false` (expected)

## Local Captain host (2026-10-08) — Verdant non-fixture

**Verdant mounted** at `/Volumes/Verdant_AI/btc_kalshi`.

### Commands

```bash
python3 scripts/execution-gate/export_verdant_actionable_returns.py \
  --out-csv .agent/evidence/execution-gate-evidence/analysis/verdant_actionable_returns.csv \
  --out-meta .agent/evidence/execution-gate-evidence/analysis/verdant_actionable_returns_meta.json

python3 scripts/execution-gate/phase_a_cpcv_dsr.py \
  --returns .agent/evidence/execution-gate-evidence/analysis/verdant_actionable_returns.csv \
  --data-class verdant_staging \
  --out .agent/evidence/execution-gate-evidence/analysis/phase_a_verdant.json
```

### Results (`phase_a_verdant.json`)

| Check | Result |
|---|---|
| `n_obs` | 207 settled actionable (Sep13–Oct2 outcomes cache) |
| `full_sample_sharpe` | **≈ -1.05** |
| `cpcv_pass` | **false** (reject_rate 0.6; median OOS Sharpe ≈ -0.57) |
| `dsr_pass` | **false** (DSR ≈ 0) |
| `phase_a_pass` | **false** |
| `data_class` | `verdant_staging` (non-fixture; research bar applicable) |

Reject reasons observed: `is_oos_gap>1.5` (7 splits), `is_oos_ratio>3.0` (2 splits).

### Interpretation

1. Harness is operable on real Verdant joins.
2. Current actionable strategy **fails** the Captain research bar (CPCV + DSR) under conservative fills.
3. Therefore **no simulated trade may count toward paper edge evidence** until a revised strategy passes Phase A.
4. This series is **not** live-forward edge proof; live paper (Phase B) remains a separate clock.
5. `approved_for_execution` remains **false**.
