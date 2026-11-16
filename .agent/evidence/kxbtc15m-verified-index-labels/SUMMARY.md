# Evidence — kxbtc15m-verified-index-labels (#31)

**Date:** 2026-11-16  
**Live money:** DENIED

## Validation

- Unit: `pytest -q tests/test_kxbtc15m_verified_index_labels.py tests/test_kxbtc15m_real_market_validation.py tests/test_kxbtc15m_live_readiness.py` → **21 passed**
- Live label harvest: `n_harvested_markets=1000`, joined/status `n_settled_labels=10088` (≥50 floor **met**)
- Monitor soft-fail without Kalshi creds: still `exchange_spot_proxy`; warning `Kalshi API credentials not set`
- Edge days: **0** until `KALSHI_API_KEY_ID` + `KALSHI_PRIVATE_KEY_PATH` (and CF entitlement) are installed on the host

## Dual floor

| Floor | Required | Observed | Met? |
|---|---:|---:|---|
| Edge-eligible calendar days | 14 | 0 | no |
| Settled labels | 50 | 10088 | yes |

`phase_a_non_fixture_ready`: false (edge floor pending CF BRTI auth).

## Ops next

1. Install Kalshi API key ID + private key PEM paths in LaunchAgent env / shell profile (never commit secrets).
2. Confirm CF Benchmarks passthrough entitlement with Kalshi if 403.
3. Reload jobs: `./scripts/verdant/ensure_verdant_jobs.sh`
4. Confirm ticks show `settlement_index_source=cf_benchmarks` and `counts_as_edge_evidence=true`.
