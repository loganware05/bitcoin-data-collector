from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd

from kalshi_settlement_eval import (
    SettlementEvalConfig,
    evaluate_from_cache,
    fit_from_cache,
    main as settlement_main,
)
from settlement_label_store import (
    apply_outcomes,
    build_or_update_labeled_table,
    filter_scan_paths,
    load_labeled_rows,
    load_scan_rows_batched,
    resolve_ticker_outcomes,
    save_labeled_rows,
)


def _write_scan(path: Path, *, stamp: str, rows: list[dict]) -> None:
    buy_yes = [r for r in rows if r["recommendation"] == "BUY YES"]
    buy_no = [r for r in rows if r["recommendation"] == "BUY NO"]
    no_trade = [r for r in rows if r["recommendation"] == "NO TRADE"]
    payload = {
        "timestamp": stamp,
        "ranked": {
            "buy_yes": buy_yes,
            "buy_no": buy_no,
            "no_trade": no_trade,
        },
    }
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_filter_scan_paths_since(tmp_path: Path) -> None:
    early = tmp_path / "scan_20260820T010000Z.json"
    late = tmp_path / "scan_20260828T120000Z.json"
    early.write_text("{}", encoding="utf-8")
    late.write_text("{}", encoding="utf-8")
    kept = filter_scan_paths(
        [early, late],
        since=datetime(2026, 8, 28, tzinfo=UTC),
    )
    assert kept == [late]


def test_unique_ticker_outcome_resolution(tmp_path: Path) -> None:
    calls: list[str] = []

    def fetch(ticker: str) -> int | None:
        calls.append(ticker)
        return 1 if ticker.endswith("YES") else 0

    outcomes = resolve_ticker_outcomes(
        ["AAA-YES", "AAA-YES", "BBB-NO", "AAA-YES"],
        cache_dir=tmp_path,
        fetch_outcome=fetch,
        persist=True,
    )
    assert outcomes["AAA-YES"] == 1
    assert outcomes["BBB-NO"] == 0
    assert calls == ["AAA-YES", "BBB-NO"]

    calls.clear()
    again = resolve_ticker_outcomes(
        ["AAA-YES", "BBB-NO"],
        cache_dir=tmp_path,
        fetch_outcome=fetch,
        persist=True,
    )
    assert again == outcomes
    assert calls == []


def test_batched_scan_load_and_cache_roundtrip(tmp_path: Path) -> None:
    scan_dir = tmp_path / "scans"
    scan_dir.mkdir()
    rows_a = [
        {
            "contract_ticker": "T1",
            "model_yes_probability": 0.2,
            "recommendation": "BUY NO",
        },
        {
            "contract_ticker": "T2",
            "model_yes_probability": 0.8,
            "recommendation": "BUY YES",
        },
    ]
    rows_b = [
        {
            "contract_ticker": "T1",
            "model_yes_probability": 0.25,
            "recommendation": "NO TRADE",
        }
    ]
    _write_scan(scan_dir / "scan_20260828T010000Z.json", stamp="2026-08-28T01:00:00Z", rows=rows_a)
    _write_scan(scan_dir / "scan_20260829T010000Z.json", stamp="2026-08-29T01:00:00Z", rows=rows_b)

    df = load_scan_rows_batched(sorted(scan_dir.glob("scan_*.json")), batch_size=1)
    assert len(df) == 3
    assert set(df["ticker"]) == {"T1", "T2"}

    cache_dir = tmp_path / "cache"
    meta = build_or_update_labeled_table(
        sorted(scan_dir.glob("scan_*.json")),
        cache_dir=cache_dir,
        fetch_outcome=lambda t: 1 if t == "T2" else 0,
        batch_size=1,
    )
    assert meta["success"] is True
    assert meta["n_unique_tickers"] == 2
    labeled = load_labeled_rows(cache_dir)
    assert len(labeled) == 3
    assert labeled["y_true"].notna().all()


def test_eval_and_fit_modes_are_separate(tmp_path: Path) -> None:
    cache_dir = tmp_path / "cache"
    models_dir = tmp_path / "models"
    labeled = pd.DataFrame(
        {
            "ticker": [f"T{i}" for i in range(40)],
            "model_yes_probability": [0.2 + (i % 5) * 0.1 for i in range(40)],
            "y_true": [0, 1] * 20,
            "recommendation": (["BUY NO", "BUY YES", "NO TRADE", "BUY YES"] * 10),
        }
    )
    save_labeled_rows(labeled, cache_dir)

    eval_out = evaluate_from_cache(
        cache_dir,
        cfg=SettlementEvalConfig(min_samples=10),
        report_out=tmp_path / "report.json",
    )
    assert eval_out["mode"] == "eval"
    assert eval_out["n"] == 40
    assert "manifest" not in eval_out
    assert Path(eval_out["report_path"]).exists()

    fit_out = fit_from_cache(cache_dir, models_dir)
    assert fit_out["success"] is True
    assert fit_out["mode"] == "fit"
    assert Path(fit_out["manifest"]).exists()


def test_cli_fit_does_not_require_eval_scan_reload(tmp_path: Path) -> None:
    cache_dir = tmp_path / "cache"
    models_dir = tmp_path / "models"
    labeled = pd.DataFrame(
        {
            "ticker": [f"T{i}" for i in range(40)],
            "model_yes_probability": [0.15 + (i % 6) * 0.1 for i in range(40)],
            "y_true": [i % 2 for i in range(40)],
            "recommendation": ["BUY YES" if i % 2 == 0 else "BUY NO" for i in range(40)],
        }
    )
    save_labeled_rows(labeled, cache_dir)

    rc = settlement_main(
        [
            "--mode",
            "fit",
            "--cache-dir",
            str(cache_dir),
            "--models-base-dir",
            str(models_dir),
        ]
    )
    assert rc == 0
    assert (models_dir / "calibration" / "manifest.json").exists()


def test_apply_outcomes_maps_tickers() -> None:
    df = pd.DataFrame({"ticker": ["A", "B", "A"], "model_yes_probability": [0.1, 0.2, 0.3]})
    out = apply_outcomes(df, {"A": 1, "B": 0})
    assert out["y_true"].tolist() == [1, 0, 1]
