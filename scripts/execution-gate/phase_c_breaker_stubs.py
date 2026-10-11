#!/usr/bin/env python3
"""Phase C — risk breaker interfaces + drill harness stubs (PRE-APPROVAL).

Stubs only. Do NOT wire into live Kalshi order paths.
Production breaker behavior requires Captain approval of plan execution-gate-evidence.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Protocol


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


@dataclass
class RiskLimits:
    max_position_contracts: int = 25
    max_gross_exposure_usd: float = 250.0
    daily_loss_cap_usd: float = 50.0
    max_open_markets: int = 5


@dataclass
class PortfolioState:
    position_contracts: int = 0
    gross_exposure_usd: float = 0.0
    day_realized_pnl_usd: float = 0.0
    open_markets: int = 0
    kill_switch_engaged: bool = False


class RiskGate(Protocol):
    name: str

    def check(self, state: PortfolioState, limits: RiskLimits) -> dict[str, Any]:
        ...


@dataclass
class PositionLimitGate:
    name: str = "position_limits"

    def check(self, state: PortfolioState, limits: RiskLimits) -> dict[str, Any]:
        ok = state.position_contracts <= limits.max_position_contracts
        return {"gate": self.name, "ok": ok, "detail": f"pos={state.position_contracts}/{limits.max_position_contracts}"}


@dataclass
class ExposureCapGate:
    name: str = "exposure_caps"

    def check(self, state: PortfolioState, limits: RiskLimits) -> dict[str, Any]:
        ok = state.gross_exposure_usd <= limits.max_gross_exposure_usd
        return {
            "gate": self.name,
            "ok": ok,
            "detail": f"exposure={state.gross_exposure_usd}/{limits.max_gross_exposure_usd}",
        }


@dataclass
class DailyLossCapGate:
    name: str = "daily_loss_cap"

    def check(self, state: PortfolioState, limits: RiskLimits) -> dict[str, Any]:
        ok = state.day_realized_pnl_usd > -abs(limits.daily_loss_cap_usd)
        return {
            "gate": self.name,
            "ok": ok,
            "detail": f"day_pnl={state.day_realized_pnl_usd} cap=-{limits.daily_loss_cap_usd}",
        }


@dataclass
class KillSwitchGate:
    name: str = "kill_switch"

    def check(self, state: PortfolioState, limits: RiskLimits) -> dict[str, Any]:
        ok = not state.kill_switch_engaged
        return {
            "gate": self.name,
            "ok": ok,
            "detail": "engaged" if state.kill_switch_engaged else "clear",
        }


@dataclass
class OpenMarketsGate:
    name: str = "open_markets"

    def check(self, state: PortfolioState, limits: RiskLimits) -> dict[str, Any]:
        ok = state.open_markets <= limits.max_open_markets
        return {
            "gate": self.name,
            "ok": ok,
            "detail": f"open={state.open_markets}/{limits.max_open_markets}",
        }


GATES: list[RiskGate] = [
    PositionLimitGate(),
    ExposureCapGate(),
    DailyLossCapGate(),
    KillSwitchGate(),
    OpenMarketsGate(),
]


def evaluate_gates(state: PortfolioState, limits: RiskLimits) -> dict[str, Any]:
    checks = [g.check(state, limits) for g in GATES]
    return {
        "schema": "bdc.execution_gate.phase_c_breakers.v1",
        "created_at": utc_now(),
        "approved_for_execution": False,
        "production_wired": False,
        "limits": asdict(limits),
        "state": asdict(state),
        "checks": checks,
        "all_clear": all(c["ok"] for c in checks),
        "note": "Stub drill only — not merged into live order path",
    }


def run_drill_suite() -> dict[str, Any]:
    limits = RiskLimits()
    scenarios: list[tuple[str, PortfolioState]] = [
        ("baseline_ok", PortfolioState()),
        ("position_breach", PortfolioState(position_contracts=40)),
        ("exposure_breach", PortfolioState(gross_exposure_usd=500)),
        ("daily_loss_breach", PortfolioState(day_realized_pnl_usd=-75)),
        ("kill_switch", PortfolioState(kill_switch_engaged=True)),
        ("open_markets_breach", PortfolioState(open_markets=9)),
    ]
    results = []
    for name, state in scenarios:
        report = evaluate_gates(state, limits)
        results.append({"scenario": name, "all_clear": report["all_clear"], "checks": report["checks"]})
    expected_trip = {r["scenario"]: (not r["all_clear"]) for r in results if r["scenario"] != "baseline_ok"}
    return {
        "schema": "bdc.execution_gate.phase_c_drill.v1",
        "created_at": utc_now(),
        "approved_for_execution": False,
        "production_wired": False,
        "scenarios": results,
        "drill_pass": results[0]["all_clear"] is True and all(expected_trip.values()),
        "captain_bar": "Gates must fire in drills before kill_switch_and_limits readiness can pass",
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--drill", action="store_true")
    args = ap.parse_args()
    payload = run_drill_suite() if args.drill else evaluate_gates(PortfolioState(), RiskLimits())
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(payload, indent=2) + "\n")
    print("wrote", args.out)
    print("drill_pass" if args.drill else "all_clear", payload.get("drill_pass", payload.get("all_clear")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
