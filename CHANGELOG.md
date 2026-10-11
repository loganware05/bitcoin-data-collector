# Changelog

## Unreleased

### Added

- Execution-gate evidence tree (`.agent/evidence/execution-gate-evidence/`) for AHF-P06 follow-on — live execution remains DENIED
- Non-execution harnesses: `scripts/execution-gate/phase_a_cpcv_dsr.py`, `phase_b_paper_loop.py`, `phase_c_breaker_stubs.py`
- BUY NO minimum OTM floor `min_buy_no_otm_pct=0.005` (0.5%) — ADR-005 / #9
- Offline Verdant snapshot cache pull/push; offline snapshot daemon when model cache present
- `kalshi_settlement_eval.py --until` and `scripts/verdant/settlement_sep13_oct2_replay.sh`

### Changed

- ADR-002 BUY NO band is now 0.5%–2% OTM (was 0%–2% ATM/OTM)
- ADR-003 staging also caches recent snapshots (`BTC_KALSHI_SNAPSHOT_CACHE_DAYS`, default 21)

### Fixed
