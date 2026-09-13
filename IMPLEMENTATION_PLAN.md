# Implementation Plan — Settlement retrain OOM (Phase 1–2)

## Metadata

| Field | Value |
|---|---|
| Status | **AWAITING APPROVAL** |
| Plan ID | `settlement-retrain-oom` |
| Supersedes | `kalshi-confidence-guards-ws-a` (CLOSED — soft-land + paper trial shipped; archived at `docs/plans/kalshi-confidence-guards-ws-a.md`) |
| Issue | https://github.com/loganware05/bitcoin-data-collector/issues/4 |
| Branch | `cursor/settlement-retrain-oom-5182` |
| Base branch | `Kalshi-BTC-Hourly-Event-Scan` (production Verdant code; **not** GitHub default `cursor/kalshi-live-decision-system`) |
| Created | 2026-09-13 |
| Last updated | 2026-09-13 |
| Approved by | |
| Approval date | |
| Approved revision | |

## Request (Captain-level)

Continue bitcoin-data-collector roadmap **Phase 1–2**:

1. Let scans accumulate with the BUY NO / post-guard fix (ops — Captain plugs in Verdant drive).
2. Re-run settlement calibration on the **Aug 28+** slice once ~2 weeks of post-guard data exist.
3. **Fix weekly retrain OOM** — batch settlement eval separately from calibrator fit.

Captain report (already done locally): settlement **eval-only** finished successfully on 298 scans / ~34.8k settled rows (6,939 actionable); raw calibration gap ~81% **FAIL** vs 12% gate; calibrator manifest unchanged (`20260828T003036Z`); post-guard scans ≈7 files (too few).

**This plan implements item (3) only.** Items (1)–(2) remain operational wait conditions documented under Non-Goals / Follow-ups.

## Problem statement

`scripts/verdant/weekly_retrain.sh` ends with:

```bash
python kalshi_settlement_eval.py \
  --scan-dir "$BTC_KALSHI_ROOT/hourly_outputs" \
  --models-base-dir "$BTC_KALSHI_ROOT/models" \
  --fit-calibration
```

In `kalshi_settlement_eval.main()` today:

1. `--fit-calibration` runs `fit_settlement_calibrator()` → `load_scan_rows(all)` + `attach_settlement_outcomes(all rows)`.
2. The same process **always** then runs `evaluate_scan_settlements()` → **second** full `load_scan_rows` + **second** full outcome attach.

Additional amplifiers:

- `attach_settlement_outcomes` issues **one Kalshi HTTP GET per dataframe row**, not per unique ticker (~34.8k calls / responses for the last full eval).
- Each `scan_*.json` is large (~0.5MB+); loading hundreds into nested dicts + two DataFrames peaks memory.
- Weekly retrain already ran multi-horizon ML train + dataset export in the same launchd job before settlement.

Result: weekly retrain OOMs / fails closed on Verdant; operators must run fragile eval-only workarounds by hand; calibrator fit cannot safely refresh.

## Desired outcome

```
weekly_retrain.sh
  ├─ preflight + ML train + dataset export (unchanged)
  ├─ Step A (subprocess): settlement EVAL only → write report JSON
  │     • stream/batch scan files
  │     • unique-ticker outcome cache (parquet/jsonl)
  │     • optional --since for Aug 28+ windows
  └─ Step B (subprocess): calibrator FIT only → read labeled cache → save joblib/manifest
        • never re-loads all scan JSON + never re-fetches outcomes in the same process as eval
```

Operators can also run eval-only (as Captain already did) without risking a fit-side OOM, and later fit from the cached labeled table.

## Acceptance criteria

- [ ] Captain approves this plan (status → APPROVED) before product behavior / script changes.
- [ ] `kalshi_settlement_eval.py` supports mutually exclusive modes: **eval** vs **fit** (fit does not re-run full eval in-process).
- [ ] Settlement outcomes are resolved **once per unique ticker** and persisted to an on-disk cache under the Verdant data root (default path configurable).
- [ ] Scan loading for labeling can process files in batches (configurable batch size) without retaining all raw JSON objects at once.
- [ ] CLI supports `--since YYYY-MM-DD` (or equivalent UTC stamp) to restrict scans for the Aug 28+ gate window.
- [ ] `weekly_retrain.sh` invokes **two separate Python processes**: eval report, then fit from cache (fit may be skipped via env flag when gate says “do not refit”).
- [ ] Unit tests cover: ticker dedupe cache, mode separation, `--since` filter, fit-from-cache path (no network).
- [ ] Docs (`README.md` settlement section, `PROGRESS.md`, `TESTING.md`) updated with the two-step commands.
- [ ] Evidence under `.agent/evidence/settlement-retrain-oom/` (test log + short design note).
- [ ] No change to `FairValueConfig.min_confidence` defaults; no calibrator overwrite required for merge (fit remains optional / gated).

## Non-goals

- Accumulating Verdant scans or mounting `/Volumes/Verdant_AI` in Cloud (Captain ops; drive not present here).
- Declaring the 12% calibration gate passed, or forcing a calibrator refit on the pre-guard BUY YES flood.
- Changing paper trial flags / soft-land formula (ADR-001 remains).
- Merging `Kalshi-BTC-Hourly-Event-Scan` → GitHub default branch (tracked as follow-up risk; out of scope unless Captain expands).
- Installing / upgrading NorthStar control files in this product repo (separate NorthStar Track C2 item).
- Live Kalshi network calls in CI.

## Assumptions

1. Production code of record is `Kalshi-BTC-Hourly-Event-Scan` (PR #2 merge), not the GitHub default branch.
2. Captain’s eval-only numbers (298 scans, ~34.8k settled, gap ~81%, manifest `20260828T003036Z`) are authoritative until a post-guard window re-run.
3. Verdant path layout (`verdant_paths` / `BTC_KALSHI_ROOT`) remains the data home for caches and reports.
4. Isotonic calibrator semantics stay the same; only I/O and process boundaries change.

## Open questions (non-blocking defaults)

| Question | Proposed default if Captain silent |
|---|---|
| Skip auto-fit in weekly retrain until post-guard gate passes? | Yes — `SETTLEMENT_FIT_ENABLE=0` default; eval always runs; fit opt-in |
| Cache format | Parquet if pandas/pyarrow available, else JSONL fallback |
| Default batch size | 25 scan files |

## Current-state analysis

| Component | Behavior | Risk |
|---|---|---|
| `kalshi_settlement_eval.main` | Fit then always eval in one process | Double memory / double HTTP |
| `attach_settlement_outcomes` | Per-row GET `/markets/{ticker}` | Memory + rate-limit + time |
| `load_scan_rows` | All files → all rows in one list | Peak RSS with 298 large JSON |
| `weekly_retrain.sh` | Single settlement invocation with `--fit-calibration` | Launchd job dies on OOM |
| Default GitHub branch | Missing Verdant/settlement modules | Cloud agents on default see incomplete tree |

## Proposed architecture

1. **Labeled settlement store** — `{data_root}/settlement_cache/labeled_rows.parquet` (+ `ticker_outcomes.json` map).
2. **`build_or_update_labeled_table(scan_dir, since=…, batch_size=…)`** — iterates scan batches; updates ticker outcome map; appends/upserts labeled rows; drops raw JSON after each batch.
3. **`eval_from_labeled(path, models_base_dir)`** — metrics + slices only; writes `{data_root}/logs/settlement_eval_<stamp>.json`.
4. **`fit_from_labeled(path, models_base_dir)`** — isotonic fit + save manifest; optional; separate process.
5. **CLI** — `--mode eval|fit|refresh-cache` (or flags that enforce exclusivity); `--since`; `--batch-size`; `--cache-dir`; `--report-out`.
6. **weekly_retrain.sh** — Step A eval; Step B fit only if `SETTLEMENT_FIT_ENABLE=1`.

## Workstreams

| ID | Owner | Scope | Depends |
|---|---|---|---|
| W1 | Implementation | Cache + batch load + mode split in `kalshi_settlement_eval.py` / small helper module if needed | Plan approval |
| W2 | Implementation | `weekly_retrain.sh` + README/TESTING | W1 |
| W3 | Test engineer | Unit tests with fixtures (no network) | W1 |
| W4 | Docs | PROGRESS / ADR note / evidence | W1–W3 |

No parallel worktrees required (single file cluster).

## Files expected to change

- `kalshi_settlement_eval.py` (primary)
- Possibly new `settlement_cache.py` (if extraction keeps `kalshi_settlement_eval` readable)
- `scripts/verdant/weekly_retrain.sh`
- `tests/test_probability_calibration.py` and/or new `tests/test_settlement_eval_cache.py`
- `README.md`, `TESTING.md`, `PROGRESS.md`, `DECISIONS.md` (ADR-002)
- `.agent/evidence/settlement-retrain-oom/*`
- `.agent/budgets/settlement-retrain-oom.md`

## Testing strategy

| Layer | What |
|---|---|
| Unit | Dedupe outcomes; batch load; `--since` filter; fit-from-cache does not call HTTP (inject fake client / prelabeled df) |
| Integration | CLI `--mode eval` then `--mode fit` on tiny fixture scan dir |
| Manual (Captain Mac + Verdant) | Run eval-only on full `hourly_outputs`; confirm RSS stays bounded vs pre-fix; optional fit with `SETTLEMENT_FIT_ENABLE=1` |
| Non-applicable | Browser, a11y, production web deploy |

## Security review

- No new secrets; Kalshi client auth unchanged.
- Cache files stay on Verdant volume (ephemeral Cloud must not commit cache artifacts).
- `.gitignore` any local `settlement_cache/` under repo if tests create one.

## Accessibility review

N/A (CLI / data pipeline).

## Migration / deployment

1. Merge to `Kalshi-BTC-Hourly-Event-Scan` (or Captain-chosen integration branch).
2. On Mac: pull; no launchd plist schema change required if script path unchanged.
3. First run builds cache (may be slow once); subsequent evals reuse ticker map.
4. Keep `SETTLEMENT_FIT_ENABLE=0` until post-guard Aug 28+ gap review.

## Rollback plan

- Revert merge commit / restore previous `kalshi_settlement_eval.py` + `weekly_retrain.sh`.
- Delete settlement cache directory if corrupt.
- Rollback tag after approval: `rollback/pre-settlement-retrain-oom`.

## Risks and mitigations

| Risk | Mitigation |
|---|---|
| Fit skipped too long → stale calibrator | Eval report still surfaces gap; Captain enables fit after gate window |
| Cache drift vs new scans | `refresh-cache` / weekly eval always ingests new scan files by mtime/name |
| Default branch still stale | Document; optional follow-up PR to retarget default or merge Kalshi → default |
| pyarrow missing | JSONL fallback |

## Follow-ups (explicitly deferred)

1. **Ops:** Keep Verdant drive connected so hourly scan + 10-minute sync accumulate post-guard files.
2. **~2 weeks:** Re-run settlement eval with `--since 2026-08-28` on post-guard slice; compare raw gap vs 12% gate before any calibrator refit or Phase 3 default change.
3. **Repo hygiene:** Align GitHub default branch with Kalshi production tree so Cloud agents boot the full pipeline.
4. **NorthStar C2:** Install NorthStar memory/Skills into this product repo (control-repo `install.sh`).

## Autonomy budget (after approval)

- Max iterations: 8
- Max agent hours: 4
- Max subagents: 2
- Stop if Verdant data required for proof and drive is unavailable — ship tests + scripts; Captain runs live smoke.

## Approval gate

**Status: AWAITING APPROVAL**

Captain: reply with explicit approval of plan id `settlement-retrain-oom` (and any lock changes to the open questions). No product implementation files will be modified until then.
