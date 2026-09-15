# Progress

## Current status

| Item | Value |
|---|---|
| Active plan | `settlement-retrain-oom` — **APPROVED / implementing** |
| Issue | [#4](https://github.com/loganware05/bitcoin-data-collector/issues/4) |
| Branch | `cursor/settlement-retrain-oom-5182` |
| Production base | `Kalshi-BTC-Hourly-Event-Scan` |
| Prior plan | `kalshi-confidence-guards-ws-a` — CLOSED (archived `docs/plans/kalshi-confidence-guards-ws-a.md`) |
| Rollback tag | `rollback/pre-settlement-retrain-oom` @ `ab64c67` |

## Phase 1–2 roadmap

| Step | Status | Notes |
|---|---|---|
| Accumulate post-guard scans (BUY NO / guard fix) | **Ops (Captain)** | Captain reports ~2 weeks of Aug 28+ data now available on Verdant |
| Settlement eval/fit on Aug 28+ slice | **Blocked in Cloud** | Verdant `/Volumes/Verdant_AI` not mounted in this agent VM — cannot see live scans here. Helper: `scripts/verdant/settlement_aug28_window.sh` |
| Fix weekly retrain OOM (eval ⊥ fit) | **Implemented (this branch)** | Cache + batch load + separate eval/fit processes; `SETTLEMENT_FIT_ENABLE=0` by default |

## Completed this cycle

- [x] Captain approved plan `settlement-retrain-oom`
- [x] `settlement_label_store.py` — unique-ticker outcomes + batched scan load + parquet/jsonl cache
- [x] `kalshi_settlement_eval.py` — `--mode eval|fit|refresh-cache`, `--since`, `--cache-dir`, `--report-out`
- [x] `scripts/verdant/weekly_retrain.sh` — two-process settlement; fit gated
- [x] `scripts/verdant/settlement_aug28_window.sh` — Aug 28+ eval (+ optional fit)
- [x] Tests: `tests/test_settlement_eval_cache.py` (+ full suite 59 passed)

## Captain Mac next (Verdant mounted)

```bash
# 1) Eval Aug 28+ window (writes report under $BTC_KALSHI_ROOT/logs)
./scripts/verdant/settlement_aug28_window.sh

# 2) If report gate_pass=true (max gap <= 12%), fit calibrator:
SETTLEMENT_FIT_ENABLE=1 ./scripts/verdant/settlement_aug28_window.sh
```

## Blockers

- Cloud agent has no Verdant volume — live Aug 28+ retrain/check must run on Captain Mac (or after scan artifacts are synced into the environment).
- GitHub default branch still lags production Kalshi branch (hygiene follow-up).
