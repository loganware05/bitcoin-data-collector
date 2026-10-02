# Two-week validation summary

Date: 2026-08-19

## Unit tests

```
pytest tests/ -q → 53 passed
```

## Ops health

| Check | Result |
|---|---|
| Verdant mounted | yes |
| Hourly LaunchAgent | loaded, 119 intervals, last exit **0** |
| Newest scan | `scan_20260819T233042Z.json` (~0.03h stale) |
| Scan files total | **185** (174 since Aug 7) |
| Snapshots | **6085** files, newest today |
| Snapshot/weekly launchd | exit **78** (Verdant log paths; snapshot daemon may be manual) |

## Scan accumulation (Aug 7–19)

~12 days continuous scanning during active UTC hours.

## Recommendation mix (deduped recent)

| Rec | Count |
|---|---|
| BUY YES | 572 |
| BUY NO | 8 |
| NO TRADE | 19,752 |

Recent days: **10–23% actionable**, almost entirely **BUY YES**.

## Settlement calibration (actionable-only, deduped, Aug 7+)

| Metric | Value |
|---|---|
| Settled actionable pairs | **538** (exceeds 80+ goal) |
| Raw max calibration gap | **0.99** |
| Calibrated gap (Aug 7 isotonic) | **0.97** |
| Brier (raw) | 0.47 |
| **Gate &lt;12% raw** | **FAIL** |

BUY YES settled mean outcome ≈ **0.006** (model heavily overpredicts YES on far OTM strikes).

## Conclusion

- History accumulation: **success**
- Phase 3 default loosening: **not warranted**
- Paper BUY YES flood needs guard tightening / recalibrator refit on current actionable slice
