# Phase C — Risk breaker interfaces + drill plan (PRE-APPROVAL)

**Status:** Interfaces + stub drills only.  
**Production wiring into live order paths:** NOT APPROVED.

## Interfaces (gate functions)

Implemented as stubs in `scripts/execution-gate/phase_c_breaker_stubs.py`:

| Gate | Trip condition |
|---|---|
| `position_limits` | `position_contracts > max_position_contracts` |
| `exposure_caps` | `gross_exposure_usd > max_gross_exposure_usd` |
| `daily_loss_cap` | `day_realized_pnl_usd <= -daily_loss_cap_usd` |
| `kill_switch` | `kill_switch_engaged == True` |
| `open_markets` | `open_markets > max_open_markets` |

Default disposable limits (starter bankroll scale):

- max position 25 contracts
- max gross exposure $250
- daily loss cap $50
- max open markets 5

## Drill plan

1. Baseline state → all gates clear.
2. Position breach → `position_limits` trips.
3. Exposure breach → `exposure_caps` trips.
4. Daily loss breach → `daily_loss_cap` trips.
5. Kill switch engaged → `kill_switch` trips.
6. Too many open markets → `open_markets` trips.
7. Record JSON under `phase_c_drill.json`; `drill_pass` requires baseline clear + all breach scenarios trip.

```bash
./.venv/bin/python scripts/execution-gate/phase_c_breaker_stubs.py --drill \
  --out .agent/evidence/execution-gate-evidence/risk-drills/phase_c_drill.json
```

## Production merge criteria (future — Captain approval required)

- [ ] Plan `execution-gate-evidence` explicitly approves production breaker merge
- [ ] Wired **before** any live order submit function
- [ ] Fail-closed if limits config missing
- [ ] Alerting on trip
- [ ] Security review of live path (Phase D)
- [ ] Never bypassable by confidence / Jev / research acceptance

## Sandbox note

Stubs live in BDC harness for coordination. Mirror into
`captain-compass-sandbox` only as non-production drill modules until approval.
