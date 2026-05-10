"""Config + Options flow for Smart EV Charging."""
from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.config_entries import ConfigFlowResult as FlowResult
from homeassistant.const import CONF_NAME
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import selector

from .const import (
    CONF_ACTIVELY_CHARGING_VALUES,
    CONF_AUTO_REPLAN_ON_PRICE_UPDATE,
    CONF_AUTO_REPLAN_ON_SOC_CHANGE,
    CONF_BATTERY_KWH,
    CONF_CHARGER_KW,
    CONF_CHARGER_SWITCH,
    CONF_CHARGING_STATUS_ENTITY,
    CONF_DEFAULT_DEPARTURE,
    CONF_DEPARTURE_ENTITY,
    CONF_END_FIELD,
    CONF_MIN_MINUTES_LEFT_IN_HOUR,
    CONF_PLUG_UNPLUGGED_VALUES,
    CONF_PRICE_ATTRIBUTE,
    CONF_PRICE_ENTITY,
    CONF_PRICE_FIELD,
    CONF_SOC_ENTITY,
    CONF_START_FIELD,
    CONF_TARGET_SOC_ENTITY,
    DEFAULT_ACTIVELY_CHARGING_VALUES,
    DEFAULT_AUTO_REPLAN_ON_PRICE_UPDATE,
    DEFAULT_AUTO_REPLAN_ON_SOC_CHANGE,
    DEFAULT_BATTERY_KWH,
    DEFAULT_CHARGER_KW,
    DEFAULT_DEPARTURE_TIME,
    DEFAULT_END_FIELD,
    DEFAULT_MIN_MINUTES_LEFT,
    DEFAULT_NAME,
    DEFAULT_PLUG_UNPLUGGED_VALUES,
    DEFAULT_PRICE_ATTRIBUTE,
    DEFAULT_PRICE_FIELD,
    DEFAULT_START_FIELD,
    DOMAIN,
)

_NM = selector.NumberSelectorMode.BOX


def _name_already_used(hass: HomeAssistant, name: str) -> bool:
    target = name.strip().lower()
    for entry in hass.config_entries.async_entries(DOMAIN):
        if entry.title.strip().lower() == target:
            return True
    return False


def _validate_price_source(
    hass: HomeAssistant, data: Mapping[str, Any]
) -> tuple[dict[str, str], str | None]:
    state = hass.states.get(data[CONF_PRICE_ENTITY])
    if state is None:
        return {CONF_PRICE_ENTITY: "entity_not_found"}, None
    attr = state.attributes.get(data[CONF_PRICE_ATTRIBUTE])
    if attr is None:
        return {CONF_PRICE_ATTRIBUTE: "attribute_not_found"}, ", ".join(
            state.attributes.keys()
        )
    if not isinstance(attr, list) or not attr:
        return {CONF_PRICE_ATTRIBUTE: "attribute_not_a_list"}, None
    first = attr[0]
    if not isinstance(first, Mapping):
        return {CONF_PRICE_ATTRIBUTE: "entries_not_dicts"}, None
    missing = [
        f for f in (data[CONF_START_FIELD], data[CONF_PRICE_FIELD]) if f not in first
    ]
    if missing:
        return {CONF_START_FIELD: "field_not_found"}, ", ".join(first.keys())
    return {}, None


_USER_SCHEMA = vol.Schema(
    {vol.Required(CONF_NAME, default=DEFAULT_NAME): str}
)

_PRICE_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_PRICE_ENTITY): selector.EntitySelector(
            selector.EntitySelectorConfig(domain=["sensor", "binary_sensor"])
        ),
        vol.Required(CONF_PRICE_ATTRIBUTE, default=DEFAULT_PRICE_ATTRIBUTE): str,
        vol.Required(CONF_START_FIELD, default=DEFAULT_START_FIELD): str,
        vol.Required(CONF_PRICE_FIELD, default=DEFAULT_PRICE_FIELD): str,
        vol.Optional(CONF_END_FIELD, default=DEFAULT_END_FIELD): str,
    }
)

_CHARGER_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_CHARGER_SWITCH): selector.EntitySelector(
            selector.EntitySelectorConfig(domain="switch")
        ),
        vol.Required(CONF_CHARGER_KW, default=DEFAULT_CHARGER_KW): (
            selector.NumberSelector(
                selector.NumberSelectorConfig(min=0.5, max=22, step=0.1, mode=_NM)
            )
        ),
    }
)


_CAR_SCHEMA = vol.Schema(
    {
        vol.Optional(CONF_SOC_ENTITY): selector.EntitySelector(
            selector.EntitySelectorConfig(domain="sensor")
        ),
        vol.Optional(CONF_TARGET_SOC_ENTITY): selector.EntitySelector(
            selector.EntitySelectorConfig(domain=["sensor", "number"])
        ),
        vol.Optional(CONF_CHARGING_STATUS_ENTITY): selector.EntitySelector(
            selector.EntitySelectorConfig(domain=["sensor", "binary_sensor"])
        ),
        vol.Optional(
            CONF_PLUG_UNPLUGGED_VALUES, default=DEFAULT_PLUG_UNPLUGGED_VALUES
        ): selector.TextSelector(selector.TextSelectorConfig(multiple=True)),
        vol.Optional(
            CONF_ACTIVELY_CHARGING_VALUES, default=DEFAULT_ACTIVELY_CHARGING_VALUES
        ): selector.TextSelector(selector.TextSelectorConfig(multiple=True)),
        vol.Optional(CONF_DEPARTURE_ENTITY): selector.EntitySelector(
            selector.EntitySelectorConfig()
        ),
        vol.Optional(CONF_BATTERY_KWH, default=DEFAULT_BATTERY_KWH): (
            selector.NumberSelector(
                selector.NumberSelectorConfig(min=1, max=200, step=0.1, mode=_NM)
            )
        ),
    }
)

_DEFAULTS_SCHEMA = vol.Schema(
    {
        vol.Required(
            CONF_DEFAULT_DEPARTURE, default=DEFAULT_DEPARTURE_TIME
        ): selector.TimeSelector(),
        vol.Optional(
            CONF_MIN_MINUTES_LEFT_IN_HOUR, default=DEFAULT_MIN_MINUTES_LEFT
        ): selector.NumberSelector(
            selector.NumberSelectorConfig(min=0, max=59, step=1, mode=_NM)
        ),
        vol.Optional(
            CONF_AUTO_REPLAN_ON_PRICE_UPDATE, default=DEFAULT_AUTO_REPLAN_ON_PRICE_UPDATE
        ): selector.BooleanSelector(),
        vol.Optional(
            CONF_AUTO_REPLAN_ON_SOC_CHANGE, default=DEFAULT_AUTO_REPLAN_ON_SOC_CHANGE
        ): selector.BooleanSelector(),
    }
)


class SmartEVConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    def __init__(self) -> None:
        self._data: dict[str, Any] = {}

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            if not user_input[CONF_NAME].strip():
                errors[CONF_NAME] = "name_empty"
            elif _name_already_used(self.hass, user_input[CONF_NAME]):
                return self.async_abort(reason="already_configured")
            else:
                self._data[CONF_NAME] = user_input[CONF_NAME].strip()
                return await self.async_step_price()
        return self.async_show_form(step_id="user", data_schema=_USER_SCHEMA, errors=errors)

    async def async_step_price(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        errors: dict[str, str] = {}
        peek: str | None = None
        if user_input is not None:
            errors, peek = _validate_price_source(self.hass, user_input)
            if not errors:
                self._data.update(user_input)
                return await self.async_step_charger()
        return self.async_show_form(
            step_id="price",
            data_schema=_PRICE_SCHEMA,
            errors=errors,
            description_placeholders={"peek": peek or ""},
        )

    async def async_step_charger(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        if user_input is not None:
            self._data.update(user_input)
            return await self.async_step_car()
        return self.async_show_form(step_id="charger", data_schema=_CHARGER_SCHEMA)

    async def async_step_car(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        if user_input is not None:
            self._data.update(user_input)
            return await self.async_step_defaults()
        return self.async_show_form(step_id="car", data_schema=_CAR_SCHEMA)

    async def async_step_defaults(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        if user_input is not None:
            self._data.update(user_input)
            return self.async_create_entry(title=self._data[CONF_NAME], data=self._data)
        return self.async_show_form(step_id="defaults", data_schema=_DEFAULTS_SCHEMA)

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> config_entries.OptionsFlow:
        return SmartEVOptionsFlow(config_entry)


class SmartEVOptionsFlow(config_entries.OptionsFlow):
    def __init__(self, entry: config_entries.ConfigEntry) -> None:
        self._entry = entry

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        if user_input is not None:
            errors, peek = _validate_price_source(
                self.hass, {**self._entry.data, **self._entry.options, **user_input}
            )
            if errors:
                return self.async_show_form(
                    step_id="init",
                    data_schema=self._build_schema(),
                    errors=errors,
                    description_placeholders={"peek": peek or ""},
                )
            return self.async_create_entry(title="", data=user_input)
        return self.async_show_form(step_id="init", data_schema=self._build_schema())

    def _build_schema(self) -> vol.Schema:
        merged: dict[str, Any] = {**self._entry.data, **self._entry.options}

        def d(key: str, fallback: object) -> object:
            return merged.get(key, fallback)

        return vol.Schema(
            {
                vol.Required(
                    CONF_PRICE_ENTITY, default=d(CONF_PRICE_ENTITY, vol.UNDEFINED)
                ): selector.EntitySelector(
                    selector.EntitySelectorConfig(domain=["sensor", "binary_sensor"])
                ),
                vol.Required(
                    CONF_PRICE_ATTRIBUTE,
                    default=d(CONF_PRICE_ATTRIBUTE, DEFAULT_PRICE_ATTRIBUTE),
                ): str,
                vol.Required(
                    CONF_START_FIELD, default=d(CONF_START_FIELD, DEFAULT_START_FIELD)
                ): str,
                vol.Required(
                    CONF_PRICE_FIELD, default=d(CONF_PRICE_FIELD, DEFAULT_PRICE_FIELD)
                ): str,
                vol.Optional(
                    CONF_END_FIELD, default=d(CONF_END_FIELD, DEFAULT_END_FIELD)
                ): str,
                vol.Required(
                    CONF_CHARGER_SWITCH,
                    default=d(CONF_CHARGER_SWITCH, vol.UNDEFINED),
                ): selector.EntitySelector(
                    selector.EntitySelectorConfig(domain="switch")
                ),
                vol.Required(
                    CONF_CHARGER_KW, default=d(CONF_CHARGER_KW, DEFAULT_CHARGER_KW)
                ): selector.NumberSelector(
                    selector.NumberSelectorConfig(min=0.5, max=22, step=0.1, mode=_NM)
                ),
                vol.Optional(
                    CONF_SOC_ENTITY, default=d(CONF_SOC_ENTITY, vol.UNDEFINED)
                ): selector.EntitySelector(
                    selector.EntitySelectorConfig(domain="sensor")
                ),
                vol.Optional(
                    CONF_TARGET_SOC_ENTITY,
                    default=d(CONF_TARGET_SOC_ENTITY, vol.UNDEFINED),
                ): selector.EntitySelector(
                    selector.EntitySelectorConfig(domain=["sensor", "number"])
                ),
                vol.Optional(
                    CONF_CHARGING_STATUS_ENTITY,
                    default=d(CONF_CHARGING_STATUS_ENTITY, vol.UNDEFINED),
                ): selector.EntitySelector(
                    selector.EntitySelectorConfig(domain=["sensor", "binary_sensor"])
                ),
                vol.Optional(
                    CONF_PLUG_UNPLUGGED_VALUES,
                    default=d(CONF_PLUG_UNPLUGGED_VALUES, DEFAULT_PLUG_UNPLUGGED_VALUES),
                ): selector.TextSelector(selector.TextSelectorConfig(multiple=True)),
                vol.Optional(
                    CONF_ACTIVELY_CHARGING_VALUES,
                    default=d(
                        CONF_ACTIVELY_CHARGING_VALUES, DEFAULT_ACTIVELY_CHARGING_VALUES
                    ),
                ): selector.TextSelector(selector.TextSelectorConfig(multiple=True)),
                vol.Optional(
                    CONF_DEPARTURE_ENTITY,
                    default=d(CONF_DEPARTURE_ENTITY, vol.UNDEFINED),
                ): selector.EntitySelector(selector.EntitySelectorConfig()),
                vol.Optional(
                    CONF_BATTERY_KWH, default=d(CONF_BATTERY_KWH, DEFAULT_BATTERY_KWH)
                ): selector.NumberSelector(
                    selector.NumberSelectorConfig(min=1, max=200, step=0.1, mode=_NM)
                ),
                vol.Required(
                    CONF_DEFAULT_DEPARTURE,
                    default=d(CONF_DEFAULT_DEPARTURE, DEFAULT_DEPARTURE_TIME),
                ): selector.TimeSelector(),
                vol.Optional(
                    CONF_MIN_MINUTES_LEFT_IN_HOUR,
                    default=d(CONF_MIN_MINUTES_LEFT_IN_HOUR, DEFAULT_MIN_MINUTES_LEFT),
                ): selector.NumberSelector(
                    selector.NumberSelectorConfig(min=0, max=59, step=1, mode=_NM)
                ),
                vol.Optional(
                    CONF_AUTO_REPLAN_ON_PRICE_UPDATE,
                    default=d(
                        CONF_AUTO_REPLAN_ON_PRICE_UPDATE,
                        DEFAULT_AUTO_REPLAN_ON_PRICE_UPDATE,
                    ),
                ): selector.BooleanSelector(),
                vol.Optional(
                    CONF_AUTO_REPLAN_ON_SOC_CHANGE,
                    default=d(
                        CONF_AUTO_REPLAN_ON_SOC_CHANGE, DEFAULT_AUTO_REPLAN_ON_SOC_CHANGE
                    ),
                ): selector.BooleanSelector(),
            }
        )
