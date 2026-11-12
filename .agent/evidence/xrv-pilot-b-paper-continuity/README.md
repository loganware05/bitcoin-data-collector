# XRV Pilot B — Paper Continuity Evidence

**Plan:** `xrv-pilot-b-paper-continuity` (#17)  
**Date:** 2026-11-12  
**Live execution:** **DENIED**  
**Baseline (PR #16 merge):** `8db4fcc8be352ab244863462f649f4c08cd63da0`  
**Rollback:** `rollback/pre-xrv-pilot-b-paper-continuity`

## What was verified

| Check | Result |
|---|---|
| PR #16 daily LaunchAgent merged | YES |
| `ensure_verdant_jobs.sh` install | PASS (`ensure_verdant_jobs_install.log`) |
| `--check` shows paper-tick loaded | PASS |
| Smoke `paper_tick_daily.sh` | PASS — remote hourly; `approved_for_execution=false` |
| Day clock post-gap restart | `calendar_gap_days=26` → day **1/30** (`day_clock_after_smoke.json`) |
| Soft-skip alert when no scans | PASS (`soft_skip_continuity_alert.json`) |
| Local staging hourly fallback | PASS (`local_staging_fallback_smoke.log`, source=local_staging) |
| Unit: DayClock gap rules | PASS (`tests/test_execution_gate_day_clock.py`) |

## Explicit non-claims

- 30d paper track record is **not** complete
- No live Kalshi orders
- Soft-skip does **not** advance the day clock

## Host path

LaunchAgents installed from this checkout:

`/Users/loganware/bitcoin-data-collector`
