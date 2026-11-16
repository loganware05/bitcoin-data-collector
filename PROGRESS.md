# Progress

## Current status (2026-11-16)

- Plan **`kxbtc15m-verified-index-labels`**: **DONE** (code) — PR [#32](https://github.com/loganware05/bitcoin-data-collector/pull/32) @ `642880e`; issue [#31](https://github.com/loganware05/bitcoin-data-collector/issues/31)
- Live execution: **DENIED**
- Dual floor: labels **met**; edge days **0** — blocked on Kalshi API credentials / CF entitlement (not present on host)

## Phase scoreboard

| Track | Status |
|---|---|
| Hourly `paper_buy_no_v1` | 30d paper in progress |
| KXBTC15M labels | Live harvester running (LaunchAgent) |
| KXBTC15M edge days | Waiting on `KALSHI_API_KEY_ID` + `KALSHI_PRIVATE_KEY_PATH` |
| Live money | **DENIED** |

## Primary next (ops)

- [ ] Install Kalshi API key ID + private key PEM on Verdant host (LaunchAgent env or `.env` loaded by jobs)
- [ ] Confirm CF Benchmarks passthrough entitlement if 403
- [ ] `./scripts/verdant/ensure_verdant_jobs.sh` then monitor tick → `settlement_index_source=cf_benchmarks`
- [ ] Accumulate ≥14 edge days; then non-fixture Phase A report only

## Standing next steps (do not bury)

- [ ] Hourly `paper_buy_no_v1` → 30d / OOS
- [ ] Keep live money denied
- [ ] Sellbird train + ≤50 outbound from `docs/promotion/`
- [ ] Compass `experiment.json` when available
- [ ] Future plan before any live order client
