"""Tests for the config + options flow."""
from __future__ import annotations

from typing import Any

from homeassistant.config_entries import ConfigFlowResult
from homeassistant.const import CONF_NAME
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType

from custom_components.smart_ev_charging.const import (
    CONF_CHARGER_KW,
    CONF_CHARGER_SWITCH,
    CONF_PRICE_ATTRIBUTE,
    CONF_PRICE_ENTITY,
    CONF_PRICE_FIELD,
    CONF_START_FIELD,
    DOMAIN,
)


async def _seed_price_entity(hass: HomeAssistant, **overrides: Any) -> None:
    entity_id = overrides.get("entity_id", "sensor.fake_prices")
    attrs = overrides.get(
        "attributes",
        {
            "prices": [
                {
                    "start": "2026-05-10T18:00:00+02:00",
                    "price": 3.05,
                    "end": "2026-05-10T19:00:00+02:00",
                }
            ],
        },
    )
    hass.states.async_set(entity_id, "1.45", attrs)


async def _seed_charger_switch(hass: HomeAssistant) -> None:
    hass.states.async_set("switch.charger", "off", {})


async def _start_user_step(hass: HomeAssistant) -> ConfigFlowResult:
    return await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": "user"}
    )


async def test_user_step_advances_to_price(hass: HomeAssistant) -> None:
    result = await _start_user_step(hass)
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "user"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_NAME: "Daily"}
    )
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "price"


async def test_price_step_validates_attribute_missing(hass: HomeAssistant) -> None:
    hass.states.async_set("sensor.fake_prices", "1.45", {})
    await _seed_charger_switch(hass)
    r = await _start_user_step(hass)
    r = await hass.config_entries.flow.async_configure(r["flow_id"], {CONF_NAME: "Daily"})
    r = await hass.config_entries.flow.async_configure(
        r["flow_id"],
        {
            CONF_PRICE_ENTITY: "sensor.fake_prices",
            CONF_PRICE_ATTRIBUTE: "prices",
            CONF_START_FIELD: "start",
            CONF_PRICE_FIELD: "price",
        },
    )
    assert r["type"] == FlowResultType.FORM
    assert r["errors"] == {CONF_PRICE_ATTRIBUTE: "attribute_not_found"}


async def test_price_step_validates_field_missing(hass: HomeAssistant) -> None:
    hass.states.async_set("sensor.fake_prices", "1.45", {
        "prices": [{"start": "2026-05-10T18:00:00+02:00", "value": 3.05}],
    })
    r = await _start_user_step(hass)
    r = await hass.config_entries.flow.async_configure(r["flow_id"], {CONF_NAME: "Daily"})
    r = await hass.config_entries.flow.async_configure(
        r["flow_id"],
        {
            CONF_PRICE_ENTITY: "sensor.fake_prices",
            CONF_PRICE_ATTRIBUTE: "prices",
            CONF_START_FIELD: "start",
            CONF_PRICE_FIELD: "price",
        },
    )
    assert r["type"] == FlowResultType.FORM
    assert r["errors"] == {CONF_START_FIELD: "field_not_found"}
    placeholders = r["description_placeholders"]
    assert placeholders is not None
    assert "value" in placeholders["peek"]


async def test_price_step_advances_on_valid_attrs(hass: HomeAssistant) -> None:
    await _seed_price_entity(hass)
    r = await _start_user_step(hass)
    r = await hass.config_entries.flow.async_configure(r["flow_id"], {CONF_NAME: "Daily"})
    r = await hass.config_entries.flow.async_configure(
        r["flow_id"],
        {
            CONF_PRICE_ENTITY: "sensor.fake_prices",
            CONF_PRICE_ATTRIBUTE: "prices",
            CONF_START_FIELD: "start",
            CONF_PRICE_FIELD: "price",
        },
    )
    assert r["step_id"] == "charger"


async def test_charger_step_advances_to_car(hass: HomeAssistant) -> None:
    await _seed_price_entity(hass)
    await _seed_charger_switch(hass)
    r = await _start_user_step(hass)
    r = await hass.config_entries.flow.async_configure(r["flow_id"], {CONF_NAME: "Daily"})
    r = await hass.config_entries.flow.async_configure(r["flow_id"], {
        CONF_PRICE_ENTITY: "sensor.fake_prices",
        CONF_PRICE_ATTRIBUTE: "prices",
        CONF_START_FIELD: "start",
        CONF_PRICE_FIELD: "price",
    })
    r = await hass.config_entries.flow.async_configure(r["flow_id"], {
        CONF_CHARGER_SWITCH: "switch.charger",
        CONF_CHARGER_KW: 11.0,
    })
    assert r["step_id"] == "car"
