#!/usr/bin/env python3
"""Paper tick for paper_kxbtc15m_v1 from KXBTC15M decision outputs.

Uses a separate state directory from paper_buy_no_v1. Never places orders.
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


def latest_tick(decision_dir: Path) -> Path:
    files = sorted(decision_dir.glob("kxbtc15m_tick_*.json"))
    if not files:
        raise SystemExit(f"no kxbtc15m_tick_*.json in {decision_dir}")
    return files[-1]


def passes_strategy(row: dict[str, Any], filters: dict[str, Any]) -> bool:
    side = str(row.get("recommendation") or "").upper().strip()
    sides = {str(s).upper() for s in (filters.get("sides") or [])}
    if not sides or side not in sides:
        return False
    conf = float(row.get("confidence") or 0.0)
    edge = float(row.get("net_edge") or 0.0)
    spread = float(row.get("bid_ask_spread") or 0.0)
    liq = float(row.get("liquidity_score") or 0.0)
    tte = float(row.get("time_remaining_seconds") or 0.0)
    ask = row.get("yes_ask") if side == "BUY YES" else row.get("no_ask")
    ask_f = float(ask) if ask is not None else 1.0
    return (
        conf >= float(filters.get("min_confidence") or 0.0)
        and edge >= float(filters.get("min_edge") or 0.0)
        and spread <= float(filters.get("max_spread") or 1.0)
        and liq >= float(filters.get("min_liquidity_score") or 0.0)
        and float(filters.get("min_tte_seconds") or 0.0)
        <= tte
        <= float(filters.get("max_tte_seconds") or 1e9)
        and ask_f <= float(filters.get("max_fill_price") or 1.0)
    )


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--decision-dir", type=Path, default=Path("live_outputs/kxbtc15m"))
    ap.add_argument(
        "--state-dir",
        type=Path,
        default=Path(".agent/evidence/execution-gate-evidence/paper-kxbtc15m"),
    )
    ap.add_argument(
        "--strategy",
        type=Path,
        default=_HERE / "paper_strategy_kxbtc15m_v1.json",
    )
    ap.add_argument("--qty", type=float, default=5.0)
    ap.add_argument("--seed", type=int, default=None)
    args = ap.parse_args()

    strategy = load_json(args.strategy, {})
    if strategy.get("approved_for_execution") is True:
        raise SystemExit("refusing strategy with approved_for_execution=true")
    strategy_id = str(strategy.get("strategy_id") or "paper_kxbtc15m_v1")
    if strategy_id == "paper_buy_no_v1":
        raise SystemExit("refusing to run kxbtc15m tick against paper_buy_no_v1")

    filters = strategy.get("filters") or {}
    state_dir = args.state_dir
    # Hard separation from hourly paper clock
    if state_dir.resolve().name == "paper":
        raise SystemExit(
            "refusing shared paper/ state dir; use paper-kxbtc15m (or other) to protect paper_buy_no_v1"
        )
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
    active_strategy = str(clock_raw.get("strategy_id") or "")
    if active_strategy and active_strategy != strategy_id:
        clock.note_manual_override(f"strategy_change:{active_strategy}->{strategy_id}")
    elif strategy_id and not active_strategy:
        clock.note_manual_override(f"strategy_adopt:{strategy_id}")
    clock.tick_calendar_day()

    tick_file = latest_tick(args.decision_dir)
    payload = load_json(tick_file, {})
    decisions = list(payload.get("decisions") or [])
    candidates = [d for d in decisions if passes_strategy(d, filters)]

    prev = load_json(metrics_path, {})
    portfolio = PortfolioState(
        position_contracts=int(prev.get("position_contracts") or 0),
        gross_exposure_usd=float(prev.get("gross_exposure_usd") or 0.0),
        day_realized_pnl_usd=float(prev.get("day_realized_pnl_usd") or 0.0),
        open_markets=int(prev.get("open_markets") or 0),
        kill_switch_engaged=bool(prev.get("kill_switch_engaged") or False),
    )
    gate_report = evaluate_gates(portfolio, RiskLimits())
    gates_ok = bool(gate_report.get("all_clear"))

    rng = random.Random(args.seed)
    model = ConservativeFillModel()
    fills: list[dict[str, Any]] = []
    if gates_ok:
        for row in candidates[:3]:
            side_rec = str(row.get("recommendation") or "").upper()
            side = "buy" if side_rec == "BUY YES" else "sell"
            yes = float(row.get("yes_ask") or row.get("model_probability_up") or 0.5)
            spread = float(row.get("bid_ask_spread") or 0.02)
            bid = max(0.01, yes - spread / 2)
            ask = min(0.99, yes + spread / 2)
            fill = model.simulate(side, bid=bid, ask=ask, qty=args.qty, rng_u=rng.random())
            fill["contract_ticker"] = row.get("contract_ticker")
            fill["recommendation"] = side_rec
            fills.append(fill)
            if fill["filled_qty"]:
                portfolio.position_contracts += int(fill["filled_qty"])
                portfolio.gross_exposure_usd += float(fill["filled_qty"]) * float(
                    fill["fill_price"] or 0
                )
                portfolio.day_realized_pnl_usd += float(fill.get("pnl_mark") or 0.0)
                portfolio.open_markets += 1
            gate_report = evaluate_gates(portfolio, RiskLimits())
            if not gate_report.get("all_clear"):
                break
    else:
        fills.append({"mode": "blocked", "reason": "risk_gates_not_clear", "gates": gate_report})

    with ledger_path.open("a") as f:
        for fill in fills:
            f.write(
                json.dumps(
                    {
                        "ts": utc_now(),
                        "source_tick": tick_file.name,
                        "strategy_id": strategy_id,
                        "fill": fill,
                        "approved_for_execution": False,
                    }
                )
                + "\n"
            )

    metrics = {
        "schema": "bdc.execution_gate.phase_b_kxbtc15m_tick.v1",
        "created_at": utc_now(),
        "approved_for_execution": False,
        "strategy_id": strategy_id,
        "source_tick": str(tick_file),
        "n_decisions": len(decisions),
        "n_candidates": len(candidates),
        "n_fills_attempted": len(fills),
        "filters": filters,
        "day_clock": asdict(clock),
        "position_contracts": portfolio.position_contracts,
        "gross_exposure_usd": portfolio.gross_exposure_usd,
        "day_realized_pnl_usd": portfolio.day_realized_pnl_usd,
        "open_markets": portfolio.open_markets,
        "kill_switch_engaged": portfolio.kill_switch_engaged,
        "gates": gate_report,
        "oos_floor": PaperMetrics(calendar_days=clock.consecutive_days).oos_floor_status(),
        "30d_complete": clock.consecutive_days >= 30,
        "note": "paper_kxbtc15m_v1 tick; live denied; separate from paper_buy_no_v1",
    }
    metrics_path.write_text(json.dumps(metrics, indent=2) + "\n")
    clock_path.write_text(
        json.dumps({**asdict(clock), "strategy_id": strategy_id}, indent=2) + "\n"
    )
    tick_path.write_text(json.dumps({**metrics, "fills": fills}, indent=2) + "\n")
    print(
        json.dumps(
            {
                "tick": str(tick_path),
                "strategy_id": strategy_id,
                "day": clock.consecutive_days,
                "gates_ok": gates_ok,
                "n_candidates": len(candidates),
                "approved_for_execution": False,
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
