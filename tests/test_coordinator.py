"""Coordinator tests."""
from __future__ import annotations

from typing import Any

from freezegun import freeze_time
from homeassistant.const import CONF_NAME
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry, async_mock_service

from custom_components.smart_ev_charging.const import (
    CONF_CHARGER_KW,
    CONF_CHARGER_SWITCH,
    CONF_DEFAULT_DEPARTURE,
    CONF_PRICE_ATTRIBUTE,
    CONF_PRICE_ENTITY,
    CONF_PRICE_FIELD,
    CONF_START_FIELD,
    DOMAIN,
    EVENT_PLAN_UPDATED,
    EVENT_TARGET_REACHED,
)


def _base_entry_data() -> dict[str, Any]:
    return {
        CONF_NAME: "Daily",
        CONF_PRICE_ENTITY: "sensor.fake_prices",
        CONF_PRICE_ATTRIBUTE: "prices",
        CONF_START_FIELD: "start",
        CONF_PRICE_FIELD: "price",
        CONF_CHARGER_SWITCH: "switch.charger",
        CONF_CHARGER_KW: 11.0,
        CONF_DEFAULT_DEPARTURE: "08:00:00",
    }


def _seed_prices(hass: HomeAssistant) -> None:
    hass.states.async_set(
        "sensor.fake_prices",
        "1.45",
        {
            "prices": [
                {"start": "2026-05-10T22:00:00+02:00", "end": "2026-05-10T23:00:00+02:00", "price": 1.80},
                {"start": "2026-05-10T23:00:00+02:00", "end": "2026-05-11T00:00:00+02:00", "price": 1.45},
                {"start": "2026-05-11T00:00:00+02:00", "end": "2026-05-11T01:00:00+02:00", "price": 1.15},
                {"start": "2026-05-11T01:00:00+02:00", "end": "2026-05-11T02:00:00+02:00", "price": 0.95},
                {"start": "2026-05-11T02:00:00+02:00", "end": "2026-05-11T03:00:00+02:00", "price": 0.65},
                {"start": "2026-05-11T03:00:00+02:00", "end": "2026-05-11T04:00:00+02:00", "price": 0.60},
                {"start": "2026-05-11T04:00:00+02:00", "end": "2026-05-11T05:00:00+02:00", "price": 0.62},
                {"start": "2026-05-11T05:00:00+02:00", "end": "2026-05-11T06:00:00+02:00", "price": 0.85},
                {"start": "2026-05-11T06:00:00+02:00", "end": "2026-05-11T07:00:00+02:00", "price": 1.30},
                {"start": "2026-05-11T07:00:00+02:00", "end": "2026-05-11T08:00:00+02:00", "price": 1.75},
            ],
        },
    )
    hass.states.async_set("switch.charger", "off", {})


async def test_coordinator_setup_and_first_refresh(hass: HomeAssistant) -> None:
    _seed_prices(hass)
    entry = MockConfigEntry(domain=DOMAIN, title="Daily", data=_base_entry_data())
    entry.add_to_hass(hass)

    events: list[Any] = []
    hass.bus.async_listen(EVENT_PLAN_UPDATED, events.append)

    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    coordinator = hass.data[DOMAIN][entry.entry_id]
    assert coordinator.data is not None
    assert coordinator.data.plan.status in {"ok", "partial", "extended", "no_data"}
    assert any(e.event_type == EVENT_PLAN_UPDATED for e in events)


async def test_coordinator_unload_cancels_listeners(hass: HomeAssistant) -> None:
    _seed_prices(hass)
    entry = MockConfigEntry(domain=DOMAIN, title="Daily", data=_base_entry_data())
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    assert await hass.config_entries.async_unload(entry.entry_id)
    assert entry.entry_id not in hass.data.get(DOMAIN, {})


async def _setup_with_soc(hass: HomeAssistant, soc: float = 30.0, target: float = 80.0) -> Any:
    async_mock_service(hass, "switch", "turn_on")
    async_mock_service(hass, "switch", "turn_off")
    _seed_prices(hass)
    hass.states.async_set("sensor.car_soc", str(soc))
    hass.states.async_set("sensor.car_target", str(target))
    hass.states.async_set("sensor.car_status", "0")  # Mercedes "actively charging"
    data = _base_entry_data()
    data["soc_entity"] = "sensor.car_soc"
    data["target_soc_entity"] = "sensor.car_target"
    data["charging_status_entity"] = "sensor.car_status"
    data["plug_unplugged_values"] = ["3"]
    data["actively_charging_values"] = ["0"]
    entry = MockConfigEntry(domain=DOMAIN, title="Daily", data=data)
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


@freeze_time("2026-05-11 03:30:00+02:00")
async def test_charge_now_on_during_planned_hour(hass: HomeAssistant) -> None:
    # _setup_with_soc registers mock switch services and returns the entry.
    # We capture the turn_on mock before setup so the same list is populated.
    turn_on_calls = async_mock_service(hass, "switch", "turn_on")
    async_mock_service(hass, "switch", "turn_off")
    _seed_prices(hass)
    hass.states.async_set("sensor.car_soc", "30")
    hass.states.async_set("sensor.car_target", "80")
    hass.states.async_set("sensor.car_status", "0")
    data = _base_entry_data()
    data["soc_entity"] = "sensor.car_soc"
    data["target_soc_entity"] = "sensor.car_target"
    data["charging_status_entity"] = "sensor.car_status"
    data["plug_unplugged_values"] = ["3"]
    data["actively_charging_values"] = ["0"]
    entry = MockConfigEntry(domain=DOMAIN, title="Daily", data=data)
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    coordinator = hass.data[DOMAIN][entry.entry_id]
    assert coordinator.data.charge_now is True
    assert any(c.data.get("entity_id") == "switch.charger" for c in turn_on_calls)


@freeze_time("2026-05-10 23:30:00+02:00")
async def test_charge_now_off_outside_planned_hour(hass: HomeAssistant) -> None:
    async_mock_service(hass, "switch", "turn_off")
    entry = await _setup_with_soc(hass)
    coordinator = hass.data[DOMAIN][entry.entry_id]
    assert coordinator.data.charge_now is False


@freeze_time("2026-05-11 02:30:00+02:00")
async def test_master_disabled_forces_off(hass: HomeAssistant) -> None:
    async_mock_service(hass, "switch", "turn_off")
    entry = await _setup_with_soc(hass)
    coordinator = hass.data[DOMAIN][entry.entry_id]
    coordinator.set_master_enabled(False)
    await hass.async_block_till_done()
    assert coordinator.data.charge_now is False
    assert coordinator.data.plan_status_label == "disabled"


@freeze_time("2026-05-11 02:30:00+02:00")
async def test_unplugged_forces_off(hass: HomeAssistant) -> None:
    entry = await _setup_with_soc(hass)
    coordinator = hass.data[DOMAIN][entry.entry_id]
    hass.states.async_set("sensor.car_status", "3")  # unplugged
    await hass.async_block_till_done()
    await coordinator.async_refresh()
    assert coordinator.data.charge_now is False
    assert coordinator.data.plan_status_label == "unplugged"


@freeze_time("2026-05-10 23:30:00+02:00")
async def test_force_override_overrides_plan(hass: HomeAssistant) -> None:
    async_mock_service(hass, "switch", "turn_on")
    async_mock_service(hass, "switch", "turn_off")
    _seed_prices(hass)
    hass.states.async_set("sensor.car_soc", "30")
    hass.states.async_set("sensor.car_target", "80")
    hass.states.async_set("sensor.car_status", "0")
    data = _base_entry_data()
    data.update(
        {
            "soc_entity": "sensor.car_soc",
            "target_soc_entity": "sensor.car_target",
            "charging_status_entity": "sensor.car_status",
            "plug_unplugged_values": ["3"],
            "actively_charging_values": ["0"],
        }
    )
    entry = MockConfigEntry(domain=DOMAIN, title="Daily", data=data)
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    coordinator = hass.data[DOMAIN][entry.entry_id]

    # Now is 23:30 — not in plan
    assert coordinator.data.charge_now is False
    coordinator.apply_override("force", until=None)
    await hass.async_block_till_done()
    assert coordinator.data.charge_now is True


@freeze_time("2026-05-11 02:30:00+02:00")
async def test_target_reached_clears_force_override(hass: HomeAssistant) -> None:
    entry = await _setup_with_soc(hass, soc=30.0, target=80.0)
    coordinator = hass.data[DOMAIN][entry.entry_id]
    coordinator.apply_override("force", until=None)
    await hass.async_block_till_done()
    hass.states.async_set("sensor.car_soc", "80")
    await coordinator.async_refresh()
    assert coordinator.data.override is None
    assert coordinator.data.charge_now is False


async def test_plug_debouncer_holds_through_unknown(hass: HomeAssistant) -> None:
    _seed_prices(hass)
    hass.states.async_set("sensor.car_status", "0")
    data = _base_entry_data()
    data.update(
        {
            "charging_status_entity": "sensor.car_status",
            "plug_unplugged_values": ["3"],
            "actively_charging_values": ["0"],
        }
    )
    entry = MockConfigEntry(domain=DOMAIN, title="Daily", data=data)
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    coordinator = hass.data[DOMAIN][entry.entry_id]
    assert coordinator.data.debounced_plugged_in is True

    hass.states.async_set("sensor.car_status", "unknown")
    await coordinator.async_refresh()
    assert coordinator.data.debounced_plugged_in is True  # held by debouncer

    hass.states.async_set("sensor.car_status", "3")  # explicit unplug
    await coordinator.async_refresh()
    assert coordinator.data.debounced_plugged_in is False


@freeze_time("2026-05-11 03:30:00+02:00")
async def test_force_override_cleared_on_unplug(hass: HomeAssistant) -> None:
    async_mock_service(hass, "switch", "turn_on")
    async_mock_service(hass, "switch", "turn_off")
    entry = await _setup_with_soc(hass)
    coordinator = hass.data[DOMAIN][entry.entry_id]
    coordinator.apply_override("force", until=None)
    await hass.async_block_till_done()
    assert coordinator.data.override is not None

    hass.states.async_set("sensor.car_status", "3")
    await coordinator.async_refresh()
    assert coordinator.data.debounced_plugged_in is False
    assert coordinator.data.override is None


@freeze_time("2026-05-11 03:30:00+02:00")
async def test_master_disable_clears_override(hass: HomeAssistant) -> None:
    async_mock_service(hass, "switch", "turn_on")
    async_mock_service(hass, "switch", "turn_off")
    entry = await _setup_with_soc(hass)
    coordinator = hass.data[DOMAIN][entry.entry_id]
    coordinator.apply_override("force", until=None)
    await hass.async_block_till_done()
    assert coordinator.data.override is not None

    coordinator.set_master_enabled(False)
    await coordinator.async_refresh()
    assert coordinator.data.override is None


@freeze_time("2026-05-11 03:30:00+02:00")
async def test_target_reached_event_fires_with_target_soc_override(hass: HomeAssistant) -> None:
    """When no target_soc_entity is configured, target_reached should still fire
    using the number.target_soc_override value (default 80)."""
    async_mock_service(hass, "switch", "turn_on")
    async_mock_service(hass, "switch", "turn_off")
    _seed_prices(hass)
    hass.states.async_set("sensor.car_soc", "30")
    hass.states.async_set("sensor.car_status", "0")
    data = _base_entry_data()
    data.update(
        {
            "soc_entity": "sensor.car_soc",
            "charging_status_entity": "sensor.car_status",
            "plug_unplugged_values": ["3"],
            "actively_charging_values": ["0"],
        }
    )
    entry = MockConfigEntry(domain=DOMAIN, title="Daily", data=data)
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    coordinator = hass.data[DOMAIN][entry.entry_id]
    assert coordinator.data.charge_now is True

    fired: list[Any] = []
    hass.bus.async_listen(EVENT_TARGET_REACHED, fired.append)

    # SoC reaches the override target (80%)
    hass.states.async_set("sensor.car_soc", "80")
    await coordinator.async_refresh()
    await hass.async_block_till_done()
    assert any(e.event_type == EVENT_TARGET_REACHED for e in fired)


@freeze_time("2026-05-11 03:30:00+02:00")
async def test_apply_override_skip_requires_until(hass: HomeAssistant) -> None:
    import pytest

    async_mock_service(hass, "switch", "turn_on")
    async_mock_service(hass, "switch", "turn_off")
    entry = await _setup_with_soc(hass)
    coordinator = hass.data[DOMAIN][entry.entry_id]
    with pytest.raises(ValueError, match="skip"):
        coordinator.apply_override("skip", None)


@freeze_time("2026-05-11 03:30:00+02:00")
async def test_expected_entities_exist(hass: HomeAssistant) -> None:
    async_mock_service(hass, "switch", "turn_on")
    async_mock_service(hass, "switch", "turn_off")
    await _setup_with_soc(hass)
    expected = {
        "sensor.daily_plan_status",
        "sensor.daily_planned_hours",
        "sensor.daily_slots_needed",
        "sensor.daily_active_deadline",
        "sensor.daily_effective_departure",
        "binary_sensor.daily_plugged_in",
        "binary_sensor.daily_actively_charging",
        "binary_sensor.daily_charge_now",
    }
    actual = {s.entity_id for s in hass.states.async_all()}
    missing = expected - actual
    assert not missing, f"missing: {missing}"
