"""Disk-backed labeled settlement store for memory-safe eval / fit.

Keeps unique-ticker outcome lookups and labeled scan rows on disk so weekly
retrain can run evaluation and calibrator fit in separate processes without
reloading every scan JSON twice or re-fetching Kalshi outcomes per row.
"""

from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Callable, Iterable

import pandas as pd

SCAN_NAME_RE = re.compile(r"scan_(\d{8}T\d{6}Z)\.json$", re.IGNORECASE)

OutcomeFetcher = Callable[[str], int | None]


def default_cache_dir(data_root: Path) -> Path:
    return Path(data_root) / "settlement_cache"


def labeled_rows_path(cache_dir: Path) -> Path:
    return Path(cache_dir) / "labeled_rows.parquet"


def labeled_rows_jsonl_path(cache_dir: Path) -> Path:
    return Path(cache_dir) / "labeled_rows.jsonl"


def ticker_outcomes_path(cache_dir: Path) -> Path:
    return Path(cache_dir) / "ticker_outcomes.json"


def parse_scan_stamp(path: Path) -> datetime | None:
    match = SCAN_NAME_RE.search(path.name)
    if not match:
        return None
    try:
        return datetime.strptime(match.group(1), "%Y%m%dT%H%M%SZ").replace(tzinfo=UTC)
    except ValueError:
        return None


def filter_scan_paths(
    scan_paths: Iterable[Path],
    *,
    since: datetime | None = None,
) -> list[Path]:
    paths = sorted(Path(p) for p in scan_paths)
    if since is None:
        return paths
    since_utc = since if since.tzinfo else since.replace(tzinfo=UTC)
    kept: list[Path] = []
    for path in paths:
        stamp = parse_scan_stamp(path)
        if stamp is None or stamp >= since_utc:
            kept.append(path)
    return kept


def load_ticker_outcomes(cache_dir: Path) -> dict[str, int | None]:
    path = ticker_outcomes_path(cache_dir)
    if not path.exists():
        return {}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    if not isinstance(raw, dict):
        return {}
    out: dict[str, int | None] = {}
    for key, value in raw.items():
        if value is None:
            out[str(key)] = None
        else:
            try:
                out[str(key)] = int(value)
            except (TypeError, ValueError):
                out[str(key)] = None
    return out


def save_ticker_outcomes(cache_dir: Path, outcomes: dict[str, int | None]) -> Path:
    cache_dir = Path(cache_dir)
    cache_dir.mkdir(parents=True, exist_ok=True)
    path = ticker_outcomes_path(cache_dir)
    path.write_text(json.dumps(outcomes, indent=2, sort_keys=True), encoding="utf-8")
    return path


def resolve_ticker_outcomes(
    tickers: Iterable[str],
    *,
    cache_dir: Path,
    fetch_outcome: OutcomeFetcher,
    persist: bool = True,
) -> dict[str, int | None]:
    """Resolve YES/NO outcomes once per unique ticker, using on-disk cache first."""
    cache_dir = Path(cache_dir)
    cached = load_ticker_outcomes(cache_dir)
    updated = False
    for ticker in sorted({str(t) for t in tickers if t}):
        if ticker in cached and cached[ticker] is not None:
            continue
        value = fetch_outcome(ticker)
        if ticker not in cached or cached[ticker] != value:
            cached[ticker] = value
            updated = True
    if persist and updated:
        save_ticker_outcomes(cache_dir, cached)
    return cached


def _rows_from_scan_obj(obj: dict[str, Any], *, scan_file: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    snap_ts = obj.get("timestamp")
    ranked = obj.get("ranked") or {}
    for bucket in ("buy_yes", "buy_no", "no_trade"):
        for item in ranked.get(bucket) or []:
            if not isinstance(item, dict):
                continue
            rows.append(
                {
                    "scan_file": scan_file,
                    "snapshot_timestamp": snap_ts,
                    "ticker": item.get("contract_ticker") or item.get("ticker"),
                    "model_yes_probability": item.get("model_yes_probability")
                    or item.get("model_probability"),
                    "market_yes_probability": item.get("market_yes_probability")
                    or item.get("market_implied_probability"),
                    "recommendation": item.get("recommendation"),
                }
            )
    for item in obj.get("ranked_opportunities") or []:
        if not isinstance(item, dict):
            continue
        rows.append(
            {
                "scan_file": scan_file,
                "snapshot_timestamp": snap_ts,
                "ticker": item.get("ticker"),
                "model_yes_probability": item.get("model_probability"),
                "market_yes_probability": item.get("market_implied_probability"),
                "recommendation": item.get("recommendation"),
            }
        )
    return rows


def load_scan_rows_batched(
    scan_paths: list[Path],
    *,
    batch_size: int = 25,
) -> pd.DataFrame:
    """Load scan JSON in batches so peak memory stays bounded."""
    if batch_size < 1:
        raise ValueError("batch_size must be >= 1")
    frames: list[pd.DataFrame] = []
    paths = list(scan_paths)
    for start in range(0, len(paths), batch_size):
        batch_rows: list[dict[str, Any]] = []
        for path in paths[start : start + batch_size]:
            if not path.exists():
                continue
            try:
                obj = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            if not isinstance(obj, dict):
                continue
            batch_rows.extend(_rows_from_scan_obj(obj, scan_file=str(path)))
            del obj
        if not batch_rows:
            continue
        frame = pd.DataFrame(batch_rows)
        frame["model_yes_probability"] = pd.to_numeric(
            frame["model_yes_probability"], errors="coerce"
        )
        frame = frame.dropna(subset=["ticker", "model_yes_probability"])
        frames.append(frame.reset_index(drop=True))
        del batch_rows
    if not frames:
        return pd.DataFrame()
    out = pd.concat(frames, ignore_index=True)
    del frames
    return out


def apply_outcomes(df: pd.DataFrame, outcomes: dict[str, int | None]) -> pd.DataFrame:
    if df.empty:
        return df.copy()
    out = df.copy()
    out["y_true"] = out["ticker"].map(lambda t: outcomes.get(str(t)))
    return out


def save_labeled_rows(df: pd.DataFrame, cache_dir: Path) -> Path:
    cache_dir = Path(cache_dir)
    cache_dir.mkdir(parents=True, exist_ok=True)
    parquet = labeled_rows_path(cache_dir)
    try:
        df.to_parquet(parquet, index=False)
        return parquet
    except (ImportError, ValueError, OSError):
        jsonl = labeled_rows_jsonl_path(cache_dir)
        df.to_json(jsonl, orient="records", lines=True)
        return jsonl


def load_labeled_rows(cache_dir: Path) -> pd.DataFrame:
    cache_dir = Path(cache_dir)
    parquet = labeled_rows_path(cache_dir)
    if parquet.exists():
        try:
            return pd.read_parquet(parquet)
        except (ImportError, ValueError, OSError):
            pass
    jsonl = labeled_rows_jsonl_path(cache_dir)
    if jsonl.exists():
        return pd.read_json(jsonl, lines=True)
    return pd.DataFrame()


def build_or_update_labeled_table(
    scan_paths: list[Path],
    *,
    cache_dir: Path,
    fetch_outcome: OutcomeFetcher,
    since: datetime | None = None,
    batch_size: int = 25,
) -> dict[str, Any]:
    """Batch-load scans, resolve unique tickers, persist labeled rows + ticker map."""
    cache_dir = Path(cache_dir)
    cache_dir.mkdir(parents=True, exist_ok=True)
    paths = filter_scan_paths(scan_paths, since=since)
    df = load_scan_rows_batched(paths, batch_size=batch_size)
    if df.empty:
        return {
            "success": False,
            "n_scans": len(paths),
            "n_rows": 0,
            "n_labeled": 0,
            "warnings": ["no scan rows found"],
            "cache_dir": str(cache_dir),
        }

    outcomes = resolve_ticker_outcomes(
        df["ticker"].astype(str).tolist(),
        cache_dir=cache_dir,
        fetch_outcome=fetch_outcome,
        persist=True,
    )
    labeled = apply_outcomes(df, outcomes)
    labeled_path = save_labeled_rows(labeled, cache_dir)
    n_labeled = int(labeled["y_true"].notna().sum())
    return {
        "success": True,
        "n_scans": len(paths),
        "n_rows": int(len(labeled)),
        "n_labeled": n_labeled,
        "n_unique_tickers": int(df["ticker"].nunique()),
        "labeled_path": str(labeled_path),
        "ticker_outcomes_path": str(ticker_outcomes_path(cache_dir)),
        "cache_dir": str(cache_dir),
        "since": since.isoformat() if since else None,
        "batch_size": batch_size,
    }


__all__ = [
    "OutcomeFetcher",
    "apply_outcomes",
    "build_or_update_labeled_table",
    "default_cache_dir",
    "filter_scan_paths",
    "labeled_rows_jsonl_path",
    "labeled_rows_path",
    "load_labeled_rows",
    "load_scan_rows_batched",
    "load_ticker_outcomes",
    "parse_scan_stamp",
    "resolve_ticker_outcomes",
    "save_labeled_rows",
    "save_ticker_outcomes",
    "ticker_outcomes_path",
]
