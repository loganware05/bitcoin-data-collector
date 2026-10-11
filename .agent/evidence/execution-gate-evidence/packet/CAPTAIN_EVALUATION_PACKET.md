# Captain Evaluation Packet — Execution Readiness

**Plan:** `execution-gate-evidence`  
**Date:** 2026-10-11  
**Upstream:** Compass PR #192 / AHF-P06; BDC PR #12 merged

## Authority scoreboard

| Field | Value |
|---|---|
| `approved_for_execution` | **false** |
| `recommend_approved_for_execution` | **false** |
| Live Kalshi orders | DENIED |
| Paper strategy | `paper_buy_no_v1` (Phase A pass) |

## Gate scoreboard

| Gate | Now | Notes |
|---|---|---|
| `non_fixture_backtests` | **IMPROVED / pending Compass ingest** | Local Phase A **pass** on revised Verdant series (`phase_a_revised_v1.json`). Baseline unfiltered still fail. |
| `paper_track_record` | FAIL | Day **1/30** under revised strategy (clock reset on adopt). |
| `multiple_live_jev_runs` | FAIL | Live `experiment.json` **not on main Compass**; fixture coupling only. |
| `live_execution_path_absent` | PASS | Unchanged. |
| `kill_switch_and_limits` | PARTIAL | Drills + paper-path gates; not live-wired. |
| `security_review_live_path` | FAIL | Checklist only. |
| `captain_written_approval` | FAIL | Live money not approved. |

## Strategy revision (`paper_buy_no_v1`)

BUY NO only; min_conf **0.65**; min_no_edge **0.20**; max_spread **0.03**; min_liq **0.70**; TTE **15–180m**; OTM ≤2%.  
Phase A: n=51, Sharpe≈2.12, median OOS≈1.34, CPCV reject_rate=0.2, DSR pass @ n_trials=324.

## Asks

1. Complete `gh auth refresh` device login (token still invalid).
2. Commit or sync live `experiment.json` into main Compass evidence path (currently only documented in `CAPTAIN_LOCAL.md`).
3. Continue paper ticks; live execution stays denied.
