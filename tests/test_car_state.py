"""Tests for the car-state adapter."""
from __future__ import annotations

from collections.abc import Mapping
from datetime import time
from typing import Any

import pytest

from custom_components.smart_ev_charging.car_state import (
    CarStateConfig,
    StateLike,
    StatesLike,
    read_car_state,
)


class _FakeState:
    def __init__(self, state: str, attributes: dict[str, Any] | None = None) -> None:
        self.state = state
        self.attributes: Mapping[str, Any] = attributes or {}


class _FakeStates:
    def __init__(self) -> None:
        self._states: dict[str, _FakeState] = {}

    def add(self, entity_id: str, state: str, attributes: dict[str, Any] | None = None) -> None:
        self._states[entity_id] = _FakeState(state, attributes)

    def get(self, entity_id: str) -> StateLike | None:
        return self._states.get(entity_id)


class _FakeHass:
    def __init__(self) -> None:
        self._fake_states = _FakeStates()
        self.states: StatesLike = self._fake_states

    def add_state(
        self, entity_id: str, state: str, attributes: dict[str, Any] | None = None
    ) -> None:
        self._fake_states.add(entity_id, state, attributes)


@pytest.fixture
def fake_hass() -> _FakeHass:
    return _FakeHass()


def _full_config() -> CarStateConfig:
    return CarStateConfig(
        soc_entity="sensor.car_soc",
        target_soc_entity="sensor.car_target",
        charging_status_entity="sensor.car_status",
        plug_unplugged_values=["3", "unplugged"],
        actively_charging_values=["0", "charging"],
        departure_entity="sensor.car_departure",
    )


def test_full_state_reported(fake_hass: _FakeHass) -> None:
    fake_hass.add_state("sensor.car_soc", "65")
    fake_hass.add_state("sensor.car_target", "80")
    fake_hass.add_state("sensor.car_status", "0")
    fake_hass.add_state("sensor.car_departure", "07:30:00")
    cs = read_car_state(fake_hass, _full_config())
    assert cs.soc_percent == 65.0
    assert cs.target_soc_percent == 80.0
    assert cs.plug_raw_state == "0"
    assert cs.plugged_in is True
    assert cs.actively_charging is True
    assert cs.departure == time(7, 30)


def test_mercedes_numeric_unplugged(fake_hass: _FakeHass) -> None:
    fake_hass.add_state("sensor.car_soc", "65")
    fake_hass.add_state("sensor.car_target", "80")
    fake_hass.add_state("sensor.car_status", "3")
    cfg = CarStateConfig(
        soc_entity="sensor.car_soc",
        target_soc_entity="sensor.car_target",
        charging_status_entity="sensor.car_status",
        plug_unplugged_values=["3"],
        actively_charging_values=["0"],
        departure_entity=None,
    )
    cs = read_car_state(fake_hass, cfg)
    assert cs.plugged_in is False
    assert cs.actively_charging is False


def test_tesla_string_unplugged(fake_hass: _FakeHass) -> None:
    fake_hass.add_state("sensor.car_soc", "65")
    fake_hass.add_state("sensor.car_target", "80")
    fake_hass.add_state("sensor.car_status", "unplugged")
    cs = read_car_state(fake_hass, _full_config())
    assert cs.plugged_in is False


def test_unknown_status_is_not_plugged(fake_hass: _FakeHass) -> None:
    fake_hass.add_state("sensor.car_status", "unknown")
    cfg = CarStateConfig(
        soc_entity=None,
        target_soc_entity=None,
        charging_status_entity="sensor.car_status",
        plug_unplugged_values=["3"],
        actively_charging_values=["0"],
        departure_entity=None,
    )
    cs = read_car_state(fake_hass, cfg)
    assert cs.plug_raw_state == "unknown"
    assert cs.plugged_in is False


def test_no_charging_status_entity_means_plugged(fake_hass: _FakeHass) -> None:
    cfg = CarStateConfig(
        soc_entity=None, target_soc_entity=None,
        charging_status_entity=None,
        plug_unplugged_values=[], actively_charging_values=[],
        departure_entity=None,
    )
    cs = read_car_state(fake_hass, cfg)
    assert cs.plug_raw_state is None
    assert cs.plugged_in is True


def test_departure_short_form(fake_hass: _FakeHass) -> None:
    fake_hass.add_state("sensor.car_departure", "08:00")
    cfg = CarStateConfig(
        soc_entity=None, target_soc_entity=None, charging_status_entity=None,
        plug_unplugged_values=[], actively_charging_values=[],
        departure_entity="sensor.car_departure",
    )
    cs = read_car_state(fake_hass, cfg)
    assert cs.departure == time(8, 0)


def test_departure_unknown_is_none(fake_hass: _FakeHass) -> None:
    fake_hass.add_state("sensor.car_departure", "unknown")
    cfg = CarStateConfig(
        soc_entity=None, target_soc_entity=None, charging_status_entity=None,
        plug_unplugged_values=[], actively_charging_values=[],
        departure_entity="sensor.car_departure",
    )
    cs = read_car_state(fake_hass, cfg)
    assert cs.departure is None


def test_unparseable_soc_is_none(fake_hass: _FakeHass) -> None:
    fake_hass.add_state("sensor.car_soc", "unavailable")
    cfg = CarStateConfig(
        soc_entity="sensor.car_soc", target_soc_entity=None, charging_status_entity=None,
        plug_unplugged_values=[], actively_charging_values=[],
        departure_entity=None,
    )
    cs = read_car_state(fake_hass, cfg)
    assert cs.soc_percent is None


def test_non_numeric_soc_is_none(fake_hass: _FakeHass) -> None:
    """Hit the ValueError branch in _read_float (state not in UNAVAILABLE_STATES)."""
    fake_hass.add_state("sensor.car_soc", "not-a-number")
    cfg = CarStateConfig(
        soc_entity="sensor.car_soc", target_soc_entity=None, charging_status_entity=None,
        plug_unplugged_values=[], actively_charging_values=[],
        departure_entity=None,
    )
    cs = read_car_state(fake_hass, cfg)
    assert cs.soc_percent is None


def test_unparseable_departure_is_none(fake_hass: _FakeHass) -> None:
    """Hit the ValueError branch in _read_time (state not in UNAVAILABLE_STATES)."""
    fake_hass.add_state("sensor.car_departure", "not-a-time")
    cfg = CarStateConfig(
        soc_entity=None, target_soc_entity=None, charging_status_entity=None,
        plug_unplugged_values=[], actively_charging_values=[],
        departure_entity="sensor.car_departure",
    )
    cs = read_car_state(fake_hass, cfg)
    assert cs.departure is None
