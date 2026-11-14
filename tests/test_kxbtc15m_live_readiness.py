"""Tests for KXBTC15M live-readiness pipeline helpers (paper-only)."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from kalshi_client import normalize_market  # noqa: E402
from kxbtc15m_decision_engine import decide_from_raw_market  # noqa: E402
from kxbtc15m_settlement_labels import join_fixture_labels  # noqa: E402

FIX = ROOT / "tests" / "fixtures" / "kxbtc15m"


def test_counts_as_edge_evidence_by_source(monkeypatch):
    pack = json.loads((FIX / "market_pack.json").read_text())
    now = datetime(2026, 11, 14, 15, 20, tzinfo=UTC)
    proxy = decide_from_raw_market(
        pack["markets"][0],
        settlement_index=65620.0,
        settlement_index_source="exchange_spot_proxy",
        model_probability_up_override=0.7,
        now=now,
    )
    assert proxy["counts_as_edge_evidence"] is False

    monkeypatch.delenv("COMPASS_KXBTC15M_ALLOW_FIXTURE_EDGE", raising=False)
    fixture = decide_from_raw_market(
        pack["markets"][0],
        settlement_index=65620.0,
        settlement_index_source="fixture",
        model_probability_up_override=0.7,
        now=now,
    )
    assert fixture["counts_as_edge_evidence"] is False

    live = decide_from_raw_market(
        pack["markets"][0],
        settlement_index=65620.0,
        settlement_index_source="kalshi_api",
        model_probability_up_override=0.7,
        now=now,
    )
    assert live["counts_as_edge_evidence"] is True


def test_daily_wrapper_soft_skip(tmp_path: Path):
    env = os.environ.copy()
    env["KXBTC15M_PAPER_STATE_DIR"] = str(tmp_path / "paper-kxbtc15m")
    env["KXBTC15M_DECISION_DIR"] = str(tmp_path / "empty_decisions")
    env["BTC_KALSHI_REMOTE_ROOT"] = str(tmp_path / "remote")
    env["BTC_KALSHI_LOCAL_ROOT"] = str(tmp_path / "local")
    (tmp_path / "empty_decisions").mkdir()
    script = ROOT / "scripts" / "execution-gate" / "paper_tick_kxbtc15m_daily.sh"
    proc = subprocess.run(
        ["bash", str(script)],
        cwd=str(ROOT),
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr
    alert = tmp_path / "paper-kxbtc15m" / "continuity_alert.json"
    assert alert.is_file()
    payload = json.loads(alert.read_text())
    assert payload["day_clock_advanced"] is False
    assert payload["approved_for_execution"] is False


def test_daily_wrapper_refuses_shared_paper_dir(tmp_path: Path):
    env = os.environ.copy()
    env["KXBTC15M_PAPER_STATE_DIR"] = str(tmp_path / "paper")
    script = ROOT / "scripts" / "execution-gate" / "paper_tick_kxbtc15m_daily.sh"
    proc = subprocess.run(
        ["bash", str(script)],
        cwd=str(ROOT),
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 2


def test_settlement_label_join_from_fixture():
    labels = json.loads((FIX / "settlement_labels.json").read_text())["rows"]
    decisions = [
        {
            "contract_ticker": labels[0]["contract_ticker"],
            "target_price": labels[0]["target_price"],
            "model_probability_up": 0.55,
            "recommendation": "BUY YES",
            "settlement_index_source": "fixture",
            "counts_as_edge_evidence": True,
            "timestamp": labels[0]["timestamp"],
        }
    ]
    joined = join_fixture_labels(decisions, labels)
    assert len(joined) == 1
    assert "outcome_up" in joined[0]


def test_ensure_jobs_lists_new_labels():
    text = (ROOT / "scripts" / "verdant" / "ensure_verdant_jobs.sh").read_text()
    assert "com.verdant.btc-kalshi.kxbtc15m-monitor" in text
    assert "com.verdant.btc-kalshi.kxbtc15m-paper-tick" in text
    assert (ROOT / "scripts" / "verdant" / "launchd" / "com.verdant.btc-kalshi.kxbtc15m-monitor.plist").is_file()
    assert (ROOT / "scripts" / "verdant" / "launchd" / "com.verdant.btc-kalshi.kxbtc15m-paper-tick.plist").is_file()
