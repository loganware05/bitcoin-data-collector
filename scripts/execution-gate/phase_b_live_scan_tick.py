#!/usr/bin/env python3
"""Phase B — one live-forward paper tick from latest Verdant hourly scan.

Real-time (or latest staged) scan IN → conservative simulated fills OUT.
Risk gates from phase_c_breaker_stubs evaluated before accepting a paper fill.
No Kalshi orders. Persists day clock + ledger under evidence/paper/.
"""

from __future__ import annotations

import argparse
import json
import random
import sys
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

from phase_b_paper_loop import ConservativeFillModel, DayClock, PaperMetrics  # noqa: E402
from phase_c_breaker_stubs import PortfolioState, RiskLimits, evaluate_gates  # noqa: E402


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def load_json(path: Path, default: Any) -> Any:
    if not path.is_file():
        return default
    return json.loads(path.read_text())


def latest_scan(hourly_dir: Path) -> Path:
    files = sorted(hourly_dir.glob("scan_*.json"))
    if not files:
        raise SystemExit(f"no scan_*.json in {hourly_dir}")
    return files[-1]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--hourly-outputs",
        type=Path,
        default=Path("/Volumes/Verdant_AI/btc_kalshi/hourly_outputs"),
    )
    ap.add_argument(
        "--state-dir",
        type=Path,
        default=Path(".agent/evidence/execution-gate-evidence/paper"),
    )
    ap.add_argument("--starter-bankroll-usd", type=float, default=250.0)
    ap.add_argument("--qty", type=float, default=5.0)
    ap.add_argument("--seed", type=int, default=None)
    args = ap.parse_args()

    state_dir = args.state_dir
    state_dir.mkdir(parents=True, exist_ok=True)
    clock_path = state_dir / "day_clock.json"
    ledger_path = state_dir / "paper_ledger.jsonl"
    metrics_path = state_dir / "metrics_snapshot.json"
    tick_path = state_dir / f"tick_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}.json"

    clock_raw = load_json(clock_path, {})
    clock = DayClock(
        consecutive_days=int(clock_raw.get("consecutive_days") or 0),
        started_on=clock_raw.get("started_on"),
        last_active_day=clock_raw.get("last_active_day"),
        reset_count=int(clock_raw.get("reset_count") or 0),
        last_reset_reason=clock_raw.get("last_reset_reason"),
    )
    clock.tick_calendar_day()

    scan_path = latest_scan(args.hourly_outputs)
    scan = json.loads(scan_path.read_text())
    ranked = scan.get("ranked") or {}
    candidates = list(ranked.get("buy_yes") or []) + list(ranked.get("buy_no") or [])

    limits = RiskLimits()
    # Load crude portfolio from last metrics if present
    prev = load_json(metrics_path, {})
    portfolio = PortfolioState(
        position_contracts=int(prev.get("position_contracts") or 0),
        gross_exposure_usd=float(prev.get("gross_exposure_usd") or 0.0),
        day_realized_pnl_usd=float(prev.get("day_realized_pnl_usd") or 0.0),
        open_markets=int(prev.get("open_markets") or 0),
        kill_switch_engaged=bool(prev.get("kill_switch_engaged") or False),
    )
    gate_report = evaluate_gates(portfolio, limits)
    gates_ok = bool(gate_report.get("all_clear"))

    rng = random.Random(args.seed)
    model = ConservativeFillModel()
    fills: list[dict[str, Any]] = []
    if gates_ok:
        for row in candidates[:3]:  # cap per tick
            side_rec = str(row.get("recommendation") or "").upper()
            side = "buy" if side_rec == "BUY YES" else "sell"
            yes = float(row.get("market_yes_probability") or 0.5)
            spread = float(row.get("bid_ask_spread") or 0.02)
            bid = max(0.01, yes - spread / 2)
            ask = min(0.99, yes + spread / 2)
            fill = model.simulate(side, bid=bid, ask=ask, qty=args.qty, rng_u=rng.random())
            fill["contract_ticker"] = row.get("contract_ticker")
            fill["recommendation"] = side_rec
            fills.append(fill)
            if fill["filled_qty"]:
                portfolio.position_contracts += int(fill["filled_qty"])
                portfolio.gross_exposure_usd += float(fill["filled_qty"]) * float(fill["fill_price"] or 0)
                portfolio.day_realized_pnl_usd += float(fill.get("pnl_mark") or 0.0)
                portfolio.open_markets += 1
            # Re-check after each fill
            gate_report = evaluate_gates(portfolio, limits)
            if not gate_report.get("all_clear"):
                break
    else:
        fills.append({"mode": "blocked", "reason": "risk_gates_not_clear", "gates": gate_report})

    # Persist ledger lines
    with ledger_path.open("a") as f:
        for fill in fills:
            f.write(
                json.dumps(
                    {
                        "ts": utc_now(),
                        "scan": scan_path.name,
                        "fill": fill,
                        "approved_for_execution": False,
                    }
                )
                + "\n"
            )

    metrics = {
        "schema": "bdc.execution_gate.phase_b_tick.v1",
        "created_at": utc_now(),
        "approved_for_execution": False,
        "mode": "simulated_fills_only",
        "starter_bankroll_usd": args.starter_bankroll_usd,
        "scan": scan_path.name,
        "scan_timestamp": scan.get("timestamp"),
        "btc_price": scan.get("btc_price"),
        "n_candidates": len(candidates),
        "n_fills_attempted": len(fills),
        "day_clock": asdict(clock),
        "position_contracts": portfolio.position_contracts,
        "gross_exposure_usd": portfolio.gross_exposure_usd,
        "day_realized_pnl_usd": portfolio.day_realized_pnl_usd,
        "open_markets": portfolio.open_markets,
        "kill_switch_engaged": portfolio.kill_switch_engaged,
        "gates": gate_report,
        "oos_floor": PaperMetrics(
            calendar_days=clock.consecutive_days,
            closed_trades=0,
        ).oos_floor_status(),
        "30d_complete": clock.consecutive_days >= 30,
        "note": "Live-forward paper tick; PnL marks are optimistic ceiling; not settlement replay edge proof.",
    }
    metrics_path.write_text(json.dumps(metrics, indent=2) + "\n")
    clock_path.write_text(json.dumps(asdict(clock), indent=2) + "\n")
    tick_path.write_text(json.dumps({**metrics, "fills": fills}, indent=2) + "\n")
    print(
        json.dumps(
            {
                "tick": str(tick_path),
                "day": clock.consecutive_days,
                "gates_ok": gates_ok,
                "n_fills": len(fills),
                "approved_for_execution": False,
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
