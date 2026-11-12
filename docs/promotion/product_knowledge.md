# Product Knowledge — BTC Kalshi Market Intel Pack

Generated for Sellbird / outbound use. Keep factual. Do not invent metrics.

## What we sell

**Primary offer:** BTC Kalshi Market Intel Pack on Agensi — a five-skill agent pack that collects Bitcoin market intelligence, scores explainable rule probabilities, fuses fair value vs market mids, and emits conservative Kalshi-style **BUY YES / BUY NO / NO TRADE** recommendations.

- Listing: https://www.agensi.io/skills/btc-kalshi-market-intel-pack
- Price: **$15 one-time** (converts to local currency at checkout)
- Security: Agensi 8-point security scan passed
- Works with agents that support Agensi MCP (Claude, ChatGPT, Cursor, and compatible agents)

**Open-source companion:** https://github.com/loganware05/bitcoin-data-collector  
Full collector, hourly scanner, ML horizons, and calibration tooling. Free to clone. The Agensi pack is the agent-ready packaging + decision scripts; the repo is the deeper pipeline.

## One-line positioning

Manual BTC → Kalshi research is slow and emotional. This pack gives an agent a guarded, explainable decision workflow that defaults to NO TRADE.

## Pain we solve

- Switching between price, derivatives, sentiment, and Kalshi contract UIs by hand
- Inconsistent probability schemas when prompting a general model
- Acting on thin books or low-confidence noise without liquidity / edge guards
- No calibration trail (Brier / log loss) to see when the model drifts

## What it does (capabilities)

1. **Collect BTC market intel** — Multi-source snapshots (price, liquidity, derivatives, on-chain, sentiment, macro) into structured JSON with graceful degradation.
2. **Rule signal engine** — Explainable direction, confidence, and 12h/24h up/down/range probabilities.
3. **Kalshi decision fusion** — Model/rule vs market mid → edge → BUY YES / BUY NO / NO TRADE with guards.
4. **Hourly BTC event scan** — Rank hourly threshold contracts with min edge, confidence, spread, and liquidity filters.
5. **Evaluate calibration** — Score prediction logs and settlement slices; abstentions are not treated as trades.

## How it works (buyer journey)

1. Connect the agent to Agensi MCP and install / purchase the skill.
2. Ask for a Kalshi hourly BTC scan or an edge decision from probabilities.
3. Review the decision report (drivers, warnings, NO TRADE majority is normal).
4. For full ML horizons and live collection, clone `bitcoin-data-collector` and point the agent at that checkout.

## Hard limits (must say)

- Research and decision-support only. **Not financial advice.**
- **Does not place trades** or call order-placement APIs.
- **NO TRADE is the default** when edge, confidence, liquidity, spread, or mapping quality fails.
- Requires Python 3.11+ for local scripts; full pipeline needs the public repo + `requirements.txt`.
- Optional API keys (CoinGecko, Glassnode, Kalshi auth) improve coverage; public endpoints work without them.

## Pricing & offer ladder

| Stage | Offer |
|---|---|
| Curious | Free sample: edge math walkthrough or redacted decision-report excerpt |
| Interested | Agensi listing ($15) — self-serve, no sales call |
| Builder | GitHub clone for full collector / ML / hourly scanner |
| Ready | Install via Agensi MCP; no meeting required |

**Entry offer language:** "Want a sample guarded decision report for one hourly BTC strike?"  
**Primary offer language:** "The agent skill pack is $15 on Agensi, security-scanned. No call needed."  
**Never lead cold email with price or a pitch.**

## Ideal customer profile (ICP)

- Founders / builders of Kalshi, Polymarket, or prediction-market tooling
- Quant / crypto researchers who already use Claude Code, Cursor, Codex, or agent skills
- Small trading research teams that want explainable guards, not a black-box bot
- Agent-skill creators packaging finance / data workflows

**Disqualify**

- Anyone asking for automated order routing or "guaranteed edge"
- Pure prop shops that need production OMS integration this week
- Prospects who want financial advice or portfolio management

## Buying triggers

- Shipping or hiring around prediction markets, market data, or quant research
- Public posts about Kalshi BTC hourly markets, agent skills, or MCP
- Frustration with manual spreadsheet / multi-tab BTC research
- Recently funded AI / fintech teams building research tooling (post Demo Day window)

## Benefits (buyer language)

- Faster scan → decision loop with explicit edge math
- Conservative defaults that refuse thin or low-confidence markets
- Security-scanned marketplace install instead of a random ZIP
- Open repo behind the pack for auditability and deeper ML

## Proof points (only what is true)

- Live Agensi listing with security scan
- Public GitHub pipeline with collector, signal engine, hourly scanner, calibration tools
- Example session on the listing shows contract table + NO TRADE abstentions + source-health warnings
- Explicit disclaimer on every decision path

Do **not** claim star counts, revenue, win rates, or live trading performance unless Captain supplies verified numbers.

## Competitive frame (short)

| Alternative | Why people leave it | Our angle |
|---|---|---|
| Generic LLM prompts | Inconsistent schemas, no guards | Deterministic edge + NO TRADE defaults |
| DIY scripts only | Setup friction for agents | Agensi one-click skill + MCP |
| Black-box signal Discord | No audit trail | Open repo + calibration logs |
| Full trading bots | Execution risk / compliance | Research-only by design |

## Demo / sample ask

Use this when they reply positively:

> I can send a short sample: model YES vs market mid → edge → BUY YES / NO TRADE with the guard checklist. Or you can install the $15 Agensi pack and run it in your agent. Prefer the sample or the listing?

## Compliance language (always available)

"Research signal only. Not financial advice. Does not place trades."

## Links (use Agensi first for conversion)

1. https://www.agensi.io/skills/btc-kalshi-market-intel-pack
2. https://github.com/loganware05/bitcoin-data-collector
