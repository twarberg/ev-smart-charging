"""Conditional fallback departure datetime."""
from __future__ import annotations

import contextlib
from datetime import datetime, time

from homeassistant.components.datetime import DateTimeEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import dt as dt_util

from .const import (
    CONF_DEFAULT_DEPARTURE,
    CONF_DEPARTURE_ENTITY,
    DEFAULT_DEPARTURE_TIME,
    DOMAIN,
)
from .coordinator import SmartEVCoordinator


class DepartureFallbackDateTime(
    CoordinatorEntity[SmartEVCoordinator], DateTimeEntity, RestoreEntity
):
    _attr_has_entity_name = True
    _attr_translation_key = "departure_fallback"

    def __init__(self, coordinator: SmartEVCoordinator) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.entry.entry_id}_departure_fallback"
        merged = {**coordinator.entry.data, **coordinator.entry.options}
        default_time = str(merged.get(CONF_DEFAULT_DEPARTURE, DEFAULT_DEPARTURE_TIME))
        parts = default_time.split(":")
        h = int(parts[0])
        m = int(parts[1]) if len(parts) > 1 else 0
        today = dt_util.now().replace(hour=h, minute=m, second=0, microsecond=0)
        self._value: datetime = today

    @property
    def device_info(self) -> DeviceInfo:
        return DeviceInfo(
            identifiers={(DOMAIN, self.coordinator.entry.entry_id)},
            name=self.coordinator.entry.title,
            manufacturer="Smart EV Charging",
            model="Charging planner",
        )

    @property
    def native_value(self) -> datetime:
        return self._value

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        last = await self.async_get_last_state()
        if last is not None:
            with contextlib.suppress(TypeError, ValueError):
                self._value = datetime.fromisoformat(last.state)
            self.coordinator.set_departure_fallback(time(self._value.hour, self._value.minute))

    async def async_set_value(self, value: datetime) -> None:
        self._value = value
        self.coordinator.set_departure_fallback(time(value.hour, value.minute))
        self.async_write_ha_state()


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: SmartEVCoordinator = hass.data[DOMAIN][entry.entry_id]
    merged = {**entry.data, **entry.options}
    if not merged.get(CONF_DEPARTURE_ENTITY):
        async_add_entities([DepartureFallbackDateTime(coordinator)])
