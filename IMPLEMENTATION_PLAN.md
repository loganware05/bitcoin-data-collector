# Implementation Plan — AHF-P03 / BTC Exchange Netflow

## Metadata

| Field | Value |
|---|---|
| Status | **APPROVED** |
| Plan ID | `ahf-p03-btc-exchange-netflow` |
| Approved | 2026-10-05 — Captain: "proceed with AHF-P02 … then AHF-P03" |
| Linear | [OVA-64](https://linear.app/ovaltechnologysolutions/issue/OVA-64/ahf-p03-btc-exchange-netflow-on-chain-metric-bitcoin-data-collector) · P-OVA-5 |
| Product | `bitcoin-data-collector` |
| Baseline | `cursor/kalshi-live-decision-system` @ `d3ce411` |
| Branch | `cursor/ahf-p03-btc-exchange-netflow-8613` |
| Rollback | `rollback/pre-ahf-p03-exchange-netflow` @ `d3ce411` |

## Request

Implement one on-chain metric family — **BTC exchange netflow** — filling existing
`exchange_inflow_btc` / `exchange_outflow_btc` stubs with a provider abstraction,
provenance, and signal-engine use. Separate from control-repo AHF-P01/P02.

## Desired Outcome

```
Provider (file fixture | optional Glassnode-compatible live)
  → normalized inflow/outflow + netflow + freshness/provenance
  → snapshot.on_chain_data fields populated
  → signals.exchange_outflow_bullish when both flows present
  → compute_onchain_signal uses netflow when available
```

## Decision Summary

| Principle | Implication |
|---|---|
| One metric family | Exchange flows only (not whale/TVL/etc.) |
| Provider abstraction | File default for hermetic; live optional via env |
| Fail soft | Missing provider → leave None (existing behavior) |
| No secrets in git | `GLASSNODE_API_KEY` Captain-local only |
| No live trading | Recommendations only unchanged |

## Acceptance Criteria

- [x] `exchange_flow_provider.py` with file + optional live Glassnode paths
- [x] Collector wires provider; provenance on `on_chain_data`
- [x] `compute_onchain_signal` incorporates netflow when present
- [x] Unit tests for provider + on-chain signal
- [x] Docs / plan / PROGRESS updated

## Non-Goals

- Full Glassnode suite / multi-chain
- AHF adapter changes (control repo)
- Live trading

## Approval Record

Captain Logan Ware — 2026-10-05 — proceed with AHF-P03 on existing bitcoin-data-collector.
