# Phase A run — CPCV + DSR + IS/OOS

**When:** 2026-10-08 (cloud)  
**Script:** `scripts/execution-gate/phase_a_cpcv_dsr.py`  
**Live execution:** not involved

## Commands

```bash
cd /workspace
./.venv/bin/python scripts/execution-gate/phase_a_cpcv_dsr.py \
  --out .agent/evidence/execution-gate-evidence/analysis/phase_a_report.json

./.venv/bin/python scripts/execution-gate/phase_a_cpcv_dsr.py \
  --data-class settlement_replay \
  --out .agent/evidence/execution-gate-evidence/analysis/phase_a_settlement_replay_class.json
```

## Environment data availability

| Source | Available? |
|---|---|
| `/Volumes/Verdant_AI/btc_kalshi` | **NO** (not mounted) |
| `~/.local/share/verdant-btc-kalshi` | **NO** |
| Per-trade return series for CPCV | **NO** in cloud |
| Settlement aggregate JSONs in `.agent/evidence/` | YES (plumbing summaries only — not a return series) |

## Results (plumbing_demo)

See `phase_a_report.json`:

| Check | Result |
|---|---|
| `phase_a_pass` | **false** |
| `cpcv_pass` | false (reject_rate 0.6 on synthetic regime-break series) |
| `dsr_pass` | false (DSR ≈ 0) |
| `data_class` | `plumbing_demo` |
| Blocker | Cannot satisfy `non_fixture_backtests` without Verdant/live returns |

## Interpretation

Harness is operable. This run is a **plumbing smoke test**, not edge evidence.
IS/OOS reject bars (`gap > 1.5` or `ratio > 3.0`) are enforced inside CPCV splits.
Settlement replay class is explicitly blocked from Phase A pass.

## Unblock path

1. Mount Verdant or sync laptop staging with scan/settlement trade-level PnL series.
2. Export CSV/JSON with a `return` column (per closed paper/backtest trade, time-ordered).
3. Re-run:

```bash
./.venv/bin/python scripts/execution-gate/phase_a_cpcv_dsr.py \
  --returns /path/to/returns.csv \
  --data-class verdant_staging \
  --out .agent/evidence/execution-gate-evidence/analysis/phase_a_verdant.json
```
