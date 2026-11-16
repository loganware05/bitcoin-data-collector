"""Tests for verified CF BRTI cascade + live settlement label harvest."""

from __future__ import annotations

import base64
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from kalshi_client import (  # noqa: E402
    KalshiClient,
    parse_cf_brti_payload,
    sign_kalshi_request,
)
from kxbtc15m_index_provider import (  # noqa: E402
    counts_as_edge_evidence,
    resolve_index_cascade,
)
from kxbtc15m_live_labels import harvest_settled_labels, market_to_label_row  # noqa: E402


def test_parse_cf_brti_nested_data():
    value, detail = parse_cf_brti_payload(
        {"data": {"payload": {"value": "65123.45"}}}
    )
    assert value == 65123.45
    assert "value" in detail


def test_cascade_prefers_cf_brti_over_spot():
    q = resolve_index_cascade(cf_brti_value=65000.0, spot_proxy=64000.0)
    assert q.source == "cf_benchmarks"
    assert q.value == 65000.0
    assert counts_as_edge_evidence(q.source) is True


def test_cascade_spot_still_not_edge():
    q = resolve_index_cascade(spot_proxy=64000.0)
    assert q.source == "exchange_spot_proxy"
    assert counts_as_edge_evidence(q.source) is False


def test_market_to_label_row_from_finalize():
    row = market_to_label_row(
        {
            "ticker": "KXBTC15M-26NOV161400-00",
            "expiration_value": "64981.95",
            "floor_strike": 64892.94,
            "result": "yes",
            "close_time": "2026-11-16T19:00:00Z",
        }
    )
    assert row is not None
    assert row["settlement_value"] == 64981.95
    assert row["target_price"] == 64892.94
    assert row["outcome_up"] is True
    assert row["label"] == "UP"


def test_sign_kalshi_request_rsa(tmp_path: Path):
    pytest.importorskip("cryptography")
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import rsa

    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    pem = key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.TraditionalOpenSSL,
        encryption_algorithm=serialization.NoEncryption(),
    )
    path = tmp_path / "kalshi.pem"
    path.write_bytes(pem)
    loaded = serialization.load_pem_private_key(pem, password=None)
    sig = sign_kalshi_request(
        loaded,
        timestamp_ms="1700000000000",
        method="GET",
        sign_path="/trade-api/v2/cfbenchmarks/values",
    )
    assert isinstance(sig, str)
    raw = base64.b64decode(sig)
    assert len(raw) > 0


def test_fetch_cf_brti_soft_fails_without_auth(monkeypatch):
    monkeypatch.delenv("KALSHI_API_KEY_ID", raising=False)
    monkeypatch.delenv("KALSHI_PRIVATE_KEY_PATH", raising=False)
    client = KalshiClient()
    value, source, detail = client.fetch_cf_brti()
    assert value is None
    assert source == "unavailable"
    assert "auth" in detail


def test_fetch_cf_brti_mocked_passthrough(monkeypatch, tmp_path: Path):
    pytest.importorskip("cryptography")
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import rsa

    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    pem = key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.TraditionalOpenSSL,
        encryption_algorithm=serialization.NoEncryption(),
    )
    pem_path = tmp_path / "k.pem"
    pem_path.write_bytes(pem)
    monkeypatch.setenv("KALSHI_API_KEY_ID", "test-key-id")
    monkeypatch.setenv("KALSHI_PRIVATE_KEY_PATH", str(pem_path))

    client = KalshiClient()
    assert client.authenticated is True

    def fake_get(path, params=None, *, signed=False):
        assert path == "/cfbenchmarks/values"
        assert signed is True
        assert params == {"id": "BRTI"}
        return {"data": {"payload": {"value": 65555.5}}}

    monkeypatch.setattr(client, "_get", fake_get)
    value, source, detail = client.fetch_cf_brti()
    assert value == 65555.5
    assert source == "cf_benchmarks"
    assert "BRTI" in detail


def test_harvest_settled_labels_mocked():
    class FakeClient:
        def fetch_settled_kxbtc15m_markets(self, *, max_pages: int = 5):
            return [
                {
                    "ticker": "KXBTC15M-AA",
                    "expiration_value": "100.0",
                    "floor_strike": 90.0,
                    "result": "yes",
                },
                {
                    "ticker": "KXBTC15M-AA",  # duplicate
                    "expiration_value": "100.0",
                    "floor_strike": 90.0,
                    "result": "yes",
                },
                {
                    "ticker": "KXBTC15M-BB",
                    "expiration_value": "",
                    "floor_strike": 90.0,
                },
            ]

    rows = harvest_settled_labels(FakeClient(), max_pages=1)  # type: ignore[arg-type]
    assert len(rows) == 1
    assert rows[0]["contract_ticker"] == "KXBTC15M-AA"


def test_labels_shell_syntax():
    import subprocess

    script = ROOT / "scripts" / "verdant" / "kxbtc15m_labels.sh"
    proc = subprocess.run(["bash", "-n", str(script)], capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr
