# Aug 28+ actionable calibration gate (2026-09-13)

## Retrain
- Models: `model_logreg_20260913T*` all 5 horizons
- Dataset: `decision_dataset_20260913T161317Z.csv`
- Stopped old single-process settlement before OOM; landed NorthStar PR #5 code (ADR-004)

## NorthStar cloud agent
- Chat: https://cursor.com/agents/bc-46bb4d6e-9599-42d5-b6a0-b7d81bd05182
- PR: https://github.com/loganware05/bitcoin-data-collector/pull/5
- Issue: #4 — settlement eval/fit split + cache

## Gate result (actionable-only, deduped)

| Metric | Value |
|--------|-------|
| Scan files (Aug 28+) | 249 |
| Unique actionable | 1261 (**0 BUY YES / 1261 BUY NO**) |
| Settled actionable | 1252 |
| Raw max calibration gap | **0.813** |
| Gate (&lt;0.12) | **FAIL** |
| BUY NO mean YES outcome | **0.823** (82% settled YES) |

Report: `/Volumes/Verdant_AI/btc_kalshi/logs/settlement_aug28_actionable_20260913T181605Z.json`

## Interpretation
Post-guard paper flow is **BUY NO–only**. Those NO recommendations settled YES ~82% of the time → model YES probs (~low) badly miscalibrated vs outcomes, hence ~81% gap (same order as pre-guard). **Do not fit calibrator** (`SETTLEMENT_FIT_ENABLE` stays 0).

## Full-window eval note
`settlement_aug28_window.sh` (all rows) ballooned to ~15GB while fetching outcomes — killed. Prefer `settlement_aug28_actionable.sh` for gate checks.

## BUY NO ITM bug (fixed same day)
Live scans recommended BUY NO on strikes **below** spot (YES ITM), e.g. strike 75750 / spot 77200 with model_no=0.99. Guard now requires YES OTM/ATM within 2%.

## Next Phase 2
1. Let post-fix scans accumulate (days)
2. Re-run `./scripts/verdant/settlement_aug28_actionable.sh` (or since=fix-date)
3. Only then `SETTLEMENT_FIT_ENABLE=1` if gate_pass
4. Coordinate merge of local branch with PR #5
