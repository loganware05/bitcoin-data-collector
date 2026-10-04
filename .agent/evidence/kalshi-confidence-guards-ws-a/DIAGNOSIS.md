# Diagnosis — Kalshi confidence guards (Workstream A)

Date: 2026-08-05  
Branch: chore/install-captains-compass  
Compass: v1.4.0  

## Verdict

**Blocking guard = confidence.** Edge/liquidity are secondary. Prior trial `--min-confidence 0.55` would still yield **0%** actionable on all historical hourly scans.

## Evidence sources

- Scans: `/Volumes/Verdant_AI/btc_kalshi/hourly_outputs/scan_*.json` (8 files; 5 with contracts)
- Settlement eval: `kalshi_settlement_eval.py` on that scan dir (2026-08-05)
- Code: `hourly_fair_value_engine.py`, `hourly_probability_model.compute_confidence()`

## Settlement eval summary

```
n_settled=1340 (all NO TRADE)
actionable_slice empty
raw_max_calibration_gap=0.4619
calibrated_max_calibration_gap=0.0 (isotonic on all_settled)
```

Calibration gate (&lt;12% on committed predictions over 2+ weeks) **not met** for actionable trades.

## Tests run (no product code changes)

```
python3.12 -m pytest tests/test_fair_value_engine.py \
  tests/test_orderbook_guardrails.py \
  tests/test_hourly_probability_ml_penalty.py -q
# 12 passed
```

## Note for sibling agent B

Scan volume is not the blocker (268 contracts evaluated when filter matches). Do not change launchd cadence expecting actionable unlock without confidence threshold/formula work.
