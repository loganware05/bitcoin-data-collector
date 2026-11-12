# Daily paper tick LaunchAgent

**Date:** 2026-10-17 (updated 2026-11-12)  
**Label:** `com.verdant.btc-kalshi.execution-gate-paper-tick`  
**Schedule:** every local day at **23:45**  
**Script:** `scripts/execution-gate/paper_tick_daily.sh`  
**Strategy:** `paper_buy_no_v1` (simulated fills only)  
**Live execution:** DENIED

## Why

Any calendar gap >1 day resets the 30d paper clock (`calendar_gap_days=N`).  
PR #15 recorded a 6-day reset; 2026-11-12 smoke recorded `calendar_gap_days=26`.  
A daily LaunchAgent keeps continuity.

## Install (Mac host)

```bash
cd /Users/loganware/bitcoin-data-collector
./scripts/verdant/ensure_verdant_jobs.sh
./scripts/verdant/ensure_verdant_jobs.sh --check
```

Expect: `OK: com.verdant.btc-kalshi.execution-gate-paper-tick loaded`

Logs: `~/Library/Logs/verdant/execution_gate_paper_tick.*.log`

## Feed resolution (2026-11-12)

1. `PAPER_HOURLY_OUTPUTS` if it contains `scan_*.json`
2. Else remote `$BTC_KALSHI_REMOTE_ROOT/hourly_outputs`
3. Else local staging `$BTC_KALSHI_LOCAL_ROOT/hourly_outputs` (ADR-003)
4. Else soft-skip (exit 0), write `continuity_alert.json`, **do not** advance day clock

## Smoke

- 2026-10-17: `daily_wrapper_smoke_20261017.log` (PR #16)
- 2026-11-12: `.agent/evidence/xrv-pilot-b-paper-continuity/smoke_tick.log` + soft-skip alert

## Safety

- No live Kalshi orders
- `approved_for_execution` remains false
- Missing hourly outputs → soft exit 0 (does not fake clock advance)
