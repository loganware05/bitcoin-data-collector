# Project Context

## Product

Bitcoin / Kalshi data collector and hourly event scanner: maps BTC price markets, scores fair value, and emits BUY YES / BUY NO / NO TRADE recommendations.

## Primary data root

`/Volumes/Verdant_AI/btc_kalshi/` (snapshots, models, hourly_outputs, datasets, logs).

**Laptop offline staging:** `~/.local/share/verdant-btc-kalshi/` — hourly scans **and snapshots** write here when the drive is unplugged (if model cache was previously pulled); `sync_verdant_staging.sh` pushes to Verdant on reconnect (ADR-003/005).

## Key hourly path

- `hourly_event_scanner.py` → `hourly_probability_model.py` → `hourly_fair_value_engine.py`
- Fair-value defaults: `min_edge=0.10`, `min_confidence=0.65`, `max_spread=0.08`, `min_liquidity_score=0.50`
- Paper trial (Phase 1, reversible): `hourly_scan.sh` uses `--min-confidence 0.48` via `PAPER_MIN_CONFIDENCE`
- Confidence formula soft-lands mapping: `0.85 + 0.15 * mapping_confidence` (ADR-001)
- BUY YES guards (ADR-002): max model YES 0.85; max OTM strike distance 2%
- BUY NO guards (ADR-002/005): YES OTM ∈ [0.5%, 2%]; never ITM; no model-NO cap
- Settlement eval/fit split + cache (ADR-004); postfix replay Sep13–Oct2 eval-only (ADR-005)

## Workflow

NorthStar (Captain's Compass) installed. Human user is Captain; coordinating agent is First Mate. Product behavior changes require APPROVED `IMPLEMENTATION_PLAN.md`.

## Active workstream

`cursor/ahf-p03-btc-exchange-netflow-8613` / Linear OVA-64 — AHF-P03 BTC
exchange-netflow provider (file fixture + optional Glassnode).

## Branch note

Default GitHub branch `cursor/kalshi-live-decision-system` now carries NorthStar harness; this feature branch merges strike-guards product modules onto that tip.
