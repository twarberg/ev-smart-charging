"""Smart EV Charging constants."""
from __future__ import annotations

from typing import Final

DOMAIN: Final = "smart_ev_charging"

PLATFORMS: Final = ["sensor", "binary_sensor", "switch", "number", "datetime"]

# Config keys
CONF_NAME: Final = "name"
CONF_PRICE_ENTITY: Final = "price_entity"
CONF_PRICE_ATTRIBUTE: Final = "price_attribute"
CONF_START_FIELD: Final = "start_field"
CONF_PRICE_FIELD: Final = "price_field"
CONF_END_FIELD: Final = "end_field"
CONF_CHARGER_SWITCH: Final = "charger_switch"
CONF_CHARGER_KW: Final = "charger_kw"
CONF_SOC_ENTITY: Final = "soc_entity"
CONF_TARGET_SOC_ENTITY: Final = "target_soc_entity"
CONF_CHARGING_STATUS_ENTITY: Final = "charging_status_entity"
CONF_PLUG_UNPLUGGED_VALUES: Final = "plug_unplugged_values"
CONF_ACTIVELY_CHARGING_VALUES: Final = "actively_charging_values"
CONF_DEPARTURE_ENTITY: Final = "departure_entity"
CONF_BATTERY_KWH: Final = "battery_kwh"
CONF_DEFAULT_DEPARTURE: Final = "default_departure"
CONF_MIN_MINUTES_LEFT_IN_HOUR: Final = "min_minutes_left_in_hour"
CONF_AUTO_REPLAN_ON_PRICE_UPDATE: Final = "auto_replan_on_price_update"
CONF_AUTO_REPLAN_ON_SOC_CHANGE: Final = "auto_replan_on_soc_change"
CONF_MIN_SOC_THRESHOLD: Final = "min_soc_threshold"

# Defaults
DEFAULT_NAME: Final = "EV"
DEFAULT_PRICE_ATTRIBUTE: Final = "prices"
DEFAULT_START_FIELD: Final = "start"
DEFAULT_PRICE_FIELD: Final = "price"
DEFAULT_END_FIELD: Final = "end"
DEFAULT_CHARGER_KW: Final = 11.0
DEFAULT_BATTERY_KWH: Final = 31.2
DEFAULT_PLUG_UNPLUGGED_VALUES: Final = ["3", "unplugged", "Unplugged", "UNPLUGGED"]
DEFAULT_ACTIVELY_CHARGING_VALUES: Final = ["0", "charging", "Charging", "CHARGING"]
DEFAULT_DEPARTURE_TIME: Final = "08:00:00"
DEFAULT_MIN_MINUTES_LEFT: Final = 15
DEFAULT_AUTO_REPLAN_ON_PRICE_UPDATE: Final = True
DEFAULT_AUTO_REPLAN_ON_SOC_CHANGE: Final = False
DEFAULT_MIN_SOC_THRESHOLD: Final = 100

# Heartbeat
HEARTBEAT_MINUTES: Final = 30

# Sentinels for HA states that mean "no value"
UNAVAILABLE_STATES: Final = frozenset({"unknown", "unavailable", "none", ""})

# Events
EVENT_PLAN_UPDATED: Final = "smart_ev_charging_plan_updated"
EVENT_STARTED: Final = "smart_ev_charging_started"
EVENT_STOPPED: Final = "smart_ev_charging_stopped"
EVENT_TARGET_REACHED: Final = "smart_ev_charging_target_reached"

# Service names
SERVICE_REPLAN: Final = "replan"
SERVICE_FORCE_CHARGE_NOW: Final = "force_charge_now"
SERVICE_SKIP_UNTIL: Final = "skip_until"
SERVICE_SET_ONE_OFF_DEPARTURE: Final = "set_one_off_departure"
