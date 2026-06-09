from __future__ import annotations

import csv
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

MARKET_PROBS_COLUMNS = (
    "timestamp",
    "snapshot_timestamp",
    "ticker",
    "contract_title",
    "market_yes_probability",
    "market_no_probability",
    "model_yes_probability",
    "yes_edge",
    "recommendation",
    "scan_type",
    "notes",
)


def market_probs_path(data_root: Path) -> Path:
    return data_root / "market_probs" / "market_probs.csv"


def _read_existing_keys(path: Path) -> set[tuple[str, str]]:
    if not path.exists():
        return set()
    keys: set[tuple[str, str]] = set()
    with path.open("r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            ts = row.get("snapshot_timestamp") or row.get("timestamp")
            ticker = row.get("ticker")
            if ts and ticker:
                keys.add((str(ts), str(ticker)))
    return keys


def append_market_probs(
    *,
    data_root: Path,
    snapshot_timestamp: str,
    rows: list[dict[str, Any]],
    scan_type: str,
) -> Path:
    """
    Append Kalshi market mids from a scan to {data_root}/market_probs/market_probs.csv.
    Deduplicates on (snapshot_timestamp, ticker).
    """
    out_path = market_probs_path(data_root)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    existing = _read_existing_keys(out_path)
    write_header = not out_path.exists() or out_path.stat().st_size == 0

    logged_at = datetime.now(UTC).isoformat()
    new_rows: list[dict[str, str]] = []
    for row in rows:
        ticker = str(row.get("ticker") or row.get("contract_ticker") or "").strip()
        if not ticker:
            continue
        key = (snapshot_timestamp, ticker)
        if key in existing:
            continue
        market_yes = row.get("market_yes_probability") or row.get("market_implied_probability")
        market_no = row.get("market_no_probability")
        model_yes = row.get("model_yes_probability") or row.get("model_probability")
        yes_edge = row.get("yes_edge") or row.get("edge")
        new_rows.append(
            {
                "timestamp": logged_at,
                "snapshot_timestamp": snapshot_timestamp,
                "ticker": ticker,
                "contract_title": str(row.get("contract_title") or row.get("title") or ""),
                "market_yes_probability": "" if market_yes is None else f"{float(market_yes):.6f}",
                "market_no_probability": "" if market_no is None else f"{float(market_no):.6f}",
                "model_yes_probability": "" if model_yes is None else f"{float(model_yes):.6f}",
                "yes_edge": "" if yes_edge is None else f"{float(yes_edge):.6f}",
                "recommendation": str(row.get("recommendation") or ""),
                "scan_type": scan_type,
                "notes": str(row.get("notes") or ""),
            }
        )
        existing.add(key)

    if not new_rows:
        return out_path

    with out_path.open("a", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(MARKET_PROBS_COLUMNS))
        if write_header:
            writer.writeheader()
        writer.writerows(new_rows)
    return out_path


def rows_from_hourly_scan(scan_result: dict[str, Any]) -> list[dict[str, Any]]:
    ranked = scan_result.get("ranked") or {}
    rows: list[dict[str, Any]] = []
    for bucket in ("buy_yes", "buy_no", "no_trade"):
        for item in ranked.get(bucket) or []:
            if isinstance(item, dict):
                rows.append(item)
    return rows


def rows_from_general_scan(scan_result: dict[str, Any]) -> list[dict[str, Any]]:
    return list(scan_result.get("ranked_opportunities") or [])


__all__ = [
    "MARKET_PROBS_COLUMNS",
    "append_market_probs",
    "market_probs_path",
    "rows_from_general_scan",
    "rows_from_hourly_scan",
]
