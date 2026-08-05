# Implementation Plan

## Metadata

- Status: APPROVED
- Plan ID: kalshi-confidence-guards-ws-a
- Issue: (none yet)
- Branch: feat/kalshi-confidence-guards-ws-a
- Created: 2026-08-05
- Last updated: 2026-08-05
- Approved by: Captain
- Approval date: 2026-08-05
- Approved revision: Phase 1 paper trial + Phase 2 soft-land + Phase 3 defer defaults until calibration gate

## Request

Workstream A: unlock actionable Kalshi BUY YES / BUY NO recommendations by carefully relaxing confidence guards (not gutting them). Prefer diagnose → plan → reversible experiment over blind default cuts.

## Problem Statement

Hourly scans evaluate hundreds of contracts per run but emit **100% NO TRADE**. Diagnosis of `/Volumes/Verdant_AI/btc_kalshi/hourly_outputs/scan_*.json` shows the dominant hard block is **`confidence < min_confidence (0.65)`**, not edge or liquidity.

Prior suggested trial values (`--min-confidence 0.55` and/or `--min-edge 0.07`) are **insufficient**: across all evaluated contracts in existing scans, **0 / 1340 unique contracts** had `confidence >= 0.55` (max observed on latest productive scans ≈ 0.53).

## Desired Outcome

1. Documented, reversible experiment path that can produce a non-zero actionable rate for paper/review.
2. Preserve edge / liquidity / mapping / time-to-expiry guards.
3. Do **not** change production defaults until calibration gate is met (or Captain explicitly waives).
4. Soft-land `compute_confidence()` so typical good signals land near 0.55–0.65 instead of permanently capping ~0.47–0.53.

## Acceptance Criteria

- [x] Captain approves this plan (status → APPROVED) before any product-behavior default or formula change.
- [x] Diagnosis evidence stored under `.agent/evidence/kalshi-confidence-guards-ws-a/`.
- [x] Reversible CLI trial commands documented with expected actionable rates from historical scans.
- [x] Phase 2 formula soft-land implemented; unit tests updated; pytest passes.
- [x] Calibration gate: Captain waived for **paper-only** Phase 1 CLI; Phase 3 defaults deferred until actionable gap &lt;12%.
- [x] Sibling workstream B (scan cadence / launchd) left untouched (except paper CLI flags via `hourly_scan.sh`).

## Non-Goals

- Changing launchd plists or scan frequency (owned by sibling agent B).
- Gutting `min_edge`, liquidity, spread, or mapping guards.
- Blindly setting `min_confidence` to 0.40.

## Phased execution (approved)

### Phase 1 — Paper CLI trial (APPROVED + executing)

`scripts/verdant/hourly_scan.sh` passes `--min-confidence 0.48 --min-edge 0.10` (overridable via `PAPER_MIN_CONFIDENCE` / `PAPER_MIN_EDGE`). Code defaults remain 0.65.

Rollback: unset env overrides and remove flags from `hourly_scan.sh`.

### Phase 2 — Formula soft-land (APPROVED + implementing)

Soft mapping multiply: `mapping_factor = 0.85 + 0.15 * mapping_confidence` (0.75 → 0.9625).

### Phase 3 — Default change (DEFERRED per Captain)

Keep `FairValueConfig.min_confidence=0.65` until actionable calibration gap &lt;12% over 2+ weeks. Prefer formula fix + paper trial over slamming default to 0.48/0.55.

## Approval Record

- **Captain:** approved 2026-08-05
- **Phase 1:** Y (paper trial + calibration-gate waiver for paper only)
- **Phase 2:** Y (soft mapping factor)
- **Phase 3:** Y on deferral — no default `min_confidence` change until gate
