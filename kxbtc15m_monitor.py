"""High-frequency KXBTC15M monitor loop (paper decisions only).

Default poll interval: 10 seconds. Does not touch paper_buy_no_v1 day clock.
Never places Kalshi orders.
"""

from __future__ import annotations

import argparse
import json
import logging
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from kalshi_client import KalshiClient, NormalizedMarket
from kxbtc15m_decision_engine import Kxbtc15mDecisionConfig, build_decision_report
from kxbtc15m_event_parser import is_kxbtc15m_market
from kxbtc15m_index_provider import (
    SettlementIndexQuote,
    counts_as_edge_evidence,
    resolve_index_cascade,
)

logger = logging.getLogger(__name__)

DEFAULT_POLL_SECONDS = 10.0
MIN_POLL_SECONDS = 5.0
MAX_POLL_SECONDS = 15.0


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _clamp_poll(seconds: float) -> float:
    return max(MIN_POLL_SECONDS, min(MAX_POLL_SECONDS, float(seconds)))


def resolve_settlement_index(
    *,
    explicit: float | None,
    spot_proxy: float | None,
    explicit_source: str | None = None,
    index_file: Path | None = None,
    market_raw: dict[str, Any] | None = None,
    snapshots_dir: Path | None = None,
) -> tuple[float | None, str]:
    """Backward-compatible wrapper with honest provenance.

    Explicit numeric values are NEVER labeled kalshi_api unless explicit_source says so.
    """
    if explicit is not None and explicit_source:
        return explicit, explicit_source
    quote = resolve_index_cascade(
        operator_value=explicit if explicit_source in (None, "operator_supplied") else None,
        index_file=index_file,
        market_raw=market_raw,
        spot_proxy=spot_proxy,
        snapshots_dir=snapshots_dir,
    )
    if explicit is not None and quote.source == "unavailable":
        # Caller passed a number without cascade hit — operator_supplied
        return explicit, "operator_supplied"
    return quote.value, quote.source


def monitor_once(
    client: KalshiClient,
    *,
    output_dir: Path,
    settlement_index: float | None = None,
    settlement_index_source: str | None = None,
    spot_proxy: float | None = None,
    index_file: Path | None = None,
    snapshots_dir: Path | None = None,
    annualized_volatility: float | None = None,
    cfg: Kxbtc15mDecisionConfig | None = None,
) -> list[dict[str, Any]]:
    """Fetch KXBTC15M markets once and write decision ticks."""
    cfg = cfg or Kxbtc15mDecisionConfig()
    output_dir.mkdir(parents=True, exist_ok=True)
    result = client.fetch_kxbtc15m_markets()
    reports: list[dict[str, Any]] = []
    ts = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")

    markets: list[NormalizedMarket] = [m for m in result.markets if is_kxbtc15m_market(m)]
    if not markets and result.markets:
        markets = list(result.markets)

    tick_sources: list[str] = []
    for market in markets:
        index, source = resolve_settlement_index(
            explicit=settlement_index,
            explicit_source=settlement_index_source,
            spot_proxy=spot_proxy,
            index_file=index_file,
            market_raw=market.raw,
            snapshots_dir=snapshots_dir,
        )
        tick_sources.append(source)
        report = build_decision_report(
            market=market,
            settlement_index=index,
            settlement_index_source=source,  # type: ignore[arg-type]
            annualized_volatility=annualized_volatility,
            cfg=cfg,
        )
        report["counts_as_edge_evidence"] = counts_as_edge_evidence(source)
        if result.warnings:
            report["api_warnings"] = list(result.warnings)
        reports.append(report)

    # Aggregate source for tick envelope (first / majority)
    source = tick_sources[0] if tick_sources else "unavailable"
    if settlement_index is not None and settlement_index_source:
        source = settlement_index_source

    out = {
        "timestamp": _now_iso(),
        "series": "KXBTC15M",
        "api_available": result.api_available,
        "warnings": result.warnings,
        "count": len(reports),
        "decisions": reports,
        "approved_for_execution": False,
        "settlement_index_source": source,
        "counts_as_edge_evidence": counts_as_edge_evidence(source),
        "note": "Paper monitor tick only; live money denied; does not advance paper_buy_no_v1 clock.",
    }
    path = output_dir / f"kxbtc15m_tick_{ts}.json"
    path.write_text(json.dumps(out, indent=2) + "\n")
    logger.info("Wrote %s (%d decisions)", path, len(reports))
    return reports


def run_loop(
    *,
    output_dir: Path,
    poll_seconds: float = DEFAULT_POLL_SECONDS,
    max_ticks: int | None = None,
    settlement_index: float | None = None,
    settlement_index_source: str | None = None,
    spot_proxy: float | None = None,
    index_file: Path | None = None,
    snapshots_dir: Path | None = None,
    annualized_volatility: float | None = None,
    client: KalshiClient | None = None,
) -> int:
    poll = _clamp_poll(poll_seconds)
    client = client or KalshiClient()
    ticks = 0
    backoff = poll
    while True:
        try:
            monitor_once(
                client,
                output_dir=output_dir,
                settlement_index=settlement_index,
                settlement_index_source=settlement_index_source,
                spot_proxy=spot_proxy,
                index_file=index_file,
                snapshots_dir=snapshots_dir,
                annualized_volatility=annualized_volatility,
            )
            ticks += 1
            backoff = poll
        except Exception as exc:  # noqa: BLE001
            logger.warning("monitor tick failed: %s; backing off", exc)
            backoff = min(backoff * 1.5, 60.0)
        if max_ticks is not None and ticks >= max_ticks:
            return 0
        time.sleep(backoff)


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--output-dir",
        type=Path,
        default=Path("live_outputs/kxbtc15m"),
        help="Decision tick output directory (separate from hourly_outputs)",
    )
    ap.add_argument("--poll-seconds", type=float, default=DEFAULT_POLL_SECONDS)
    ap.add_argument("--max-ticks", type=int, default=None, help="Stop after N ticks (tests/smoke)")
    ap.add_argument("--once", action="store_true", help="Single tick then exit")
    ap.add_argument("--settlement-index", type=float, default=None)
    ap.add_argument(
        "--settlement-index-source",
        default=None,
        choices=[
            "cf_benchmarks",
            "kalshi_api",
            "exchange_spot_proxy",
            "operator_supplied",
            "file_drop",
            "fixture",
            "unavailable",
        ],
        help="Honest provenance for --settlement-index (default operator_supplied)",
    )
    ap.add_argument("--index-file", type=Path, default=None, help="JSON file drop for index")
    ap.add_argument("--spot-proxy", type=float, default=None, help="Exchange spot used as index proxy")
    ap.add_argument(
        "--snapshots-dir",
        type=Path,
        default=None,
        help="Optional snapshots dir for spot fallback",
    )
    ap.add_argument("--vol", type=float, default=None)
    args = ap.parse_args(argv)

    explicit_source = args.settlement_index_source
    if args.settlement_index is not None and explicit_source is None:
        explicit_source = "operator_supplied"

    kwargs = dict(
        output_dir=args.output_dir,
        settlement_index=args.settlement_index,
        settlement_index_source=explicit_source,
        spot_proxy=args.spot_proxy,
        index_file=args.index_file,
        snapshots_dir=args.snapshots_dir,
        annualized_volatility=args.vol,
    )

    if args.once or args.max_ticks == 1:
        monitor_once(KalshiClient(), **kwargs)
        return 0
    return run_loop(
        poll_seconds=args.poll_seconds,
        max_ticks=args.max_ticks,
        client=KalshiClient(),
        **kwargs,
    )


if __name__ == "__main__":
    raise SystemExit(main())
