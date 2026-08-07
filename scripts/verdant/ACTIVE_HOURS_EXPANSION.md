# Workstream B — Active-hours scan expansion (Captain note)

**Status:** Implemented (ops-only; no confidence/trade-gate changes).
**Date:** 2026-08-05

## Why

Settlement/calibration needs ~80+ settled outcome pairs before looser trade gates are trustworthy. Scan history was stalled (8 `scan_*.json` files, last 2026-06-24). Launchd hourly-scan showed `last exit code = 78 EX_CONFIG` and no `hourly_scan.*.log` on Verdant — consistent with launchd failing to open StandardOut/Error on the volume.

## Change (reversible)

| | Before | After |
|---|---|---|
| Days | Mon–Fri | All days (Sun–Sat) |
| Hours (UTC) | 13:00–21:00 at :00 | 12:00–23:00 at :00 |
| Peak cadence | none | Mon–Fri 14:00–20:00 also at :30 |
| Fires/week | 45 | 119 (~2.6×) |
| Job logs | `$BTC_KALSHI_ROOT/logs/hourly_scan.*.log` | `~/Library/Logs/verdant/hourly_scan.*.log` |

Data root unchanged: `BTC_KALSHI_ROOT=/Volumes/Verdant_AI/btc_kalshi`.

## Rollback

Restore prior plist intervals (Mon–Fri 13–21) and Verdant log paths from git, then:

```bash
./scripts/verdant/install_launchd.sh
launchctl bootout gui/$(id -u)/com.verdant.btc-kalshi.hourly-scan 2>/dev/null || true
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.verdant.btc-kalshi.hourly-scan.plist
```

## Out of scope

Sibling A (confidence guards): soft-land + paper trial approved 2026-08-05 — see ADR-001 / `IMPLEMENTATION_PLAN.md`.
