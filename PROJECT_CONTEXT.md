# Project Context

## Product

Bitcoin / Kalshi data collector and hourly event scanner: maps BTC price markets, scores fair value, and emits BUY YES / BUY NO / NO TRADE recommendations.

## Primary data root

`/Volumes/Verdant_AI/btc_kalshi/` (snapshots, models, hourly_outputs, datasets, logs).

**Laptop offline staging:** `~/.local/share/verdant-btc-kalshi/` — hourly scans write here when the drive is unplugged; `sync_verdant_staging.sh` pushes to Verdant on reconnect (ADR-003).

## Key hourly path

- `hourly_event_scanner.py` → `hourly_probability_model.py` → `hourly_fair_value_engine.py`
- Fair-value defaults: `min_edge=0.10`, `min_confidence=0.65`, `max_spread=0.08`, `min_liquidity_score=0.50`
- Paper trial (Phase 1, reversible): `hourly_scan.sh` uses `--min-confidence 0.48` via `PAPER_MIN_CONFIDENCE`
- Confidence formula soft-lands mapping: `0.85 + 0.15 * mapping_confidence` (ADR-001)
- BUY YES guards (ADR-002): max model YES 0.85; max OTM strike distance 2%; BUY NO only when YES is OTM/ATM within 2% (never ITM); no model-NO cap
- Settlement eval/fit split + cache (ADR-004, PR #5 merged)


## Workflow

Captain's Compass v1.4.0 installed. Human user is Captain; coordinating agent is First Mate. Product behavior changes require APPROVED `IMPLEMENTATION_PLAN.md`.

## Active workstream

`feature/buy-yes-strike-guards` — asymmetric guards + offline staging on top of merged PR #5.
Aug 28+ calibration gate still FAIL until post–ITM-fix scans accumulate.

## Branch note

Production Verdant/settlement code lives on `Kalshi-BTC-Hourly-Event-Scan`.
GitHub default `cursor/kalshi-live-decision-system` is behind and missing those modules.
