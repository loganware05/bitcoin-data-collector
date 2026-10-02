#!/usr/bin/env bash
# Actionable-only settlement replay for Sep 13–Oct 2 (postfix-buy-no-calibration).
# Loads BUY YES / BUY NO only (never NO TRADE) to avoid OOM (ADR-004).
# Uses an isolated cache dir so it cannot clobber the shared settlement_cache.
# Fit stays disabled (SETTLEMENT_FIT_ENABLE defaults 0).
#
# Usage:
#   ./scripts/verdant/settlement_sep13_oct2_replay.sh
set -euo pipefail
source "$(dirname "$0")/env.sh"
# shellcheck source=verdant_staging.sh
source "$(dirname "$0")/verdant_staging.sh"
cd "$REPO_ROOT"

SETTLEMENT_SINCE="${SETTLEMENT_SINCE:-2026-09-13}"
SETTLEMENT_UNTIL="${SETTLEMENT_UNTIL:-2026-10-02}"
SETTLEMENT_FIT_ENABLE="${SETTLEMENT_FIT_ENABLE:-0}"

if ! verdant_resolve_active_root; then
  echo "ERROR: cannot resolve BTC_KALSHI_ROOT for Sep13–Oct2 replay" >&2
  exit 1
fi

# Isolated cache — do not overwrite shared $BTC_KALSHI_ROOT/settlement_cache
CACHE_DIR="${SETTLEMENT_CACHE_DIR:-$BTC_KALSHI_ROOT/settlement_cache_sep13_oct2}"
REPORT_DIR="${SETTLEMENT_REPORT_DIR:-$BTC_KALSHI_ROOT/logs}"
EVIDENCE_DIR="${REPO_ROOT}/.agent/evidence/postfix-buy-no-calibration"
mkdir -p "$CACHE_DIR" "$REPORT_DIR" "$EVIDENCE_DIR"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
REPORT_OUT="$REPORT_DIR/settlement_sep13_oct2_replay_${STAMP}.json"
EVIDENCE_OUT="$EVIDENCE_DIR/sep13_oct2_replay_${STAMP}.json"

echo "=== Actionable-only postfix replay ${SETTLEMENT_SINCE} → ${SETTLEMENT_UNTIL} ==="
echo "Root: $BTC_KALSHI_ROOT"
echo "Isolated cache: $CACHE_DIR"

SCAN_COUNT="$(find "$BTC_KALSHI_ROOT/hourly_outputs" -maxdepth 1 -name 'scan_*.json' 2>/dev/null | wc -l | tr -d ' ')"
if [[ "${SCAN_COUNT}" == "0" ]]; then
  cat > "$EVIDENCE_OUT" <<JSON
{
  "success": false,
  "blocker": "no_scan_files",
  "btc_kalshi_root": "$BTC_KALSHI_ROOT",
  "since": "$SETTLEMENT_SINCE",
  "until": "$SETTLEMENT_UNTIL",
  "message": "No scan_*.json under hourly_outputs. Mount Verdant or sync local staging, then re-run."
}
JSON
  cp "$EVIDENCE_OUT" "$REPORT_OUT"
  echo "BLOCKER: no scans at $BTC_KALSHI_ROOT/hourly_outputs" >&2
  echo "Evidence: $EVIDENCE_OUT"
  exit 2
fi

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
# Inclusive end-of-day for date-only until
UNTIL = datetime.fromisoformat("${SETTLEMENT_UNTIL}").replace(
    hour=23, minute=59, second=59, tzinfo=timezone.utc
)
REPORT_OUT = Path(r"""$REPORT_OUT""")

paths = filter_scan_paths(
    sorted((ROOT / "hourly_outputs").glob("scan_*.json")),
    since=SINCE,
    until=UNTIL,
)
print(json.dumps({"phase": "load_scans", "n_files": len(paths)}), flush=True)
if not paths:
    result = {
        "success": False,
        "blocker": "empty_window",
        "window": {"since": SINCE.isoformat(), "until": UNTIL.isoformat()},
        "n_scan_files": 0,
        "warnings": ["no scan files in Sep13–Oct2 window; refusing stale-cache eval"],
        "cache_dir": str(CACHE),
        "report_path": str(REPORT_OUT),
    }
    REPORT_OUT.write_text(json.dumps(result, indent=2, default=str), encoding="utf-8")
    print(json.dumps(result, indent=2, default=str), flush=True)
    raise SystemExit(2)

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
    result = {
        "success": False,
        "blocker": "no_actionable_rows",
        "window": {"since": SINCE.isoformat(), "until": UNTIL.isoformat()},
        "n_scan_files": len(paths),
        "warnings": ["no actionable BUY YES/NO rows in window"],
        "cache_dir": str(CACHE),
        "report_path": str(REPORT_OUT),
    }
    REPORT_OUT.write_text(json.dumps(result, indent=2, default=str), encoding="utf-8")
    print(json.dumps(result, indent=2, default=str), flush=True)
    raise SystemExit(2)

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
    "window": {"since": SINCE.isoformat(), "until": UNTIL.isoformat()},
    "mode": "actionable_only_deduped",
    "plan_id": "postfix-buy-no-calibration",
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
    "cache_dir": str(CACHE),
    "report_path": str(REPORT_OUT),
    "fit_enabled": False,
}
REPORT_OUT.write_text(json.dumps(result, indent=2, default=str), encoding="utf-8")
print(json.dumps(result, indent=2, default=str), flush=True)
PY

cp "$REPORT_OUT" "$EVIDENCE_OUT"
echo "Report: $REPORT_OUT"
echo "Evidence: $EVIDENCE_OUT"

if [[ "$SETTLEMENT_FIT_ENABLE" == "1" ]]; then
  echo "WARNING: SETTLEMENT_FIT_ENABLE=1 ignored for postfix replay — fit stays off (ADR-005)." >&2
else
  echo "Fit skipped (SETTLEMENT_FIT_ENABLE=${SETTLEMENT_FIT_ENABLE}) — postfix-buy-no-calibration is eval-only."
fi
