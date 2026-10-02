# Offline staging setup evidence (2026-08-28)

## Actions
- `sync_verdant_staging.sh --pull` — model cache copied to `~/.local/share/verdant-btc-kalshi`
- `ensure_verdant_jobs.sh` — 4 launchd jobs loaded (snapshot, weekly, hourly-scan, sync-staging)
- `ensure_hourly_scan_schedule.sh --check` — issues=0; newest scan `scan_20260828T020112Z.json`

## LaunchAgents
| Label | Purpose |
|-------|---------|
| `com.verdant.btc-kalshi.hourly-scan` | 119 fires/week UTC |
| `com.verdant.btc-kalshi.sync-staging` | Every 10 min + login: push/pull |
| `com.verdant.btc-kalshi.snapshot-daemon` | 15 min snapshots (requires drive) |
| `com.verdant.btc-kalshi.weekly-retrain` | Weekly (requires drive) |

## Offline behavior
- Hourly scan: local staging if drive offline + model cache present
- Snapshot daemon: skip exit 0 when offline
- Weekly retrain: skip exit 0 when offline
