# Promotion pack (Agensi + Sellbird)

Paste-ready assets to promote:

- Agensi listing: https://www.agensi.io/skills/btc-kalshi-market-intel-pack
- Public repo: https://github.com/loganware05/bitcoin-data-collector

## Files

| File | Use |
|---|---|
| `product_knowledge.md` | Copy into Sellbird as `product_knowledge.md` (usually under `SELLBIRD_HOME` / `skills/`) |
| `competitive_intel.md` | Optional Sellbird competitive battle cards |
| `cold_sequences.md` | Human-approved cold email campaigns + social launch copy |
| `icp-and-signals.md` | Who to target and which Sellbird signals to confirm |

## Load into Sellbird

```bash
# After sellbird train on the Agensi page, overwrite generated product knowledge:
cp docs/promotion/product_knowledge.md "$SELLBIRD_HOME/skills/product_knowledge.md"
cp docs/promotion/competitive_intel.md "$SELLBIRD_HOME/skills/competitive_intel.md"
```

On macOS default home: `~/Library/Application Support/sellbird`.

Recommended train order:

```bash
sellbird train https://www.agensi.io/skills/btc-kalshi-market-intel-pack
# then replace product_knowledge.md with this repo's version
sellbird signals --confirm free
```

## Rules

- Always deep-link the **Agensi listing** for paid conversion, not only GitHub.
- Research signals only. Never claim automated trading or guaranteed edge.
- Cold email: approve every Outbox draft; keep email 1 under ~60 words with no link.
