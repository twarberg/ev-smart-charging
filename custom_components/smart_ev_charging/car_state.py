"""Adapter that reads optional car entities into a uniform CarState."""
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import time
from typing import Any, Protocol

from .const import UNAVAILABLE_STATES


@dataclass(frozen=True)
class CarStateConfig:
    soc_entity: str | None
    target_soc_entity: str | None
    charging_status_entity: str | None
    plug_unplugged_values: list[str]
    actively_charging_values: list[str]
    departure_entity: str | None


@dataclass(frozen=True)
class CarState:
    soc_percent: float | None
    target_soc_percent: float | None
    plug_raw_state: str | None
    plugged_in: bool
    actively_charging: bool
    departure: time | None


class StateLike(Protocol):
    """Structural type for a HA-like state object."""

    state: str
    attributes: Mapping[str, Any]


class StatesLike(Protocol):
    """Structural type for hass.states."""

    def get(self, entity_id: str) -> StateLike | None: ...


class HassLike(Protocol):
    """Structural type for a HA-like core object."""

    states: StatesLike


def _read_float(hass: HassLike, entity_id: str | None) -> float | None:
    if not entity_id:
        return None
    state = hass.states.get(entity_id)
    if state is None or state.state in UNAVAILABLE_STATES:
        return None
    try:
        return float(state.state)
    except (TypeError, ValueError):
        return None


def _read_time(hass: HassLike, entity_id: str | None) -> time | None:
    if not entity_id:
        return None
    state = hass.states.get(entity_id)
    if state is None or state.state in UNAVAILABLE_STATES:
        return None
    try:
        parts = state.state.split(":")
        h = int(parts[0])
        m = int(parts[1]) if len(parts) > 1 else 0
        s = int(parts[2]) if len(parts) > 2 else 0
        return time(hour=h, minute=m, second=s)
    except (TypeError, ValueError, IndexError):
        return None


def read_car_state(hass: HassLike, config: CarStateConfig) -> CarState:
    soc = _read_float(hass, config.soc_entity)
    target = _read_float(hass, config.target_soc_entity)
    departure = _read_time(hass, config.departure_entity)

    if config.charging_status_entity is None:
        return CarState(
            soc_percent=soc,
            target_soc_percent=target,
            plug_raw_state=None,
            plugged_in=True,
            actively_charging=False,
            departure=departure,
        )

    state = hass.states.get(config.charging_status_entity)
    raw = state.state if state is not None else None
    if raw is None or raw in UNAVAILABLE_STATES:
        return CarState(
            soc_percent=soc,
            target_soc_percent=target,
            plug_raw_state=raw,
            plugged_in=False,
            actively_charging=False,
            departure=departure,
        )

    plugged_in = raw not in config.plug_unplugged_values
    actively_charging = raw in config.actively_charging_values
    return CarState(
        soc_percent=soc,
        target_soc_percent=target,
        plug_raw_state=raw,
        plugged_in=plugged_in,
        actively_charging=actively_charging,
        departure=departure,
    )
