"""Adapter that reads a price-bearing entity and normalizes to PriceSlot list."""
from __future__ import annotations

import logging
from collections.abc import Mapping
from datetime import UTC, datetime, timedelta
from typing import Any, Protocol

from .const import UNAVAILABLE_STATES
from .planner import PriceSlot

_LOGGER = logging.getLogger(__name__)


class StateLike(Protocol):
    """Structural type for a HA-like state object."""

    state: str
    attributes: Mapping[str, Any]


class StatesLike(Protocol):
    """Structural type for hass.states."""

    def get(self, entity_id: str) -> StateLike | None: ...


class HassLike(Protocol):
    """Structural type for a HA-like core object."""

    states: StatesLike


def _parse_dt(value: object) -> datetime | None:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=UTC)
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(float(value), tz=UTC)
    if isinstance(value, str):
        try:
            dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
        return dt if dt.tzinfo else dt.replace(tzinfo=UTC)
    return None


class PriceSource:
    """Reads a price-bearing entity, normalizes to list[PriceSlot]."""

    def __init__(
        self,
        hass: HassLike,
        entity_id: str,
        attr_name: str,
        start_field: str,
        price_field: str,
        end_field: str | None = None,
    ) -> None:
        self._hass = hass
        self._entity_id = entity_id
        self._attr_name = attr_name
        self._start_field = start_field
        self._price_field = price_field
        self._end_field = end_field
        self._warned: set[str] = set()

    def _warn_once(self, key: str, msg: str) -> None:
        if key in self._warned:
            return
        self._warned.add(key)
        _LOGGER.warning("PriceSource(%s): %s", self._entity_id, msg)

    def get_slots(self) -> list[PriceSlot]:
        state = self._hass.states.get(self._entity_id)
        if state is None or state.state in UNAVAILABLE_STATES:
            self._warn_once("unavailable", "entity missing or unavailable")
            return []
        raw = state.attributes.get(self._attr_name)
        if raw is None:
            self._warn_once("attr_missing", f"attribute {self._attr_name!r} missing")
            return []
        if not isinstance(raw, list) or not raw:
            self._warn_once(
                "attr_not_list",
                f"attribute {self._attr_name!r} is not a non-empty list",
            )
            return []
        slots: list[PriceSlot] = []
        for entry in raw:
            if not isinstance(entry, Mapping):
                self._warn_once("entry_not_mapping", "entry is not a mapping; skipping")
                continue
            start = _parse_dt(entry.get(self._start_field))
            price = entry.get(self._price_field)
            if start is None or not isinstance(price, (int, float)):
                self._warn_once("entry_malformed", "entry missing start or price field; skipping")
                continue
            end_raw = entry.get(self._end_field) if self._end_field else None
            end = _parse_dt(end_raw) if end_raw is not None else start + timedelta(hours=1)
            if end is None:
                end = start + timedelta(hours=1)
            slots.append(PriceSlot(start=start, end=end, price=float(price)))
        slots.sort(key=lambda s: s.start)
        return slots
