# Smart EV Charging — design spec

**Status:** approved 2026-05-10
**Owner:** @twarberg
**Repo target:** `github.com/twarberg/ev-smart-charging`
**Audience:** personal use first, public HACS repo later (architecture must stay HACS-clean)
**Reference inputs:** the build guide in `~/Downloads/smart_ev_charging_guide.zip` (read at design time) and its `working_package.yaml` proof-of-concept

## 1. Goal

Replace a working YAML package that plans EV charging during the cheapest hours of dynamic electricity pricing (Strømligning, Nord Pool, Tibber, etc.) with a HACS-installable Home Assistant custom integration. The integration is UI-configured, supports multiple EVs per install, and exposes proper HA entities (sensors, binary sensors, switch, number, datetime) plus services and events for downstream automations.

## 2. Confirmed scope decisions

- **Distribution path:** personal-first, public-later. v0.1 must keep the architecture HACS-grade (multi-instance, config-flow-only, no hardcoded entity IDs, translations, type-strict) so a future public release is a polish pass, not a rewrite.
- **Real hardware target:** Mercedes PHEV (the integration that exposes `*_state_of_charge`, `*_max_state_of_charge`, `*_charging_status`, `*_departure_time`) + Strømligning (`sensor.stromligning_current_price_vat` + `binary_sensor.stromligning_tomorrow_spotprice_vat` joined by user-side template) + an OCPP-exposed `switch.charger_charge_control`. Defaults in the config flow are tuned to this stack.
- **v0.1 surface:** full feature set per the guide — all 9 (+conditional) entities, all 3 services, all 4 events, EN + DA translations.
- **Test approach:** pytest only, including `pytest-homeassistant-custom-component` for the integration tier; no live HA dev container in the loop. Manual smoke against real HA is the user's job before any release.
- **Build order:** inside-out (planner first, then adapters, config flow, coordinator, entities, services, packaging).

Out of scope for v1 (deferred to a hypothetical v2): solar surplus charging, per-phase amperage control, multi-tariff calculation inside the integration, V2H/V2G.

## 3. Non-negotiable design principles

- No hardcoded entity IDs in code — everything user-specific comes from the config flow.
- Every action must be idempotent (calling `switch.turn_on` while already on is a no-op; events fire only on actual transitions).
- Defensive against missing/unavailable upstream data — the integration must never crash because the price sensor is unavailable, the SoC is `unknown`, or the plug status flickered.
- The integration provides primitives (entities + events). It does NOT wrap user automations like notifications.
- The integration takes a single price entity; if the user needs today+tomorrow joined (Strømligning), they configure that via a template sensor — README ships a recipe.
- The planner is pure Python with zero `homeassistant` imports.

## 4. Repository layout

```
ev-smart-charging/
├── custom_components/smart_ev_charging/
│   ├── __init__.py            # async_setup_entry, async_unload_entry, service registration
│   ├── manifest.json
│   ├── const.py               # DOMAIN, CONF_*, DEFAULT_*
│   ├── config_flow.py         # ConfigFlow + OptionsFlow
│   ├── coordinator.py         # SmartEVCoordinator(DataUpdateCoordinator) + charge controller
│   ├── planner.py             # pure Python; PlanInput → Plan; zero HA imports
│   ├── price_source.py        # adapter: price entity → list[PriceSlot]
│   ├── car_state.py           # adapter: car entities → CarState
│   ├── sensor.py
│   ├── binary_sensor.py
│   ├── switch.py
│   ├── number.py
│   ├── datetime.py
│   ├── services.yaml
│   ├── strings.json
│   └── translations/
│       ├── en.json
│       └── da.json
├── tests/
│   ├── conftest.py
│   ├── test_planner.py
│   ├── test_price_source.py
│   ├── test_car_state.py
│   ├── test_config_flow.py
│   ├── test_coordinator.py
│   └── fixtures/
│       ├── prices_24h.json
│       └── stromligning_state.json
├── docs/superpowers/specs/    # this spec + the implementation plan that follows
├── hacs.json
├── README.md
├── LICENSE                    # MIT
├── pyproject.toml             # ruff + mypy --strict + pytest config + dev extras
└── .github/workflows/ci.yml   # stub for v0.1; full matrix before public release
```

### Toolchain

- Python 3.12+, Home Assistant 2024.10+.
- `ruff check` and `mypy --strict` clean across `custom_components/` and `tests/`.
- Test deps (in `[project.optional-dependencies].dev`): `pytest`, `pytest-asyncio`, `pytest-cov`, `pytest-homeassistant-custom-component`, `hypothesis`, `freezegun` (only for the coordinator e2e tests; the pure planner takes `now` as an explicit parameter).
- `from __future__ import annotations` and PEP 604 unions everywhere.

### Manifest

```json
{
  "domain": "smart_ev_charging",
  "name": "Smart EV Charging",
  "version": "0.1.0",
  "config_flow": true,
  "documentation": "https://github.com/twarberg/ev-smart-charging",
  "issue_tracker": "https://github.com/twarberg/ev-smart-charging/issues",
  "codeowners": ["@twarberg"],
  "iot_class": "calculated",
  "integration_type": "service",
  "requirements": [],
  "dependencies": []
}
```

## 5. Module boundaries

The integration is layered. Each layer has a tight contract; tests at lower layers run without HA.

### Layer 1 — `planner.py` (pure)

```python
@dataclass(frozen=True)
class PriceSlot:
    start: datetime  # tz-aware
    end: datetime    # tz-aware, normally start + 1h
    price: float

@dataclass(frozen=True)
class PlanInput:
    prices: list[PriceSlot]              # may be unsorted; planner sorts defensively
    slots_needed: int                    # planner clamps to max(1, slots_needed)
    departure: datetime                  # tz-aware deadline
    now: datetime                        # tz-aware "current time"
    min_minutes_left_in_hour: int = 15

@dataclass(frozen=True)
class Plan:
    selected_starts: list[datetime]      # tz-aware, sorted ascending
    deadline: datetime                   # may be initial_deadline + 24h
    initial_deadline: datetime
    was_extended: bool
    window_size: int
    status: Literal["ok", "partial", "extended", "no_data"]

def make_plan(inp: PlanInput) -> Plan: ...
```

Algorithm (exactly as `04_planner.md` of the guide):

1. `effective_start`: `next_hour_start` if `(next_hour_start - now)` minutes is `< min_minutes_left_in_hour`, else `this_hour_start`.
2. `was_extended`: `(departure - now)` < 1 hour. If true, `deadline = departure + 24h`; else `deadline = departure`.
3. `window = sorted([s for s in prices if effective_start <= s.start < deadline], key=start)`.
4. `effective_slots = min(slots_needed, len(window))`.
5. `selected_starts = sorted(s.start for s in sorted(window, key=price)[:effective_slots])`.
6. `status` = `no_data` if `len(window) == 0`; else `extended` if `was_extended`; else `partial` if `len(window) < slots_needed`; else `ok`.

Constraints:
- Zero `homeassistant` imports.
- All datetime math is tz-aware. Mixed-tz inputs are normalized via `astimezone(UTC)` before comparison.
- Never reconstruct datetimes from `hour` ints (breaks across midnight + DST). Use `datetime` arithmetic.
- DST-spring-forward: a missing 02:00 slot simply isn't in `prices`; planner doesn't synthesize it.
- DST-fall-back: a doubled 02:00 may appear as two distinct UTC slots; both are eligible but no slot appears twice in `selected_starts` (set semantics on `start`).
- Stable sort on identical prices; tests accept either tied ordering.

### Layer 2 — Adapters

`price_source.py`:

```python
class PriceSource:
    def __init__(self, hass: HomeAssistant, entity_id: str, attr_name: str,
                 start_field: str, price_field: str, end_field: str | None = None) -> None: ...
    def get_slots(self) -> list[PriceSlot]:
        """Sorted by start ascending. Empty list if entity unavailable, attribute missing,
        attribute not a list, or the list contains only malformed entries.
        Logs a single warning per failure mode (deduped by failure key)."""
```

Handles attribute-name variation (`prices`, `today`, `forecast`), field-name variation (`start`/`price`, `start`/`value`, `startsAt`/`total`, optional end field), value-type variation (string ISO / `datetime` / unix timestamp). Drops malformed entries while keeping good ones.

`car_state.py`:

```python
@dataclass(frozen=True)
class CarState:
    soc_percent: float | None
    target_soc_percent: float | None
    plug_raw_state: str | None        # raw state string from charging_status_entity (or None if not configured)
    plugged_in: bool                  # adapter best-guess; coordinator applies last-known-good debounce
    actively_charging: bool
    departure: time | None            # parsed from "HH:MM" or "HH:MM:SS"

def read_car_state(hass: HomeAssistant, config: SmartEVConfig) -> CarState: ...
```

Each field is `None` when the corresponding entity isn't configured or its state is `unknown`/`unavailable`. Plug detection is `state not in plug_unplugged_values` once `unknown`/`unavailable`/`none`/`""` are excluded.

### Layer 3 — `coordinator.py`

`SmartEVCoordinator(DataUpdateCoordinator[CoordinatorData])` where:

```python
@dataclass
class ChargeOverride:
    mode: Literal["force", "skip"]
    until: datetime | None  # tz-aware; None means "until target SoC reached" (force) — illegal for skip

@dataclass
class CoordinatorData:
    plan: Plan
    car_state: CarState
    last_replan: datetime
    override: ChargeOverride | None
```

Responsibilities:

1. **Source-entity listeners.** On `async_setup`, register `async_track_state_change_event` for: price entity, SoC entity, target SoC entity, charging-status entity, departure entity (each only if configured). Listener handler triggers a debounced refresh.
2. **Heartbeat.** `update_interval = timedelta(minutes=30)` — same code path as listener-driven refreshes. Catches missed events and refreshes plans when Strømligning publishes tomorrow's prices around 14:00 CET.
3. **`_async_replan()`.** Read `PriceSource.get_slots()` + `read_car_state()`; compute `slots_needed` (SoC math when `soc_entity` is configured, else read from `number.<n>_charge_slots_override`); compute `effective_departure` (resolution order `car_state.departure` → `datetime.<n>_departure_fallback` → `default_departure` from config); build `PlanInput`; call `planner.make_plan`; store result in `self.data`; fire `smart_ev_charging_plan_updated` with `entry_id, status, selected_starts, deadline, was_extended`.
4. **Charge controller (`_async_evaluate_charge_now`).** Runs after every refresh and on switch/override changes. Computes the boolean using this priority order:
   1. Master `switch.<n>_smart_charging_enabled` is off → `False`, status `disabled`.
   2. Override mode `force` AND (SoC unknown OR SoC < target) → `True`. (Unknown-SoC case applies when no `soc_entity` is configured; force keeps charging until `until` passes or the user unplugs.)
   3. Override mode `skip` and `now < override.until` → `False`.
   4. `plugged_in` is `False` → `False`.
   5. SoC ≥ target (only evaluated when SoC and target are both known) → `False`. If SoC just crossed target while `charge_now` was `True`, fire `smart_ev_charging_target_reached`. If a `force` override is active, also clear it.
   6. Current `this_hour_start` is in `plan.selected_starts` → `True`.
   7. Else → `False`.
   On state transitions, call `switch.turn_on` / `switch.turn_off` on the configured `charger_switch` and fire `smart_ev_charging_started` / `_stopped` with `reason ∈ {"plan", "force", "manual", "plan_end", "target_reached", "unplugged", "disabled", "skip", "override_expired"}`. The transition is detected against `self._last_charge_now` to keep events idempotent.
5. **Slots-needed math** (when SoC entity is configured):
   ```
   buffer = 1.05 if target <= 80 else 1.10
   kwh_needed = max(0, (target - current) / 100 * battery_kwh)
   hours_raw = kwh_needed / charger_kw * buffer
   slots_needed = max(1, ceil(hours_raw))
   ```
6. **Plug debouncing (lessons-learned #8).** A small `_PlugDebouncer` tracks the last raw status. The coordinator only flips `plugged_in` to `False` when the raw status is *explicitly* in `plug_unplugged_values`; raw `unknown`/`unavailable` keeps the last-known-good value. The adapter reports raw + best-guess; the coordinator owns the final debounced answer used in `_async_evaluate_charge_now`.
7. **Public methods.** `async_replan()` (used by the service), `apply_override(mode, until)` (used by the override services), `async_set_master_enabled(bool)` (called by the switch entity).
8. **Override lifetime.** In-memory only; not persisted across HA restarts (intentional). Cleared automatically when: user unplugs (raw status enters `plug_unplugged_values`); `until` passes; master switch toggled to off; SoC reaches target while in `force` mode.
9. **Teardown.** `async_unload` cancels all state-change listeners so OptionsFlow reload works without an HA restart.

### Layer 4 — Entity files

Every entity inherits `CoordinatorEntity[SmartEVCoordinator]` + the platform base. Entities are pure projections of `coordinator.data`; no business logic. Entity unique IDs are `f"{entry.entry_id}_{key}"` so multiple config entries don't collide. All entities for an entry share one device (`identifiers={(DOMAIN, entry.entry_id)}`) named after the entry. `_attr_has_entity_name = True` so HA composes "EV Charging Plan Status" automatically.

- `sensor.py`: `plan_status`, `planned_hours`, `slots_needed`, `active_deadline` (timestamp device_class), `effective_departure`. State + attribute layout matches `05_entities.md`. Icons change with state on `plan_status` (`mdi:check-circle` / `mdi:alert-circle` / `mdi:clock-fast` / `mdi:database-off` / `mdi:power-plug-off`).
- `binary_sensor.py`: `plugged_in` (device_class `plug`), `actively_charging` (device_class `battery_charging`), `charge_now` (device_class `power`). `charge_now` reads `coordinator.data.charge_now` — it does **not** drive the charger; the coordinator's charge controller does. The entity is a reflection.
- `switch.py`: `smart_charging_enabled`, RestoreEntity, calls back into the coordinator on user toggle.
- `number.py`: `target_soc` (50–100 step 5 default 80, only when no `target_soc_entity` configured) and `charge_slots_override` (1–12 step 1 default 3, only when no `soc_entity` configured), both RestoreEntity, both trigger a coordinator refresh on change.
- `datetime.py`: `departure_fallback` (only when no `departure_entity` configured), RestoreEntity, only `.time()` part used.

## 6. Config flow

Five steps in order: `user`, `price`, `charger`, `car`, `defaults`. The `OptionsFlow` exposes steps 2–5 only.

### Step `user`
| Field | Selector | Required | Default | Validation |
|---|---|---|---|---|
| `name` | text | yes | "EV" | non-empty; lowercased name not already used by another entry (else abort `already_configured`) |

### Step `price`
| Field | Selector | Required | Default | Notes |
|---|---|---|---|---|
| `price_entity` | EntitySelector(domain=["sensor","binary_sensor"]) | yes | — | |
| `price_attribute` | text | yes | `prices` | |
| `start_field` | text | yes | `start` | |
| `price_field` | text | yes | `price` | |
| `end_field` | text | no | `end` | |

Validation on submit: read entity's attributes, find the named attribute, verify it's a non-empty list of dicts containing the named fields. On failure, re-render the form with `description_placeholders["peek"]` set to the actual top-level keys of the first entry — so the user sees `Found fields: ['start', 'value', 'spotPrice']`. Error keys: `entity_not_found`, `attribute_not_found`, `attribute_not_a_list`, `entries_not_dicts`, `field_not_found`.

### Step `charger`
| Field | Selector | Required | Default |
|---|---|---|---|
| `charger_switch` | EntitySelector(domain="switch") | yes | — |
| `charger_kw` | NumberSelector(0.5–22, step 0.1) | yes | 11 |

Warns (does not block) if the chosen switch is currently `unavailable`.

### Step `car` (all fields optional)
| Field | Selector | Default |
|---|---|---|
| `soc_entity` | EntitySelector(domain="sensor", device_class="battery") | — |
| `target_soc_entity` | EntitySelector(domain=["sensor","number"]) | — |
| `charging_status_entity` | EntitySelector(domain=["sensor","binary_sensor"]) | — |
| `plug_unplugged_values` | TextSelector(multiple) | `["3","unplugged","Unplugged","UNPLUGGED"]` |
| `actively_charging_values` | TextSelector(multiple) | `["0","charging","Charging","CHARGING"]` |
| `departure_entity` | EntitySelector | — |
| `battery_kwh` | NumberSelector(1–200, step 0.1) | 31.2 |

Skipping any optional entity decides which fallback entity the integration creates (see entity table above).

### Step `defaults`
| Field | Selector | Required | Default |
|---|---|---|---|
| `default_departure` | TimeSelector | yes | 08:00 |
| `min_minutes_left_in_hour` | NumberSelector(0–59) | no | 15 |
| `auto_replan_on_price_update` | BooleanSelector | no | true |
| `auto_replan_on_soc_change` | BooleanSelector | no | false |

On submit, store everything in `entry.data` at creation time (standard HA convention). The OptionsFlow always writes its result to `entry.options`. The integration reads its config as `{**entry.data, **entry.options}` so options shadow data. The OptionsFlow exposes the same fields as steps 2–5 but does not allow changing `name`. An update listener calls `async_reload(entry.entry_id)` so changes take effect without an HA restart.

## 7. Services

`services.yaml` declares three services, registered globally in `async_setup_entry` (idempotent — register once, not per entry).

| Service | Fields | Behavior |
|---|---|---|
| `smart_ev_charging.replan` | none | Resolve target → coordinator, `await coordinator.async_replan()`. |
| `smart_ev_charging.force_charge_now` | `duration` (DurationSelector, no day) optional | Resolve target → coordinator, set `ChargeOverride(mode="force", until=now+duration if duration else None)`. |
| `smart_ev_charging.skip_until` | `until` (datetime, required) | Resolve target → coordinator, set `ChargeOverride(mode="skip", until=until)`. |

All three target by `device_id` or `entity_id`; the handler resolves the owning config entry. Calling either override service while one is active replaces the existing override. The active override is exposed via `sensor.<n>_plan_status`'s `override_mode` and `override_until` attributes.

## 8. Events

| Event | When | Payload |
|---|---|---|
| `smart_ev_charging_plan_updated` | Every replan | `entry_id`, `status`, `selected_starts` (ISO list), `deadline` (ISO), `was_extended` |
| `smart_ev_charging_started` | `charge_now` flips `false → true` | `entry_id`, `reason ∈ {plan, force, manual}` |
| `smart_ev_charging_stopped` | `charge_now` flips `true → false` | `entry_id`, `reason ∈ {plan_end, target_reached, unplugged, disabled, skip, override_expired}` |
| `smart_ev_charging_target_reached` | SoC crosses target while charging | `entry_id`, `final_soc` |

Schema is part of the public contract starting at v0.1; any breaking change requires a minor-version bump and migration notes.

## 9. Translations

`strings.json` is canonical and lists all step titles, field labels, field descriptions, error keys, abort keys, and service display names. `translations/en.json` mirrors it. `translations/da.json` ships at v0.1.

Keys are flat-grouped by step: `config.step.user.data.name`, `config.error.attribute_not_found`, `options.step.charger.data.charger_kw`, `services.replan.name`, etc.

## 10. Test strategy

### Tier 1 — pure planner

`tests/test_planner.py` runs in milliseconds, no HA. Hand-written cases per the algorithm matrix:
- `normal_overnight` → `ok`
- `plug_in_late_one_hour` → `partial`
- `plug_in_after_departure` → `extended`
- `departure_in_30_min` → `extended`
- `empty_prices` → `no_data`
- `not_enough_prices` → `partial`
- mid-hour skip at xx:50 with `min_minutes_left ∈ {15, 0}` → current hour kept iff threshold is 0
- plug-in at 23:50 — `effective_start` rolls to next-day 00:00 via `datetime` arithmetic
- DST spring-forward — a missing 02:00 isn't selected
- DST fall-back — a doubled 02:00 isn't selected twice
- Mixed-tz inputs — converted to UTC before comparison

Hypothesis property tests for the picker:
- `len(plan.selected_starts) == min(slots_needed, len(window))`
- `selected_starts ⊆ {s.start for s in window}`
- `sum(prices of selection) ≤ sum(prices of any other same-size subset of window)`
- `selected_starts` is sorted ascending
- `status` follows the algorithm rules

Goal: 100% line + branch coverage of `planner.py`.

### Tier 2 — adapters

`tests/test_price_source.py` + `tests/test_car_state.py`. Mock `hass` exposes a `states.get(entity_id)` that returns a `State`-like with `state` + `attributes`. No event loop required.

`PriceSource`:
- Strømligning shape (`prices: [{start, price, end}]`)
- Nord Pool shape (`today: [{start, value}]`)
- Tibber shape (`startsAt`/`total`)
- Mixed string-ISO / `datetime` / unix timestamp `start`
- Malformed entry mixed with good ones — good ones survive, single warning logged via `caplog`
- Entity missing → `[]`
- Attribute missing → `[]`
- Attribute not a list → `[]`
- Entity `unavailable` → `[]`

`CarState`:
- SoC=100 / target=100 → both reported
- Mercedes numeric `'3'` with `plug_unplugged_values=["3"]` → `plugged_in=False`
- Tesla string `'unplugged'` with `plug_unplugged_values=["unplugged"]` → `False`
- Status `unknown` → `plug_raw_state="unknown"`, `plugged_in=False` (coordinator applies debounce)
- No `charging_status_entity` configured → `plugged_in=True` always
- Departure `'08:00'` → `time(8, 0)`; `'08:30:00'` → `time(8, 30)`; `unknown` → `None`

Goal: ≥95% coverage of both modules.

### Tier 3 — config flow

`tests/test_config_flow.py` uses `pytest-homeassistant-custom-component`'s `hass` fixture.
- Happy path through all 5 steps ends with `create_entry`; entry has expected `data`/`options` shape.
- Validation errors return form re-renders with the right error key and `description_placeholders["peek"]` populated.
- Optional steps: skip all car fields → entry created without those keys, fallback entities created on setup.
- OptionsFlow re-opens an existing entry, modifies a field, submits — entry options update, `async_reload` is invoked, no orphan entities.
- Duplicate name (case-insensitive) → abort `already_configured`.

Goal: ≥90% coverage of `config_flow.py`; every error path exercised.

### Tier 4 — coordinator + entities + e2e

`tests/test_coordinator.py` uses a full `hass` instance per test.
- Entity creation: assert all expected entity_ids exist after first refresh, with right initial states (and conditional fallbacks present/absent based on which optional entities are configured).
- Plan-driven controller: `freezegun.freeze_time` pins `now`; price attribute set; SoC=30, target=80, plugged in. After refresh: `plan` has the expected 3 cheapest hours and `binary_sensor.charge_now=off` outside them. Advance to a planned hour, refresh: `charge_now=on` AND `switch.turn_on` was called on the configured charger entity (verified via captured service calls). Advance past last planned hour: `charge_now=off` AND `switch.turn_off` called.
- `force_charge_now` service: `charge_now=on` regardless of plan; SoC reaches target → override clears, `turn_off` called, `target_reached` event fired.
- `skip_until` service: `charge_now=off`; advance past `until`: plan resumes.
- Reload via OptionsFlow: change `default_departure`, submit → coordinator unloaded + recreated, `RestoreEntity`-backed entities preserve their state.
- Master switch off → `turn_off` called, `plan_status=disabled`, `charge_now=off`. On → resumes on next refresh.
- Plug debouncing: status flips `unknown` while previously `plugged_in=True` → `plugged_in` stays `on`, no `stopped` event, no `turn_off` call. Status flips to an explicit unplugged value → `plugged_in=off`, `turn_off` called, `stopped` event with `reason='unplugged'`.

Goal: ≥85% coverage of `coordinator.py`, ≥80% of entity files.

### Coverage thresholds

Enforced in `pyproject.toml` via `[tool.coverage]`:

| Module | Threshold |
|---|---|
| `planner.py` | 100% line + branch |
| `price_source.py`, `car_state.py` | 95% |
| `config_flow.py` | 90% |
| `coordinator.py` | 85% |
| Entity files (`sensor.py`, `binary_sensor.py`, `switch.py`, `number.py`, `datetime.py`) | 80% |

### Dev-loop verification

```
pip install -e ".[dev]"
ruff check .
mypy --strict custom_components tests
pytest --cov --cov-report=term-missing
```

All four commands must be green before any milestone is marked complete.

## 11. Build order (approach B — inside-out)

1. Repo skeleton: `pyproject.toml` (ruff + mypy + pytest + dev extras), `LICENSE`, `.gitignore`, `README.md` placeholder, `hacs.json`, `manifest.json`, empty `custom_components/smart_ev_charging/__init__.py`. Verify `ruff check` and `mypy --strict` run green on the empty package.
2. `planner.py` + `tests/test_planner.py` + `tests/fixtures/prices_24h.json`. Hand-written cases pass. Hypothesis property tests pass. 100% line + branch coverage achieved.
3. `const.py` + `price_source.py` + `tests/test_price_source.py`. ≥95% coverage.
4. `car_state.py` + `tests/test_car_state.py`. ≥95% coverage.
5. `config_flow.py` (incl. OptionsFlow) + `strings.json` + `translations/en.json` + `tests/test_config_flow.py`. ≥90% coverage and all error paths.
6. `coordinator.py` (incl. charge controller, plug debouncer, override handling, heartbeat) + `__init__.py` (`async_setup_entry`, `async_unload_entry`, update listener for OptionsFlow) + `tests/test_coordinator.py` for setup/refresh/teardown. ≥85% coverage.
7. Entity files (`sensor.py`, `binary_sensor.py`, `switch.py`, `number.py`, `datetime.py`) + extend `test_coordinator.py` with entity assertions and the e2e plan-drives-charger test. ≥80% coverage on entity files.
8. `services.yaml` + service handlers (registered once in `async_setup` for the integration, not per entry) + service-related tests in `test_coordinator.py` (`force_charge_now`, `skip_until`, `replan`).
9. `translations/da.json` mirroring `en.json`.
10. README write-up: HACS install steps, configuration walkthrough, entity table, recipes (notification on partial, Lovelace card, Strømligning today+tomorrow joiner template), troubleshooting.
11. `.github/workflows/ci.yml` (lint + mypy + pytest matrix, Python 3.12 + 3.13).

Each step ends with `ruff check` + `mypy --strict` + `pytest --cov` green before moving on. The implementation plan that follows this spec will list the per-step tasks in detail.

## 12. Lessons-learned encoded in the design

- **`input_text` 255-char limit.** Plan lives in `coordinator.data` and entity attributes (no length limit). Never serialize the plan to a string-bounded helper.
- **Trigger-based template restore gap.** Coordinator populates `data` on `async_config_entry_first_refresh()` so entities are populated immediately after restart.
- **Mercedes numeric vs. string charging status.** Default `plug_unplugged_values` includes both; user-editable in config flow.
- **`today_at()` midnight rollover.** Planner uses `datetime + timedelta(hours=1)` exclusively; never reconstructs from `hour` ints.
- **Strømligning today+tomorrow split.** README ships a template-sensor recipe. The integration takes one entity.
- **Plug status flickers `unknown`.** Coordinator's `_PlugDebouncer` keeps last-known-good for `unknown`/`unavailable`; only flips on explicit unplugged values.
- **Mid-hour plug-in claiming half-elapsed slot.** `min_minutes_left_in_hour` is configurable (default 15).
- **AIO Energy Management isn't a perfect upstream.** The integration owns the planning; no AIO dependency.
- **30-min heartbeat.** `update_interval=timedelta(minutes=30)` on the coordinator.
- **Friendly icons + device classes.** Spelled out in entity definitions.

## 13. Done criteria for v0.1 (personal-use cut)

- Real Mercedes PHEV + Strømligning + OCPP setup is configurable through the UI in a single pass; entities populate; charger toggles on/off at the right moments in real-world usage for at least one full charge cycle.
- All four test tiers pass; coverage thresholds met.
- `ruff check` and `mypy --strict` clean.
- README has installation, configuration, entity table, and at least one recipe.
- `LICENSE` (MIT) present.
- The integration installs into a real HA instance via "Install via custom HACS repository" without errors.

The "public release" cut adds: HACS validation green, `da.json` complete and proofread, brand assets PR, CI on push/PR for Python 3.12 + 3.13, CHANGELOG, `0.1.0` git tag and GitHub release.

## 14. Out of scope explicitly

- Solar surplus charging
- Per-phase amperage control
- Multi-tariff calculation inside the integration
- V2H/V2G
- Bundled "today+tomorrow" price aggregation (a recipe in README, not integration code)
- Persisting overrides across HA restarts
