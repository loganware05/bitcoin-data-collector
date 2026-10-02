# Phase 1 + Phase 2 execution evidence

Date: 2026-08-05  
Branch: `feat/kalshi-confidence-guards-ws-a`  
Captain approval: Phase 1 paper trial, Phase 2 soft-land, Phase 3 defer defaults

## Code changes

- `hourly_probability_model.py`: `_soft_mapping_factor` = `0.85 + 0.15 * mapping_confidence`
- `scripts/verdant/hourly_scan.sh`: paper flags `--min-confidence 0.48 --min-edge 0.10` (env-overridable)
- Defaults unchanged: `FairValueConfig.min_confidence=0.65`

## Tests

```
python3.12 -m pytest tests/test_fair_value_engine.py \
  tests/test_orderbook_guardrails.py \
  tests/test_hourly_probability_ml_penalty.py -q
# 14 passed
```

## Live scans (Verdant)

| Run | Flags | Result |
|---|---|---|
| Phase 1 paper | conf 0.48 / edge 0.10 | `scan_20260805T222945Z.json` — 188 eval, **BUY NO=107**, BUY YES=0, NO TRADE=81 |
| Phase 2 control | conf **0.65** / edge 0.10 | `scan_20260805T223016Z.json` — same **BUY NO=107** |

NO TRADE breakdown (both): **100% `edge_below_min`** — confidence is no longer the blocker.

Top actionable confidences now ~0.67–0.71 (were capped ~0.53 pre soft-land).

## Logs

- `phase1_dry_scan.log`
- `phase2_default065_control.log`
