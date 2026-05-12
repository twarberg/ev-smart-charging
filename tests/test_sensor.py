"""Sensor attribute tests."""
from __future__ import annotations

from freezegun import freeze_time
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.smart_ev_charging.const import (
    CONF_MIN_SOC_THRESHOLD,
    CONF_SOC_ENTITY,
    CONF_TARGET_SOC_ENTITY,
    DOMAIN,
)
from tests.test_coordinator import _base_entry_data, _seed_prices


async def test_plan_status_sensor_exposes_discovery_hints(hass: HomeAssistant) -> None:
    """PlanStatusSensor.extra_state_attributes must include the four discovery hints."""
    _seed_prices(hass)

    data = _base_entry_data()
    data[CONF_SOC_ENTITY] = "sensor.test_soc"
    data[CONF_TARGET_SOC_ENTITY] = "number.test_target_soc"

    entry = MockConfigEntry(domain=DOMAIN, title="Daily", data=data)
    entry.add_to_hass(hass)

    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    state = hass.states.get("sensor.daily_plan_status")
    assert state is not None, "sensor.daily_plan_status not found"

    attrs = state.attributes

    # Four discovery hints
    assert attrs["source_price_entity"] == "sensor.fake_prices"
    assert attrs["charger_kw"] == 11.0
    assert attrs["soc_entity"] == "sensor.test_soc"
    assert attrs["target_soc_entity"] == "number.test_target_soc"

    # Existing keys must still be present (backwards-compatible)
    assert "override_mode" in attrs
    assert "override_until" in attrs

    # SoC gate: default threshold = 100 → gate disabled
    assert attrs["min_soc_threshold"] == 100
    assert attrs["min_soc_gate_active"] is False


@freeze_time("2026-05-11 02:30:00+02:00")
async def test_plan_status_sensor_reports_soc_gate(hass: HomeAssistant) -> None:
    """PlanStatusSensor must surface min_soc_threshold + min_soc_gate_active."""
    _seed_prices(hass)
    hass.states.async_set("sensor.car_soc", "75")
    hass.states.async_set("sensor.car_target", "90")
    hass.states.async_set("sensor.car_status", "0")

    data = _base_entry_data()
    data[CONF_SOC_ENTITY] = "sensor.car_soc"
    data[CONF_TARGET_SOC_ENTITY] = "sensor.car_target"
    data["charging_status_entity"] = "sensor.car_status"
    data["plug_unplugged_values"] = ["3"]
    data["actively_charging_values"] = ["0"]
    data[CONF_MIN_SOC_THRESHOLD] = 70

    entry = MockConfigEntry(domain=DOMAIN, title="Daily", data=data)
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    state = hass.states.get("sensor.daily_plan_status")
    assert state is not None
    attrs = state.attributes
    assert attrs["min_soc_threshold"] == 70
    assert attrs["min_soc_gate_active"] is True


@freeze_time("2026-05-11 01:30:00+02:00")
async def test_planned_hours_sensor_exposes_hour_kwh(hass: HomeAssistant) -> None:
    """PlannedHoursSensor.extra_state_attributes must include hour_kwh parallel to hours."""
    _seed_prices(hass)

    entry = MockConfigEntry(domain=DOMAIN, title="Daily", data=_base_entry_data())
    entry.add_to_hass(hass)

    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    state = hass.states.get("sensor.daily_planned_hours")
    assert state is not None, "sensor.daily_planned_hours not found"

    attrs = state.attributes

    # Existing keys must still be present (backwards-compatible)
    assert "hours" in attrs
    assert "hour_prices" in attrs
    assert "estimated_cost" in attrs
    assert "cost_unit" in attrs
    assert "next_charge_start" in attrs
    assert "next_charge_end" in attrs

    # New key: hour_kwh must be present and parallel to hours
    assert "hour_kwh" in attrs, "hour_kwh key missing from PlannedHoursSensor attributes"
    hour_kwh = attrs["hour_kwh"]
    hours = attrs["hours"]

    assert isinstance(hour_kwh, list), "hour_kwh must be a list"
    assert len(hour_kwh) == len(hours), "hour_kwh must have same length as hours"

    # With freeze_time at 01:30 CEST and cheap slots from 02:00 onward, planner
    # should select at least one hour — verify each element equals charger_kw (11.0)
    if hours:
        assert all(v == 11.0 for v in hour_kwh), f"Each hour_kwh entry must equal 11.0; got {hour_kwh}"
    else:
        # Zero selected hours is still valid; hour_kwh must be an empty list
        assert hour_kwh == []
