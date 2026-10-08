#!/usr/bin/env python3
"""Phase B — live-forward paper loop design harness (simulated fills only).

Real-time market data IN → conservative simulated fills OUT.
No real money. No Kalshi live orders. Day clock + reset rule encoded.

Does NOT claim a 30-day track record. Emits schema + optional dry-run tick.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Literal


FillMode = Literal["cross_spread", "partial", "no_fill"]


@dataclass
class DayClock:
    consecutive_days: int = 0
    started_on: str | None = None
    last_active_day: str | None = None
    reset_count: int = 0
    last_reset_reason: str | None = None

    def note_manual_override(self, reason: str) -> None:
        """Any manual override resets the day clock to 0 (Captain bar)."""
        self.consecutive_days = 0
        self.started_on = None
        self.last_active_day = None
        self.reset_count += 1
        self.last_reset_reason = reason

    def tick_calendar_day(self, today: date | None = None) -> None:
        today = today or datetime.now(timezone.utc).date()
        iso = today.isoformat()
        if self.last_active_day is None:
            self.started_on = iso
            self.last_active_day = iso
            self.consecutive_days = 1
            return
        last = date.fromisoformat(self.last_active_day)
        delta = (today - last).days
        if delta == 0:
            return
        if delta == 1:
            self.consecutive_days += 1
            self.last_active_day = iso
            return
        # Gap in continuous live paper → reset
        self.note_manual_override(f"calendar_gap_days={delta}")
        self.started_on = iso
        self.last_active_day = iso
        self.consecutive_days = 1


@dataclass
class ConservativeFillModel:
    """Optimistic-ceiling paper PnL: cross spread, fees, slippage, partial/no-fill."""

    fee_bps: float = 7.0
    slippage_bps: float = 5.0
    partial_fill_prob: float = 0.25
    no_fill_prob: float = 0.10
    partial_fill_frac: float = 0.5

    def simulate(
        self,
        side: Literal["buy", "sell"],
        bid: float,
        ask: float,
        qty: float,
        rng_u: float,
    ) -> dict[str, Any]:
        mid = (bid + ask) / 2.0
        spread = max(ask - bid, 0.0)
        if rng_u < self.no_fill_prob:
            return {
                "mode": "no_fill",
                "filled_qty": 0.0,
                "fill_price": None,
                "fees": 0.0,
                "slippage": 0.0,
                "pnl_mark": 0.0,
                "note": "conservative no-fill",
            }
        filled = qty
        mode: FillMode = "cross_spread"
        if rng_u < self.no_fill_prob + self.partial_fill_prob:
            filled = qty * self.partial_fill_frac
            mode = "partial"
        # Cross the spread (buy at ask, sell at bid)
        px = ask if side == "buy" else bid
        notional = filled * px
        fees = notional * (self.fee_bps / 10_000.0)
        slip = notional * (self.slippage_bps / 10_000.0)
        # Mark to mid immediately → adverse selection vs mid
        mark = filled * (mid - px) if side == "buy" else filled * (px - mid)
        pnl = mark - fees - slip
        return {
            "mode": mode,
            "filled_qty": filled,
            "fill_price": px,
            "mid": mid,
            "spread": spread,
            "fees": fees,
            "slippage": slip,
            "pnl_mark": pnl,
            "note": "paper PnL is optimistic ceiling after fees+slip; still not live edge",
        }


@dataclass
class PaperMetrics:
    closed_trades: int = 0
    total_return_pct: float = 0.0
    max_drawdown_pct: float = 0.0
    paper_sharpe_per_trade: float = 0.0
    profit_factor: float = 0.0
    calendar_days: int = 0
    regimes_spanned: list[str] = field(default_factory=list)

    def oos_floor_status(self) -> dict[str, Any]:
        """Phase B OOS floor (paper). Later live floor profit_factor >= 1.5."""
        checks = {
            "days_ge_14": self.calendar_days >= 14,
            "trades_ge_50": self.closed_trades >= 50,
            "total_return_gt_0": self.total_return_pct > 0.0,
            "max_dd_lt_15": self.max_drawdown_pct < 15.0,
            "paper_sharpe_ge_1": self.paper_sharpe_per_trade >= 1.0,
            "profit_factor_ge_1_2": self.profit_factor >= 1.2,
        }
        return {
            "target_days_30": False,  # never claim 30d complete from this harness alone
            "oos_floor_checks": checks,
            "oos_floor_pass": all(checks.values()),
            "live_floor_profit_factor_later": 1.5,
        }


def emit_schema() -> dict[str, Any]:
    clock = DayClock()
    metrics = PaperMetrics()
    return {
        "schema": "bdc.execution_gate.phase_b_paper.v1",
        "approved_for_execution": False,
        "mode": "simulated_fills_only",
        "feed": "real_time_market_data_in",
        "fills": "conservative_simulated_out",
        "day_clock": asdict(clock),
        "fill_model": asdict(ConservativeFillModel()),
        "metrics": asdict(metrics),
        "oos_floor": metrics.oos_floor_status(),
        "rules": [
            "Continuous live paper (not settlement replay) is the edge path.",
            "Any manual override resets day clock to 0.",
            "30 calendar days required before paper track_record gate can pass.",
            "Disposable/reduced starter bankroll; span multiple regimes.",
            "Do not claim 30d complete until day_clock.consecutive_days >= 30.",
        ],
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--dry-run-tick", action="store_true")
    args = ap.parse_args()
    payload = emit_schema()
    if args.dry_run_tick:
        clock = DayClock()
        clock.tick_calendar_day()
        model = ConservativeFillModel()
        fill = model.simulate("buy", bid=0.42, ask=0.48, qty=10.0, rng_u=0.30)
        payload["dry_run"] = {"day_clock": asdict(clock), "sample_fill": fill}
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(payload, indent=2) + "\n")
    print("wrote", args.out)
    print("30d_complete", False)
    print("approved_for_execution", False)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
