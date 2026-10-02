# Sep 13–Oct 2 replay — Cloud attempt

Date: 2026-10-02  
Plan: `postfix-buy-no-calibration` (#9)

## Result

**BLOCKED in Cloud Agent** — Verdant volume not mounted and no local model/snapshot cache at `~/.local/share/verdant-btc-kalshi`.

Command:

```bash
./scripts/verdant/settlement_sep13_oct2_replay.sh
```

Observed:

```
ERROR: Verdant not mounted and no local model cache at /home/ubuntu/.local/share/verdant-btc-kalshi
ERROR: cannot resolve BTC_KALSHI_ROOT for Sep13–Oct2 replay
```

See `replay-cloud-attempt.txt`.

## Captain Mac runbook (existing Sep 13–Oct 2 scans)

```bash
# With Verdant mounted:
./scripts/verdant/sync_verdant_staging.sh --pull   # also refreshes offline snapshot cache
./scripts/verdant/settlement_sep13_oct2_replay.sh
# Report → $BTC_KALSHI_ROOT/logs/settlement_sep13_oct2_replay_*.json
# Copy → .agent/evidence/postfix-buy-no-calibration/
```

Fit remains **disabled** (`SETTLEMENT_FIT_ENABLE=0`).

## Unit evidence (Cloud)

`pytest.txt` — **66 passed** including BUY NO OTM floor 0.5% and scan `until` filter.
