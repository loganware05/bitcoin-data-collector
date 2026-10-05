# Progress

## Current status (2026-10-05)

- Active plan: **AHF-P03** `ahf-p03-btc-exchange-netflow` — **APPROVED** / implementing
- Branch: `cursor/ahf-p03-btc-exchange-netflow-8613`
- Linear: [OVA-64](https://linear.app/ovaltechnologysolutions/issue/OVA-64/ahf-p03-btc-exchange-netflow-on-chain-metric-bitcoin-data-collector)
  · Project [NorthStar On-Chain / AI Hedge Fund](https://linear.app/ovaltechnologysolutions/project/northstar-on-chain-ai-hedge-fund-67b1475ea115)
- Rollback: `rollback/pre-ahf-p03-exchange-netflow` @ `d3ce411`

## AHF-P03 scope

- Exchange netflow provider (`file` fixture / optional Glassnode)
- Fill `exchange_inflow_btc` / `exchange_outflow_btc` / `exchange_netflow_btc`
- Signal + feature wiring with provenance

## Prior (postfix BUY NO)

- Plan `postfix-buy-no-calibration` completed on prior branch; Sep13–Oct2 replay evidence retained

## Next after P03

- Captain review / merge AHF-P03 PR
- Optional: enable `COMPASS_EXCHANGE_FLOW_PROVIDER=file` for demos or
  `GLASSNODE_API_KEY` for live
- AHF-P04+ (on-chain analyst) remains deferred in control-repo track
