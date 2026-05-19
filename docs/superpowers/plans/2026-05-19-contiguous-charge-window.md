# Contiguous Charge Window Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a `contiguous_block` config option (default on) that makes the planner pick one back-to-back block of `slots_needed` cheap hours instead of N scattered cheapest hours, exposed via sensor attribute and editable via the options flow.

**Architecture:** New boolean `PlanInput.contiguous` field with a sliding-window-of-N picker inside `make_plan` (lowest summed price, earliest-start tie-breaker). Coordinator reads `CONF_CONTIGUOUS_BLOCK` from merged config and passes it through. `PlanStatusSensor` surfaces the flag as a discovery attribute. Pure-planner module remains HA-free.

**Tech Stack:** Python 3.12, Home Assistant `custom_components`, `voluptuous` + HA `selector`, `pytest` + `pytest-homeassistant-custom-component`, `hypothesis`, `freezegun`.

---

## File Structure

| File | Role | Action |
|------|------|--------|
| `custom_components/smart_ev_charging/planner.py` | Pure picker | Modify: add `contiguous` field + sliding-window branch |
| `custom_components/smart_ev_charging/const.py` | Constants | Modify: add `CONF_CONTIGUOUS_BLOCK`, `DEFAULT_CONTIGUOUS_BLOCK` |
| `custom_components/smart_ev_charging/coordinator.py` | Glue | Modify: read flag, pass to `PlanInput`, add to `CoordinatorData` |
| `custom_components/smart_ev_charging/config_flow.py` | UI | Modify: add field to `_DEFAULTS_SCHEMA` and options-flow defaults |
| `custom_components/smart_ev_charging/sensor.py` | Discovery | Modify: expose `contiguous_block` on `PlanStatusSensor` |
| `custom_components/smart_ev_charging/translations/en.json` | i18n | Modify: label + help for the new field |
| `custom_components/smart_ev_charging/strings.json` | i18n source | Modify: mirror en.json |
| `tests/test_planner.py` | Planner tests | Modify: new contiguous cases, gate existing optimality property |
| `tests/test_coordinator.py` | Coord smoke | Modify: pass-through test |
| `tests/test_config_flow.py` | Flow tests | Modify: option appears, round-trips |
| `tests/test_sensor.py` | Sensor attr | Modify: new attribute assertion |
| `README.md` | Docs | Modify: discovery row + Options bullet |

---

### Task 1: Planner — add `contiguous` field + cheapest-contiguous-block branch

**Files:**
- Modify: `custom_components/smart_ev_charging/planner.py`
- Modify: `tests/test_planner.py`

- [ ] **Step 1: Add a failing test for cheapest-contiguous-block selection**

Edit `tests/test_planner.py`. Add the new test below `test_picks_three_cheapest_overnight` (so existing imports are reused). Add these tests verbatim:

```python
def test_contiguous_picks_cheapest_consecutive_window() -> None:
    """contiguous=True picks the cheapest run-of-N, not the globally cheapest N.

    Layout: 00:0.3, 01:1.0, 02:0.2, 03:1.0, 04:0.1, 05:0.4, 06:0.5
      Scatter cheapest 3 = {00,02,04} sum=0.6 (NOT contiguous).
      Contiguous 3-window sums:
        00..02 = 1.5
        01..03 = 2.2
        02..04 = 1.3
        03..05 = 1.5
        04..06 = 1.0  ← cheapest contiguous block
    """
    cph = ZoneInfo("Europe/Copenhagen")
    base = datetime(2026, 5, 10, 0, 0, tzinfo=cph)
    offsets = [0.3, 1.0, 0.2, 1.0, 0.1, 0.4, 0.5]
    prices = [
        PriceSlot(
            start=base + timedelta(hours=i),
            end=base + timedelta(hours=i + 1),
            price=offsets[i],
        )
        for i in range(len(offsets))
    ]
    plan = make_plan(
        PlanInput(
            prices=prices,
            slots_needed=3,
            departure=base + timedelta(hours=12),
            now=base - timedelta(minutes=1),
            contiguous=True,
        )
    )
    assert plan.status == "ok"
    assert list(plan.selected_starts) == [
        base + timedelta(hours=4),
        base + timedelta(hours=5),
        base + timedelta(hours=6),
    ]
    assert plan.selected_prices == (0.1, 0.4, 0.5)


def test_contiguous_tie_breaker_picks_earliest() -> None:
    """When two contiguous windows have equal sum, the earliest start wins."""
    cph = ZoneInfo("Europe/Copenhagen")
    base = datetime(2026, 5, 10, 0, 0, tzinfo=cph)
    # Two flat-priced blocks separated by a spike — both 2-windows sum to 2.0.
    offsets = [1.0, 1.0, 9.0, 1.0, 1.0]
    prices = [
        PriceSlot(
            start=base + timedelta(hours=i),
            end=base + timedelta(hours=i + 1),
            price=offsets[i],
        )
        for i in range(len(offsets))
    ]
    plan = make_plan(
        PlanInput(
            prices=prices,
            slots_needed=2,
            departure=base + timedelta(hours=12),
            now=base - timedelta(minutes=1),
            contiguous=True,
        )
    )
    assert list(plan.selected_starts) == [base, base + timedelta(hours=1)]


def test_contiguous_partial_returns_whole_window() -> None:
    """Window shorter than slots_needed: entire window is one contiguous block."""
    cph = ZoneInfo("Europe/Copenhagen")
    base = datetime(2026, 5, 10, 18, 0, tzinfo=cph)
    offsets = [5.0, 4.0, 6.0]
    prices = [
        PriceSlot(
            start=base + timedelta(hours=i),
            end=base + timedelta(hours=i + 1),
            price=offsets[i],
        )
        for i in range(3)
    ]
    plan = make_plan(
        PlanInput(
            prices=prices,
            slots_needed=10,
            departure=base + timedelta(hours=3),
            now=base - timedelta(minutes=1),
            contiguous=True,
        )
    )
    assert plan.status == "partial"
    assert len(plan.selected_starts) == 3
    assert list(plan.selected_starts) == [
        base, base + timedelta(hours=1), base + timedelta(hours=2)
    ]


def test_contiguous_false_matches_legacy_scatter() -> None:
    """contiguous=False keeps the global cheapest-N picker."""
    cph = ZoneInfo("Europe/Copenhagen")
    base = datetime(2026, 5, 10, 0, 0, tzinfo=cph)
    offsets = [0.3, 1.0, 0.2, 1.0, 0.1, 0.4, 0.5]
    prices = [
        PriceSlot(
            start=base + timedelta(hours=i),
            end=base + timedelta(hours=i + 1),
            price=offsets[i],
        )
        for i in range(len(offsets))
    ]
    plan = make_plan(
        PlanInput(
            prices=prices,
            slots_needed=3,
            departure=base + timedelta(hours=12),
            now=base - timedelta(minutes=1),
            contiguous=False,
        )
    )
    # Global cheapest 3 = hours 0, 2, 4 (prices 0.3, 0.2, 0.1) — NOT contiguous.
    assert set(plan.selected_starts) == {
        base,
        base + timedelta(hours=2),
        base + timedelta(hours=4),
    }
```

- [ ] **Step 2: Run the new tests to confirm they fail**

Run: `pytest tests/test_planner.py::test_contiguous_picks_cheapest_consecutive_window tests/test_planner.py::test_contiguous_tie_breaker_picks_earliest tests/test_planner.py::test_contiguous_partial_returns_whole_window tests/test_planner.py::test_contiguous_false_matches_legacy_scatter -v`
Expected: all FAIL with `TypeError: PlanInput.__init__() got an unexpected keyword argument 'contiguous'`.

- [ ] **Step 3: Implement the `contiguous` field + branching in `make_plan`**

Modify `custom_components/smart_ev_charging/planner.py`. Replace the file body so the final version reads:

```python
"""Pure Python charging planner. Zero Home Assistant imports — keep it that way."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Literal

PlanStatus = Literal["ok", "partial", "extended", "no_data"]

_SENTINEL_DT: datetime = datetime(1970, 1, 1, tzinfo=UTC)


@dataclass(frozen=True)
class PriceSlot:
    start: datetime
    end: datetime
    price: float


@dataclass(frozen=True)
class PlanInput:
    prices: list[PriceSlot]
    slots_needed: int
    departure: datetime
    now: datetime
    min_minutes_left_in_hour: int = 15
    contiguous: bool = True


@dataclass(frozen=True)
class Plan:
    selected_starts: tuple[datetime, ...] = ()
    selected_prices: tuple[float, ...] = ()
    deadline: datetime = _SENTINEL_DT
    initial_deadline: datetime = _SENTINEL_DT
    was_extended: bool = False
    window_size: int = 0
    status: PlanStatus = "no_data"


def _pick_contiguous(
    window: list[PriceSlot], n: int
) -> list[PriceSlot]:
    """Return the contiguous n-slot block with the lowest summed price.

    Tie-breaker: earliest start (we iterate left-to-right and update only on a
    strict-less-than, so the first occurrence wins).
    """
    best_i = 0
    best_sum = sum(s.price for s in window[:n])
    rolling = best_sum
    for i in range(1, len(window) - n + 1):
        rolling += window[i + n - 1].price - window[i - 1].price
        if rolling < best_sum:
            best_sum = rolling
            best_i = i
    return window[best_i : best_i + n]


def make_plan(inp: PlanInput) -> Plan:
    """Compute a charging plan. See spec § 5 Layer 1."""
    # Defensive non-negative clamp; 0 is a legitimate "no charge needed" signal
    # the caller can use when SoC is already at or above target.
    slots_needed = max(0, inp.slots_needed)
    prices = sorted(inp.prices, key=lambda s: s.start)

    this_hour_start = inp.now.replace(minute=0, second=0, microsecond=0)
    next_hour_start = this_hour_start + timedelta(hours=1)
    minutes_left = (next_hour_start - inp.now).total_seconds() / 60
    effective_start = (
        next_hour_start if minutes_left < inp.min_minutes_left_in_hour else this_hour_start
    )

    hours_until_deadline = (inp.departure - inp.now).total_seconds() / 3600
    if hours_until_deadline < 1:
        deadline = inp.departure + timedelta(hours=24)
        was_extended = True
    else:
        deadline = inp.departure
        was_extended = False

    window = [s for s in prices if effective_start <= s.start < deadline]
    effective_slots = min(slots_needed, len(window))

    if effective_slots == 0:
        chronological: list[PriceSlot] = []
    elif inp.contiguous and len(window) >= slots_needed:
        # Window has room for the full block — slide to find the cheapest.
        chronological = _pick_contiguous(window, slots_needed)
    elif inp.contiguous:
        # Window shorter than slots_needed: the whole window IS one contiguous
        # block (already sorted).
        chronological = list(window)
    else:
        # Legacy scatter behaviour: globally-cheapest N slots, then sort.
        cheapest = sorted(window, key=lambda s: s.price)[:effective_slots]
        chronological = sorted(cheapest, key=lambda s: s.start)

    selected_starts = tuple(s.start for s in chronological)
    selected_prices = tuple(s.price for s in chronological)

    if len(window) == 0:
        status: PlanStatus = "no_data"
    elif was_extended:
        status = "extended"
    elif len(window) < slots_needed:
        status = "partial"
    else:
        status = "ok"

    return Plan(
        selected_starts=selected_starts,
        selected_prices=selected_prices,
        deadline=deadline,
        initial_deadline=inp.departure,
        was_extended=was_extended,
        window_size=len(window),
        status=status,
    )
```

- [ ] **Step 4: Run the new tests to confirm they pass**

Run: `pytest tests/test_planner.py::test_contiguous_picks_cheapest_consecutive_window tests/test_planner.py::test_contiguous_tie_breaker_picks_earliest tests/test_planner.py::test_contiguous_partial_returns_whole_window tests/test_planner.py::test_contiguous_false_matches_legacy_scatter -v`
Expected: 4 PASS.

- [ ] **Step 5: Gate the existing global-optimality property test**

The existing `test_picker_optimality` asserts the picker is globally optimal across *all* combinations, which contiguous mode does not satisfy. Modify it to pass `contiguous=False` explicitly.

Open `tests/test_planner.py`, locate the `PlanInput(...)` literal inside `test_picker_optimality`, and add `contiguous=False,` after the `now=` argument. The call should read:

```python
plan = make_plan(
    PlanInput(
        prices=prices,
        slots_needed=slots,
        departure=departure,
        now=datetime(2026, 5, 10, 0, 0, tzinfo=CPH) - timedelta(minutes=1),
        contiguous=False,
    )
)
```

- [ ] **Step 6: Add a contiguous-optimality property test**

Append this property test to `tests/test_planner.py` (uses the existing `_build_prices` helper and `CPH` constant):

```python
@given(
    count=st.integers(min_value=1, max_value=24),
    slots=st.integers(min_value=1, max_value=12),
    delta_hours=st.integers(min_value=2, max_value=36),
    seed=st.integers(min_value=0, max_value=10_000),
)
@settings(max_examples=80, deadline=None)
def test_contiguous_picker_optimality(
    count: int, slots: int, delta_hours: int, seed: int
) -> None:
    """contiguous=True picks the lowest-summed contiguous run-of-N in the window."""
    import random

    rng = random.Random(seed)
    offsets = [rng.uniform(0.1, 5.0) for _ in range(count)]
    prices = _build_prices(start_hour=0, count=count, offsets=offsets)
    departure = datetime(2026, 5, 10, 0, 0, tzinfo=CPH) + timedelta(hours=delta_hours)
    plan = make_plan(
        PlanInput(
            prices=prices,
            slots_needed=slots,
            departure=departure,
            now=datetime(2026, 5, 10, 0, 0, tzinfo=CPH) - timedelta(minutes=1),
            contiguous=True,
        )
    )
    if plan.status == "no_data":
        assert plan.selected_starts == ()
        return
    assert list(plan.selected_starts) == sorted(plan.selected_starts)
    window = [
        p
        for p in prices
        if datetime(2026, 5, 10, 0, 0, tzinfo=CPH) <= p.start < plan.deadline
    ]
    selected = [p for p in prices if p.start in plan.selected_starts]
    assert len(selected) == min(slots, len(window))
    # When the window is smaller than slots_needed, the picker returns the whole
    # window; no optimality assertion beyond that.
    if len(window) < slots:
        assert {p.start for p in selected} == {p.start for p in window}
        return
    sel_total = sum(s.price for s in selected)
    # Selected block must be no more expensive than any other contiguous N-block.
    for i in range(0, len(window) - slots + 1):
        alt_total = sum(p.price for p in window[i : i + slots])
        assert sel_total <= alt_total + 1e-9
```

- [ ] **Step 7: Run the full planner test module**

Run: `pytest tests/test_planner.py -v`
Expected: all tests pass (existing + 5 new).

- [ ] **Step 8: Commit**

```bash
git add custom_components/smart_ev_charging/planner.py tests/test_planner.py
git commit -m "feat(planner): cheapest-contiguous-block picker behind PlanInput.contiguous"
```

---

### Task 2: Const + Coordinator wire-through

**Files:**
- Modify: `custom_components/smart_ev_charging/const.py`
- Modify: `custom_components/smart_ev_charging/coordinator.py`
- Modify: `tests/test_coordinator.py`

- [ ] **Step 1: Write the failing coordinator pass-through test**

Append to `tests/test_coordinator.py` (uses existing `_base_entry_data`, `_seed_prices`, `_setup_with_soc` helpers; add `CONF_CONTIGUOUS_BLOCK` to the existing const import block at the top of the file):

```python
@freeze_time("2026-05-11 02:30:00+02:00")
async def test_contiguous_block_default_on_picks_contiguous(
    hass: HomeAssistant,
) -> None:
    """No explicit flag → default contiguous=True → cheapest contiguous block."""
    async_mock_service(hass, "switch", "turn_on")
    async_mock_service(hass, "switch", "turn_off")
    entry = await _setup_with_soc(hass, soc=30.0, target=80.0)
    coordinator = hass.data[DOMAIN][entry.entry_id]
    starts = coordinator.data.plan.selected_starts
    # _seed_prices puts the cheapest stretch at 02-04, which is contiguous;
    # the assertion that matters here is that contiguous_block is reported True
    # and that starts are sorted (contract holds either way).
    assert coordinator.data.contiguous_block is True
    assert list(starts) == sorted(starts)


@freeze_time("2026-05-11 02:30:00+02:00")
async def test_contiguous_block_false_passes_through(hass: HomeAssistant) -> None:
    """Setting CONF_CONTIGUOUS_BLOCK=False propagates into CoordinatorData."""
    async_mock_service(hass, "switch", "turn_on")
    async_mock_service(hass, "switch", "turn_off")
    _seed_prices(hass)
    hass.states.async_set("sensor.car_soc", "30")
    hass.states.async_set("sensor.car_target", "80")
    hass.states.async_set("sensor.car_status", "0")
    data = _base_entry_data()
    data["soc_entity"] = "sensor.car_soc"
    data["target_soc_entity"] = "sensor.car_target"
    data["charging_status_entity"] = "sensor.car_status"
    data["plug_unplugged_values"] = ["3"]
    data["actively_charging_values"] = ["0"]
    data[CONF_CONTIGUOUS_BLOCK] = False
    entry = MockConfigEntry(domain=DOMAIN, title="Daily", data=data)
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    coordinator = hass.data[DOMAIN][entry.entry_id]
    assert coordinator.data.contiguous_block is False
```

Also extend the existing import block at the top of `tests/test_coordinator.py`:

```python
from custom_components.smart_ev_charging.const import (
    CONF_CHARGER_KW,
    CONF_CHARGER_SWITCH,
    CONF_CONTIGUOUS_BLOCK,
    CONF_DEFAULT_DEPARTURE,
    CONF_MIN_SOC_THRESHOLD,
    CONF_PRICE_ATTRIBUTE,
    CONF_PRICE_ENTITY,
    CONF_PRICE_FIELD,
    CONF_START_FIELD,
    DOMAIN,
    EVENT_PLAN_UPDATED,
    EVENT_TARGET_REACHED,
)
```

- [ ] **Step 2: Run the new tests; they must fail**

Run: `pytest tests/test_coordinator.py::test_contiguous_block_default_on_picks_contiguous tests/test_coordinator.py::test_contiguous_block_false_passes_through -v`
Expected: FAIL with `ImportError: cannot import name 'CONF_CONTIGUOUS_BLOCK'`.

- [ ] **Step 3: Add the constants**

Modify `custom_components/smart_ev_charging/const.py`. Add to the Config keys block (alphabetised next to `CONF_BATTERY_KWH`):

```python
CONF_CONTIGUOUS_BLOCK: Final = "contiguous_block"
```

Add to the Defaults block (next to `DEFAULT_BATTERY_KWH`):

```python
DEFAULT_CONTIGUOUS_BLOCK: Final = True
```

- [ ] **Step 4: Wire the flag into the coordinator**

Modify `custom_components/smart_ev_charging/coordinator.py`.

(a) Add to the const-import block:

```python
from .const import (
    ...
    CONF_CHARGER_SWITCH,
    CONF_CONTIGUOUS_BLOCK,
    ...
    DEFAULT_CHARGER_KW,
    DEFAULT_CONTIGUOUS_BLOCK,
    ...
)
```

(b) Add a new field to `CoordinatorData` (next to `min_soc_threshold`):

```python
@dataclass
class CoordinatorData:
    ...
    min_soc_threshold: float
    min_soc_gate_active: bool
    contiguous_block: bool  # mirrors CONF_CONTIGUOUS_BLOCK; default True
    ...
```

(c) In `_async_update_data`, read the flag and pass it into `PlanInput`:

Find the existing `plan = make_plan(PlanInput(...))` block and add `contiguous=` to it. After the change it should read:

```python
contiguous_block = bool(
    self._merged.get(CONF_CONTIGUOUS_BLOCK, DEFAULT_CONTIGUOUS_BLOCK)
)
plan = make_plan(
    PlanInput(
        prices=prices,
        slots_needed=slots_needed,
        departure=deadline,
        now=now,
        min_minutes_left_in_hour=int(
            self._merged.get(CONF_MIN_MINUTES_LEFT_IN_HOUR, DEFAULT_MIN_MINUTES_LEFT)
        ),
        contiguous=contiguous_block,
    )
)
```

(d) Populate the new `CoordinatorData` field in the `data = CoordinatorData(...)` constructor at the bottom of `_async_update_data`. Add the line next to `min_soc_gate_active=...`:

```python
data = CoordinatorData(
    ...
    min_soc_threshold=min_soc_threshold,
    min_soc_gate_active=min_soc_gate_active,
    contiguous_block=contiguous_block,
    ...
)
```

- [ ] **Step 5: Run the coordinator pass-through tests; they must pass**

Run: `pytest tests/test_coordinator.py::test_contiguous_block_default_on_picks_contiguous tests/test_coordinator.py::test_contiguous_block_false_passes_through -v`
Expected: 2 PASS.

- [ ] **Step 6: Run the full coordinator module**

Run: `pytest tests/test_coordinator.py -v`
Expected: all tests pass (no existing tests should regress; existing fixture's cheapest 3 hours 02/03/04 are already contiguous so default-on does not perturb them).

- [ ] **Step 7: Commit**

```bash
git add custom_components/smart_ev_charging/const.py custom_components/smart_ev_charging/coordinator.py tests/test_coordinator.py
git commit -m "feat(coordinator): wire contiguous_block flag through to planner"
```

---

### Task 3: Config flow — surface `contiguous_block` in Defaults step + Options flow

**Files:**
- Modify: `custom_components/smart_ev_charging/config_flow.py`
- Modify: `custom_components/smart_ev_charging/translations/en.json`
- Modify: `custom_components/smart_ev_charging/strings.json`
- Modify: `tests/test_config_flow.py`

- [ ] **Step 1: Write the failing options-flow round-trip test**

Append to `tests/test_config_flow.py`. This mirrors the existing `test_options_flow_can_change_default_departure` pattern (lines 171–205): seed price + switch, build entry with the same minimum fields, submit a flat options dict that includes the new flag set to False.

```python
async def test_options_flow_round_trips_contiguous_block_false(
    hass: HomeAssistant,
) -> None:
    from pytest_homeassistant_custom_component.common import MockConfigEntry

    from custom_components.smart_ev_charging.const import CONF_CONTIGUOUS_BLOCK

    await _seed_price_entity(hass)
    await _seed_charger_switch(hass)
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Daily",
        data={
            CONF_NAME: "Daily",
            CONF_PRICE_ENTITY: "sensor.fake_prices",
            CONF_PRICE_ATTRIBUTE: "prices",
            CONF_START_FIELD: "start",
            CONF_PRICE_FIELD: "price",
            CONF_CHARGER_SWITCH: "switch.charger",
            CONF_CHARGER_KW: 11.0,
            "default_departure": "08:00:00",
        },
    )
    entry.add_to_hass(hass)

    r = await hass.config_entries.options.async_init(entry.entry_id)
    assert r["type"] == FlowResultType.FORM
    assert r["step_id"] == "init"

    r = await hass.config_entries.options.async_configure(r["flow_id"], {
        CONF_PRICE_ENTITY: "sensor.fake_prices",
        CONF_PRICE_ATTRIBUTE: "prices",
        CONF_START_FIELD: "start",
        CONF_PRICE_FIELD: "price",
        CONF_CHARGER_SWITCH: "switch.charger",
        CONF_CHARGER_KW: 11.0,
        "default_departure": "08:00:00",
        CONF_CONTIGUOUS_BLOCK: False,
    })
    assert r["type"] == FlowResultType.CREATE_ENTRY
    assert r["data"][CONF_CONTIGUOUS_BLOCK] is False
```

Also add this lightweight schema-introspection test:

```python
def test_defaults_schema_has_contiguous_block_default_true() -> None:
    """_DEFAULTS_SCHEMA must include CONF_CONTIGUOUS_BLOCK defaulted to True."""
    from custom_components.smart_ev_charging.config_flow import _DEFAULTS_SCHEMA
    from custom_components.smart_ev_charging.const import (
        CONF_CONTIGUOUS_BLOCK,
    )

    keys = {str(k): k for k in _DEFAULTS_SCHEMA.schema}
    assert CONF_CONTIGUOUS_BLOCK in keys
    assert keys[CONF_CONTIGUOUS_BLOCK].default() is True
```

- [ ] **Step 2: Run the new tests; they must fail**

Run: `pytest tests/test_config_flow.py::test_defaults_schema_has_contiguous_block_default_true tests/test_config_flow.py::test_options_flow_round_trips_contiguous_block_false -v`
Expected: FAIL — first with `KeyError`/`AttributeError` for the missing key, second with `r["data"]` not containing `CONF_CONTIGUOUS_BLOCK`.

- [ ] **Step 3: Add the field to `_DEFAULTS_SCHEMA`**

Modify `custom_components/smart_ev_charging/config_flow.py`. In the const-import block add `CONF_CONTIGUOUS_BLOCK` and `DEFAULT_CONTIGUOUS_BLOCK`. Then extend `_DEFAULTS_SCHEMA` — insert this after the `CONF_MIN_SOC_THRESHOLD` entry so the form ordering matches the option list in the README:

```python
vol.Optional(
    CONF_CONTIGUOUS_BLOCK, default=DEFAULT_CONTIGUOUS_BLOCK
): selector.BooleanSelector(),
```

- [ ] **Step 4: Add the field to the options-flow defaults block**

In the same file, find the options-flow schema (the large `vol.Schema({...})` that uses `d(...)` for defaults). Insert after the `CONF_MIN_SOC_THRESHOLD` entry:

```python
vol.Optional(
    CONF_CONTIGUOUS_BLOCK,
    default=d(CONF_CONTIGUOUS_BLOCK, DEFAULT_CONTIGUOUS_BLOCK),
): selector.BooleanSelector(),
```

- [ ] **Step 5: Add translations**

Modify `custom_components/smart_ev_charging/translations/en.json`. Under `config.step.defaults.data` add a key after `min_soc_threshold`:

```json
"contiguous_block": "Charge in one contiguous block (back-to-back hours)"
```

Under `options.step.init.data` add the same key/value after the existing `min_soc_threshold` entry.

Modify `custom_components/smart_ev_charging/strings.json` identically (same two locations, same string).

- [ ] **Step 6: Run the new config-flow tests**

Run: `pytest tests/test_config_flow.py::test_defaults_schema_has_contiguous_block_default_true tests/test_config_flow.py::test_options_flow_round_trips_contiguous_block_false -v`
Expected: 2 PASS.

- [ ] **Step 7: Run the full config-flow module**

Run: `pytest tests/test_config_flow.py -v`
Expected: no regressions.

- [ ] **Step 8: Commit**

```bash
git add custom_components/smart_ev_charging/config_flow.py custom_components/smart_ev_charging/translations/en.json custom_components/smart_ev_charging/strings.json tests/test_config_flow.py
git commit -m "feat(config_flow): expose contiguous_block toggle in Defaults step + Options"
```

---

### Task 4: Sensor — expose `contiguous_block` discovery attribute

**Files:**
- Modify: `custom_components/smart_ev_charging/sensor.py`
- Modify: `tests/test_sensor.py`

- [ ] **Step 1: Write the failing sensor-attribute test**

Append to `tests/test_sensor.py` (helpers `_base_entry_data` / `_seed_prices` are already imported from `tests.test_coordinator`):

```python
async def test_plan_status_sensor_exposes_contiguous_block_default(
    hass: HomeAssistant,
) -> None:
    """Default-on flag must surface as contiguous_block=True on plan_status."""
    _seed_prices(hass)
    entry = MockConfigEntry(domain=DOMAIN, title="Daily", data=_base_entry_data())
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    state = hass.states.get("sensor.daily_plan_status")
    assert state is not None
    assert state.attributes["contiguous_block"] is True


async def test_plan_status_sensor_exposes_contiguous_block_false(
    hass: HomeAssistant,
) -> None:
    """When CONF_CONTIGUOUS_BLOCK is false, the attribute is False."""
    from custom_components.smart_ev_charging.const import CONF_CONTIGUOUS_BLOCK

    _seed_prices(hass)
    data = _base_entry_data()
    data[CONF_CONTIGUOUS_BLOCK] = False
    entry = MockConfigEntry(domain=DOMAIN, title="Daily", data=data)
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    state = hass.states.get("sensor.daily_plan_status")
    assert state is not None
    assert state.attributes["contiguous_block"] is False
```

- [ ] **Step 2: Run the new tests; they must fail**

Run: `pytest tests/test_sensor.py::test_plan_status_sensor_exposes_contiguous_block_default tests/test_sensor.py::test_plan_status_sensor_exposes_contiguous_block_false -v`
Expected: FAIL with `KeyError: 'contiguous_block'`.

- [ ] **Step 3: Expose the attribute**

Modify `custom_components/smart_ev_charging/sensor.py`. In `PlanStatusSensor.extra_state_attributes` add a new key inside the returned dict, after `min_soc_gate_active`:

```python
"contiguous_block": data.contiguous_block,
```

- [ ] **Step 4: Run the sensor tests; they must pass**

Run: `pytest tests/test_sensor.py -v`
Expected: all tests pass.

- [ ] **Step 5: Commit**

```bash
git add custom_components/smart_ev_charging/sensor.py tests/test_sensor.py
git commit -m "feat(sensor): expose contiguous_block on plan_status discovery attrs"
```

---

### Task 5: README + version bump

**Files:**
- Modify: `README.md`
- Modify: `custom_components/smart_ev_charging/manifest.json`

- [ ] **Step 1: Add a row to the plan_status discovery table**

Modify `README.md`. In the **Discovery attributes on `sensor.<n>_plan_status`** table, insert a row after `min_soc_gate_active`:

```markdown
| `contiguous_block` | `true` when the planner is configured to pick one back-to-back block of cheap hours (default) |
```

- [ ] **Step 2: Add an Options bullet**

In the **Options** section, just under the existing `Replan when prices update / Replan on every SoC change` bullet, insert:

```markdown
- **Charge in one contiguous block** *(default on)* — when on, the planner
  picks one back-to-back block of `slots_needed` cheap hours finishing before
  departure. When off, it picks the N globally-cheapest hours regardless of
  order. Contiguous mode avoids charger on/off cycling but can be slightly
  more expensive on days with an isolated bargain hour.
```

- [ ] **Step 3: Bump the integration version**

Modify `custom_components/smart_ev_charging/manifest.json`. Bump `"version"` from `0.3.3` to `0.4.0` (new user-visible feature flag → minor bump).

- [ ] **Step 4: Run the full test suite + linters**

Run: `pytest -q && ruff check . && mypy --strict custom_components tests`
Expected: green across the board.

- [ ] **Step 5: Commit**

```bash
git add README.md custom_components/smart_ev_charging/manifest.json
git commit -m "docs(README): document contiguous_block option and bump version"
```

---

## Final verification

- [ ] **Step 1: Re-run the entire test suite from scratch**

Run: `pytest --cov --cov-report=term-missing`
Expected: all green; coverage on `planner.py` and `coordinator.py` does not drop.

- [ ] **Step 2: Lint + type-check**

Run: `ruff check . && mypy --strict custom_components tests`
Expected: clean.

- [ ] **Step 3: Manual sanity check on Home Assistant**

Spin up the integration locally (`pip install -e ".[dev]"` and run HA via the dev container if available). Verify:
1. Fresh setup shows the **Charge in one contiguous block** field on the **Defaults** step, default ON.
2. **Configure** on an existing entry shows the same toggle.
3. `sensor.<n>_plan_status` exposes `contiguous_block` in **Developer Tools → States**.
4. Toggling the option off and replanning produces a scattered plan; toggling on produces a back-to-back plan.

Note in the PR description if any of this could not be tested in your local environment.

- [ ] **Step 4: Open the PR**

```bash
git push -u origin <branch>
gh pr create --title "feat: contiguous charge window option (default on)" --body "<<<see spec docs/superpowers/specs/2026-05-19-contiguous-charge-window-design.md>>>"
```
