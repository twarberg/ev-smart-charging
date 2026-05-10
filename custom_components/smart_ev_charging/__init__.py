"""Smart EV Charging integration."""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

import voluptuous as vol
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.util import dt as dt_util

from .const import (
    DOMAIN,
    PLATFORMS,
    SERVICE_FORCE_CHARGE_NOW,
    SERVICE_REPLAN,
    SERVICE_SKIP_UNTIL,
)
from .coordinator import SmartEVCoordinator

_REPLAN_SCHEMA = vol.Schema({}, extra=vol.ALLOW_EXTRA)
_FORCE_SCHEMA = vol.Schema({vol.Optional("duration"): cv.time_period}, extra=vol.ALLOW_EXTRA)
_SKIP_SCHEMA = vol.Schema({vol.Required("until"): cv.datetime}, extra=vol.ALLOW_EXTRA)


def _resolve_coordinators(hass: HomeAssistant, call: ServiceCall) -> list[SmartEVCoordinator]:
    bucket: dict[str, SmartEVCoordinator] = hass.data.get(DOMAIN, {})
    targeted_entries: set[str] = set()
    ent_reg = er.async_get(hass)
    dev_reg = dr.async_get(hass)
    raw_entities = call.data.get("entity_id") or []
    if isinstance(raw_entities, str):
        raw_entities = [raw_entities]
    for entity_id in raw_entities:
        ent = ent_reg.async_get(entity_id)
        if ent is not None and ent.config_entry_id in bucket:
            targeted_entries.add(ent.config_entry_id)
    raw_devices = call.data.get("device_id") or []
    if isinstance(raw_devices, str):
        raw_devices = [raw_devices]
    for device_id in raw_devices:
        device_entry = dev_reg.async_get(device_id)
        if device_entry is not None:
            for entry_id in device_entry.config_entries:
                if entry_id in bucket:
                    targeted_entries.add(entry_id)
    if not targeted_entries:
        targeted_entries = set(bucket.keys())
    return [bucket[entry_id] for entry_id in targeted_entries if entry_id in bucket]


async def _register_services(hass: HomeAssistant) -> None:
    if hass.services.has_service(DOMAIN, SERVICE_REPLAN):
        return

    async def _replan(call: ServiceCall) -> None:
        for c in _resolve_coordinators(hass, call):
            await c.async_replan()

    async def _force(call: ServiceCall) -> None:
        duration: timedelta | None = call.data.get("duration")
        until = dt_util.now() + duration if duration is not None else None
        for c in _resolve_coordinators(hass, call):
            c.apply_override("force", until=until)

    async def _skip(call: ServiceCall) -> None:
        until: datetime = call.data["until"]
        if until.tzinfo is None:
            until = dt_util.as_local(until)
        for c in _resolve_coordinators(hass, call):
            c.apply_override("skip", until=until)

    hass.services.async_register(DOMAIN, SERVICE_REPLAN, _replan, schema=_REPLAN_SCHEMA)
    hass.services.async_register(
        DOMAIN, SERVICE_FORCE_CHARGE_NOW, _force, schema=_FORCE_SCHEMA
    )
    hass.services.async_register(DOMAIN, SERVICE_SKIP_UNTIL, _skip, schema=_SKIP_SCHEMA)


async def async_setup(hass: HomeAssistant, config: dict[str, Any]) -> bool:
    await _register_services(hass)
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    coordinator = SmartEVCoordinator(hass, entry)
    await coordinator.async_setup()
    await coordinator.async_config_entry_first_refresh()
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_options_updated))
    await _register_services(hass)
    return True


async def _async_options_updated(hass: HomeAssistant, entry: ConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    coordinator: SmartEVCoordinator = hass.data[DOMAIN][entry.entry_id]
    await coordinator.async_unload()
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        hass.data[DOMAIN].pop(entry.entry_id, None)
    return unloaded
