"""Tests for the pure planner. No HA dependency."""
from __future__ import annotations

import itertools
import json
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

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


def test_zero_slots_returns_empty_plan(prices: list[PriceSlot]) -> None:
    """slots_needed=0 means \"no charge needed\" — planner returns empty."""
    inp = PlanInput(
        prices=prices,
        slots_needed=0,
        departure=datetime(2026, 5, 11, 8, 0, tzinfo=CPH),
        now=datetime(2026, 5, 10, 18, 0, tzinfo=CPH),
    )
    plan = make_plan(inp)
    assert plan.selected_starts == ()
    assert plan.status == "ok"
    assert plan.window_size > 0


def test_negative_slots_clamped_to_zero(prices: list[PriceSlot]) -> None:
    inp = PlanInput(
        prices=prices,
        slots_needed=-5,
        departure=datetime(2026, 5, 11, 8, 0, tzinfo=CPH),
        now=datetime(2026, 5, 10, 18, 0, tzinfo=CPH),
    )
    plan = make_plan(inp)
    assert plan.selected_starts == ()


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


def test_mid_hour_plug_in_skips_current_hour(prices: list[PriceSlot]) -> None:
    # at 18:50 with default min_minutes_left=15, current hour (18:00) is skipped
    inp = PlanInput(
        prices=prices,
        slots_needed=2,
        departure=datetime(2026, 5, 10, 22, 0, tzinfo=CPH),
        now=datetime(2026, 5, 10, 18, 50, tzinfo=CPH),
    )
    plan = make_plan(inp)
    assert datetime(2026, 5, 10, 18, 0, tzinfo=CPH) not in plan.selected_starts
    assert plan.window_size == 3  # 19, 20, 21


def test_mid_hour_keeps_current_hour_when_threshold_zero(prices: list[PriceSlot]) -> None:
    inp = PlanInput(
        prices=prices,
        slots_needed=2,
        departure=datetime(2026, 5, 10, 22, 0, tzinfo=CPH),
        now=datetime(2026, 5, 10, 18, 50, tzinfo=CPH),
        min_minutes_left_in_hour=0,
    )
    plan = make_plan(inp)
    assert plan.window_size == 4  # 18, 19, 20, 21


def test_late_night_plug_in_crosses_midnight(prices: list[PriceSlot]) -> None:
    # plug in at 23:50, departure 08:00 next day; effective_start rolls to 00:00
    inp = PlanInput(
        prices=prices,
        slots_needed=3,
        departure=datetime(2026, 5, 11, 8, 0, tzinfo=CPH),
        now=datetime(2026, 5, 10, 23, 50, tzinfo=CPH),
    )
    plan = make_plan(inp)
    assert plan.status == "ok"
    assert all(
        s >= datetime(2026, 5, 11, 0, 0, tzinfo=CPH) for s in plan.selected_starts
    )
    expected = {
        datetime(2026, 5, 11, 2, 0, tzinfo=CPH),
        datetime(2026, 5, 11, 3, 0, tzinfo=CPH),
        datetime(2026, 5, 11, 4, 0, tzinfo=CPH),
    }
    assert set(plan.selected_starts) == expected


def test_filters_past_slots(prices: list[PriceSlot]) -> None:
    inp = PlanInput(
        prices=prices,
        slots_needed=3,
        departure=datetime(2026, 5, 11, 8, 0, tzinfo=CPH),
        now=datetime(2026, 5, 10, 18, 0, tzinfo=CPH),
    )
    plan = make_plan(inp)
    cutoff = datetime(2026, 5, 10, 18, 0, tzinfo=CPH)
    assert all(s >= cutoff for s in plan.selected_starts)


def test_dst_spring_forward_does_not_synthesize_missing_hour() -> None:
    # 2026-03-29 in Europe/Copenhagen: 02:00 doesn't exist (clock jumps to 03:00)
    cph = ZoneInfo("Europe/Copenhagen")
    base = datetime(2026, 3, 28, 0, 0, tzinfo=cph)
    prices: list[PriceSlot] = []
    for h in range(48):
        start = base + timedelta(hours=h)
        # Skip the non-existent 2026-03-29 02:00 CET slot
        if start.date() == datetime(2026, 3, 29).date() and start.hour == 2:
            continue
        prices.append(PriceSlot(start=start, end=start + timedelta(hours=1), price=1.0 + h * 0.01))
    plan = make_plan(
        PlanInput(
            prices=prices,
            slots_needed=3,
            departure=datetime(2026, 3, 29, 8, 0, tzinfo=cph),
            now=datetime(2026, 3, 28, 18, 0, tzinfo=cph),
        )
    )
    nonexistent = datetime(2026, 3, 29, 2, 0, tzinfo=cph)
    assert nonexistent not in plan.selected_starts


def test_mixed_timezones_compare_correctly(prices: list[PriceSlot]) -> None:
    from datetime import UTC

    inp = PlanInput(
        prices=prices,
        slots_needed=3,
        departure=datetime(2026, 5, 11, 8, 0, tzinfo=CPH),
        now=datetime(2026, 5, 10, 16, 0, tzinfo=UTC),  # = 18:00 CPH
    )
    plan = make_plan(inp)
    assert plan.status == "ok"
    assert len(plan.selected_starts) == 3


def _build_prices(start_hour: int, count: int, offsets: list[float]) -> list[PriceSlot]:
    base = datetime(2026, 5, 10, start_hour, 0, tzinfo=CPH)
    return [
        PriceSlot(
            start=base + timedelta(hours=i),
            end=base + timedelta(hours=i + 1),
            price=offsets[i],
        )
        for i in range(count)
    ]


@given(
    count=st.integers(min_value=1, max_value=24),
    slots=st.integers(min_value=1, max_value=12),
    delta_hours=st.integers(min_value=2, max_value=36),
    seed=st.integers(min_value=0, max_value=10_000),
)
@settings(max_examples=80, deadline=None)
def test_picker_optimality(count: int, slots: int, delta_hours: int, seed: int) -> None:
    import random

    rng = random.Random(seed)
    offsets = [rng.uniform(0.1, 5.0) for _ in range(count)]
    prices = _build_prices(start_hour=0, count=count, offsets=offsets)
    departure = datetime(2026, 5, 10, 0, 0, tzinfo=CPH) + timedelta(hours=delta_hours)
    plan = make_plan(
        PlanInput(
            prices=prices,
            slots_needed=slots,
            departure=departure,
            now=datetime(2026, 5, 10, 0, 0, tzinfo=CPH) - timedelta(minutes=1),
        )
    )
    if plan.status == "no_data":
        assert plan.selected_starts == ()
        return
    assert list(plan.selected_starts) == sorted(plan.selected_starts)
    window = [
        p
        for p in prices
        if datetime(2026, 5, 10, 0, 0, tzinfo=CPH) <= p.start < plan.deadline
    ]
    selected = [p for p in prices if p.start in plan.selected_starts]
    assert len(selected) == min(slots, len(window))
    sel_total = sum(s.price for s in selected)
    for sub in itertools.combinations(window, len(selected)):
        sub_total = sum(s.price for s in sub)
        assert sel_total <= sub_total + 1e-9
