# KXBTC15M Decision Engine — validation summary

| Field | Value |
|---|---|
| Plan | `kxbtc15m-decision-engine` (#21) |
| Branch | `feature/21-kxbtc15m-decision-engine` |
| Baseline / rollback | `addc982` / `rollback/pre-kxbtc15m-decision-engine` |
| Date | 2026-11-14 |
| Live execution | **DENIED** (`approved_for_execution=false`) |

## Validation

```text
python3 -m pytest tests/ -q
88 passed
```

## Wave evidence

| Wave | Artifact |
|---|---|
| A | `wave-a/decision_report.json`, `wave-a/no_trade_incomplete.json` |
| B | `wave-b/settlement_edge_report.json` |
| C | `wave-c/sample_tick.json` |
| D | `wave-d/train_eval.json` + `../execution-gate-evidence/paper-kxbtc15m/` |

## Safety checks

- Hourly `paper_buy_no_v1` state dir not used by 15m paper tick
- `phase_b_kxbtc15m_paper_tick.py` refuses `.../paper` shared dir and `approved_for_execution=true`
- No Kalshi order placement APIs added
