"""DayClock calendar-gap rules for Phase B paper continuity."""

from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts" / "execution-gate"))

from phase_b_paper_loop import DayClock  # noqa: E402


def test_same_day_noop():
    clock = DayClock(consecutive_days=3, started_on="2026-11-10", last_active_day="2026-11-10")
    clock.tick_calendar_day(date(2026, 11, 10))
    assert clock.consecutive_days == 3
    assert clock.last_active_day == "2026-11-10"


def test_next_day_increments():
    clock = DayClock(consecutive_days=3, started_on="2026-11-09", last_active_day="2026-11-09")
    clock.tick_calendar_day(date(2026, 11, 10))
    assert clock.consecutive_days == 4
    assert clock.last_active_day == "2026-11-10"


def test_gap_resets_to_day_one():
    clock = DayClock(
        consecutive_days=12,
        started_on="2026-10-17",
        last_active_day="2026-10-17",
        reset_count=2,
    )
    clock.tick_calendar_day(date(2026, 11, 10))
    assert clock.consecutive_days == 1
    assert clock.last_active_day == "2026-11-10"
    assert clock.started_on == "2026-11-10"
    assert clock.reset_count == 3
    assert clock.last_reset_reason == "calendar_gap_days=24"
