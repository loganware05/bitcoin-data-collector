"""BTC exchange inflow/outflow provider (AHF-P03).

Providers:
- ``file`` / ``fixture`` — hermetic JSON fixture (default when explicitly selected)
- ``glassnode`` — optional live Glassnode metrics when ``GLASSNODE_API_KEY`` is set
- ``off`` / unset — return empty observation (collector keeps None stubs)

Never logs or persists API keys. Fail soft on network errors.
"""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

DEFAULT_FIXTURE = (
    Path(__file__).resolve().parent / "fixtures" / "exchange_flow_btc.json"
)


@dataclass(frozen=True)
class ExchangeFlowObservation:
    exchange_inflow_btc: float | None
    exchange_outflow_btc: float | None
    exchange_netflow_btc: float | None
    provider: str
    freshness_seconds: float | None
    as_of: str
    coverage: float
    source_path: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def select_exchange_flow_provider() -> str:
    raw = os.environ.get("COMPASS_EXCHANGE_FLOW_PROVIDER", "").strip().lower()
    if raw in {"file", "fixture", "glassnode", "off", "none", "stub"}:
        return "off" if raw in {"none", "stub"} else raw
    # Auto: use glassnode when key present, else off (preserve historical None stubs).
    if os.environ.get("GLASSNODE_API_KEY", "").strip():
        return "glassnode"
    return "off"


def _from_payload(payload: Mapping[str, Any], *, provider: str, source_path: str = "") -> ExchangeFlowObservation:
    inflow = payload.get("exchange_inflow_btc")
    outflow = payload.get("exchange_outflow_btc")
    try:
        inflow_f = float(inflow) if inflow is not None else None
    except (TypeError, ValueError):
        inflow_f = None
    try:
        outflow_f = float(outflow) if outflow is not None else None
    except (TypeError, ValueError):
        outflow_f = None
    netflow = payload.get("exchange_netflow_btc")
    if netflow is None and inflow_f is not None and outflow_f is not None:
        netflow_f = inflow_f - outflow_f
    else:
        try:
            netflow_f = float(netflow) if netflow is not None else None
        except (TypeError, ValueError):
            netflow_f = None
    freshness = payload.get("freshness_seconds")
    try:
        freshness_f = float(freshness) if freshness is not None else None
    except (TypeError, ValueError):
        freshness_f = None
    coverage = payload.get("coverage")
    try:
        coverage_f = float(coverage) if coverage is not None else (
            1.0 if inflow_f is not None and outflow_f is not None else 0.0
        )
    except (TypeError, ValueError):
        coverage_f = 0.0
    return ExchangeFlowObservation(
        exchange_inflow_btc=inflow_f,
        exchange_outflow_btc=outflow_f,
        exchange_netflow_btc=netflow_f,
        provider=provider,
        freshness_seconds=freshness_f,
        as_of=str(payload.get("as_of") or _utc_now()),
        coverage=coverage_f,
        source_path=source_path,
    )


def fetch_exchange_flow_file(path: Path | None = None) -> ExchangeFlowObservation:
    fixture = Path(path) if path else Path(
        os.environ.get("COMPASS_EXCHANGE_FLOW_FIXTURE", "").strip() or DEFAULT_FIXTURE
    )
    with fixture.open(encoding="utf-8") as handle:
        payload = json.load(handle)
    if not isinstance(payload, dict):
        raise ValueError("exchange flow fixture must be a JSON object")
    return _from_payload(payload, provider="file", source_path=str(fixture))


def fetch_exchange_flow_glassnode(
    *,
    api_key: str | None = None,
    http_get: Any | None = None,
    base_url: str = "https://api.glassnode.com",
    asset: str = "BTC",
) -> ExchangeFlowObservation:
    """Fetch 24h exchange inflow/outflow from Glassnode (Captain-local key).

    Uses metrics:
    - ``transactions/transfers_volume_to_exchanges_sum``
    - ``transactions/transfers_volume_from_exchanges_sum``
    """
    key = (api_key if api_key is not None else os.environ.get("GLASSNODE_API_KEY", "")).strip()
    if not key:
        raise ValueError("GLASSNODE_API_KEY required for glassnode exchange-flow provider")

    def _default_get(url: str, params: dict[str, str]) -> list[Any]:
        import urllib.parse
        import urllib.request

        query = urllib.parse.urlencode(params)
        req = urllib.request.Request(
            f"{url}?{query}",
            headers={"Accept": "application/json"},
            method="GET",
        )
        with urllib.request.urlopen(req, timeout=20) as resp:  # noqa: S310 — allowlisted HTTPS base
            raw = resp.read().decode("utf-8")
        data = json.loads(raw)
        if not isinstance(data, list):
            raise ValueError("glassnode response must be a list")
        return data

    getter = http_get or _default_get
    params = {"a": asset, "api_key": key, "i": "24h", "s": "0"}
    # Avoid embedding key in source_path / logs.
    safe_source = f"{base_url}/v1/metrics/transactions/transfers_volume_*_exchanges_sum"
    inflow_rows = getter(
        f"{base_url}/v1/metrics/transactions/transfers_volume_to_exchanges_sum",
        params,
    )
    outflow_rows = getter(
        f"{base_url}/v1/metrics/transactions/transfers_volume_from_exchanges_sum",
        params,
    )

    def _last_v(rows: list[Any]) -> float | None:
        if not rows:
            return None
        row = rows[-1]
        if isinstance(row, dict) and row.get("v") is not None:
            return float(row["v"])
        return None

    inflow = _last_v(inflow_rows)
    outflow = _last_v(outflow_rows)
    return _from_payload(
        {
            "exchange_inflow_btc": inflow,
            "exchange_outflow_btc": outflow,
            "freshness_seconds": 0,
            "coverage": 1.0 if inflow is not None and outflow is not None else 0.5,
            "as_of": _utc_now(),
        },
        provider="glassnode",
        source_path=safe_source,
    )


def fetch_exchange_flow() -> ExchangeFlowObservation | None:
    """Resolve provider from env and fetch; return None when off/unavailable."""
    name = select_exchange_flow_provider()
    if name in {"off"}:
        return None
    try:
        if name in {"file", "fixture"}:
            return fetch_exchange_flow_file()
        if name == "glassnode":
            return fetch_exchange_flow_glassnode()
    except (OSError, ValueError, json.JSONDecodeError, TimeoutError) as exc:
        # Fail soft — collector keeps None stubs and can record warning separately.
        del exc
        return None
    return None


def apply_exchange_flow_to_onchain(
    on_chain_data: dict[str, Any],
    observation: ExchangeFlowObservation | None,
) -> dict[str, Any]:
    """Mutate and return on_chain_data with exchange-flow fields + provenance."""
    if observation is None:
        on_chain_data.setdefault(
            "whale_movement_note",
            "Exchange flows unavailable (set COMPASS_EXCHANGE_FLOW_PROVIDER=file "
            "or GLASSNODE_API_KEY for glassnode).",
        )
        return on_chain_data
    on_chain_data["exchange_inflow_btc"] = observation.exchange_inflow_btc
    on_chain_data["exchange_outflow_btc"] = observation.exchange_outflow_btc
    on_chain_data["exchange_netflow_btc"] = observation.exchange_netflow_btc
    on_chain_data["exchange_flow_provider"] = observation.provider
    on_chain_data["exchange_flow_freshness_seconds"] = observation.freshness_seconds
    on_chain_data["exchange_flow_coverage"] = observation.coverage
    on_chain_data["exchange_flow_as_of"] = observation.as_of
    on_chain_data["exchange_flow_source"] = observation.source_path
    on_chain_data["whale_movement_note"] = (
        f"Exchange netflow via {observation.provider} "
        f"(net={observation.exchange_netflow_btc})."
    )
    return on_chain_data
