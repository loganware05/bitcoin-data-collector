# Project Context

## Product

Bitcoin / Kalshi data collector and hourly event scanner: maps BTC price markets, scores fair value, and emits BUY YES / BUY NO / NO TRADE recommendations.

## Primary data root

`/Volumes/Verdant_AI/btc_kalshi/` (snapshots, models, hourly_outputs, datasets, logs).

## Key hourly path

- `hourly_event_scanner.py` → `hourly_probability_model.py` → `hourly_fair_value_engine.py`
- Fair-value defaults: `min_edge=0.10`, `min_confidence=0.65`, `max_spread=0.08`, `min_liquidity_score=0.50`
- Paper trial (Phase 1, reversible): `hourly_scan.sh` uses `--min-confidence 0.48` via `PAPER_MIN_CONFIDENCE`
- Confidence formula soft-lands mapping: `0.85 + 0.15 * mapping_confidence` (ADR-001)


## Workflow

Captain's Compass v1.4.0 installed. Human user is Captain; coordinating agent is First Mate. Product behavior changes require APPROVED `IMPLEMENTATION_PLAN.md`.

## Active workstream

`settlement-retrain-oom` — split weekly settlement eval from calibrator fit to stop OOM
(AWAITING APPROVAL). Prior: `kalshi-confidence-guards-ws-a` (shipped soft-land + paper trial).

## Branch note

Production Verdant/settlement code lives on `Kalshi-BTC-Hourly-Event-Scan`.
GitHub default `cursor/kalshi-live-decision-system` is behind and missing those modules.
