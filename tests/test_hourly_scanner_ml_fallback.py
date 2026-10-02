from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import hourly_event_scanner as scanner
from hourly_event_scanner import HourlyScanConfig, run_hourly_scan
from kalshi_client import FetchResult, NormalizedMarket


def _snapshot_path(repo_root: Path) -> Path:
    return repo_root / "outputs" / "btc_market_intel_20260526T233055Z.json"


def _hourly_market() -> NormalizedMarket:
    close_time = (datetime.now(UTC) + timedelta(hours=2)).isoformat()
    return NormalizedMarket(
        ticker="KXBTCD-26MAY2717-T77000.99",
        title="Bitcoin above $77,000 at 5 PM EDT",
        close_time=close_time,
        yes_bid=0.35,
        yes_ask=0.40,
        no_bid=0.60,
        no_ask=0.65,
        last_price=0.37,
        volume=5000.0,
        open_interest=2000.0,
        implied_probability_mid=0.375,
        liquidity_score=0.7,
        updated_time=datetime.now(UTC).isoformat(),
        event_ticker="KXBTCD-26MAY2717",
        raw={"yes_sub_title": "Bitcoin above $77,000 at 5 PM EDT"},
    )


class _StubKalshiClient:
    def fetch_btc_markets(self) -> FetchResult:
        return FetchResult(markets=[_hourly_market()], warnings=[], api_available=True)

    def fetch_market_orderbook(self, ticker: str) -> dict:
        return {
            "orderbook": {
                "yes": [[35, 100], [34, 50]],
                "no": [[65, 100], [66, 50]],
            }
        }


def test_scan_no_trade_when_ml_unavailable(tmp_path: Path, monkeypatch):
    repo_root = Path(__file__).resolve().parent.parent
    snapshot = json.loads(_snapshot_path(repo_root).read_text(encoding="utf-8"))

    monkeypatch.setattr(scanner, "KalshiClient", _StubKalshiClient)
    monkeypatch.setattr(
        scanner,
        "load_snapshot_json",
        lambda _path: snapshot,
    )

    cfg = HourlyScanConfig(
        snapshot_path=_snapshot_path(repo_root),
        no_collect=True,
        models_base_dir=tmp_path,
        fetch_orderbook=True,
        repo_root=repo_root,
    )

    result = run_hourly_scan(cfg)

    assert result["scan_meta"]["contracts_evaluated"] >= 1
    assert result["model_summary"]["ml_any_available"] is False
    assert result["model_summary"]["horizons_available"] == []

    warnings = result["scan_meta"]["pipeline_warnings"]
    assert any("no_ml_model_for_horizon" in w for w in warnings)

    all_rows = result["ranked"]["all_contracts"]
    assert all_rows
    assert all(row["recommendation"] == "NO TRADE" for row in all_rows)
