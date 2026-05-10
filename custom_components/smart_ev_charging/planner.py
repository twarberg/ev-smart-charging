"""Pure Python charging planner. Zero Home Assistant imports — keep it that way."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Literal

PlanStatus = Literal["ok", "partial", "extended", "no_data"]

_SENTINEL_DT: datetime = datetime(1970, 1, 1, tzinfo=UTC)


@dataclass(frozen=True)
class PriceSlot:
    start: datetime
    end: datetime
    price: float


@dataclass(frozen=True)
class PlanInput:
    prices: list[PriceSlot]
    slots_needed: int
    departure: datetime
    now: datetime
    min_minutes_left_in_hour: int = 15


@dataclass(frozen=True)
class Plan:
    selected_starts: tuple[datetime, ...] = ()
    deadline: datetime = _SENTINEL_DT
    initial_deadline: datetime = _SENTINEL_DT
    was_extended: bool = False
    window_size: int = 0
    status: PlanStatus = "no_data"


def make_plan(inp: PlanInput) -> Plan:
    """Compute a charging plan. See spec § 5 Layer 1."""
    # Defensive non-negative clamp; 0 is a legitimate "no charge needed" signal
    # the caller can use when SoC is already at or above target.
    slots_needed = max(0, inp.slots_needed)
    prices = sorted(inp.prices, key=lambda s: s.start)

    this_hour_start = inp.now.replace(minute=0, second=0, microsecond=0)
    next_hour_start = this_hour_start + timedelta(hours=1)
    minutes_left = (next_hour_start - inp.now).total_seconds() / 60
    effective_start = (
        next_hour_start if minutes_left < inp.min_minutes_left_in_hour else this_hour_start
    )

    hours_until_deadline = (inp.departure - inp.now).total_seconds() / 3600
    if hours_until_deadline < 1:
        deadline = inp.departure + timedelta(hours=24)
        was_extended = True
    else:
        deadline = inp.departure
        was_extended = False

    window = [s for s in prices if effective_start <= s.start < deadline]
    effective_slots = min(slots_needed, len(window))
    cheapest = sorted(window, key=lambda s: s.price)[:effective_slots]
    selected_starts = tuple(sorted(s.start for s in cheapest))

    if len(window) == 0:
        status: PlanStatus = "no_data"
    elif was_extended:
        status = "extended"
    elif len(window) < slots_needed:
        status = "partial"
    else:
        status = "ok"

    return Plan(
        selected_starts=selected_starts,
        deadline=deadline,
        initial_deadline=inp.departure,
        was_extended=was_extended,
        window_size=len(window),
        status=status,
    )
