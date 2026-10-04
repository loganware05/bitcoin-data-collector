#!/usr/bin/env bash
# Lean Aug 28+ actionable-only settlement calibration (Phase 2 gate).
# Avoids loading NO TRADE rows (full-window eval ballooned to ~15GB).
set -euo pipefail
source "$(dirname "$0")/env.sh"
# shellcheck source=verdant_staging.sh
source "$(dirname "$0")/verdant_staging.sh"
cd "$REPO_ROOT"

if ! verdant_remote_mounted; then
  echo "ERROR: Verdant not mounted at $BTC_KALSHI_REMOTE_ROOT" >&2
  exit 1
fi
export BTC_KALSHI_ROOT="$BTC_KALSHI_REMOTE_ROOT"

SETTLEMENT_SINCE="${SETTLEMENT_SINCE:-2026-08-28}"
CACHE_DIR="${SETTLEMENT_CACHE_DIR:-$BTC_KALSHI_ROOT/settlement_cache}"
REPORT_DIR="${SETTLEMENT_REPORT_DIR:-$BTC_KALSHI_ROOT/logs}"
mkdir -p "$CACHE_DIR" "$REPORT_DIR"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
REPORT_OUT="$REPORT_DIR/settlement_aug28_actionable_${STAMP}.json"

echo "=== Actionable-only settlement eval since ${SETTLEMENT_SINCE} ==="
"$PY" - <<PY
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

sys.path.insert(0, r"""$REPO_ROOT""")
from kalshi_client import KalshiClient, KalshiClientConfig
from probability_calibration import (
    CalibratorConfig,
    evaluate_calibration_slices,
    load_settlement_calibrator,
)
from settlement_label_store import (
    filter_scan_paths,
    load_ticker_outcomes,
    save_ticker_outcomes,
    ticker_outcomes_path,
)

ROOT = Path(r"""$BTC_KALSHI_ROOT""")
CACHE = Path(r"""$CACHE_DIR""")
CACHE.mkdir(parents=True, exist_ok=True)
SINCE = datetime.fromisoformat("${SETTLEMENT_SINCE}").replace(tzinfo=timezone.utc)
REPORT_OUT = Path(r"""$REPORT_OUT""")

paths = filter_scan_paths(sorted((ROOT / "hourly_outputs").glob("scan_*.json")), since=SINCE)
print(json.dumps({"phase": "load_scans", "n_files": len(paths)}), flush=True)

rows: list[dict] = []
for i, path in enumerate(paths):
    try:
        obj = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        continue
    ranked = obj.get("ranked") or {}
    snap = obj.get("timestamp")
    for bucket in ("buy_yes", "buy_no"):
        for item in ranked.get(bucket) or []:
            if not isinstance(item, dict):
                continue
            ticker = item.get("contract_ticker") or item.get("ticker")
            p = item.get("model_yes_probability")
            if ticker is None or p is None:
                continue
            rows.append(
                {
                    "scan_file": str(path),
                    "snapshot_timestamp": snap,
                    "ticker": ticker,
                    "model_yes_probability": float(p),
                    "recommendation": item.get("recommendation")
                    or bucket.replace("_", " ").upper(),
                }
            )
    if (i + 1) % 50 == 0:
        print(json.dumps({"phase": "scan_progress", "i": i + 1, "rows": len(rows)}), flush=True)

df = pd.DataFrame(rows)
if df.empty:
    print(json.dumps({"success": False, "error": "no actionable rows"}))
    raise SystemExit(1)

df["recommendation"] = df["recommendation"].replace({"BUY_YES": "BUY YES", "BUY_NO": "BUY NO"})
df = df.sort_values("snapshot_timestamp").drop_duplicates("ticker", keep="last")
print(
    json.dumps(
        {
            "phase": "deduped",
            "n_actionable_unique": int(len(df)),
            "buy_yes": int((df.recommendation == "BUY YES").sum()),
            "buy_no": int((df.recommendation == "BUY NO").sum()),
        }
    ),
    flush=True,
)

client = KalshiClient(KalshiClientConfig(status="settled"))


def fetch(ticker: str):
    try:
        data = client._get(f"/markets/{ticker}")  # noqa: SLF001
        market = data.get("market") if isinstance(data, dict) else data
        if not isinstance(market, dict):
            return None
        result = market.get("result") or market.get("settlement_value")
        if result is None:
            return None
        r = str(result).strip().lower()
        if r in ("yes", "true", "1"):
            return 1
        if r in ("no", "false", "0"):
            return 0
    except Exception:
        return None
    return None


tickers = sorted(set(df["ticker"].astype(str)))
print(json.dumps({"phase": "fetch_outcomes", "n_unique_tickers": len(tickers)}), flush=True)

cached = load_ticker_outcomes(CACHE)
dirty = 0
for i, t in enumerate(tickers):
    if t in cached and cached[t] is not None:
        continue
    cached[t] = fetch(t)
    dirty += 1
    if dirty and dirty % 50 == 0:
        save_ticker_outcomes(CACHE, cached)
        print(json.dumps({"phase": "fetch_progress", "i": i + 1, "saved": dirty}), flush=True)
if dirty:
    save_ticker_outcomes(CACHE, cached)

df = df.copy()
df["y_true"] = df["ticker"].map(lambda t: cached.get(str(t)))
labeled = df.dropna(subset=["y_true"]).copy()
labeled["y_true"] = labeled["y_true"].astype(int)
print(json.dumps({"phase": "labeled", "n_settled": int(len(labeled))}), flush=True)

cfg = CalibratorConfig(min_samples=10)
calibrator = load_settlement_calibrator(ROOT / "models")
slices = evaluate_calibration_slices(labeled, cfg=cfg, calibrator=calibrator)
primary = slices.get("no_trade_excluded") or slices.get("actionable") or slices.get("all_settled") or {}
gap = primary.get("max_calibration_gap_raw")
if gap is None:
    gap = slices.get("max_calibration_gap")
gate_pass = gap is not None and float(gap) <= 0.12
by_rec = labeled.groupby("recommendation")["y_true"].agg(["count", "mean"]).to_dict()

result = {
    "success": True,
    "window": "${SETTLEMENT_SINCE}+",
    "mode": "actionable_only_deduped",
    "n_scan_files": len(paths),
    "n_actionable_unique": int(len(df)),
    "n_settled_actionable": int(len(labeled)),
    "raw_max_calibration_gap": gap,
    "gate_max_calibration_gap": 0.12,
    "gate_pass": bool(gate_pass),
    "by_recommendation": by_rec,
    "calibration_slices": slices,
    "calibrator_meta": getattr(calibrator, "meta", None) if calibrator else None,
    "ticker_outcomes_path": str(ticker_outcomes_path(CACHE)),
    "report_path": str(REPORT_OUT),
}
REPORT_OUT.write_text(json.dumps(result, indent=2, default=str), encoding="utf-8")
print(json.dumps(result, indent=2, default=str), flush=True)
PY

echo "Report: $REPORT_OUT"
