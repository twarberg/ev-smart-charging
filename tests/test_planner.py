"""Tests for the pure planner. No HA dependency."""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from custom_components.smart_ev_charging.planner import (
    PlanInput,
    PriceSlot,
    make_plan,
)

CPH = ZoneInfo("Europe/Copenhagen")
FIXTURES = Path(__file__).parent / "fixtures"


def _load_prices() -> list[PriceSlot]:
    raw = json.loads((FIXTURES / "prices_24h.json").read_text())
    return [
        PriceSlot(
            start=datetime.fromisoformat(p["start"]),
            end=datetime.fromisoformat(p["end"]),
            price=p["price"],
        )
        for p in raw
    ]


@pytest.fixture
def prices() -> list[PriceSlot]:
    return _load_prices()


def test_picks_three_cheapest_overnight(prices: list[PriceSlot]) -> None:
    inp = PlanInput(
        prices=prices,
        slots_needed=3,
        departure=datetime(2026, 5, 11, 8, 0, tzinfo=CPH),
        now=datetime(2026, 5, 10, 18, 0, tzinfo=CPH),
    )
    plan = make_plan(inp)
    assert plan.status == "ok"
    assert len(plan.selected_starts) == 3
    expected = {
        datetime(2026, 5, 11, 2, 0, tzinfo=CPH),
        datetime(2026, 5, 11, 3, 0, tzinfo=CPH),
        datetime(2026, 5, 11, 4, 0, tzinfo=CPH),
    }
    assert set(plan.selected_starts) == expected
    assert list(plan.selected_starts) == sorted(plan.selected_starts)
    assert plan.was_extended is False
    assert plan.deadline == datetime(2026, 5, 11, 8, 0, tzinfo=CPH)
    assert plan.initial_deadline == plan.deadline
    assert plan.window_size == 14


def test_no_data_when_prices_empty() -> None:
    plan = make_plan(
        PlanInput(
            prices=[],
            slots_needed=3,
            departure=datetime(2026, 5, 11, 8, 0, tzinfo=CPH),
            now=datetime(2026, 5, 10, 18, 0, tzinfo=CPH),
        )
    )
    assert plan.status == "no_data"
    assert plan.selected_starts == ()
    assert plan.window_size == 0


def test_partial_when_window_smaller_than_slots(prices: list[PriceSlot]) -> None:
    inp = PlanInput(
        prices=prices,
        slots_needed=10,
        departure=datetime(2026, 5, 10, 22, 0, tzinfo=CPH),
        now=datetime(2026, 5, 10, 19, 0, tzinfo=CPH),
    )
    plan = make_plan(inp)
    assert plan.status == "partial"
    assert plan.window_size == 3
    assert len(plan.selected_starts) == 3


def test_extended_when_departure_within_one_hour(prices: list[PriceSlot]) -> None:
    inp = PlanInput(
        prices=prices,
        slots_needed=3,
        departure=datetime(2026, 5, 10, 18, 30, tzinfo=CPH),
        now=datetime(2026, 5, 10, 18, 0, tzinfo=CPH),
    )
    plan = make_plan(inp)
    assert plan.status == "extended"
    assert plan.was_extended is True
    assert plan.deadline == datetime(2026, 5, 11, 18, 30, tzinfo=CPH)
    assert len(plan.selected_starts) == 3


def test_extended_when_now_after_departure(prices: list[PriceSlot]) -> None:
    inp = PlanInput(
        prices=prices,
        slots_needed=3,
        departure=datetime(2026, 5, 10, 8, 0, tzinfo=CPH),
        now=datetime(2026, 5, 10, 18, 0, tzinfo=CPH),
    )
    plan = make_plan(inp)
    assert plan.status == "extended"
    assert plan.was_extended is True
    assert plan.deadline == datetime(2026, 5, 11, 8, 0, tzinfo=CPH)


def test_clamps_zero_slots_to_one(prices: list[PriceSlot]) -> None:
    inp = PlanInput(
        prices=prices,
        slots_needed=0,
        departure=datetime(2026, 5, 11, 8, 0, tzinfo=CPH),
        now=datetime(2026, 5, 10, 18, 0, tzinfo=CPH),
    )
    plan = make_plan(inp)
    assert len(plan.selected_starts) == 1
    assert plan.status == "ok"


def test_sorts_unsorted_prices_defensively(prices: list[PriceSlot]) -> None:
    shuffled = list(reversed(prices))
    inp = PlanInput(
        prices=shuffled,
        slots_needed=3,
        departure=datetime(2026, 5, 11, 8, 0, tzinfo=CPH),
        now=datetime(2026, 5, 10, 18, 0, tzinfo=CPH),
    )
    plan = make_plan(inp)
    assert list(plan.selected_starts) == sorted(plan.selected_starts)
