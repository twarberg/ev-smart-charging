"""Binary sensors for Smart EV Charging."""
from __future__ import annotations

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import SmartEVCoordinator


class _BinaryBase(CoordinatorEntity[SmartEVCoordinator], BinarySensorEntity):
    _attr_has_entity_name = True

    def __init__(self, coordinator: SmartEVCoordinator, key: str, translation_key: str) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.entry.entry_id}_{key}"
        self._attr_translation_key = translation_key

    @property
    def device_info(self) -> DeviceInfo:
        return DeviceInfo(
            identifiers={(DOMAIN, self.coordinator.entry.entry_id)},
            name=self.coordinator.entry.title,
            manufacturer="Smart EV Charging",
            model="Charging planner",
        )


class PluggedInBinary(_BinaryBase):
    _attr_device_class = BinarySensorDeviceClass.PLUG

    @property
    def is_on(self) -> bool:
        return self.coordinator.data.debounced_plugged_in


class ActivelyChargingBinary(_BinaryBase):
    _attr_device_class = BinarySensorDeviceClass.BATTERY_CHARGING

    @property
    def is_on(self) -> bool:
        return self.coordinator.data.actively_charging


class ChargeNowBinary(_BinaryBase):
    _attr_device_class = BinarySensorDeviceClass.POWER

    @property
    def is_on(self) -> bool:
        return self.coordinator.data.charge_now


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: SmartEVCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        [
            PluggedInBinary(coordinator, "plugged_in", "plugged_in"),
            ActivelyChargingBinary(coordinator, "actively_charging", "actively_charging"),
            ChargeNowBinary(coordinator, "charge_now", "charge_now"),
        ]
    )
