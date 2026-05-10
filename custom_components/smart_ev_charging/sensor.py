"""Sensors for Smart EV Charging."""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import SmartEVCoordinator

_ICONS = {
    "ok": "mdi:check-circle",
    "partial": "mdi:alert-circle",
    "extended": "mdi:clock-fast",
    "no_data": "mdi:database-off",
    "unplugged": "mdi:power-plug-off",
    "disabled": "mdi:cancel",
}


class _Base(CoordinatorEntity[SmartEVCoordinator], SensorEntity):
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


class PlanStatusSensor(_Base):
    @property
    def native_value(self) -> str:
        return self.coordinator.data.plan_status_label

    @property
    def icon(self) -> str:
        return _ICONS.get(self.coordinator.data.plan_status_label, "mdi:car-electric")

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        ov = self.coordinator.data.override
        return {
            "override_mode": ov.mode if ov else None,
            "override_until": ov.until.isoformat() if ov and ov.until else None,
        }


class PlannedHoursSensor(_Base):
    _attr_native_unit_of_measurement = "h"

    @property
    def native_value(self) -> int:
        return len(self.coordinator.data.plan.selected_starts)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        starts = self.coordinator.data.plan.selected_starts
        return {
            "hours": [s.isoformat() for s in starts],
            "next_charge_start": starts[0].isoformat() if starts else None,
            "next_charge_end": (starts[-1] + timedelta(hours=1)).isoformat() if starts else None,
        }


class SlotsNeededSensor(_Base):
    _attr_native_unit_of_measurement = "h"

    @property
    def native_value(self) -> int:
        return self.coordinator.data.slots_needed

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return {"source": self.coordinator.data.slots_needed_source}


class ActiveDeadlineSensor(_Base):
    _attr_device_class = SensorDeviceClass.TIMESTAMP

    @property
    def native_value(self) -> datetime:
        return self.coordinator.data.plan.deadline

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        plan = self.coordinator.data.plan
        return {
            "was_extended": plan.was_extended,
            "initial_deadline": plan.initial_deadline.isoformat(),
        }


class EffectiveDepartureSensor(_Base):
    @property
    def native_value(self) -> str:
        return self.coordinator.data.effective_departure_time

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return {"source": self.coordinator.data.effective_departure_source}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: SmartEVCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        [
            PlanStatusSensor(coordinator, "plan_status", "plan_status"),
            PlannedHoursSensor(coordinator, "planned_hours", "planned_hours"),
            SlotsNeededSensor(coordinator, "slots_needed", "slots_needed"),
            ActiveDeadlineSensor(coordinator, "active_deadline", "active_deadline"),
            EffectiveDepartureSensor(coordinator, "effective_departure", "effective_departure"),
        ]
    )
