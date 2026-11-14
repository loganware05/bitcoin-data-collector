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
) -> tuple[float | None, str]:
    if explicit is not None:
        return explicit, "kalshi_api"
    if spot_proxy is not None:
        return spot_proxy, "exchange_spot_proxy"
    return None, "unavailable"


def monitor_once(
    client: KalshiClient,
    *,
    output_dir: Path,
    settlement_index: float | None = None,
    spot_proxy: float | None = None,
    annualized_volatility: float | None = None,
    cfg: Kxbtc15mDecisionConfig | None = None,
) -> list[dict[str, Any]]:
    """Fetch KXBTC15M markets once and write decision ticks."""
    cfg = cfg or Kxbtc15mDecisionConfig()
    output_dir.mkdir(parents=True, exist_ok=True)
    result = client.fetch_kxbtc15m_markets()
    index, source = resolve_settlement_index(explicit=settlement_index, spot_proxy=spot_proxy)
    reports: list[dict[str, Any]] = []
    ts = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")

    markets: list[NormalizedMarket] = [m for m in result.markets if is_kxbtc15m_market(m)]
    if not markets and result.markets:
        markets = list(result.markets)

    for market in markets:
        report = build_decision_report(
            market=market,
            settlement_index=index,
            settlement_index_source=source,  # type: ignore[arg-type]
            annualized_volatility=annualized_volatility,
            cfg=cfg,
        )
        if result.warnings:
            report["api_warnings"] = list(result.warnings)
        reports.append(report)

    out = {
        "timestamp": _now_iso(),
        "series": "KXBTC15M",
        "api_available": result.api_available,
        "warnings": result.warnings,
        "count": len(reports),
        "decisions": reports,
        "approved_for_execution": False,
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
    spot_proxy: float | None = None,
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
                spot_proxy=spot_proxy,
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
    ap.add_argument("--spot-proxy", type=float, default=None, help="Exchange spot used as index proxy")
    ap.add_argument("--vol", type=float, default=None)
    args = ap.parse_args(argv)

    if args.once or args.max_ticks == 1:
        monitor_once(
            KalshiClient(),
            output_dir=args.output_dir,
            settlement_index=args.settlement_index,
            spot_proxy=args.spot_proxy,
            annualized_volatility=args.vol,
        )
        return 0
    return run_loop(
        output_dir=args.output_dir,
        poll_seconds=args.poll_seconds,
        max_ticks=args.max_ticks,
        settlement_index=args.settlement_index,
        spot_proxy=args.spot_proxy,
        annualized_volatility=args.vol,
    )


if __name__ == "__main__":
    raise SystemExit(main())
