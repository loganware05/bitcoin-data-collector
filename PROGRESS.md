# Progress

## Current status (2026-11-16)

- Plan **`kxbtc15m-verified-index-labels`**: **IMPLEMENTING** — issue [#31](https://github.com/loganware05/bitcoin-data-collector/issues/31)
- Prior validation code: DONE (PR #28/#30)
- Live execution: **DENIED**
- Dual floor: labels **met** (~10k joined rows); edge days **0** (need Kalshi-signed CF BRTI creds)

## Phase scoreboard

| Track | Status |
|---|---|
| Hourly `paper_buy_no_v1` | 30d paper in progress |
| KXBTC15M labels | Live harvester + LaunchAgent |
| KXBTC15M edge days | Blocked on CF passthrough auth |
| Live money | **DENIED** |

## Primary next

- [ ] Install `KALSHI_API_KEY_ID` + `KALSHI_PRIVATE_KEY_PATH` on Verdant host (CF entitlement)
- [ ] Confirm monitor ticks with `cf_benchmarks` + edge evidence
- [ ] Accumulate ≥14 edge days; then non-fixture Phase A report only
- [ ] Keep LaunchAgents loaded (`ensure_verdant_jobs.sh --check`)

## Standing next steps (do not bury)

- [ ] Hourly `paper_buy_no_v1` → 30d / OOS
- [ ] Keep live money denied
- [ ] Sellbird train + ≤50 outbound from `docs/promotion/`
- [ ] Compass `experiment.json` when available
- [ ] Future plan before any live order client

## Commands

```bash
./scripts/verdant/ensure_verdant_jobs.sh --check
./scripts/verdant/kxbtc15m_labels.sh
./scripts/verdant/kxbtc15m_monitor.sh
python3 scripts/execution-gate/kxbtc15m_validation_status.py \
  --decision-dir /Volumes/Verdant_AI/btc_kalshi/live_outputs/kxbtc15m \
  --labels /Volumes/Verdant_AI/btc_kalshi/live_outputs/kxbtc15m/labels/settled_labels.json \
  --out .agent/evidence/kxbtc15m-verified-index-labels/validation_status.json
```
