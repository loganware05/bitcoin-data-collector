# Sep 13–Oct 2 replay

Date: 2026-10-03  
Plan: `postfix-buy-no-calibration` (#9)  
Report: `sep13_oct2_replay_20261003T054308Z.json`

## Result (Captain Mac + Verdant)

| Metric | Value |
|---|---|
| Success | **true** |
| Scans in window | 246 |
| Actionable unique (settled) | **207** |
| Mix | **207 BUY NO / 0 BUY YES** |
| BUY NO mean `y_true` (YES settled) | **0.333** |
| Raw max calibration gap | **0.323** |
| Gate (&lt;0.12) | **FAIL** (`gate_pass: false`) |
| Fit | disabled (`fit_enabled: false`) |
| Isolated cache | `/Volumes/Verdant_AI/btc_kalshi/settlement_cache_sep13_oct2` |
| Existing calibrator | `20260828T003036Z` — calibrated gap on this slice still ~0.323 (no help) |

## Interpretation

- Post–OTM-floor window is **BUY NO–only** actionable flow (BUY YES flood remains suppressed).
- When recommending BUY NO, YES still settled ~1/3 of the time → model/market still miscalibrated vs 12% gate.
- Keep `SETTLEMENT_FIT_ENABLE=0`; do **not** promote Phase 3 `min_confidence` defaults from this window alone.

## Cloud earlier

Cloud Agent could not mount Verdant; Mac run completed the replay.
