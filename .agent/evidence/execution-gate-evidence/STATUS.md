# STATUS — Execution Gate Evidence (AHF-P06 follow-on)

**Agent:** Execution Gate Evidence (cloud tandem)  
**Plan ID:** `execution-gate-evidence`  
**Session:** 2026-10-08  
**Live execution authority:** **DENIED** (`approved_for_execution: false`)

## Repo inventory

| Repo | Path | Branch | HEAD SHA |
|---|---|---|---|
| bitcoin-data-collector (COORDINATION HOME) | `/workspace` | `cursor/execution-gate-evidence-1043` (from `cursor/kalshi-live-decision-system`) | see `analysis/repo-shas.txt` |
| captains-compass-cursor | `/home/ubuntu/repos/captains-compass-cursor` | `main` (PR #192 merged) | see `analysis/repo-shas.txt` |
| captain-compass-sandbox | `/home/ubuntu/repos/captain-compass-sandbox` | `main` | see `analysis/repo-shas.txt` |

Compass + sandbox were **not** pre-mounted; cloned as siblings under `/home/ubuntu/repos/` (outside BDC git tree).

## Safety locks (this session)

- No live Kalshi orders
- No production execution flags enabled
- Never set `approved_for_execution: true` / Compass “execution allowed”
- Sandbox / paper = simulated fills only
- Settlement replay = plumbing check only
- No live trading secrets committed

## Session progress

| Deliverable | Status |
|---|---|
| Workspace inventory | DONE |
| Prior P05/P06 artifact locate + coupling re-run | DONE (experiment.json still MISSING) |
| Evidence tree + Captain packet | DONE |
| Phase A CPCV/DSR harness + run | DONE (plumbing_demo; Verdant blocker) |
| Phase B paper loop design | DONE (schema + dry-run; 30d NOT claimed) |
| Phase C breaker stubs + drill plan | DONE (stubs/drills only) |
| Phase D security checklist | DONE |
| PROGRESS.md handoff | DONE |

## Handoff for local First Mate

1. Captain-local: place `exp-20261007T211148Z-23fa367a/experiment.json` into Compass evidence and re-run coupling.
2. Mount Verdant (`/Volumes/Verdant_AI/btc_kalshi` or laptop staging) and re-run Phase A with `--data-class verdant_staging`.
3. Start continuous live-forward paper loop (sandbox) — day clock starts at 0; no manual overrides without reset.
4. Do **not** merge Phase C stubs into live order paths until Captain approves production breaker scope.
5. Keep packet scoreboard `approved_for_execution: false` until all gates pass **and** Captain writes approval.
