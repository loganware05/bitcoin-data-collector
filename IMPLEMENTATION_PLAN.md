# Implementation Plan — Agensi Promo Hygiene

- Status: APPROVED

## Metadata

| Field | Value |
|---|---|
| Status | APPROVED |
| Plan ID | `agensi-promo-hygiene` |
| Repo | `bitcoin-data-collector` only |
| Baseline HEAD | `cursor/kalshi-live-decision-system` @ `59367ad` |
| Branch | `feature/19-agensi-promo-hygiene` |
| Issue | [#19](https://github.com/loganware05/bitcoin-data-collector/issues/19) |
| Rollback | tag `rollback/pre-agensi-promo-hygiene` @ `59367ad` |

## Approval

Captain approved on 2026-11-12 with utterance: **"Yes, do both"** (Sellbird product knowledge + cold sequences, and README/homepage/topics hygiene PR).

## Desired Outcome

Make the live Agensi skill listing discoverable from the public repo, and ship Sellbird-ready product knowledge plus cold sequences so outbound can run without inventing positioning.

## Non-Goals

- Live Kalshi orders / execution changes
- Changing the Agensi ZIP package contents
- Automating sends or warming mailboxes in this PR
- Claiming sales or review metrics

## Workstreams

| ID | Focus | Status |
|---|---|---|
| W1 | README Agensi CTA + research-only framing | DONE |
| W2 | GitHub About: description, homepage, topics | DONE |
| W3 | `docs/promotion/` Sellbird product knowledge + sequences | DONE |
| W4 | PROGRESS/CHANGELOG + PR | DONE |

## Acceptance Criteria

- [x] README links https://www.agensi.io/skills/btc-kalshi-market-intel-pack near the top
- [x] Repo homepage/description/topics updated via GitHub API
- [x] `docs/promotion/product_knowledge.md` and cold sequences committed
- [x] Research-only / no-trade framing preserved
- [x] PR opened from `feature/19-agensi-promo-hygiene` → [#20](https://github.com/loganware05/bitcoin-data-collector/pull/20)

## Rollback

```bash
git checkout cursor/kalshi-live-decision-system
git reset --hard rollback/pre-agensi-promo-hygiene
# Revert GitHub About fields manually if needed
```

## Autonomy Budget

| Limit | Value |
|---|---|
| Maximum iterations | 4 |
| Maximum failed validation cycles | 2 |
| Maximum estimated cost (USD) | 25 |
| Maximum elapsed minutes | 60 |
| Ledger | `.agent/budgets/agensi-promo-hygiene.md` |
