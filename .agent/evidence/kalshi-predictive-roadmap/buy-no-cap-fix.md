# BUY NO cap fix — dry scan evidence (2026-08-28)

## Change
Removed `max_buy_no_model_probability` from `FairValueConfig` / `evaluate_contract()`.

## Dry scan
- File: `scan_20260828T014006Z.json`
- BTC spot: 81150.01
- **17 BUY NO / 0 BUY YES / 171 NO TRADE**
- Remaining NO TRADE: edge_below_min (66), other_guardrail (105)

## Tests
`pytest tests/test_fair_value_engine.py` — 9 passed
