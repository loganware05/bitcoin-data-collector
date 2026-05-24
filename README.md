# Bitcoin Data Collector

A decision-grade pipeline for Bitcoin market intelligence and Kalshi-style probability forecasts. The system collects multi-source BTC data, produces explainable rule-based signals, engineers ML features (including liquidity sweeps and IFVG indicators), trains calibrated classifiers, and runs a live loop that fuses rule + ML outputs into conservative trade recommendations.

**This project generates recommendations only — it does not execute trades.**

## What it does

1. **Collect** — Pull price, liquidity, derivatives, on-chain, sentiment, and macro data from public APIs with graceful degradation.
2. **Signal (rules)** — Deterministic scoring and 24h up/down/range probabilities from the snapshot schema.
3. **Features + ML** — Build numeric features from 15m candles + snapshot fields; train interpretable models with time-series validation and calibration.
4. **Fuse + map** — Combine rule and ML probabilities; compare to a manual market-implied probability to compute edge and BUY YES / BUY NO / NO TRADE.
5. **Evaluate** — Log predictions live, backfill realized outcomes, and monitor rolling accuracy and calibration drift.

## Architecture

```mermaid
flowchart TD
  collector[btc_market_intel_collector] --> snapshot[Snapshot JSON]
  snapshot --> ruleSignal[signal_engine]
  snapshot --> candles[Candles 15m]
  candles --> indicators[indicator_engine]
  snapshot --> features[feature_engineering]
  indicators --> features
  features --> model[ml_model]
  ruleSignal --> fusion[kalshi_mapper]
  model --> fusion
  fusion --> decision[Decision JSON]
  decision --> eval[eval_utils]
```

## Requirements

- Python 3.11+
- See `requirements.txt` for core dependencies (`pandas`, `numpy<2`, `scikit-learn`, etc.)
- Collector also needs: `httpx`, `python-dotenv`

```bash
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
pip install httpx python-dotenv
```

Optional: set `COINGECKO_API_KEY` in a `.env` file for higher CoinGecko rate limits.

## Quick start

### 1. Collect a snapshot

```bash
python btc_market_intel_collector.py --output-dir outputs
```

Writes timestamped JSON (and optional CSV) under `outputs/`. Each snapshot includes `market_data.candles_15m` for reproducible feature engineering.

### 2. Run the rule-based signal engine

```bash
python signal_engine.py outputs/btc_market_intel_<timestamp>.json --pretty
```

Or use the example runner:

```bash
python examples/run_signal_engine.py outputs/btc_market_intel_<timestamp>.json
```

### 3. Backtest rule probabilities (needs history)

Point-in-time snapshots in `outputs/` can be backtested once you have enough files spaced across your horizon:

```bash
python backtester.py outputs --horizon-hours 24 --plot-dir backtest_plots
```

For the small bundled sample set, use a shorter horizon:

```bash
python examples/run_backtest.py --input outputs --horizon-hours 1
```

### 4. Train an ML model

Build a labeled dataset from a directory of snapshots (or CSV), train with time-series CV, calibrate on a holdout tail, and save artifacts under `models/`:

```bash
python ml_model.py outputs --model-family logreg --horizon-hours 24
```

Model families: `logreg` (default), `decision_tree`, `hgb`.

### 5. Run the live loop

Runs the collector, fuses rule + latest saved model, and appends to `live_outputs/predictions_log.jsonl`. Pass a manual market-implied probability to enable edge-based recommendations:

```bash
python live_runner.py --once --market-implied-prob 0.52
```

Continuous mode (default interval: 15 minutes):

```bash
python live_runner.py --interval-seconds 900 --market-implied-prob 0.52
```

If no model exists or candles are missing, the runner degrades to rule-only and logs warnings.

### 6. Evaluate live performance

After outcomes are backfilled (automatic in the live loop once the 24h horizon passes):

```bash
python eval_utils.py --predictions-log live_outputs/predictions_log.jsonl --outcomes-log live_outputs/outcomes_log.jsonl
```

Reports rolling accuracy, Brier score, log loss, calibration gaps, and `retrain_recommended` when drift thresholds are exceeded.

### 7. Build labeled dataset on Verdant_AI

Export ML training labels and a full decision dataset (rule + ML fusion, edge, recommendations) to the external volume. Requires enough snapshot history for your horizon (e.g. 24h labels need files spanning at least one day).

**Layout on the volume:**

```
/Volumes/Verdant_AI/btc_kalshi/
  datasets/
    labeled_features_{UTC}.csv
    decision_dataset_{UTC}.csv
    dataset_manifest_{UTC}.json
  market_probs/
    market_probs.csv    # your sidecar (one row per snapshot timestamp)
```

**Steps:**

1. Collect snapshots into `outputs/` (or copy `live_outputs/snapshots/`).
2. Train a model: `python ml_model.py outputs --horizon-hours 24`
3. Copy `examples/market_probs.template.csv` to `/Volumes/Verdant_AI/btc_kalshi/market_probs/market_probs.csv` and add a `market_implied_prob` (0–1) per snapshot timestamp.
4. Export:

```bash
python dataset_builder.py outputs \
  --output-dir /Volumes/Verdant_AI/btc_kalshi/datasets \
  --market-probs-csv /Volumes/Verdant_AI/btc_kalshi/market_probs/market_probs.csv \
  --horizon-hours 24
```

**Sidecar CSV** (required columns: `timestamp`, `market_implied_prob`; optional: `contract_hint`, `notes`). Timestamps are matched with nearest-neighbor join within 5 minutes (configurable via `--market-match-tolerance-minutes`). Rows without a sidecar match get `edge` null and **NO TRADE**.

**Decision CSV columns** include `rule_p_*`, `ml_p_*`, `fused_p_*`, `market_implied_prob`, `edge`, `recommendation` (`BUY YES` / `BUY NO` / `NO TRADE`), and realized `y_true` for evaluation.

Use `--labeled-only` or `--decision-only` for partial exports. For a short bundled sample, use `--horizon-hours 1`.

**Label vs rule band:** ML labels use ±1% (`TrainConfig.range_threshold_pct`); rule range probabilities use ±0.5% (`SignalEngineConfig.range_band_pct`). The manifest JSON records both.

## Project layout

| Module | Role |
|--------|------|
| `btc_market_intel_collector.py` | Multi-source data collection and unified snapshot schema |
| `signal_engine.py` | Explainable rule engine → score, direction, 24h probabilities |
| `indicator_engine.py` | Liquidity sweeps + IFVG features on 15m candles |
| `feature_engineering.py` | ML feature row from snapshot + candles + indicators |
| `ml_model.py` | Dataset build, train/calibrate, persist, explain, importance |
| `kalshi_mapper.py` | Fuse rule/ML probs → edge and recommendation |
| `decision_utils.py` | Shared rule-probability extraction and confidence helper |
| `dataset_builder.py` | Batch labeled/decision CSV export to Verdant_AI |
| `live_runner.py` | Live loop, degraded mode, prediction/outcome logs |
| `eval_utils.py` | Rolling metrics and retrain warnings from live logs |
| `backtester.py` | Historical evaluation of rule-engine probabilities |
| `metrics.py` | Shared accuracy, Brier, log loss, calibration helpers |

## Snapshot schema (high level)

Snapshots are JSON objects with stable keys, including:

- `price_data`, `volume_data`, `liquidity_data`, `derivatives_data`
- `on_chain_data`, `sentiment_data`, `macro_data`
- `market_data.candles_15m` — list of `{timestamp, open, high, low, close, volume}`
- `source_health` — per-source status for confidence haircuts
- `signals` — derived boolean flags (volume spike, low liquidity, etc.)

## Kalshi decision output

When `market_implied_prob` is provided, `kalshi_mapper` returns objects like:

```json
{
  "contract": "up",
  "probability": 0.58,
  "market_implied_prob": 0.52,
  "edge": 0.06,
  "confidence": 0.61,
  "recommendation": "BUY YES",
  "key_factors": ["..."],
  "ml_explanation": ["ret_log_24h (+0.12)", "..."],
  "warnings": []
}
```

Without market implied probability, `edge` is `null` and recommendation is **NO TRADE** (conservative default).

## Data sources

Public APIs with fallbacks where noted:

- **Spot / candles / order book** — Binance (primary), Coinbase (fallback)
- **Aggregates** — CoinGecko
- **Derivatives** — Binance Futures (OI, funding, liquidations)
- **On-chain** — Blockchain.com charts
- **Sentiment** — Alternative.me Fear & Greed
- **Macro correlations** — CoinGecko BTC series + FRED (SPX, gold, NASDAQ)

Some fields are intentionally `null` with TODO notes (ETF flows, exchange flows, options IV) until paid feeds are integrated.

## Configuration

Behavior is controlled via dataclasses in each module (e.g. `SignalEngineConfig`, `FeatureConfig`, `TrainConfig`, `FusionConfig`, `LiveConfig`). Adjust weights, horizons, edge thresholds, and indicator parameters in code or by extending CLI flags.

Default fusion weights: **55% rule / 45% ML**. Minimum edge: **3%**, minimum confidence: **0.55**.

## Limitations

- Snapshots are point-in-time; backtests and ML training need enough historical files for your chosen horizon.
- Binance endpoints may be blocked in some environments; Coinbase fallbacks apply.
- Live runner invokes the collector as a subprocess; ensure the working directory is the repo root.
- Recommendations require a manually supplied market-implied probability (no Kalshi API integration yet).

## License

Add your license here.
