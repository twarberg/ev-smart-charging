"""Conditional fallback number entities."""
from __future__ import annotations

import contextlib

from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    CONF_SOC_ENTITY,
    CONF_TARGET_SOC_ENTITY,
    DOMAIN,
)
from .coordinator import SmartEVCoordinator


class _NumberBase(CoordinatorEntity[SmartEVCoordinator], NumberEntity, RestoreEntity):
    _attr_has_entity_name = True
    _attr_mode = NumberMode.SLIDER

    def __init__(
        self,
        coordinator: SmartEVCoordinator,
        key: str,
        translation_key: str,
        default: float,
    ) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.entry.entry_id}_{key}"
        self._attr_translation_key = translation_key
        self._value: float = default

    @property
    def device_info(self) -> DeviceInfo:
        return DeviceInfo(
            identifiers={(DOMAIN, self.coordinator.entry.entry_id)},
            name=self.coordinator.entry.title,
            manufacturer="Smart EV Charging",
            model="Charging planner",
        )

    @property
    def native_value(self) -> float:
        return self._value

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        last = await self.async_get_last_state()
        if last is not None:
            with contextlib.suppress(TypeError, ValueError):
                self._value = float(last.state)
            self._sync()

    def _sync(self) -> None:
        raise NotImplementedError


class TargetSoCNumber(_NumberBase):
    _attr_native_min_value = 50
    _attr_native_max_value = 100
    _attr_native_step = 5

    def __init__(self, coordinator: SmartEVCoordinator) -> None:
        super().__init__(
            coordinator, key="target_soc", translation_key="target_soc", default=80.0
        )

    def _sync(self) -> None:
        self.coordinator.set_target_soc_override(self._value)

    async def async_set_native_value(self, value: float) -> None:
        self._value = float(value)
        self._sync()
        self.async_write_ha_state()


class ChargeSlotsOverrideNumber(_NumberBase):
    _attr_native_min_value = 1
    _attr_native_max_value = 12
    _attr_native_step = 1

    def __init__(self, coordinator: SmartEVCoordinator) -> None:
        super().__init__(
            coordinator,
            key="charge_slots_override",
            translation_key="charge_slots_override",
            default=3.0,
        )

    def _sync(self) -> None:
        self.coordinator.set_slots_override(int(self._value))

    async def async_set_native_value(self, value: float) -> None:
        self._value = float(value)
        self._sync()
        self.async_write_ha_state()


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: SmartEVCoordinator = hass.data[DOMAIN][entry.entry_id]
    merged = {**entry.data, **entry.options}
    entities: list[_NumberBase] = []
    if not merged.get(CONF_TARGET_SOC_ENTITY):
        entities.append(TargetSoCNumber(coordinator))
    if not merged.get(CONF_SOC_ENTITY):
        entities.append(ChargeSlotsOverrideNumber(coordinator))
    async_add_entities(entities)
