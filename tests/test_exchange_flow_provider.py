"""AHF-P03 exchange-flow provider + on-chain signal tests."""

from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path

from exchange_flow_provider import (
    apply_exchange_flow_to_onchain,
    fetch_exchange_flow_file,
    fetch_exchange_flow_glassnode,
    select_exchange_flow_provider,
)
from signal_engine import SignalEngineConfig, compute_onchain_signal


ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "fixtures" / "exchange_flow_btc.json"


class ExchangeFlowProviderTests(unittest.TestCase):
    def test_file_fixture(self) -> None:
        obs = fetch_exchange_flow_file(FIXTURE)
        self.assertEqual(obs.provider, "file")
        self.assertAlmostEqual(obs.exchange_inflow_btc or 0.0, 12500.0)
        self.assertAlmostEqual(obs.exchange_outflow_btc or 0.0, 18420.0)
        self.assertAlmostEqual(obs.exchange_netflow_btc or 0.0, -5920.0)

    def test_apply_to_onchain(self) -> None:
        obs = fetch_exchange_flow_file(FIXTURE)
        data: dict = {}
        apply_exchange_flow_to_onchain(data, obs)
        self.assertEqual(data["exchange_flow_provider"], "file")
        self.assertIsNotNone(data["exchange_netflow_btc"])

    def test_select_off_by_default(self) -> None:
        prev = os.environ.pop("COMPASS_EXCHANGE_FLOW_PROVIDER", None)
        prev_key = os.environ.pop("GLASSNODE_API_KEY", None)
        try:
            self.assertEqual(select_exchange_flow_provider(), "off")
        finally:
            if prev is not None:
                os.environ["COMPASS_EXCHANGE_FLOW_PROVIDER"] = prev
            if prev_key is not None:
                os.environ["GLASSNODE_API_KEY"] = prev_key

    def test_glassnode_injected_http(self) -> None:
        def fake_get(url: str, params: dict[str, str]) -> list:
            self.assertIn("api_key", params)
            if "to_exchanges" in url:
                return [{"t": 1, "v": 100.0}]
            return [{"t": 1, "v": 250.0}]

        obs = fetch_exchange_flow_glassnode(api_key="test-key", http_get=fake_get)
        self.assertEqual(obs.provider, "glassnode")
        self.assertAlmostEqual(obs.exchange_inflow_btc or 0.0, 100.0)
        self.assertAlmostEqual(obs.exchange_outflow_btc or 0.0, 250.0)
        self.assertAlmostEqual(obs.exchange_netflow_btc or 0.0, -150.0)
        self.assertNotIn("test-key", obs.source_path)


class OnchainSignalNetflowTests(unittest.TestCase):
    def test_netflow_outflow_bullish_tilt(self) -> None:
        snap = {
            "on_chain_data": {
                "transaction_count": 300000,
                "hash_rate": 5e20,
                "exchange_netflow_btc": -5000.0,
            }
        }
        sig = compute_onchain_signal(snap, SignalEngineConfig())
        self.assertGreater(sig.value, 0.1)
        self.assertTrue(any("net outflow" in d.lower() for d in sig.drivers))

    def test_missing_flow_still_works(self) -> None:
        snap = {
            "on_chain_data": {
                "transaction_count": 300000,
                "hash_rate": 5e20,
            }
        }
        sig = compute_onchain_signal(snap, SignalEngineConfig())
        self.assertAlmostEqual(sig.value, 0.10)


if __name__ == "__main__":
    unittest.main()
