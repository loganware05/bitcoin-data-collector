# STATUS — Execution Gate Evidence

**Updated:** 2026-11-14 (real-market validation)  
**Live execution authority:** **DENIED**

## Dual-track readiness (Captain board)

| Track | Strategy | Day clock | Monitor / tick jobs | Phase A | Live GO? |
|---|---|---|---|---|---|
| Hourly | `paper_buy_no_v1` | Separate `paper/` | `execution-gate-paper-tick` @ 23:45 | **PASS** (prior) | **NO** |
| KXBTC15M | `paper_kxbtc15m_v1` | Separate `paper-kxbtc15m/` | `kxbtc15m-monitor` @ 15s + paper tick @ 23:50 | Non-fixture dual floor not met | **NO** |

**Edge evidence rule (15m):** `counts_as_edge_evidence=true` only for verified live sources `{kalshi_api, cf_benchmarks}`. Fixtures require `COMPASS_KXBTC15M_ALLOW_FIXTURE_EDGE=1` (tests only). Operator/manual numeric → `operator_supplied` (never mislabeled as `kalshi_api`). Spot-proxy / file_drop keep continuity but are not readiness edge.

**Non-fixture Phase A dual floor:** ≥14 edge-eligible calendar days **and** ≥50 settled labels.

### Update 2026-11-14 (live-readiness pipeline)

- Plan `kxbtc15m-live-readiness` (#24): monitor + daily 15m paper LaunchAgents wired into `ensure_verdant_jobs.sh`
- Does **not** reset hourly `paper_buy_no_v1` clock
- Live orders still absent; `approved_for_execution` remains false

## Repo inventory

| Repo | Path | Notes |
|---|---|---|
| bitcoin-data-collector | this workspace | `feature/local-execution-gate-evidence`; PR #12 merged upstream |
| captains-compass-cursor (**main**) | `.repos/compass-run/captains-compass-cursor-main` (from GitHub zip; gitignored) | https://github.com/loganware05/captains-compass-cursor.git |
| Vorssaint Compass copy | do not use for AHF evidence | project-local only |

## experiment.json

| Artifact | Status |
|---|---|
| `.agent/evidence/ahf-p05-portfolio-experiment/exp-20261007T211148Z-23fa367a/experiment.json` on **main** | **MISSING** (404 / not in tree) |
| Same dir `CAPTAIN_LOCAL.md` | Present — states file is Captain-local only |
| Fixture `experiment_outcome_sample.json` | Present — coupling re-run 2026-10-11 → still deny execution |

## Session progress

| Item | Status |
|---|---|
| PR #12 merged | YES |
| Strategy revision `paper_buy_no_v1` | YES — Phase A **pass** |
| Paper clock reset on strategy adopt | YES — day 1/30 |
| Fixture coupling from main Compass | YES — `analysis/compass-coupling-20261011/` |
| Live Jev experiment.json | BLOCKED — not in main repo |
| `gh auth refresh` | BLOCKED — device login required |

## Safety locks

- No live Kalshi orders
- No `approved_for_execution: true`
- Paper = simulated fills under revised filters only for edge counting

## Update 2026-10-17

- PR #14 merged.
- Paper clock gap reset: `calendar_gap_days=6` → consecutive_days back to **1**.
- Cloud agent handoff superseded; live execution still DENIED.

## Update 2026-10-17 (daily paper LaunchAgent)

- Added `scripts/execution-gate/paper_tick_daily.sh`
- LaunchAgent `com.verdant.btc-kalshi.execution-gate-paper-tick` @ local 23:45 daily
- Wired into `ensure_verdant_jobs.sh`
- Live execution remains DENIED

## Update 2026-11-12 (XRV Pilot B)

- PR #16 **merged** @ `8db4fcc`.
- Plan `xrv-pilot-b-paper-continuity` APPROVED (#17).
- Host LaunchAgent **loaded** from `/Users/loganware/bitcoin-data-collector`.
- Smoke tick reset clock: `calendar_gap_days=26` → day **1/30**.
- Wrapper now falls back to local staging hourly outputs; soft-skip writes `continuity_alert.json`.
- Evidence: `.agent/evidence/xrv-pilot-b-paper-continuity/`
- Live execution remains DENIED.

