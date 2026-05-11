"""Sensor attribute tests."""
from __future__ import annotations

from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.smart_ev_charging.const import (
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

    # Four new discovery hints
    assert attrs["source_price_entity"] == "sensor.fake_prices"
    assert attrs["charger_kw"] == 11.0
    assert attrs["soc_entity"] == "sensor.test_soc"
    assert attrs["target_soc_entity"] == "number.test_target_soc"

    # Existing keys must still be present (backwards-compatible)
    assert "override_mode" in attrs
    assert "override_until" in attrs
