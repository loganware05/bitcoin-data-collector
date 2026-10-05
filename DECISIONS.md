# Decisions

Record architectural and process decisions here (ADR style).

## Template

### ADR-XXX: Title

- **Status:** Proposed | Accepted | Superseded | Deprecated
- **Date:**
- **Context:**
- **Decision:**
- **Consequences:**

### ADR-006: BTC exchange-netflow provider (AHF-P03)

- **Status:** Accepted
- **Date:** 2026-10-05
- **Context:** NorthStar On-Chain / AI Hedge Fund track (OVA-64). Snapshot schema
  already stubbed `exchange_inflow_btc` / `exchange_outflow_btc` but never filled.
- **Decision:**
  1. Add `exchange_flow_provider.py` with `file` fixture and optional
     `glassnode` live path (`GLASSNODE_API_KEY` Captain-local).
  2. Env `COMPASS_EXCHANGE_FLOW_PROVIDER` (`file`|`glassnode`|`off`); default
     `off` unless Glassnode key present.
  3. Persist provenance fields on `on_chain_data`; enhance
     `compute_onchain_signal` and feature `exchange_netflow_btc`.
- **Consequences:** Hermetic tests use fixtures; production stays None without
  key/fixture. Recommendations-only product unchanged.

### ADR-005: BUY NO minimum OTM floor + offline snapshot cache (no-calibration postfix)

- **Status:** Accepted
- **Date:** 2026-10-02
- **Context:** After ADR-002 ITM BUY NO fix, near-ATM BUY NO (`0 ≤ dist < 0.5%`) still concentrates risk. Captain approved postfix plan without waiting for calibrator fit. Offline staging lacked snapshot continuity when Verdant was unplugged.
- **Decision:**
  1. `FairValueConfig.min_buy_no_otm_pct = 0.005` — BUY NO only when YES OTM ∈ [0.5%, max_buy_no_strike_distance_pct].
  2. Extend ADR-003 local staging to pull/push **snapshots** (bounded by `BTC_KALSHI_SNAPSHOT_CACHE_DAYS`, default 21); snapshot daemon writes local when remote offline if model cache present.
  3. Replay Sep 13–Oct 2 via `settlement_sep13_oct2_replay.sh` / `--until` **eval-only** (`SETTLEMENT_FIT_ENABLE=0`).
- **Consequences:** Tighter BUY NO band; offline laptop can continue snapshot collection; calibrator fit still Captain-gated.

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
  - Snapshot daemon: when remote offline **and** model cache present, write snapshots to local staging and push on reconnect (ADR-005); otherwise skip carefully
- **Consequences:** No lost scan intervals on laptop; models must be pulled at least once while drive connected. Weekly retrain still requires Verdant mounted. Snapshot continuity available offline after first pull.

### ADR-002: BUY YES strike-distance and max-model-YES guards

- **Status:** Accepted (revised 2026-08-28)
- **Date:** 2026-08-19
- **Context:** Two-week validation showed 538 settled actionable pairs but raw calibration gap 0.99. Paper trial at `min_confidence=0.48` flooded BUY YES on far-OTM strikes with model YES ~96% that settled YES ~0.6% of the time. Symmetric `max_buy_no_model_probability` blocked **all** BUY NO when model NO was ~0.99 on far-above strikes (expected behavior).
- **Decision:** Keep paper `min_confidence=0.48` with asymmetric guards in `FairValueConfig`:
  - `max_buy_yes_model_probability=0.85` — blocks overconfident far-OTM BUY YES
  - `max_buy_yes_strike_distance_pct=0.02` (2% OTM)
  - `max_buy_no_strike_distance_pct=0.02` with `min_buy_no_otm_pct=0.005` (ADR-005) — BUY NO only when YES is **OTM within 0.5%–2%** (never ITM or sub-floor ATM)
  - **No** `max_buy_no_model_probability` cap (removed 2026-08-28)
- **Consequences:** BUY YES flood remains blocked; BUY NO no longer bets against ITM YES or near-ATM noise. Phase 3 default cuts remain deferred until actionable raw gap &lt;12%.

### ADR-001: Kalshi hourly confidence guards — paper trial + soft-land

- **Status:** Accepted
- **Date:** 2026-08-05
- **Context:** Hourly scans were 100% NO TRADE because `compute_confidence()` multiplied raw `mapping_confidence` (~0.75), structurally capping scores ~0.47–0.53 below `min_confidence=0.65`. Prior trial at 0.55 would still unlock 0%. Actionable settlement calibration gap gate (&lt;12%) cannot be measured until some BUY YES/NO rows exist.
- **Decision:**
  1. Soft-land mapping in `compute_confidence()` via `0.85 + 0.15 * mapping_confidence`.
  2. Run paper-only Phase 1 with `--min-confidence 0.48` (keep `min_edge=0.10`) via `hourly_scan.sh`, waiving the calibration gate for paper recommendations only.
  3. Defer changing `FairValueConfig` / CLI defaults from 0.65 until actionable calibration gap &lt;12% over 2+ weeks.
- **Consequences:** Paper scans can emit BUY YES/NO for review. Production code defaults stay conservative. Rollback = remove paper flags from `hourly_scan.sh` and/or revert soft-land commit.
