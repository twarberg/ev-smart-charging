"""Coordinator for Smart EV Charging."""
from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, time, timedelta
from math import ceil
from typing import Any, Literal

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import Event, EventStateChangedData, HomeAssistant, callback
from homeassistant.helpers.event import async_track_state_change_event
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.util import dt as dt_util

from .car_state import CarState, CarStateConfig, read_car_state
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
    DEFAULT_MIN_MINUTES_LEFT,
    DEFAULT_PLUG_UNPLUGGED_VALUES,
    DOMAIN,
    EVENT_PLAN_UPDATED,
    EVENT_STARTED,
    EVENT_STOPPED,
    EVENT_TARGET_REACHED,
    HEARTBEAT_MINUTES,
    UNAVAILABLE_STATES,
)
from .planner import Plan, PlanInput, make_plan
from .price_source import PriceSource

_LOGGER = logging.getLogger(__name__)


@dataclass
class ChargeOverride:
    mode: Literal["force", "skip"]
    until: datetime | None


@dataclass
class CoordinatorData:
    plan: Plan
    car_state: CarState
    last_replan: datetime
    override: ChargeOverride | None
    charge_now: bool
    plan_status_label: str  # "ok" / "partial" / ... / "disabled" / "unplugged"
    debounced_plugged_in: bool
    actively_charging: bool
    slots_needed: int
    slots_needed_source: str  # "calculated" or "override"
    effective_departure_time: str  # "HH:MM"
    effective_departure_source: str  # "car" / "helper" / "default"


class SmartEVCoordinator(DataUpdateCoordinator[CoordinatorData]):
    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN}.{entry.entry_id}",
            update_interval=timedelta(minutes=HEARTBEAT_MINUTES),
        )
        self.entry = entry
        self._merged: dict[str, Any] = {**entry.data, **entry.options}
        self._price_source = PriceSource(
            hass=hass,  # type: ignore[arg-type]
            entity_id=self._merged[CONF_PRICE_ENTITY],
            attr_name=self._merged[CONF_PRICE_ATTRIBUTE],
            start_field=self._merged[CONF_START_FIELD],
            price_field=self._merged[CONF_PRICE_FIELD],
            end_field=self._merged.get(CONF_END_FIELD),
        )
        self._car_config = CarStateConfig(
            soc_entity=self._merged.get(CONF_SOC_ENTITY),
            target_soc_entity=self._merged.get(CONF_TARGET_SOC_ENTITY),
            charging_status_entity=self._merged.get(CONF_CHARGING_STATUS_ENTITY),
            plug_unplugged_values=list(
                self._merged.get(CONF_PLUG_UNPLUGGED_VALUES, DEFAULT_PLUG_UNPLUGGED_VALUES)
            ),
            actively_charging_values=list(
                self._merged.get(CONF_ACTIVELY_CHARGING_VALUES, DEFAULT_ACTIVELY_CHARGING_VALUES)
            ),
            departure_entity=self._merged.get(CONF_DEPARTURE_ENTITY),
        )
        self._unsub: list[Callable[[], None]] = []
        self._last_plug_known: bool = False
        self._master_enabled: bool = True
        self._slots_override: int = 3
        self._target_soc_override: float = 80.0
        self._departure_fallback: time | None = None
        self._override: ChargeOverride | None = None
        self._last_charge_now: bool = False

    async def async_setup(self) -> None:
        replan_on_price = bool(
            self._merged.get(CONF_AUTO_REPLAN_ON_PRICE_UPDATE, DEFAULT_AUTO_REPLAN_ON_PRICE_UPDATE)
        )
        replan_on_soc = bool(
            self._merged.get(CONF_AUTO_REPLAN_ON_SOC_CHANGE, DEFAULT_AUTO_REPLAN_ON_SOC_CHANGE)
        )
        ids: list[str | None] = []
        if replan_on_price:
            ids.append(self._merged.get(CONF_PRICE_ENTITY))
        if replan_on_soc:
            ids.append(self._merged.get(CONF_SOC_ENTITY))
        # Target SoC, charging status, and departure are control inputs —
        # changes there should always trigger a replan regardless of flags.
        ids.append(self._merged.get(CONF_TARGET_SOC_ENTITY))
        ids.append(self._merged.get(CONF_CHARGING_STATUS_ENTITY))
        ids.append(self._merged.get(CONF_DEPARTURE_ENTITY))
        watch = [e for e in ids if e]
        if watch:
            self._unsub.append(
                async_track_state_change_event(self.hass, watch, self._handle_state_change)
            )

    @callback
    def _handle_state_change(self, _event: Event[EventStateChangedData]) -> None:
        self.hass.async_create_task(self.async_request_refresh())

    async def async_unload(self) -> None:
        for unsub in self._unsub:
            unsub()
        self._unsub.clear()

    async def async_replan(self) -> None:
        await self.async_refresh()

    def set_master_enabled(self, value: bool) -> None:
        self._master_enabled = value
        if not value:
            self._override = None
        self.hass.async_create_task(self.async_request_refresh())

    def set_slots_override(self, value: int) -> None:
        self._slots_override = max(1, int(value))
        self.hass.async_create_task(self.async_request_refresh())

    def set_target_soc_override(self, value: float) -> None:
        self._target_soc_override = float(value)
        self.hass.async_create_task(self.async_request_refresh())

    def set_departure_fallback(self, value: time | None) -> None:
        self._departure_fallback = value
        self.hass.async_create_task(self.async_request_refresh())

    def apply_override(self, mode: Literal["force", "skip"], until: datetime | None) -> None:
        if mode == "skip" and until is None:
            raise ValueError("skip override requires a non-None until datetime")
        self._override = ChargeOverride(mode=mode, until=until)
        self.hass.async_create_task(self.async_request_refresh())

    def _slots_needed(self, car: CarState) -> int:
        soc = car.soc_percent
        target = (
            car.target_soc_percent
            if car.target_soc_percent is not None
            else self._target_soc_override
        )
        battery_kwh = float(self._merged.get(CONF_BATTERY_KWH, DEFAULT_BATTERY_KWH))
        charger_kw = float(self._merged.get(CONF_CHARGER_KW, DEFAULT_CHARGER_KW))
        if soc is None:
            return self._slots_override
        if soc >= target:
            return 1
        buffer = 1.05 if target <= 80 else 1.10
        kwh_needed = max(0.0, (target - soc) / 100.0 * battery_kwh)
        hours_raw = kwh_needed / charger_kw * buffer
        return max(1, ceil(hours_raw))

    def _resolve_departure(self, car: CarState, now: datetime) -> tuple[datetime, str]:
        time_part: time | None = None
        source = "default"
        if car.departure is not None:
            time_part = car.departure
            source = "car"
        elif self._departure_fallback is not None:
            time_part = self._departure_fallback
            source = "helper"
        if time_part is None:
            txt = str(self._merged.get(CONF_DEFAULT_DEPARTURE, DEFAULT_DEPARTURE_TIME))
            parts = txt.split(":")
            time_part = time(int(parts[0]), int(parts[1]) if len(parts) > 1 else 0)
        today = now.replace(
            hour=time_part.hour, minute=time_part.minute, second=0, microsecond=0
        )
        deadline = today if today > now else today + timedelta(days=1)
        return deadline, source

    def _debounce_plug(self, car: CarState) -> bool:
        raw = car.plug_raw_state
        if raw is None:
            self._last_plug_known = car.plugged_in
            return car.plugged_in
        if raw in UNAVAILABLE_STATES:
            return self._last_plug_known
        plugged = raw not in self._car_config.plug_unplugged_values
        self._last_plug_known = plugged
        return plugged

    def _evaluate_charge_now(
        self,
        plan: Plan,
        car: CarState,
        debounced_plugged: bool,
        now: datetime,
    ) -> tuple[bool, str, str | None]:
        """Return (charge_now, status_label, stop_reason_if_off).

        Priority order matches spec § 5 Layer 3 step 4.
        """
        if not self._master_enabled:
            return False, "disabled", "disabled"

        target = (
            car.target_soc_percent
            if car.target_soc_percent is not None
            else self._target_soc_override
        )
        soc = car.soc_percent

        # Expire override if it has a deadline that's now in the past.
        override = self._override
        override_expired = False
        if override is not None and override.until is not None and now >= override.until:
            override = None
            self._override = None
            override_expired = True

        # Force override: charge as long as SoC < target (or unknown).
        if override is not None and override.mode == "force" and (soc is None or soc < target):
            return True, plan.status, None

        skip_active = (
            override is not None
            and override.mode == "skip"
            and override.until is not None
            and now < override.until
        )
        if skip_active:
            return False, plan.status, "skip"

        if not debounced_plugged:
            return False, "unplugged", "unplugged"

        if soc is not None and target is not None and soc >= target:
            # Clear lingering force override when target reached.
            if self._override is not None and self._override.mode == "force":
                self._override = None
            return False, plan.status, "target_reached"

        this_hour = now.replace(minute=0, second=0, microsecond=0)
        if this_hour in plan.selected_starts:
            return True, plan.status, None
        return False, plan.status, "override_expired" if override_expired else "plan_end"

    def _start_reason(self) -> str:
        if self._override is not None and self._override.mode == "force":
            return "force"
        return "plan"

    async def _apply_charger(
        self,
        charge_now: bool,
        stop_reason: str | None,
        prev_soc: float | None,
        car: CarState,
    ) -> None:
        switch_id = self._merged[CONF_CHARGER_SWITCH]
        if charge_now and not self._last_charge_now:
            await self.hass.services.async_call(
                "switch", "turn_on", {"entity_id": switch_id}, blocking=False
            )
            self.hass.bus.async_fire(
                EVENT_STARTED,
                {"entry_id": self.entry.entry_id, "reason": self._start_reason()},
            )
        elif not charge_now and self._last_charge_now:
            await self.hass.services.async_call(
                "switch", "turn_off", {"entity_id": switch_id}, blocking=False
            )
            self.hass.bus.async_fire(
                EVENT_STOPPED,
                {"entry_id": self.entry.entry_id, "reason": stop_reason or "plan_end"},
            )
        effective_target = (
            car.target_soc_percent
            if car.target_soc_percent is not None
            else self._target_soc_override
        )
        if (
            self._last_charge_now
            and prev_soc is not None
            and car.soc_percent is not None
            and prev_soc < effective_target
            and car.soc_percent >= effective_target
        ):
            self.hass.bus.async_fire(
                EVENT_TARGET_REACHED,
                {"entry_id": self.entry.entry_id, "final_soc": car.soc_percent},
            )
        self._last_charge_now = charge_now

    async def _async_update_data(self) -> CoordinatorData:
        now = dt_util.now()
        car = read_car_state(self.hass, self._car_config)  # type: ignore[arg-type]
        debounced_plugged = self._debounce_plug(car)
        prices = self._price_source.get_slots()
        slots_needed = self._slots_needed(car)
        deadline, departure_source = self._resolve_departure(car, now)
        plan = make_plan(
            PlanInput(
                prices=prices,
                slots_needed=slots_needed,
                departure=deadline,
                now=now,
                min_minutes_left_in_hour=int(
                    self._merged.get(CONF_MIN_MINUTES_LEFT_IN_HOUR, DEFAULT_MIN_MINUTES_LEFT)
                ),
            )
        )

        # Spec § 5.8: clear any active override the moment the car is unplugged.
        # Done before _evaluate_charge_now so the force-override branch can't fire
        # on an unplugged car.
        if not debounced_plugged and self._override is not None:
            self._override = None

        prev_soc = self.data.car_state.soc_percent if self.data is not None else None
        charge_now, status_label, stop_reason = self._evaluate_charge_now(
            plan, car, debounced_plugged, now
        )
        await self._apply_charger(charge_now, stop_reason, prev_soc, car)

        # Override the planner status if master is off or unplugged.
        if not self._master_enabled:
            status_label = "disabled"
        elif not debounced_plugged:
            status_label = "unplugged"

        slots_needed_source = "calculated" if car.soc_percent is not None else "override"
        effective_departure_time = plan.initial_deadline.strftime("%H:%M")
        # When no charging-status entity is configured, we can't observe physical
        # charging state, so we mirror the integration's own intent (charge_now).
        if self._car_config.charging_status_entity is None:
            actively_charging = charge_now
        else:
            actively_charging = car.actively_charging

        data = CoordinatorData(
            plan=plan,
            car_state=car,
            last_replan=now,
            override=self._override,
            charge_now=charge_now,
            plan_status_label=status_label,
            debounced_plugged_in=debounced_plugged,
            actively_charging=actively_charging,
            slots_needed=slots_needed,
            slots_needed_source=slots_needed_source,
            effective_departure_time=effective_departure_time,
            effective_departure_source=departure_source,
        )

        # Only fire plan_updated when something downstream subscribers care about
        # actually changed. The 30-minute heartbeat would otherwise spam 48 events per day.
        prev = self.data
        plan_changed = (
            prev is None
            or prev.plan.status != plan.status
            or prev.plan.was_extended != plan.was_extended
            or prev.plan.deadline != plan.deadline
            or prev.plan.selected_starts != plan.selected_starts
        )
        if plan_changed:
            self.hass.bus.async_fire(
                EVENT_PLAN_UPDATED,
                {
                    "entry_id": self.entry.entry_id,
                    "status": plan.status,
                    "selected_starts": [s.isoformat() for s in plan.selected_starts],
                    "deadline": plan.deadline.isoformat(),
                    "was_extended": plan.was_extended,
                },
            )
        return data
