"""Master enable switch."""
from __future__ import annotations

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import SmartEVCoordinator


class SmartChargingSwitch(CoordinatorEntity[SmartEVCoordinator], SwitchEntity, RestoreEntity):
    _attr_has_entity_name = True
    _attr_translation_key = "smart_charging_enabled"

    def __init__(self, coordinator: SmartEVCoordinator) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.entry.entry_id}_smart_charging_enabled"
        self._is_on: bool = True

    @property
    def device_info(self) -> DeviceInfo:
        return DeviceInfo(
            identifiers={(DOMAIN, self.coordinator.entry.entry_id)},
            name=self.coordinator.entry.title,
            manufacturer="Smart EV Charging",
            model="Charging planner",
        )

    @property
    def is_on(self) -> bool:
        return self._is_on

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        last_state = await self.async_get_last_state()
        if last_state is not None:
            self._is_on = last_state.state == "on"
            self.coordinator.set_master_enabled(self._is_on)

    async def async_turn_on(self, **kwargs: object) -> None:
        self._is_on = True
        self.coordinator.set_master_enabled(True)
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs: object) -> None:
        self._is_on = False
        self.coordinator.set_master_enabled(False)
        self.async_write_ha_state()


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: SmartEVCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([SmartChargingSwitch(coordinator)])
