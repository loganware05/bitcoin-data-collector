# Daily paper tick LaunchAgent

**Date:** 2026-10-17  
**Label:** `com.verdant.btc-kalshi.execution-gate-paper-tick`  
**Schedule:** every local day at **23:45**  
**Script:** `scripts/execution-gate/paper_tick_daily.sh`  
**Strategy:** `paper_buy_no_v1` (simulated fills only)  
**Live execution:** DENIED

## Why

Any calendar gap >1 day resets the 30d paper clock (`calendar_gap_days=N`).  
PR #15 recorded a 6-day reset. A daily LaunchAgent keeps continuity.

## Captain install (required on Mac host)

Cursor sandbox cannot write `~/Library/LaunchAgents`. Run locally:

```bash
cd /Users/loganware/Documents/Buisness/GitHub/bitcoin-data-collector
git checkout feature/13-execution-gate-daily-paper-tick   # or after merge: tip
./scripts/verdant/ensure_verdant_jobs.sh
./scripts/verdant/ensure_verdant_jobs.sh --check
```

Expect: `OK: com.verdant.btc-kalshi.execution-gate-paper-tick loaded`

Logs: `~/Library/Logs/verdant/execution_gate_paper_tick.*.log`

## Smoke (this session)

- Wrapper ran successfully: `daily_wrapper_smoke_20261017.log`
- LaunchAgent install from agent environment: **blocked** (Operation not permitted on LaunchAgents) — Captain must load.

## Safety

- No live Kalshi orders
- `approved_for_execution` remains false
- Missing hourly outputs → soft exit 0 (does not fake clock advance)
