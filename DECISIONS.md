# Decisions

Record architectural and process decisions here (ADR style).

## Template

### ADR-XXX: Title

- **Status:** Proposed | Accepted | Superseded | Deprecated
- **Date:**
- **Context:**
- **Decision:**
- **Consequences:**

### ADR-001: Kalshi hourly confidence guards — paper trial + soft-land

- **Status:** Accepted
- **Date:** 2026-08-05
- **Context:** Hourly scans were 100% NO TRADE because `compute_confidence()` multiplied raw `mapping_confidence` (~0.75), structurally capping scores ~0.47–0.53 below `min_confidence=0.65`. Prior trial at 0.55 would still unlock 0%. Actionable settlement calibration gap gate (&lt;12%) cannot be measured until some BUY YES/NO rows exist.
- **Decision:**
  1. Soft-land mapping in `compute_confidence()` via `0.85 + 0.15 * mapping_confidence`.
  2. Run paper-only Phase 1 with `--min-confidence 0.48` (keep `min_edge=0.10`) via `hourly_scan.sh`, waiving the calibration gate for paper recommendations only.
  3. Defer changing `FairValueConfig` / CLI defaults from 0.65 until actionable calibration gap &lt;12% over 2+ weeks.
- **Consequences:** Paper scans can emit BUY YES/NO for review. Production code defaults stay conservative. Rollback = remove paper flags from `hourly_scan.sh` and/or revert soft-land commit.

### ADR-002: Settlement eval and calibrator fit run in separate processes

- **Status:** Accepted
- **Date:** 2026-09-13
- **Context:** Weekly retrain OOM’d when `kalshi_settlement_eval.py --fit-calibration` loaded all scan JSON twice and fetched Kalshi outcomes once per row (~35k) in the same process as ML retrain.
- **Decision:**
  1. Persist a labeled settlement cache (unique-ticker outcomes + batched scan load).
  2. CLI modes `eval` / `fit` / `refresh-cache` are mutually exclusive in one process.
  3. `weekly_retrain.sh` runs eval then optional fit as two Python processes; `SETTLEMENT_FIT_ENABLE` defaults to `0` until the Aug 28+ 12% gate passes.
- **Consequences:** Retrain survives large scan histories; calibrator updates are explicit. Operators use `settlement_aug28_window.sh` for post-guard checks.
