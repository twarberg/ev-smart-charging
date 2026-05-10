"""Tests for the price-source adapter."""
from __future__ import annotations

import json
import logging
from collections.abc import Mapping
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import pytest

from custom_components.smart_ev_charging.price_source import (
    PriceSource,
    StateLike,
    StatesLike,
)

CPH = ZoneInfo("Europe/Copenhagen")
FIXTURES = Path(__file__).parent / "fixtures"


class _FakeState:
    def __init__(self, state: str, attributes: dict[str, Any]) -> None:
        self.state = state
        self.attributes: Mapping[str, Any] = attributes


class _FakeStates:
    def __init__(self) -> None:
        self._data: dict[str, _FakeState] = {}

    def add(self, entity_id: str, state: str, attributes: dict[str, Any]) -> None:
        self._data[entity_id] = _FakeState(state, attributes)

    def get(self, entity_id: str) -> StateLike | None:
        return self._data.get(entity_id)


class _FakeHass:
    """Minimal hass double; satisfies HassLike structurally."""

    def __init__(self) -> None:
        self._fake_states = _FakeStates()
        self.states: StatesLike = self._fake_states

    def add_state(self, entity_id: str, state: str, attributes: dict[str, Any]) -> None:
        """Convenience helper: add a fake state entry."""
        self._fake_states.add(entity_id, state, attributes)


@pytest.fixture
def fake_hass() -> _FakeHass:
    return _FakeHass()


@pytest.fixture
def state_fixture() -> dict[str, Any]:
    data: dict[str, Any] = json.loads((FIXTURES / "stromligning_state.json").read_text())
    return data


def test_stromligning_shape(fake_hass: _FakeHass, state_fixture: dict[str, Any]) -> None:
    fx = state_fixture["stromligning"]
    fake_hass.add_state(fx["entity_id"], fx["state"], fx["attributes"])
    src = PriceSource(
        hass=fake_hass,
        entity_id=fx["entity_id"],
        attr_name="prices",
        start_field="start",
        price_field="price",
        end_field="end",
    )
    slots = src.get_slots()
    assert len(slots) == 3
    assert slots[0].start == datetime(2026, 5, 10, 18, 0, tzinfo=CPH)
    assert slots[0].end == datetime(2026, 5, 10, 19, 0, tzinfo=CPH)
    assert slots[0].price == 3.05
    assert slots == sorted(slots, key=lambda s: s.start)


def test_nordpool_shape(fake_hass: _FakeHass, state_fixture: dict[str, Any]) -> None:
    fx = state_fixture["nordpool"]
    fake_hass.add_state(fx["entity_id"], fx["state"], fx["attributes"])
    src = PriceSource(
        hass=fake_hass,
        entity_id=fx["entity_id"],
        attr_name="today",
        start_field="start",
        price_field="value",
    )
    slots = src.get_slots()
    assert len(slots) == 3
    assert slots[0].price == 3.05


def test_tibber_shape(fake_hass: _FakeHass, state_fixture: dict[str, Any]) -> None:
    fx = state_fixture["tibber"]
    fake_hass.add_state(fx["entity_id"], fx["state"], fx["attributes"])
    src = PriceSource(
        hass=fake_hass,
        entity_id=fx["entity_id"],
        attr_name="today",
        start_field="startsAt",
        price_field="total",
    )
    slots = src.get_slots()
    assert len(slots) == 3


def test_entity_missing_returns_empty(fake_hass: _FakeHass) -> None:
    src = PriceSource(hass=fake_hass, entity_id="sensor.does_not_exist",
                      attr_name="prices", start_field="start", price_field="price")
    assert src.get_slots() == []


def test_entity_unavailable_returns_empty(fake_hass: _FakeHass) -> None:
    fake_hass.add_state(
        "sensor.x", "unavailable",
        {"prices": [{"start": "2026-05-10T00:00:00+02:00", "price": 1.0}]},
    )
    src = PriceSource(hass=fake_hass, entity_id="sensor.x",
                      attr_name="prices", start_field="start", price_field="price")
    assert src.get_slots() == []


def test_attribute_missing_returns_empty(fake_hass: _FakeHass) -> None:
    fake_hass.add_state("sensor.x", "1.0", {})
    src = PriceSource(hass=fake_hass, entity_id="sensor.x",
                      attr_name="prices", start_field="start", price_field="price")
    assert src.get_slots() == []


def test_attribute_not_a_list_returns_empty(fake_hass: _FakeHass) -> None:
    fake_hass.add_state("sensor.x", "1.0", {"prices": "oops"})
    src = PriceSource(hass=fake_hass, entity_id="sensor.x",
                      attr_name="prices", start_field="start", price_field="price")
    assert src.get_slots() == []


def test_attribute_empty_list_returns_empty(fake_hass: _FakeHass) -> None:
    fake_hass.add_state("sensor.x", "1.0", {"prices": []})
    src = PriceSource(hass=fake_hass, entity_id="sensor.x",
                      attr_name="prices", start_field="start", price_field="price")
    assert src.get_slots() == []


def test_malformed_entries_dropped_good_ones_kept(
    fake_hass: _FakeHass, caplog: pytest.LogCaptureFixture
) -> None:
    fake_hass.add_state("sensor.x", "1.0", {
        "prices": [
            {"start": "2026-05-10T00:00:00+02:00", "price": 1.0},
            {"start": "not a date", "price": 2.0},
            {"start": "2026-05-10T02:00:00+02:00"},  # missing price
            {"start": "2026-05-10T01:00:00+02:00", "price": 1.5},
        ],
    })
    src = PriceSource(hass=fake_hass, entity_id="sensor.x",
                      attr_name="prices", start_field="start", price_field="price")
    slots = src.get_slots()
    assert len(slots) == 2
    assert slots[0].start.hour == 0
    assert slots[1].start.hour == 1


def test_warns_only_once_per_failure(
    fake_hass: _FakeHass, caplog: pytest.LogCaptureFixture
) -> None:
    src = PriceSource(hass=fake_hass, entity_id="sensor.missing",
                      attr_name="prices", start_field="start", price_field="price")
    with caplog.at_level(logging.WARNING):
        src.get_slots()
        src.get_slots()
        src.get_slots()
    matching = [r for r in caplog.records if "entity missing or unavailable" in r.message]
    assert len(matching) == 1


def test_unix_timestamp_start_is_parsed(fake_hass: _FakeHass) -> None:
    fake_hass.add_state("sensor.x", "1.0", {
        "prices": [{"start": 1746883200, "price": 1.0}],
    })
    src = PriceSource(hass=fake_hass, entity_id="sensor.x",
                      attr_name="prices", start_field="start", price_field="price")
    slots = src.get_slots()
    assert len(slots) == 1
    assert slots[0].start.tzinfo is not None


def test_naive_datetime_start_gets_utc(fake_hass: _FakeHass) -> None:
    """Cover _parse_dt branch: datetime with no tzinfo -> attach UTC."""
    naive = datetime(2026, 5, 10, 18, 0, 0)  # no tzinfo
    fake_hass.add_state("sensor.x", "1.0", {
        "prices": [{"start": naive, "price": 2.5}],
    })
    src = PriceSource(hass=fake_hass, entity_id="sensor.x",
                      attr_name="prices", start_field="start", price_field="price")
    slots = src.get_slots()
    assert len(slots) == 1
    assert slots[0].start.tzinfo == UTC


def test_non_entry_list_items_dropped(fake_hass: _FakeHass) -> None:
    """Cover _warn_once('entry_not_mapping'): list contains non-Mapping items."""
    fake_hass.add_state("sensor.x", "1.0", {
        "prices": [
            "not_a_dict",
            {"start": "2026-05-10T00:00:00+02:00", "price": 1.0},
        ],
    })
    src = PriceSource(hass=fake_hass, entity_id="sensor.x",
                      attr_name="prices", start_field="start", price_field="price")
    slots = src.get_slots()
    assert len(slots) == 1


def test_unparseable_end_field_falls_back_to_one_hour(fake_hass: _FakeHass) -> None:
    """Cover line 93: end_field present but _parse_dt returns None -> start+1h."""
    fake_hass.add_state("sensor.x", "1.0", {
        "prices": [{"start": "2026-05-10T00:00:00+02:00", "end": "not-a-date", "price": 1.0}],
    })
    src = PriceSource(hass=fake_hass, entity_id="sensor.x",
                      attr_name="prices", start_field="start", price_field="price",
                      end_field="end")
    slots = src.get_slots()
    assert len(slots) == 1
    assert slots[0].end == slots[0].start + timedelta(hours=1)


def test_unknown_type_start_returns_none(fake_hass: _FakeHass) -> None:
    """Cover _parse_dt line 39: non-datetime/int/str value returns None -> entry dropped."""
    fake_hass.add_state("sensor.x", "1.0", {
        "prices": [
            {"start": ["2026-05-10T00:00:00+02:00"], "price": 1.0},  # list is not a valid start
            {"start": "2026-05-10T01:00:00+02:00", "price": 2.0},
        ],
    })
    src = PriceSource(hass=fake_hass, entity_id="sensor.x",
                      attr_name="prices", start_field="start", price_field="price")
    slots = src.get_slots()
    assert len(slots) == 1
    assert slots[0].price == 2.0
