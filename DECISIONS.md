# Decisions

Record architectural and process decisions here (ADR style).

## Template

### ADR-XXX: Title

- **Status:** Proposed | Accepted | Superseded | Deprecated
- **Date:**
- **Context:**
- **Decision:**
- **Consequences:**

### ADR-004: Settlement eval and calibrator fit run in separate processes

- **Status:** Accepted
- **Date:** 2026-09-13
- **Context:** Weekly retrain OOM’d when `kalshi_settlement_eval.py --fit-calibration` loaded all scan JSON twice and fetched Kalshi outcomes once per row (~35k) in the same process as ML retrain. NorthStar cloud agent (PR #5 / issue #4) implemented the fix.
- **Decision:**
  1. Persist a labeled settlement cache (unique-ticker outcomes + batched scan load) via `settlement_label_store.py`.
  2. CLI modes `eval` / `fit` / `refresh-cache` are mutually exclusive in one process.
  3. `weekly_retrain.sh` runs eval then optional fit as two Python processes; `SETTLEMENT_FIT_ENABLE` defaults to `0` until the Aug 28+ 12% gate passes.
- **Consequences:** Retrain survives large scan histories; calibrator updates are explicit. Operators use `settlement_aug28_window.sh` for post-guard checks.

### ADR-003: Local laptop staging when Verdant drive offline

- **Status:** Accepted
- **Date:** 2026-08-28
- **Context:** Hourly scans run on a laptop; `/Volumes/Verdant_AI` may be unplugged at scheduled times. Prior `env.sh` hard-exited when unmounted, losing scan slots.
- **Decision:**
  - Local staging root: `~/.local/share/verdant-btc-kalshi` (`BTC_KALSHI_LOCAL_ROOT`)
  - When remote mounted: scan to Verdant; `rsync` models → local cache; push any pending local scans
  - When remote offline: scan to local staging if model cache exists; push on reconnect
  - `com.verdant.btc-kalshi.sync-staging` LaunchAgent runs every 10 min + at login
  - Snapshot daemon skips gracefully when drive offline (snapshots stay on Verdant only)
- **Consequences:** No lost scan intervals on laptop; models must be pulled at least once while drive connected. Weekly retrain still requires Verdant mounted.

### ADR-002: BUY YES strike-distance and max-model-YES guards

- **Status:** Accepted (revised 2026-08-28)
- **Date:** 2026-08-19
- **Context:** Two-week validation showed 538 settled actionable pairs but raw calibration gap 0.99. Paper trial at `min_confidence=0.48` flooded BUY YES on far-OTM strikes with model YES ~96% that settled YES ~0.6% of the time. Symmetric `max_buy_no_model_probability` blocked **all** BUY NO when model NO was ~0.99 on far-above strikes (expected behavior).
- **Decision:** Keep paper `min_confidence=0.48` with asymmetric guards in `FairValueConfig`:
  - `max_buy_yes_model_probability=0.85` — blocks overconfident far-OTM BUY YES
  - `max_buy_yes_strike_distance_pct=0.02` (2% OTM)
  - `max_buy_no_strike_distance_pct=0.02` — BUY NO only when YES is **OTM/ATM within 2%** (never when YES is ITM; fixed 2026-09-13 after Aug 28+ gate showed ITM BUY NOs settling YES ~82%)
  - **No** `max_buy_no_model_probability` cap (removed 2026-08-28)
- **Consequences:** BUY YES flood remains blocked; BUY NO no longer bets against ITM YES. Phase 3 default cuts remain deferred until actionable raw gap &lt;12%.

### ADR-001: Kalshi hourly confidence guards — paper trial + soft-land

- **Status:** Accepted
- **Date:** 2026-08-05
- **Context:** Hourly scans were 100% NO TRADE because `compute_confidence()` multiplied raw `mapping_confidence` (~0.75), structurally capping scores ~0.47–0.53 below `min_confidence=0.65`. Prior trial at 0.55 would still unlock 0%. Actionable settlement calibration gap gate (&lt;12%) cannot be measured until some BUY YES/NO rows exist.
- **Decision:**
  1. Soft-land mapping in `compute_confidence()` via `0.85 + 0.15 * mapping_confidence`.
  2. Run paper-only Phase 1 with `--min-confidence 0.48` (keep `min_edge=0.10`) via `hourly_scan.sh`, waiving the calibration gate for paper recommendations only.
  3. Defer changing `FairValueConfig` / CLI defaults from 0.65 until actionable calibration gap &lt;12% over 2+ weeks.
- **Consequences:** Paper scans can emit BUY YES/NO for review. Production code defaults stay conservative. Rollback = remove paper flags from `hourly_scan.sh` and/or revert soft-land commit.
