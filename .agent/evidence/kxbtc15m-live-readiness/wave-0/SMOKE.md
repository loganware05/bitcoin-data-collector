# Wave 0 smoke — 2026-11-14T19:11:24.944589+00:00

- Hourly paper LaunchAgent: still loaded (`execution-gate-paper-tick` last_exit=0)
- New jobs not loaded until `./scripts/verdant/ensure_verdant_jobs.sh` (install) — expected pre-merge
- Live money: DENIED
- Standing backlog preserved in PROGRESS.md

## Live read-only smoke (Captain-local)

```bash
python3 kxbtc15m_monitor.py --once --output-dir live_outputs/kxbtc15m
# If series empty/unavailable, soft path still OK — record warning in tick JSON
```
