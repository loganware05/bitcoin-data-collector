# Phase B — Live-forward paper loop (sandbox)

**Status:** Designed + schema harness started. **30-day track record NOT complete.**  
**Mode:** Real-time market data IN → conservative simulated fills OUT. No real money.

## Goals

Satisfy readiness gate `paper_track_record` with continuous live paper that is
**not** settlement replay.

## Architecture (sandbox-isolated)

```
Kalshi/public market feed (read-only)
        │
        ▼
┌───────────────────────────┐
│  paper_loop (sandbox)     │
│  - signal from BDC hourly │
│  - DayClock               │
│  - ConservativeFillModel  │
│  - metrics accumulator    │
└───────────┬───────────────┘
            │ simulated fills / paper ledger
            ▼
   .agent/evidence/.../paper/ledger/*.jsonl
```

Order path stays in `captain-compass-sandbox` (or disposable sandbox process).
BDC remains recommendations + research; no live order client enablement.

## Day clock

- Increment only on continuous calendar days with live-forward activity.
- Any manual override → `consecutive_days = 0` (encoded in
  `scripts/execution-gate/phase_b_paper_loop.py`).
- Gap > 1 calendar day also resets.
- Gate target: **30** consecutive calendar days.

## Conservative fill model

| Rule | Behavior |
|---|---|
| Cross the spread | Buys @ ask, sells @ bid |
| Partial fills | Probabilistic partial qty |
| No-fills | Probabilistic zero fill |
| Fees + slippage | bps deducted from mark PnL |
| PnL interpretation | Optimistic ceiling — still not live edge |

## Metrics schema (`bdc.execution_gate.phase_b_paper.v1`)

See `phase_b_schema.json` (generated).

OOS floor (paper):

- ≥14 days paper
- ≥50 closed trades
- total return > 0%
- max DD < 15%
- paper Sharpe (per-trade t-stat) ≥ 1.0
- profit factor ≥ 1.2  
  (later live floor ≥ 1.5)

## Start commands (when feed available)

```bash
# Schema + dry-run only (safe anywhere)
./.venv/bin/python scripts/execution-gate/phase_b_paper_loop.py \
  --dry-run-tick \
  --out .agent/evidence/execution-gate-evidence/paper/phase_b_schema.json
```

Continuous loop requires Captain laptop / sandbox with real-time feed credentials
that are **trading-disabled / read-only**. Do not start 30d clock in cloud without
a durable always-on feed.

## Explicit non-claims

- This session does **not** claim 30d complete.
- Settlement replay under `postfix-buy-no-calibration` is plumbing only.
- Fixture paper_session in AHF-P05 sample is insufficient for the gate.
