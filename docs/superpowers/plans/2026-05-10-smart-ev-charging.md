# Smart EV Charging Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a HACS-installable Home Assistant custom integration that plans EV charging during the cheapest hours of dynamic electricity pricing, finishing by a configurable departure time.

**Architecture:** Inside-out, four layers: pure-Python `planner.py` (zero HA imports) → adapters (`price_source.py`, `car_state.py`) → `coordinator.py` (DataUpdateCoordinator subclass owning state, charge controller, services) → thin `CoordinatorEntity` projections in platform files. Multi-entry per integration; everything user-specific comes from a 5-step config flow.

**Tech Stack:** Python 3.12+, Home Assistant 2024.10+, `pytest-homeassistant-custom-component`, `hypothesis`, `freezegun`, `ruff`, `mypy --strict`.

**Spec:** [`docs/superpowers/specs/2026-05-10-smart-ev-charging-design.md`](../specs/2026-05-10-smart-ev-charging-design.md)

---

## File structure

Files created by task. Each entry shows the file's single responsibility.

| File | Responsibility | Created in |
|---|---|---|
| `pyproject.toml` | Build/lint/type/test config + dev extras | T1 |
| `LICENSE` | MIT | T1 |
| `.gitignore` | Standard Python + HA cache | T1 |
| `hacs.json` | HACS metadata | T1 |
| `README.md` | User-facing docs (placeholder T1, full T20) | T1, T20 |
| `custom_components/smart_ev_charging/manifest.json` | HA integration manifest | T1 |
| `custom_components/smart_ev_charging/__init__.py` | `async_setup`, `async_setup_entry`, `async_unload_entry`, options listener (services T18) | T1, T14, T18 |
| `custom_components/smart_ev_charging/const.py` | DOMAIN, CONF_*, DEFAULT_*, PLATFORMS | T7 |
| `custom_components/smart_ev_charging/planner.py` | Pure planning algorithm | T2-T6 |
| `custom_components/smart_ev_charging/price_source.py` | Price entity → `list[PriceSlot]` adapter | T7 |
| `custom_components/smart_ev_charging/car_state.py` | Car entities → `CarState` adapter | T8 |
| `custom_components/smart_ev_charging/config_flow.py` | ConfigFlow + OptionsFlow | T9-T11 |
| `custom_components/smart_ev_charging/strings.json` | Canonical translation source | T12 |
| `custom_components/smart_ev_charging/translations/en.json` | English translations | T12 |
| `custom_components/smart_ev_charging/translations/da.json` | Danish translations | T19 |
| `custom_components/smart_ev_charging/coordinator.py` | DataUpdateCoordinator + charge controller + plug debouncer | T13-T14 |
| `custom_components/smart_ev_charging/sensor.py` | 5 read-only sensors | T15 |
| `custom_components/smart_ev_charging/binary_sensor.py` | 3 binary sensors | T15 |
| `custom_components/smart_ev_charging/switch.py` | Master enable switch (RestoreEntity) | T16 |
| `custom_components/smart_ev_charging/number.py` | Conditional fallback numbers (RestoreEntity) | T16 |
| `custom_components/smart_ev_charging/datetime.py` | Conditional fallback departure datetime | T16 |
| `custom_components/smart_ev_charging/services.yaml` | Service schemas | T18 |
| `tests/__init__.py` | (empty) | T1 |
| `tests/conftest.py` | Shared fixtures + `enable_custom_integrations` autouse | T1 |
| `tests/fixtures/prices_24h.json` | Realistic 24h Strømligning-style prices | T2 |
| `tests/fixtures/stromligning_state.json` | Sample full state for adapters/coordinator | T7 |
| `tests/test_planner.py` | Pure planner tests + hypothesis | T2-T6 |
| `tests/test_price_source.py` | Adapter unit tests | T7 |
| `tests/test_car_state.py` | Adapter unit tests | T8 |
| `tests/test_config_flow.py` | Config + options flow tests | T9-T11 |
| `tests/test_coordinator.py` | Setup, refresh, charge controller, services, e2e | T13-T17 |
| `.github/workflows/ci.yml` | GH Actions matrix (3.12, 3.13) | T21 |

---

## Task 1: Repo skeleton + tooling

**Files:**
- Create: `pyproject.toml`, `.gitignore`, `LICENSE`, `hacs.json`, `README.md`, `custom_components/smart_ev_charging/__init__.py`, `custom_components/smart_ev_charging/manifest.json`, `tests/__init__.py`, `tests/conftest.py`

- [ ] **Step 1: Create `pyproject.toml`**

```toml
[build-system]
requires = ["setuptools>=68"]
build-backend = "setuptools.build_meta"

[project]
name = "smart-ev-charging"
version = "0.1.0"
description = "Home Assistant custom integration: plans EV charging during the cheapest hours of dynamic pricing."
readme = "README.md"
requires-python = ">=3.12"
license = { text = "MIT" }
authors = [{ name = "twarberg", email = "tim@tlw.dk" }]
dependencies = []

[project.optional-dependencies]
dev = [
    "pytest>=8.0",
    "pytest-asyncio>=0.23",
    "pytest-cov>=5.0",
    "pytest-homeassistant-custom-component>=0.13",
    "hypothesis>=6.100",
    "freezegun>=1.5",
    "ruff>=0.5",
    "mypy>=1.10",
]

[tool.setuptools]
packages = []

[tool.ruff]
target-version = "py312"
line-length = 100

[tool.ruff.lint]
select = ["E", "F", "W", "I", "B", "UP", "ANN", "PT", "SIM", "RUF"]
ignore = ["ANN101", "ANN102"]

[tool.ruff.lint.per-file-ignores]
"tests/*" = ["ANN", "B011"]

[tool.mypy]
python_version = "3.12"
strict = true
warn_unreachable = true
disallow_untyped_decorators = false
plugins = []

[[tool.mypy.overrides]]
module = "homeassistant.*"
ignore_missing_imports = true

[[tool.mypy.overrides]]
module = "pytest_homeassistant_custom_component.*"
ignore_missing_imports = true

[tool.pytest.ini_options]
asyncio_mode = "auto"
addopts = "-ra --strict-markers"
testpaths = ["tests"]

[tool.coverage.run]
source = ["custom_components/smart_ev_charging"]
branch = true

[tool.coverage.report]
show_missing = true
skip_covered = false
fail_under = 0  # raised per-module by CI
```

- [ ] **Step 2: Create `.gitignore`**

```
__pycache__/
*.pyc
.pytest_cache/
.mypy_cache/
.ruff_cache/
.coverage
htmlcov/
*.egg-info/
build/
dist/
.venv/
venv/
.env
.hass_storage/
```

- [ ] **Step 3: Create `LICENSE` (MIT)**

```
MIT License

Copyright (c) 2026 twarberg

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```

- [ ] **Step 4: Create `hacs.json`**

```json
{
  "name": "Smart EV Charging",
  "render_readme": true,
  "homeassistant": "2024.10.0",
  "country": ["DK", "NO", "SE", "FI", "DE", "NL"]
}
```

- [ ] **Step 5: Create `README.md` (placeholder; rewritten in T20)**

```markdown
# Smart EV Charging

Plans your EV charging during the cheapest hours of dynamic electricity pricing,
finishing by your departure time.

This README is a placeholder during development. Final content lands in T20.
```

- [ ] **Step 6: Create `custom_components/smart_ev_charging/manifest.json`**

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

- [ ] **Step 7: Create `custom_components/smart_ev_charging/__init__.py` (skeleton — gets fleshed out in T14)**

```python
"""Smart EV Charging integration."""
from __future__ import annotations
```

- [ ] **Step 8: Create `tests/__init__.py`**

```python
```

- [ ] **Step 9: Create `tests/conftest.py`**

```python
"""Shared pytest fixtures."""
from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations: None) -> None:
    """Auto-enable custom_components for every test (provided by pytest-homeassistant-custom-component)."""
    return None
```

- [ ] **Step 10: Install dev deps and verify lint + type-check are clean on the empty package**

Run:
```bash
cd /home/tlw/dev/ev-smart-charging
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
ruff check .
mypy --strict custom_components tests
```

Expected: all three commands exit 0. (mypy may emit a "Success: no issues found in N source files" line.)

- [ ] **Step 11: Commit**

```bash
git -c user.name=twarberg -c user.email=tim@tlw.dk add pyproject.toml .gitignore LICENSE hacs.json README.md custom_components/smart_ev_charging/__init__.py custom_components/smart_ev_charging/manifest.json tests/__init__.py tests/conftest.py
git -c user.name=twarberg -c user.email=tim@tlw.dk commit -m "$(cat <<'EOF'
chore: scaffold repo skeleton with tooling

Adds pyproject.toml (ruff+mypy strict+pytest+coverage), MIT LICENSE,
.gitignore, hacs.json, manifest.json, README placeholder, empty package
init, and tests conftest with the custom-integrations enabler fixture.

ruff and mypy --strict are green on the empty package.
EOF
)"
```

---

## Task 2: Planner — data types and happy-path test

**Files:**
- Create: `custom_components/smart_ev_charging/planner.py`, `tests/test_planner.py`, `tests/fixtures/prices_24h.json`

- [ ] **Step 1: Create the price fixture `tests/fixtures/prices_24h.json`**

A 48-hour realistic Strømligning-style price array spanning 2026-05-10 00:00 → 2026-05-12 00:00 Europe/Copenhagen, with peak 17–21 (~3.0 DKK/kWh) and valley 02–05 (~0.7 DKK/kWh). All `start`/`end` are ISO 8601 with `+02:00` offset.

```json
[
  {"start": "2026-05-10T00:00:00+02:00", "end": "2026-05-10T01:00:00+02:00", "price": 1.20},
  {"start": "2026-05-10T01:00:00+02:00", "end": "2026-05-10T02:00:00+02:00", "price": 1.05},
  {"start": "2026-05-10T02:00:00+02:00", "end": "2026-05-10T03:00:00+02:00", "price": 0.75},
  {"start": "2026-05-10T03:00:00+02:00", "end": "2026-05-10T04:00:00+02:00", "price": 0.70},
  {"start": "2026-05-10T04:00:00+02:00", "end": "2026-05-10T05:00:00+02:00", "price": 0.72},
  {"start": "2026-05-10T05:00:00+02:00", "end": "2026-05-10T06:00:00+02:00", "price": 0.95},
  {"start": "2026-05-10T06:00:00+02:00", "end": "2026-05-10T07:00:00+02:00", "price": 1.40},
  {"start": "2026-05-10T07:00:00+02:00", "end": "2026-05-10T08:00:00+02:00", "price": 1.85},
  {"start": "2026-05-10T08:00:00+02:00", "end": "2026-05-10T09:00:00+02:00", "price": 2.10},
  {"start": "2026-05-10T09:00:00+02:00", "end": "2026-05-10T10:00:00+02:00", "price": 1.95},
  {"start": "2026-05-10T10:00:00+02:00", "end": "2026-05-10T11:00:00+02:00", "price": 1.75},
  {"start": "2026-05-10T11:00:00+02:00", "end": "2026-05-10T12:00:00+02:00", "price": 1.60},
  {"start": "2026-05-10T12:00:00+02:00", "end": "2026-05-10T13:00:00+02:00", "price": 1.50},
  {"start": "2026-05-10T13:00:00+02:00", "end": "2026-05-10T14:00:00+02:00", "price": 1.55},
  {"start": "2026-05-10T14:00:00+02:00", "end": "2026-05-10T15:00:00+02:00", "price": 1.70},
  {"start": "2026-05-10T15:00:00+02:00", "end": "2026-05-10T16:00:00+02:00", "price": 2.00},
  {"start": "2026-05-10T16:00:00+02:00", "end": "2026-05-10T17:00:00+02:00", "price": 2.45},
  {"start": "2026-05-10T17:00:00+02:00", "end": "2026-05-10T18:00:00+02:00", "price": 3.05},
  {"start": "2026-05-10T18:00:00+02:00", "end": "2026-05-10T19:00:00+02:00", "price": 3.25},
  {"start": "2026-05-10T19:00:00+02:00", "end": "2026-05-10T20:00:00+02:00", "price": 3.10},
  {"start": "2026-05-10T20:00:00+02:00", "end": "2026-05-10T21:00:00+02:00", "price": 2.75},
  {"start": "2026-05-10T21:00:00+02:00", "end": "2026-05-10T22:00:00+02:00", "price": 2.20},
  {"start": "2026-05-10T22:00:00+02:00", "end": "2026-05-10T23:00:00+02:00", "price": 1.80},
  {"start": "2026-05-10T23:00:00+02:00", "end": "2026-05-11T00:00:00+02:00", "price": 1.45},
  {"start": "2026-05-11T00:00:00+02:00", "end": "2026-05-11T01:00:00+02:00", "price": 1.15},
  {"start": "2026-05-11T01:00:00+02:00", "end": "2026-05-11T02:00:00+02:00", "price": 0.95},
  {"start": "2026-05-11T02:00:00+02:00", "end": "2026-05-11T03:00:00+02:00", "price": 0.65},
  {"start": "2026-05-11T03:00:00+02:00", "end": "2026-05-11T04:00:00+02:00", "price": 0.60},
  {"start": "2026-05-11T04:00:00+02:00", "end": "2026-05-11T05:00:00+02:00", "price": 0.62},
  {"start": "2026-05-11T05:00:00+02:00", "end": "2026-05-11T06:00:00+02:00", "price": 0.85},
  {"start": "2026-05-11T06:00:00+02:00", "end": "2026-05-11T07:00:00+02:00", "price": 1.30},
  {"start": "2026-05-11T07:00:00+02:00", "end": "2026-05-11T08:00:00+02:00", "price": 1.75},
  {"start": "2026-05-11T08:00:00+02:00", "end": "2026-05-11T09:00:00+02:00", "price": 2.05},
  {"start": "2026-05-11T09:00:00+02:00", "end": "2026-05-11T10:00:00+02:00", "price": 1.90},
  {"start": "2026-05-11T10:00:00+02:00", "end": "2026-05-11T11:00:00+02:00", "price": 1.70},
  {"start": "2026-05-11T11:00:00+02:00", "end": "2026-05-11T12:00:00+02:00", "price": 1.55},
  {"start": "2026-05-11T12:00:00+02:00", "end": "2026-05-11T13:00:00+02:00", "price": 1.45},
  {"start": "2026-05-11T13:00:00+02:00", "end": "2026-05-11T14:00:00+02:00", "price": 1.50},
  {"start": "2026-05-11T14:00:00+02:00", "end": "2026-05-11T15:00:00+02:00", "price": 1.65},
  {"start": "2026-05-11T15:00:00+02:00", "end": "2026-05-11T16:00:00+02:00", "price": 1.95},
  {"start": "2026-05-11T16:00:00+02:00", "end": "2026-05-11T17:00:00+02:00", "price": 2.40},
  {"start": "2026-05-11T17:00:00+02:00", "end": "2026-05-11T18:00:00+02:00", "price": 3.00},
  {"start": "2026-05-11T18:00:00+02:00", "end": "2026-05-11T19:00:00+02:00", "price": 3.20},
  {"start": "2026-05-11T19:00:00+02:00", "end": "2026-05-11T20:00:00+02:00", "price": 3.05},
  {"start": "2026-05-11T20:00:00+02:00", "end": "2026-05-11T21:00:00+02:00", "price": 2.70},
  {"start": "2026-05-11T21:00:00+02:00", "end": "2026-05-11T22:00:00+02:00", "price": 2.15},
  {"start": "2026-05-11T22:00:00+02:00", "end": "2026-05-11T23:00:00+02:00", "price": 1.75},
  {"start": "2026-05-11T23:00:00+02:00", "end": "2026-05-12T00:00:00+02:00", "price": 1.40}
]
```

- [ ] **Step 2: Create `custom_components/smart_ev_charging/planner.py` with data types and a stub `make_plan` that raises `NotImplementedError`**

```python
"""Pure Python charging planner. Zero Home Assistant imports — keep it that way."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Literal

PlanStatus = Literal["ok", "partial", "extended", "no_data"]


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


@dataclass(frozen=True)
class Plan:
    selected_starts: list[datetime] = field(default_factory=list)
    deadline: datetime = field(default_factory=lambda: datetime.now(tz=timezone.utc))
    initial_deadline: datetime = field(default_factory=lambda: datetime.now(tz=timezone.utc))
    was_extended: bool = False
    window_size: int = 0
    status: PlanStatus = "no_data"


def make_plan(inp: PlanInput) -> Plan:
    """Compute a charging plan. See spec § 5 Layer 1."""
    raise NotImplementedError
```

- [ ] **Step 3: Create `tests/test_planner.py` with the happy-path test**

```python
"""Tests for the pure planner. No HA dependency."""
from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from custom_components.smart_ev_charging.planner import (
    Plan,
    PlanInput,
    PriceSlot,
    make_plan,
)

CPH = ZoneInfo("Europe/Copenhagen")
FIXTURES = Path(__file__).parent / "fixtures"


def _load_prices() -> list[PriceSlot]:
    raw = json.loads((FIXTURES / "prices_24h.json").read_text())
    return [
        PriceSlot(
            start=datetime.fromisoformat(p["start"]),
            end=datetime.fromisoformat(p["end"]),
            price=p["price"],
        )
        for p in raw
    ]


@pytest.fixture
def prices() -> list[PriceSlot]:
    return _load_prices()


def test_picks_three_cheapest_overnight(prices: list[PriceSlot]) -> None:
    inp = PlanInput(
        prices=prices,
        slots_needed=3,
        departure=datetime(2026, 5, 11, 8, 0, tzinfo=CPH),
        now=datetime(2026, 5, 10, 18, 0, tzinfo=CPH),
    )
    plan = make_plan(inp)
    assert plan.status == "ok"
    assert len(plan.selected_starts) == 3
    expected = {
        datetime(2026, 5, 11, 2, 0, tzinfo=CPH),
        datetime(2026, 5, 11, 3, 0, tzinfo=CPH),
        datetime(2026, 5, 11, 4, 0, tzinfo=CPH),
    }
    assert set(plan.selected_starts) == expected
    assert plan.selected_starts == sorted(plan.selected_starts)
    assert plan.was_extended is False
    assert plan.deadline == datetime(2026, 5, 11, 8, 0, tzinfo=CPH)
    assert plan.initial_deadline == plan.deadline
    assert plan.window_size == 14  # 18:00 today → 08:00 tomorrow exclusive
```

- [ ] **Step 4: Run the test, expect failure with `NotImplementedError`**

Run: `pytest tests/test_planner.py::test_picks_three_cheapest_overnight -v`
Expected: FAIL — `NotImplementedError` raised.

- [ ] **Step 5: Implement `make_plan` to make the test pass**

Replace the stub `make_plan` in `custom_components/smart_ev_charging/planner.py` with:

```python
def make_plan(inp: PlanInput) -> Plan:
    """Compute a charging plan. See spec § 5 Layer 1."""
    slots_needed = max(1, inp.slots_needed)
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
    cheapest = sorted(window, key=lambda s: s.price)[:effective_slots]
    selected_starts = sorted(s.start for s in cheapest)

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
        deadline=deadline,
        initial_deadline=inp.departure,
        was_extended=was_extended,
        window_size=len(window),
        status=status,
    )
```

- [ ] **Step 6: Re-run, expect pass**

Run: `pytest tests/test_planner.py::test_picks_three_cheapest_overnight -v`
Expected: PASS.

- [ ] **Step 7: Lint + type-check**

Run:
```bash
ruff check custom_components/smart_ev_charging/planner.py tests/test_planner.py
mypy --strict custom_components/smart_ev_charging/planner.py tests/test_planner.py
```
Expected: both clean.

- [ ] **Step 8: Commit**

```bash
git -c user.name=twarberg -c user.email=tim@tlw.dk add custom_components/smart_ev_charging/planner.py tests/test_planner.py tests/fixtures/prices_24h.json
git -c user.name=twarberg -c user.email=tim@tlw.dk commit -m "$(cat <<'EOF'
feat(planner): add data types and cheapest-N picking

Adds PriceSlot, PlanInput, Plan dataclasses and make_plan() with the
core algorithm: effective_start, deadline auto-extension, window slice,
cheapest-N selection, and status derivation. Covers the normal-overnight
happy path with a real 48h fixture (peak 17-21, valley 02-05).
EOF
)"
```

---

## Task 3: Planner — full status matrix

**Files:**
- Modify: `tests/test_planner.py` (add parametrized cases)

The planner code is already complete; this task adds the parametrized status-matrix tests required by the spec.

- [ ] **Step 1: Append the status-matrix tests to `tests/test_planner.py`**

```python
def test_no_data_when_prices_empty() -> None:
    plan = make_plan(
        PlanInput(
            prices=[],
            slots_needed=3,
            departure=datetime(2026, 5, 11, 8, 0, tzinfo=CPH),
            now=datetime(2026, 5, 10, 18, 0, tzinfo=CPH),
        )
    )
    assert plan.status == "no_data"
    assert plan.selected_starts == []
    assert plan.window_size == 0


def test_partial_when_window_smaller_than_slots(prices: list[PriceSlot]) -> None:
    inp = PlanInput(
        prices=prices,
        slots_needed=10,
        departure=datetime(2026, 5, 10, 22, 0, tzinfo=CPH),
        now=datetime(2026, 5, 10, 19, 0, tzinfo=CPH),
    )
    plan = make_plan(inp)
    assert plan.status == "partial"
    assert plan.window_size == 3  # 19, 20, 21
    assert len(plan.selected_starts) == 3


def test_extended_when_departure_within_one_hour(prices: list[PriceSlot]) -> None:
    inp = PlanInput(
        prices=prices,
        slots_needed=3,
        departure=datetime(2026, 5, 10, 18, 30, tzinfo=CPH),
        now=datetime(2026, 5, 10, 18, 0, tzinfo=CPH),
    )
    plan = make_plan(inp)
    assert plan.status == "extended"
    assert plan.was_extended is True
    assert plan.deadline == datetime(2026, 5, 11, 18, 30, tzinfo=CPH)
    assert len(plan.selected_starts) == 3


def test_extended_when_now_after_departure(prices: list[PriceSlot]) -> None:
    inp = PlanInput(
        prices=prices,
        slots_needed=3,
        departure=datetime(2026, 5, 10, 8, 0, tzinfo=CPH),
        now=datetime(2026, 5, 10, 18, 0, tzinfo=CPH),
    )
    plan = make_plan(inp)
    assert plan.status == "extended"
    assert plan.was_extended is True
    assert plan.deadline == datetime(2026, 5, 11, 8, 0, tzinfo=CPH)


def test_clamps_zero_slots_to_one(prices: list[PriceSlot]) -> None:
    inp = PlanInput(
        prices=prices,
        slots_needed=0,
        departure=datetime(2026, 5, 11, 8, 0, tzinfo=CPH),
        now=datetime(2026, 5, 10, 18, 0, tzinfo=CPH),
    )
    plan = make_plan(inp)
    assert len(plan.selected_starts) == 1
    assert plan.status == "ok"


def test_sorts_unsorted_prices_defensively(prices: list[PriceSlot]) -> None:
    shuffled = list(reversed(prices))
    inp = PlanInput(
        prices=shuffled,
        slots_needed=3,
        departure=datetime(2026, 5, 11, 8, 0, tzinfo=CPH),
        now=datetime(2026, 5, 10, 18, 0, tzinfo=CPH),
    )
    plan = make_plan(inp)
    assert plan.selected_starts == sorted(plan.selected_starts)
```

- [ ] **Step 2: Run the new tests**

Run: `pytest tests/test_planner.py -v`
Expected: 7 passed (1 from T2 + 6 new).

- [ ] **Step 3: Lint + type-check**

Run:
```bash
ruff check tests/test_planner.py
mypy --strict tests/test_planner.py
```
Expected: clean.

- [ ] **Step 4: Commit**

```bash
git -c user.name=twarberg -c user.email=tim@tlw.dk add tests/test_planner.py
git -c user.name=twarberg -c user.email=tim@tlw.dk commit -m "test(planner): cover status matrix and slot-clamp edges"
```

---

## Task 4: Planner — mid-hour skip and midnight rollover

**Files:**
- Modify: `tests/test_planner.py`

- [ ] **Step 1: Append mid-hour and midnight-cross tests**

```python
def test_mid_hour_plug_in_skips_current_hour(prices: list[PriceSlot]) -> None:
    # at 18:50 with default min_minutes_left=15, current hour (18:00) is skipped
    inp = PlanInput(
        prices=prices,
        slots_needed=2,
        departure=datetime(2026, 5, 10, 22, 0, tzinfo=CPH),
        now=datetime(2026, 5, 10, 18, 50, tzinfo=CPH),
    )
    plan = make_plan(inp)
    assert datetime(2026, 5, 10, 18, 0, tzinfo=CPH) not in plan.selected_starts
    assert plan.window_size == 3  # 19, 20, 21


def test_mid_hour_keeps_current_hour_when_threshold_zero(prices: list[PriceSlot]) -> None:
    inp = PlanInput(
        prices=prices,
        slots_needed=2,
        departure=datetime(2026, 5, 10, 22, 0, tzinfo=CPH),
        now=datetime(2026, 5, 10, 18, 50, tzinfo=CPH),
        min_minutes_left_in_hour=0,
    )
    plan = make_plan(inp)
    assert plan.window_size == 4  # 18, 19, 20, 21


def test_late_night_plug_in_crosses_midnight(prices: list[PriceSlot]) -> None:
    # plug in at 23:50, departure 08:00 next day; effective_start rolls to 00:00
    inp = PlanInput(
        prices=prices,
        slots_needed=3,
        departure=datetime(2026, 5, 11, 8, 0, tzinfo=CPH),
        now=datetime(2026, 5, 10, 23, 50, tzinfo=CPH),
    )
    plan = make_plan(inp)
    assert plan.status == "ok"
    assert all(
        s >= datetime(2026, 5, 11, 0, 0, tzinfo=CPH) for s in plan.selected_starts
    )
    expected = {
        datetime(2026, 5, 11, 2, 0, tzinfo=CPH),
        datetime(2026, 5, 11, 3, 0, tzinfo=CPH),
        datetime(2026, 5, 11, 4, 0, tzinfo=CPH),
    }
    assert set(plan.selected_starts) == expected


def test_filters_past_slots(prices: list[PriceSlot]) -> None:
    # earlier slots in the fixture (00:00-17:00 today) must not appear
    inp = PlanInput(
        prices=prices,
        slots_needed=3,
        departure=datetime(2026, 5, 11, 8, 0, tzinfo=CPH),
        now=datetime(2026, 5, 10, 18, 0, tzinfo=CPH),
    )
    plan = make_plan(inp)
    cutoff = datetime(2026, 5, 10, 18, 0, tzinfo=CPH)
    assert all(s >= cutoff for s in plan.selected_starts)
```

- [ ] **Step 2: Run, expect pass**

Run: `pytest tests/test_planner.py -v`
Expected: 11 passed.

- [ ] **Step 3: Commit**

```bash
git -c user.name=twarberg -c user.email=tim@tlw.dk add tests/test_planner.py
git -c user.name=twarberg -c user.email=tim@tlw.dk commit -m "test(planner): cover mid-hour skip and midnight rollover"
```

---

## Task 5: Planner — DST and mixed timezones

**Files:**
- Modify: `tests/test_planner.py`

- [ ] **Step 1: Append DST + mixed-tz tests**

```python
def test_dst_spring_forward_does_not_synthesize_missing_hour() -> None:
    # 2026-03-29 in Europe/Copenhagen: 02:00 doesn't exist (clock jumps to 03:00)
    # The price array reflects this — only 23 slots that day.
    cph = ZoneInfo("Europe/Copenhagen")
    base = datetime(2026, 3, 28, 0, 0, tzinfo=cph)
    prices: list[PriceSlot] = []
    for h in range(48):
        start = base + timedelta(hours=h)
        # Skip the non-existent 2026-03-29 02:00 CET slot
        if start.date() == datetime(2026, 3, 29).date() and start.hour == 2:
            continue
        prices.append(PriceSlot(start=start, end=start + timedelta(hours=1), price=1.0 + h * 0.01))
    plan = make_plan(
        PlanInput(
            prices=prices,
            slots_needed=3,
            departure=datetime(2026, 3, 29, 8, 0, tzinfo=cph),
            now=datetime(2026, 3, 28, 18, 0, tzinfo=cph),
        )
    )
    nonexistent = datetime(2026, 3, 29, 2, 0, tzinfo=cph)
    assert nonexistent not in plan.selected_starts


def test_mixed_timezones_compare_correctly(prices: list[PriceSlot]) -> None:
    # Pass `now` as UTC; `departure` as CPH. Should still compute correctly.
    from datetime import timezone

    inp = PlanInput(
        prices=prices,
        slots_needed=3,
        departure=datetime(2026, 5, 11, 8, 0, tzinfo=CPH),
        now=datetime(2026, 5, 10, 16, 0, tzinfo=timezone.utc),  # = 18:00 CPH
    )
    plan = make_plan(inp)
    assert plan.status == "ok"
    assert len(plan.selected_starts) == 3
```

- [ ] **Step 2: Run**

Run: `pytest tests/test_planner.py -v`
Expected: 13 passed.

- [ ] **Step 3: Commit**

```bash
git -c user.name=twarberg -c user.email=tim@tlw.dk add tests/test_planner.py
git -c user.name=twarberg -c user.email=tim@tlw.dk commit -m "test(planner): cover DST spring-forward and mixed timezones"
```

---

## Task 6: Planner — hypothesis property tests

**Files:**
- Modify: `tests/test_planner.py`

- [ ] **Step 1: Append property tests**

```python
import itertools

from hypothesis import given, settings
from hypothesis import strategies as st


def _build_prices(start_hour: int, count: int, offsets: list[float]) -> list[PriceSlot]:
    base = datetime(2026, 5, 10, start_hour, 0, tzinfo=CPH)
    return [
        PriceSlot(
            start=base + timedelta(hours=i),
            end=base + timedelta(hours=i + 1),
            price=offsets[i],
        )
        for i in range(count)
    ]


@given(
    count=st.integers(min_value=1, max_value=24),
    slots=st.integers(min_value=1, max_value=12),
    delta_hours=st.integers(min_value=2, max_value=36),
    seed=st.integers(min_value=0, max_value=10_000),
)
@settings(max_examples=80, deadline=None)
def test_picker_optimality(count: int, slots: int, delta_hours: int, seed: int) -> None:
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
        )
    )
    if plan.status == "no_data":
        assert plan.selected_starts == []
        return
    assert plan.selected_starts == sorted(plan.selected_starts)
    window = [
        p
        for p in prices
        if datetime(2026, 5, 10, 0, 0, tzinfo=CPH) <= p.start < plan.deadline
    ]
    selected = [p for p in prices if p.start in plan.selected_starts]
    assert len(selected) == min(slots, len(window))
    sel_total = sum(s.price for s in selected)
    for sub in itertools.combinations(window, len(selected)):
        sub_total = sum(s.price for s in sub)
        assert sel_total <= sub_total + 1e-9
```

- [ ] **Step 2: Run hypothesis suite**

Run: `pytest tests/test_planner.py -v`
Expected: 14 passed (including 80 hypothesis examples).

- [ ] **Step 3: Verify 100% line + branch coverage of `planner.py`**

Run:
```bash
pytest tests/test_planner.py --cov=custom_components.smart_ev_charging.planner --cov-branch --cov-report=term-missing
```
Expected: `planner.py` shows 100% coverage; if any line/branch is uncovered, add a hand-written test for it before committing.

- [ ] **Step 4: Commit**

```bash
git -c user.name=twarberg -c user.email=tim@tlw.dk add tests/test_planner.py
git -c user.name=twarberg -c user.email=tim@tlw.dk commit -m "test(planner): add hypothesis property tests, reach 100% coverage"
```

---

## Task 7: Constants and `price_source.py` adapter

**Files:**
- Create: `custom_components/smart_ev_charging/const.py`, `custom_components/smart_ev_charging/price_source.py`, `tests/test_price_source.py`, `tests/fixtures/stromligning_state.json`

- [ ] **Step 1: Create `const.py`**

```python
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
```

- [ ] **Step 2: Create the sample state fixture `tests/fixtures/stromligning_state.json`**

```json
{
  "stromligning": {
    "entity_id": "sensor.stromligning_current_price_vat",
    "state": "1.45",
    "attributes": {
      "prices": [
        {"start": "2026-05-10T18:00:00+02:00", "end": "2026-05-10T19:00:00+02:00", "price": 3.05},
        {"start": "2026-05-10T19:00:00+02:00", "end": "2026-05-10T20:00:00+02:00", "price": 3.25},
        {"start": "2026-05-10T20:00:00+02:00", "end": "2026-05-10T21:00:00+02:00", "price": 2.75}
      ]
    }
  },
  "nordpool": {
    "entity_id": "sensor.nordpool_kwh_dk2_dkk_3_10_025",
    "state": "1.45",
    "attributes": {
      "today": [
        {"start": "2026-05-10T18:00:00+02:00", "value": 3.05},
        {"start": "2026-05-10T19:00:00+02:00", "value": 3.25},
        {"start": "2026-05-10T20:00:00+02:00", "value": 2.75}
      ]
    }
  },
  "tibber": {
    "entity_id": "sensor.electricity_price_home",
    "state": "1.45",
    "attributes": {
      "today": [
        {"startsAt": "2026-05-10T18:00:00+02:00", "total": 3.05},
        {"startsAt": "2026-05-10T19:00:00+02:00", "total": 3.25},
        {"startsAt": "2026-05-10T20:00:00+02:00", "total": 2.75}
      ]
    }
  }
}
```

- [ ] **Step 3: Create `tests/test_price_source.py` with the failing happy-path test**

```python
"""Tests for the price-source adapter."""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import pytest

from custom_components.smart_ev_charging.price_source import PriceSource

CPH = ZoneInfo("Europe/Copenhagen")
FIXTURES = Path(__file__).parent / "fixtures"


class _FakeState:
    def __init__(self, state: str, attributes: dict[str, Any]) -> None:
        self.state = state
        self.attributes = attributes


class _FakeStates:
    def __init__(self) -> None:
        self._states: dict[str, _FakeState] = {}

    def add(self, entity_id: str, state: str, attributes: dict[str, Any]) -> None:
        self._states[entity_id] = _FakeState(state, attributes)

    def get(self, entity_id: str) -> _FakeState | None:
        return self._states.get(entity_id)


class _FakeHass:
    def __init__(self) -> None:
        self.states = _FakeStates()


@pytest.fixture
def hass() -> _FakeHass:
    return _FakeHass()


@pytest.fixture
def state_fixture() -> dict[str, Any]:
    return json.loads((FIXTURES / "stromligning_state.json").read_text())


def test_stromligning_shape(hass: _FakeHass, state_fixture: dict[str, Any]) -> None:
    fx = state_fixture["stromligning"]
    hass.states.add(fx["entity_id"], fx["state"], fx["attributes"])
    src = PriceSource(
        hass=hass,
        entity_id=fx["entity_id"],
        attr_name="prices",
        start_field="start",
        price_field="price",
        end_field="end",
    )
    slots = src.get_slots()
    assert len(slots) == 3
    assert slots[0].start == datetime(2026, 5, 10, 18, 0, tzinfo=CPH)
    assert slots[0].end == datetime(2026, 5, 10, 19, 0, tzinfo=CPH)
    assert slots[0].price == 3.05
    assert slots == sorted(slots, key=lambda s: s.start)
```

- [ ] **Step 4: Create `custom_components/smart_ev_charging/price_source.py`**

```python
"""Adapter that reads a price-bearing entity and normalizes to PriceSlot list."""
from __future__ import annotations

import logging
from collections.abc import Mapping
from datetime import datetime, timedelta, timezone
from typing import Any, Protocol

from .const import UNAVAILABLE_STATES
from .planner import PriceSlot

_LOGGER = logging.getLogger(__name__)


class _StateLike(Protocol):
    state: str
    attributes: Mapping[str, Any]


class _StatesLike(Protocol):
    def get(self, entity_id: str) -> _StateLike | None: ...


class _HassLike(Protocol):
    states: _StatesLike


def _parse_dt(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(float(value), tz=timezone.utc)
    if isinstance(value, str):
        try:
            dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    return None


class PriceSource:
    """Reads a price-bearing entity, normalizes to list[PriceSlot]."""

    def __init__(
        self,
        hass: _HassLike,
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
            self._warn_once("attr_not_list", f"attribute {self._attr_name!r} is not a non-empty list")
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
```

- [ ] **Step 5: Run the test, expect pass**

Run: `pytest tests/test_price_source.py -v`
Expected: 1 passed.

- [ ] **Step 6: Add Nord Pool, Tibber, error-handling, and malformed-entry tests**

Append to `tests/test_price_source.py`:

```python
def test_nordpool_shape(hass: _FakeHass, state_fixture: dict[str, Any]) -> None:
    fx = state_fixture["nordpool"]
    hass.states.add(fx["entity_id"], fx["state"], fx["attributes"])
    src = PriceSource(
        hass=hass,
        entity_id=fx["entity_id"],
        attr_name="today",
        start_field="start",
        price_field="value",
    )
    slots = src.get_slots()
    assert len(slots) == 3
    assert slots[0].price == 3.05


def test_tibber_shape(hass: _FakeHass, state_fixture: dict[str, Any]) -> None:
    fx = state_fixture["tibber"]
    hass.states.add(fx["entity_id"], fx["state"], fx["attributes"])
    src = PriceSource(
        hass=hass,
        entity_id=fx["entity_id"],
        attr_name="today",
        start_field="startsAt",
        price_field="total",
    )
    slots = src.get_slots()
    assert len(slots) == 3


def test_entity_missing_returns_empty(hass: _FakeHass) -> None:
    src = PriceSource(hass=hass, entity_id="sensor.does_not_exist",
                      attr_name="prices", start_field="start", price_field="price")
    assert src.get_slots() == []


def test_entity_unavailable_returns_empty(hass: _FakeHass) -> None:
    hass.states.add("sensor.x", "unavailable", {"prices": [{"start": "2026-05-10T00:00:00+02:00", "price": 1.0}]})
    src = PriceSource(hass=hass, entity_id="sensor.x",
                      attr_name="prices", start_field="start", price_field="price")
    assert src.get_slots() == []


def test_attribute_missing_returns_empty(hass: _FakeHass) -> None:
    hass.states.add("sensor.x", "1.0", {})
    src = PriceSource(hass=hass, entity_id="sensor.x",
                      attr_name="prices", start_field="start", price_field="price")
    assert src.get_slots() == []


def test_attribute_not_a_list_returns_empty(hass: _FakeHass) -> None:
    hass.states.add("sensor.x", "1.0", {"prices": "oops"})
    src = PriceSource(hass=hass, entity_id="sensor.x",
                      attr_name="prices", start_field="start", price_field="price")
    assert src.get_slots() == []


def test_malformed_entries_dropped_good_ones_kept(hass: _FakeHass, caplog: pytest.LogCaptureFixture) -> None:
    hass.states.add("sensor.x", "1.0", {
        "prices": [
            {"start": "2026-05-10T00:00:00+02:00", "price": 1.0},
            {"start": "not a date", "price": 2.0},
            {"start": "2026-05-10T02:00:00+02:00"},  # missing price
            {"start": "2026-05-10T01:00:00+02:00", "price": 1.5},
        ],
    })
    src = PriceSource(hass=hass, entity_id="sensor.x",
                      attr_name="prices", start_field="start", price_field="price")
    slots = src.get_slots()
    assert len(slots) == 2
    assert slots[0].start.hour == 0
    assert slots[1].start.hour == 1


def test_warns_only_once_per_failure(hass: _FakeHass, caplog: pytest.LogCaptureFixture) -> None:
    import logging

    src = PriceSource(hass=hass, entity_id="sensor.missing",
                      attr_name="prices", start_field="start", price_field="price")
    with caplog.at_level(logging.WARNING):
        src.get_slots()
        src.get_slots()
        src.get_slots()
    matching = [r for r in caplog.records if "entity missing or unavailable" in r.message]
    assert len(matching) == 1


def test_unix_timestamp_start_is_parsed(hass: _FakeHass) -> None:
    hass.states.add("sensor.x", "1.0", {
        "prices": [{"start": 1746883200, "price": 1.0}],  # 2025-05-10 14:00:00 UTC
    })
    src = PriceSource(hass=hass, entity_id="sensor.x",
                      attr_name="prices", start_field="start", price_field="price")
    slots = src.get_slots()
    assert len(slots) == 1
    assert slots[0].start.tzinfo is not None
```

- [ ] **Step 7: Run all price_source tests**

Run: `pytest tests/test_price_source.py -v --cov=custom_components.smart_ev_charging.price_source --cov-branch`
Expected: 9 passed; coverage ≥ 95%.

- [ ] **Step 8: Lint + type-check**

Run:
```bash
ruff check custom_components/smart_ev_charging tests
mypy --strict custom_components/smart_ev_charging tests
```
Expected: clean.

- [ ] **Step 9: Commit**

```bash
git -c user.name=twarberg -c user.email=tim@tlw.dk add custom_components/smart_ev_charging/const.py custom_components/smart_ev_charging/price_source.py tests/test_price_source.py tests/fixtures/stromligning_state.json
git -c user.name=twarberg -c user.email=tim@tlw.dk commit -m "$(cat <<'EOF'
feat(price_source): adapter for hourly-price entities

const.py defines DOMAIN, CONF_*, DEFAULT_*, PLATFORMS, event names and
the heartbeat interval. price_source.py normalizes Strømligning,
Nord Pool and Tibber attribute shapes into list[PriceSlot] with
defensive parsing of mixed start types and dedup-once warnings on
failure modes.
EOF
)"
```

---

## Task 8: `car_state.py` adapter

**Files:**
- Create: `custom_components/smart_ev_charging/car_state.py`, `tests/test_car_state.py`

- [ ] **Step 1: Create `tests/test_car_state.py` with happy-path tests**

```python
"""Tests for the car-state adapter."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import time
from typing import Any

import pytest

from custom_components.smart_ev_charging.car_state import (
    CarStateConfig,
    read_car_state,
)


class _FakeState:
    def __init__(self, state: str, attributes: dict[str, Any] | None = None) -> None:
        self.state = state
        self.attributes = attributes or {}


class _FakeStates:
    def __init__(self) -> None:
        self._states: dict[str, _FakeState] = {}

    def add(self, entity_id: str, state: str, attributes: dict[str, Any] | None = None) -> None:
        self._states[entity_id] = _FakeState(state, attributes)

    def get(self, entity_id: str) -> _FakeState | None:
        return self._states.get(entity_id)


class _FakeHass:
    def __init__(self) -> None:
        self.states = _FakeStates()


@pytest.fixture
def hass() -> _FakeHass:
    return _FakeHass()


def _full_config() -> CarStateConfig:
    return CarStateConfig(
        soc_entity="sensor.car_soc",
        target_soc_entity="sensor.car_target",
        charging_status_entity="sensor.car_status",
        plug_unplugged_values=["3", "unplugged"],
        actively_charging_values=["0", "charging"],
        departure_entity="sensor.car_departure",
    )


def test_full_state_reported(hass: _FakeHass) -> None:
    hass.states.add("sensor.car_soc", "65")
    hass.states.add("sensor.car_target", "80")
    hass.states.add("sensor.car_status", "0")
    hass.states.add("sensor.car_departure", "07:30:00")
    cs = read_car_state(hass, _full_config())
    assert cs.soc_percent == 65.0
    assert cs.target_soc_percent == 80.0
    assert cs.plug_raw_state == "0"
    assert cs.plugged_in is True
    assert cs.actively_charging is True
    assert cs.departure == time(7, 30)


def test_mercedes_numeric_unplugged(hass: _FakeHass) -> None:
    hass.states.add("sensor.car_soc", "65")
    hass.states.add("sensor.car_target", "80")
    hass.states.add("sensor.car_status", "3")
    cfg = _full_config()
    cfg = CarStateConfig(**{**cfg.__dict__, "departure_entity": None})
    cs = read_car_state(hass, cfg)
    assert cs.plugged_in is False
    assert cs.actively_charging is False


def test_tesla_string_unplugged(hass: _FakeHass) -> None:
    hass.states.add("sensor.car_soc", "65")
    hass.states.add("sensor.car_target", "80")
    hass.states.add("sensor.car_status", "unplugged")
    cs = read_car_state(hass, _full_config())
    assert cs.plugged_in is False


def test_unknown_status_is_not_plugged(hass: _FakeHass) -> None:
    hass.states.add("sensor.car_status", "unknown")
    cfg = CarStateConfig(
        soc_entity=None,
        target_soc_entity=None,
        charging_status_entity="sensor.car_status",
        plug_unplugged_values=["3"],
        actively_charging_values=["0"],
        departure_entity=None,
    )
    cs = read_car_state(hass, cfg)
    assert cs.plug_raw_state == "unknown"
    assert cs.plugged_in is False


def test_no_charging_status_entity_means_plugged(hass: _FakeHass) -> None:
    cfg = CarStateConfig(
        soc_entity=None, target_soc_entity=None,
        charging_status_entity=None,
        plug_unplugged_values=[], actively_charging_values=[],
        departure_entity=None,
    )
    cs = read_car_state(hass, cfg)
    assert cs.plug_raw_state is None
    assert cs.plugged_in is True


def test_departure_short_form(hass: _FakeHass) -> None:
    hass.states.add("sensor.car_departure", "08:00")
    cfg = CarStateConfig(
        soc_entity=None, target_soc_entity=None, charging_status_entity=None,
        plug_unplugged_values=[], actively_charging_values=[],
        departure_entity="sensor.car_departure",
    )
    cs = read_car_state(hass, cfg)
    assert cs.departure == time(8, 0)


def test_departure_unknown_is_none(hass: _FakeHass) -> None:
    hass.states.add("sensor.car_departure", "unknown")
    cfg = CarStateConfig(
        soc_entity=None, target_soc_entity=None, charging_status_entity=None,
        plug_unplugged_values=[], actively_charging_values=[],
        departure_entity="sensor.car_departure",
    )
    cs = read_car_state(hass, cfg)
    assert cs.departure is None


def test_unparseable_soc_is_none(hass: _FakeHass) -> None:
    hass.states.add("sensor.car_soc", "unavailable")
    cfg = CarStateConfig(
        soc_entity="sensor.car_soc", target_soc_entity=None, charging_status_entity=None,
        plug_unplugged_values=[], actively_charging_values=[],
        departure_entity=None,
    )
    cs = read_car_state(hass, cfg)
    assert cs.soc_percent is None
```

- [ ] **Step 2: Create `custom_components/smart_ev_charging/car_state.py`**

```python
"""Adapter that reads optional car entities into a uniform CarState."""
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import time
from typing import Any, Protocol

from .const import UNAVAILABLE_STATES


@dataclass(frozen=True)
class CarStateConfig:
    soc_entity: str | None
    target_soc_entity: str | None
    charging_status_entity: str | None
    plug_unplugged_values: list[str]
    actively_charging_values: list[str]
    departure_entity: str | None


@dataclass(frozen=True)
class CarState:
    soc_percent: float | None
    target_soc_percent: float | None
    plug_raw_state: str | None
    plugged_in: bool
    actively_charging: bool
    departure: time | None


class _StateLike(Protocol):
    state: str
    attributes: Mapping[str, Any]


class _StatesLike(Protocol):
    def get(self, entity_id: str) -> _StateLike | None: ...


class _HassLike(Protocol):
    states: _StatesLike


def _read_float(hass: _HassLike, entity_id: str | None) -> float | None:
    if not entity_id:
        return None
    state = hass.states.get(entity_id)
    if state is None or state.state in UNAVAILABLE_STATES:
        return None
    try:
        return float(state.state)
    except (TypeError, ValueError):
        return None


def _read_time(hass: _HassLike, entity_id: str | None) -> time | None:
    if not entity_id:
        return None
    state = hass.states.get(entity_id)
    if state is None or state.state in UNAVAILABLE_STATES:
        return None
    try:
        parts = state.state.split(":")
        h = int(parts[0])
        m = int(parts[1]) if len(parts) > 1 else 0
        s = int(parts[2]) if len(parts) > 2 else 0
        return time(hour=h, minute=m, second=s)
    except (TypeError, ValueError, IndexError):
        return None


def read_car_state(hass: _HassLike, config: CarStateConfig) -> CarState:
    soc = _read_float(hass, config.soc_entity)
    target = _read_float(hass, config.target_soc_entity)
    departure = _read_time(hass, config.departure_entity)

    if config.charging_status_entity is None:
        return CarState(
            soc_percent=soc,
            target_soc_percent=target,
            plug_raw_state=None,
            plugged_in=True,
            actively_charging=False,
            departure=departure,
        )

    state = hass.states.get(config.charging_status_entity)
    raw = state.state if state is not None else None
    if raw is None or raw in UNAVAILABLE_STATES:
        return CarState(
            soc_percent=soc,
            target_soc_percent=target,
            plug_raw_state=raw,
            plugged_in=False,
            actively_charging=False,
            departure=departure,
        )

    plugged_in = raw not in config.plug_unplugged_values
    actively_charging = raw in config.actively_charging_values
    return CarState(
        soc_percent=soc,
        target_soc_percent=target,
        plug_raw_state=raw,
        plugged_in=plugged_in,
        actively_charging=actively_charging,
        departure=departure,
    )
```

- [ ] **Step 3: Run tests**

Run: `pytest tests/test_car_state.py -v --cov=custom_components.smart_ev_charging.car_state --cov-branch`
Expected: 8 passed; coverage ≥ 95%.

- [ ] **Step 4: Lint + type-check**

Run:
```bash
ruff check custom_components/smart_ev_charging tests
mypy --strict custom_components/smart_ev_charging tests
```
Expected: clean.

- [ ] **Step 5: Commit**

```bash
git -c user.name=twarberg -c user.email=tim@tlw.dk add custom_components/smart_ev_charging/car_state.py tests/test_car_state.py
git -c user.name=twarberg -c user.email=tim@tlw.dk commit -m "feat(car_state): adapter normalizing optional car entities"
```

---

## Task 9: Config flow — `user`, `price`, `charger` steps

**Files:**
- Create: `custom_components/smart_ev_charging/config_flow.py`, `tests/test_config_flow.py`

- [ ] **Step 1: Create `custom_components/smart_ev_charging/config_flow.py` with the user, price, charger steps**

```python
"""Config + Options flow for Smart EV Charging."""
from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.const import CONF_NAME
from homeassistant.core import HomeAssistant, callback
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers import selector

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
    DEFAULT_END_FIELD,
    DEFAULT_MIN_MINUTES_LEFT,
    DEFAULT_NAME,
    DEFAULT_PLUG_UNPLUGGED_VALUES,
    DEFAULT_PRICE_ATTRIBUTE,
    DEFAULT_PRICE_FIELD,
    DEFAULT_START_FIELD,
    DOMAIN,
)


def _name_already_used(hass: HomeAssistant, name: str) -> bool:
    target = name.strip().lower()
    for entry in hass.config_entries.async_entries(DOMAIN):
        if entry.title.strip().lower() == target:
            return True
    return False


def _validate_price_source(
    hass: HomeAssistant, data: Mapping[str, Any]
) -> tuple[dict[str, str], str | None]:
    state = hass.states.get(data[CONF_PRICE_ENTITY])
    if state is None:
        return {CONF_PRICE_ENTITY: "entity_not_found"}, None
    attr = state.attributes.get(data[CONF_PRICE_ATTRIBUTE])
    if attr is None:
        return {CONF_PRICE_ATTRIBUTE: "attribute_not_found"}, ", ".join(state.attributes.keys())
    if not isinstance(attr, list) or not attr:
        return {CONF_PRICE_ATTRIBUTE: "attribute_not_a_list"}, None
    first = attr[0]
    if not isinstance(first, Mapping):
        return {CONF_PRICE_ATTRIBUTE: "entries_not_dicts"}, None
    missing = [
        f for f in (data[CONF_START_FIELD], data[CONF_PRICE_FIELD]) if f not in first
    ]
    if missing:
        return {CONF_START_FIELD: "field_not_found"}, ", ".join(first.keys())
    return {}, None


_USER_SCHEMA = vol.Schema(
    {vol.Required(CONF_NAME, default=DEFAULT_NAME): str}
)

_PRICE_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_PRICE_ENTITY): selector.EntitySelector(
            selector.EntitySelectorConfig(domain=["sensor", "binary_sensor"])
        ),
        vol.Required(CONF_PRICE_ATTRIBUTE, default=DEFAULT_PRICE_ATTRIBUTE): str,
        vol.Required(CONF_START_FIELD, default=DEFAULT_START_FIELD): str,
        vol.Required(CONF_PRICE_FIELD, default=DEFAULT_PRICE_FIELD): str,
        vol.Optional(CONF_END_FIELD, default=DEFAULT_END_FIELD): str,
    }
)

_CHARGER_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_CHARGER_SWITCH): selector.EntitySelector(
            selector.EntitySelectorConfig(domain="switch")
        ),
        vol.Required(CONF_CHARGER_KW, default=DEFAULT_CHARGER_KW): selector.NumberSelector(
            selector.NumberSelectorConfig(min=0.5, max=22, step=0.1, mode=selector.NumberSelectorMode.BOX)
        ),
    }
)


class SmartEVConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    def __init__(self) -> None:
        self._data: dict[str, Any] = {}

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            if not user_input[CONF_NAME].strip():
                errors[CONF_NAME] = "name_empty"
            elif _name_already_used(self.hass, user_input[CONF_NAME]):
                return self.async_abort(reason="already_configured")
            else:
                self._data[CONF_NAME] = user_input[CONF_NAME].strip()
                return await self.async_step_price()
        return self.async_show_form(step_id="user", data_schema=_USER_SCHEMA, errors=errors)

    async def async_step_price(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        errors: dict[str, str] = {}
        peek: str | None = None
        if user_input is not None:
            errors, peek = _validate_price_source(self.hass, user_input)
            if not errors:
                self._data.update(user_input)
                return await self.async_step_charger()
        return self.async_show_form(
            step_id="price",
            data_schema=_PRICE_SCHEMA,
            errors=errors,
            description_placeholders={"peek": peek or ""},
        )

    async def async_step_charger(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        if user_input is not None:
            self._data.update(user_input)
            return await self.async_step_car()
        return self.async_show_form(step_id="charger", data_schema=_CHARGER_SCHEMA)

    async def async_step_car(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        # Implemented in T10
        if user_input is not None:
            self._data.update(user_input)
            return await self.async_step_defaults()
        return self.async_show_form(step_id="car", data_schema=vol.Schema({}))

    async def async_step_defaults(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        # Implemented in T10
        if user_input is not None:
            self._data.update(user_input)
            return self.async_create_entry(title=self._data[CONF_NAME], data=self._data)
        return self.async_show_form(step_id="defaults", data_schema=vol.Schema({}))

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> config_entries.OptionsFlow:
        return SmartEVOptionsFlow(config_entry)


class SmartEVOptionsFlow(config_entries.OptionsFlow):
    def __init__(self, entry: config_entries.ConfigEntry) -> None:
        self._entry = entry
        self._data: dict[str, Any] = {}

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        # Full implementation in T11
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)
        return self.async_show_form(step_id="init", data_schema=vol.Schema({}))
```

- [ ] **Step 2: Create `tests/test_config_flow.py` with first three steps tested**

```python
"""Tests for the config + options flow."""
from __future__ import annotations

from typing import Any

import pytest
from homeassistant.const import CONF_NAME
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType

from custom_components.smart_ev_charging.const import (
    CONF_CHARGER_KW,
    CONF_CHARGER_SWITCH,
    CONF_PRICE_ATTRIBUTE,
    CONF_PRICE_ENTITY,
    CONF_PRICE_FIELD,
    CONF_START_FIELD,
    DOMAIN,
)


async def _seed_price_entity(hass: HomeAssistant, **overrides: Any) -> None:
    entity_id = overrides.get("entity_id", "sensor.fake_prices")
    attrs = overrides.get("attributes", {
        "prices": [{"start": "2026-05-10T18:00:00+02:00", "price": 3.05, "end": "2026-05-10T19:00:00+02:00"}],
    })
    hass.states.async_set(entity_id, "1.45", attrs)


async def _seed_charger_switch(hass: HomeAssistant) -> None:
    hass.states.async_set("switch.charger", "off", {})


async def _start_user_step(hass: HomeAssistant) -> dict[str, Any]:
    return await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})


async def test_user_step_advances_to_price(hass: HomeAssistant) -> None:
    result = await _start_user_step(hass)
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "user"

    result = await hass.config_entries.flow.async_configure(result["flow_id"], {CONF_NAME: "Daily"})
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "price"


async def test_price_step_validates_attribute_missing(hass: HomeAssistant) -> None:
    hass.states.async_set("sensor.fake_prices", "1.45", {})
    await _seed_charger_switch(hass)
    r = await _start_user_step(hass)
    r = await hass.config_entries.flow.async_configure(r["flow_id"], {CONF_NAME: "Daily"})
    r = await hass.config_entries.flow.async_configure(
        r["flow_id"],
        {
            CONF_PRICE_ENTITY: "sensor.fake_prices",
            CONF_PRICE_ATTRIBUTE: "prices",
            CONF_START_FIELD: "start",
            CONF_PRICE_FIELD: "price",
        },
    )
    assert r["type"] == FlowResultType.FORM
    assert r["errors"] == {CONF_PRICE_ATTRIBUTE: "attribute_not_found"}


async def test_price_step_validates_field_missing(hass: HomeAssistant) -> None:
    hass.states.async_set("sensor.fake_prices", "1.45", {
        "prices": [{"start": "2026-05-10T18:00:00+02:00", "value": 3.05}],
    })
    r = await _start_user_step(hass)
    r = await hass.config_entries.flow.async_configure(r["flow_id"], {CONF_NAME: "Daily"})
    r = await hass.config_entries.flow.async_configure(
        r["flow_id"],
        {
            CONF_PRICE_ENTITY: "sensor.fake_prices",
            CONF_PRICE_ATTRIBUTE: "prices",
            CONF_START_FIELD: "start",
            CONF_PRICE_FIELD: "price",  # actual key is `value`
        },
    )
    assert r["type"] == FlowResultType.FORM
    assert r["errors"] == {CONF_START_FIELD: "field_not_found"}
    assert "value" in r["description_placeholders"]["peek"]


async def test_price_step_advances_on_valid_attrs(hass: HomeAssistant) -> None:
    await _seed_price_entity(hass)
    r = await _start_user_step(hass)
    r = await hass.config_entries.flow.async_configure(r["flow_id"], {CONF_NAME: "Daily"})
    r = await hass.config_entries.flow.async_configure(
        r["flow_id"],
        {
            CONF_PRICE_ENTITY: "sensor.fake_prices",
            CONF_PRICE_ATTRIBUTE: "prices",
            CONF_START_FIELD: "start",
            CONF_PRICE_FIELD: "price",
        },
    )
    assert r["step_id"] == "charger"


async def test_charger_step_advances_to_car(hass: HomeAssistant) -> None:
    await _seed_price_entity(hass)
    await _seed_charger_switch(hass)
    r = await _start_user_step(hass)
    r = await hass.config_entries.flow.async_configure(r["flow_id"], {CONF_NAME: "Daily"})
    r = await hass.config_entries.flow.async_configure(r["flow_id"], {
        CONF_PRICE_ENTITY: "sensor.fake_prices",
        CONF_PRICE_ATTRIBUTE: "prices",
        CONF_START_FIELD: "start",
        CONF_PRICE_FIELD: "price",
    })
    r = await hass.config_entries.flow.async_configure(r["flow_id"], {
        CONF_CHARGER_SWITCH: "switch.charger",
        CONF_CHARGER_KW: 11.0,
    })
    assert r["step_id"] == "car"
```

- [ ] **Step 3: Run tests**

Run: `pytest tests/test_config_flow.py -v`
Expected: 5 passed.

- [ ] **Step 4: Lint + type-check**

Run:
```bash
ruff check custom_components/smart_ev_charging tests
mypy --strict custom_components/smart_ev_charging tests
```
Expected: clean.

- [ ] **Step 5: Commit**

```bash
git -c user.name=twarberg -c user.email=tim@tlw.dk add custom_components/smart_ev_charging/config_flow.py tests/test_config_flow.py
git -c user.name=twarberg -c user.email=tim@tlw.dk commit -m "feat(config_flow): user/price/charger steps with peek validation"
```

---

## Task 10: Config flow — `car` and `defaults` steps

**Files:**
- Modify: `custom_components/smart_ev_charging/config_flow.py`, `tests/test_config_flow.py`

- [ ] **Step 1: Replace the placeholder `async_step_car` and `async_step_defaults` in `config_flow.py`**

Add these schemas near the top, alongside the existing ones:

```python
_CAR_SCHEMA = vol.Schema(
    {
        vol.Optional(CONF_SOC_ENTITY): selector.EntitySelector(
            selector.EntitySelectorConfig(domain="sensor")
        ),
        vol.Optional(CONF_TARGET_SOC_ENTITY): selector.EntitySelector(
            selector.EntitySelectorConfig(domain=["sensor", "number"])
        ),
        vol.Optional(CONF_CHARGING_STATUS_ENTITY): selector.EntitySelector(
            selector.EntitySelectorConfig(domain=["sensor", "binary_sensor"])
        ),
        vol.Optional(CONF_PLUG_UNPLUGGED_VALUES, default=DEFAULT_PLUG_UNPLUGGED_VALUES): selector.TextSelector(
            selector.TextSelectorConfig(multiple=True)
        ),
        vol.Optional(CONF_ACTIVELY_CHARGING_VALUES, default=DEFAULT_ACTIVELY_CHARGING_VALUES): selector.TextSelector(
            selector.TextSelectorConfig(multiple=True)
        ),
        vol.Optional(CONF_DEPARTURE_ENTITY): selector.EntitySelector(
            selector.EntitySelectorConfig()
        ),
        vol.Optional(CONF_BATTERY_KWH, default=DEFAULT_BATTERY_KWH): selector.NumberSelector(
            selector.NumberSelectorConfig(min=1, max=200, step=0.1, mode=selector.NumberSelectorMode.BOX)
        ),
    }
)

_DEFAULTS_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_DEFAULT_DEPARTURE, default=DEFAULT_DEPARTURE_TIME): selector.TimeSelector(),
        vol.Optional(CONF_MIN_MINUTES_LEFT_IN_HOUR, default=DEFAULT_MIN_MINUTES_LEFT): selector.NumberSelector(
            selector.NumberSelectorConfig(min=0, max=59, step=1, mode=selector.NumberSelectorMode.BOX)
        ),
        vol.Optional(CONF_AUTO_REPLAN_ON_PRICE_UPDATE, default=DEFAULT_AUTO_REPLAN_ON_PRICE_UPDATE): selector.BooleanSelector(),
        vol.Optional(CONF_AUTO_REPLAN_ON_SOC_CHANGE, default=DEFAULT_AUTO_REPLAN_ON_SOC_CHANGE): selector.BooleanSelector(),
    }
)
```

Replace the two `async_step_car` and `async_step_defaults` methods with:

```python
    async def async_step_car(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        if user_input is not None:
            self._data.update(user_input)
            return await self.async_step_defaults()
        return self.async_show_form(step_id="car", data_schema=_CAR_SCHEMA)

    async def async_step_defaults(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        if user_input is not None:
            self._data.update(user_input)
            return self.async_create_entry(title=self._data[CONF_NAME], data=self._data)
        return self.async_show_form(step_id="defaults", data_schema=_DEFAULTS_SCHEMA)
```

- [ ] **Step 2: Append happy-path + duplicate-name + skip-car tests**

```python
async def test_full_happy_path_creates_entry(hass: HomeAssistant) -> None:
    await _seed_price_entity(hass)
    await _seed_charger_switch(hass)
    r = await _start_user_step(hass)
    r = await hass.config_entries.flow.async_configure(r["flow_id"], {CONF_NAME: "Daily"})
    r = await hass.config_entries.flow.async_configure(r["flow_id"], {
        CONF_PRICE_ENTITY: "sensor.fake_prices",
        CONF_PRICE_ATTRIBUTE: "prices",
        CONF_START_FIELD: "start",
        CONF_PRICE_FIELD: "price",
    })
    r = await hass.config_entries.flow.async_configure(r["flow_id"], {
        CONF_CHARGER_SWITCH: "switch.charger",
        CONF_CHARGER_KW: 11.0,
    })
    r = await hass.config_entries.flow.async_configure(r["flow_id"], {})  # all car fields skipped
    r = await hass.config_entries.flow.async_configure(r["flow_id"], {
        "default_departure": "08:00:00",
    })
    assert r["type"] == FlowResultType.CREATE_ENTRY
    assert r["title"] == "Daily"
    assert r["data"][CONF_PRICE_ENTITY] == "sensor.fake_prices"


async def test_duplicate_name_aborts(hass: HomeAssistant) -> None:
    from pytest_homeassistant_custom_component.common import MockConfigEntry

    MockConfigEntry(domain=DOMAIN, title="Daily", data={CONF_NAME: "Daily"}).add_to_hass(hass)
    r = await _start_user_step(hass)
    r = await hass.config_entries.flow.async_configure(r["flow_id"], {CONF_NAME: "daily"})
    assert r["type"] == FlowResultType.ABORT
    assert r["reason"] == "already_configured"
```

- [ ] **Step 3: Run tests**

Run: `pytest tests/test_config_flow.py -v`
Expected: 7 passed.

- [ ] **Step 4: Lint + type-check + commit**

```bash
ruff check custom_components/smart_ev_charging tests
mypy --strict custom_components/smart_ev_charging tests
git -c user.name=twarberg -c user.email=tim@tlw.dk add custom_components/smart_ev_charging/config_flow.py tests/test_config_flow.py
git -c user.name=twarberg -c user.email=tim@tlw.dk commit -m "feat(config_flow): car + defaults steps and entry creation"
```

---

## Task 11: OptionsFlow

**Files:**
- Modify: `custom_components/smart_ev_charging/config_flow.py`, `tests/test_config_flow.py`

- [ ] **Step 1: Replace `SmartEVOptionsFlow` with the full implementation**

Build the schema explicitly per field, pre-filling defaults from the merged
config so the form opens populated with the user's existing settings.

```python
class SmartEVOptionsFlow(config_entries.OptionsFlow):
    def __init__(self, entry: config_entries.ConfigEntry) -> None:
        self._entry = entry

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        if user_input is not None:
            errors, peek = _validate_price_source(self.hass, {**self._entry.data, **self._entry.options, **user_input})
            if errors:
                return self.async_show_form(
                    step_id="init",
                    data_schema=self._build_schema(),
                    errors=errors,
                    description_placeholders={"peek": peek or ""},
                )
            return self.async_create_entry(title="", data=user_input)
        return self.async_show_form(step_id="init", data_schema=self._build_schema())

    def _build_schema(self) -> vol.Schema:
        merged: dict[str, Any] = {**self._entry.data, **self._entry.options}

        def d(key: str, fallback: Any) -> Any:
            return merged.get(key, fallback)

        return vol.Schema({
            vol.Required(CONF_PRICE_ENTITY, default=d(CONF_PRICE_ENTITY, vol.UNDEFINED)): selector.EntitySelector(
                selector.EntitySelectorConfig(domain=["sensor", "binary_sensor"])
            ),
            vol.Required(CONF_PRICE_ATTRIBUTE, default=d(CONF_PRICE_ATTRIBUTE, DEFAULT_PRICE_ATTRIBUTE)): str,
            vol.Required(CONF_START_FIELD, default=d(CONF_START_FIELD, DEFAULT_START_FIELD)): str,
            vol.Required(CONF_PRICE_FIELD, default=d(CONF_PRICE_FIELD, DEFAULT_PRICE_FIELD)): str,
            vol.Optional(CONF_END_FIELD, default=d(CONF_END_FIELD, DEFAULT_END_FIELD)): str,
            vol.Required(CONF_CHARGER_SWITCH, default=d(CONF_CHARGER_SWITCH, vol.UNDEFINED)): selector.EntitySelector(
                selector.EntitySelectorConfig(domain="switch")
            ),
            vol.Required(CONF_CHARGER_KW, default=d(CONF_CHARGER_KW, DEFAULT_CHARGER_KW)): selector.NumberSelector(
                selector.NumberSelectorConfig(min=0.5, max=22, step=0.1, mode=selector.NumberSelectorMode.BOX)
            ),
            vol.Optional(CONF_SOC_ENTITY, default=d(CONF_SOC_ENTITY, vol.UNDEFINED)): selector.EntitySelector(
                selector.EntitySelectorConfig(domain="sensor")
            ),
            vol.Optional(CONF_TARGET_SOC_ENTITY, default=d(CONF_TARGET_SOC_ENTITY, vol.UNDEFINED)): selector.EntitySelector(
                selector.EntitySelectorConfig(domain=["sensor", "number"])
            ),
            vol.Optional(CONF_CHARGING_STATUS_ENTITY, default=d(CONF_CHARGING_STATUS_ENTITY, vol.UNDEFINED)): selector.EntitySelector(
                selector.EntitySelectorConfig(domain=["sensor", "binary_sensor"])
            ),
            vol.Optional(CONF_PLUG_UNPLUGGED_VALUES, default=d(CONF_PLUG_UNPLUGGED_VALUES, DEFAULT_PLUG_UNPLUGGED_VALUES)): selector.TextSelector(
                selector.TextSelectorConfig(multiple=True)
            ),
            vol.Optional(CONF_ACTIVELY_CHARGING_VALUES, default=d(CONF_ACTIVELY_CHARGING_VALUES, DEFAULT_ACTIVELY_CHARGING_VALUES)): selector.TextSelector(
                selector.TextSelectorConfig(multiple=True)
            ),
            vol.Optional(CONF_DEPARTURE_ENTITY, default=d(CONF_DEPARTURE_ENTITY, vol.UNDEFINED)): selector.EntitySelector(
                selector.EntitySelectorConfig()
            ),
            vol.Optional(CONF_BATTERY_KWH, default=d(CONF_BATTERY_KWH, DEFAULT_BATTERY_KWH)): selector.NumberSelector(
                selector.NumberSelectorConfig(min=1, max=200, step=0.1, mode=selector.NumberSelectorMode.BOX)
            ),
            vol.Required(CONF_DEFAULT_DEPARTURE, default=d(CONF_DEFAULT_DEPARTURE, DEFAULT_DEPARTURE_TIME)): selector.TimeSelector(),
            vol.Optional(CONF_MIN_MINUTES_LEFT_IN_HOUR, default=d(CONF_MIN_MINUTES_LEFT_IN_HOUR, DEFAULT_MIN_MINUTES_LEFT)): selector.NumberSelector(
                selector.NumberSelectorConfig(min=0, max=59, step=1, mode=selector.NumberSelectorMode.BOX)
            ),
            vol.Optional(CONF_AUTO_REPLAN_ON_PRICE_UPDATE, default=d(CONF_AUTO_REPLAN_ON_PRICE_UPDATE, DEFAULT_AUTO_REPLAN_ON_PRICE_UPDATE)): selector.BooleanSelector(),
            vol.Optional(CONF_AUTO_REPLAN_ON_SOC_CHANGE, default=d(CONF_AUTO_REPLAN_ON_SOC_CHANGE, DEFAULT_AUTO_REPLAN_ON_SOC_CHANGE)): selector.BooleanSelector(),
        })
```

Use the explicit form (the one immediately above).

- [ ] **Step 2: Append OptionsFlow tests**

```python
async def test_options_flow_can_change_default_departure(hass: HomeAssistant) -> None:
    from pytest_homeassistant_custom_component.common import MockConfigEntry

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
        "default_departure": "07:30:00",
    })
    assert r["type"] == FlowResultType.CREATE_ENTRY
    assert r["data"]["default_departure"] == "07:30:00"
```

- [ ] **Step 3: Run, lint, type-check, commit**

```bash
pytest tests/test_config_flow.py -v
ruff check custom_components/smart_ev_charging tests
mypy --strict custom_components/smart_ev_charging tests
git -c user.name=twarberg -c user.email=tim@tlw.dk add custom_components/smart_ev_charging/config_flow.py tests/test_config_flow.py
git -c user.name=twarberg -c user.email=tim@tlw.dk commit -m "feat(config_flow): OptionsFlow exposing reconfigurable fields"
```

Expected: 8 passed; coverage of `config_flow.py` ≥ 90%. If under target, add a test for whichever branch is missing.

---

## Task 12: `strings.json` and `translations/en.json`

**Files:**
- Create: `custom_components/smart_ev_charging/strings.json`, `custom_components/smart_ev_charging/translations/en.json`

- [ ] **Step 1: Create `strings.json`**

```json
{
  "title": "Smart EV Charging",
  "config": {
    "step": {
      "user": {
        "title": "Smart EV Charging",
        "description": "Choose a name for this EV. You can install the integration multiple times for multiple cars.",
        "data": {
          "name": "Name"
        }
      },
      "price": {
        "title": "Price source",
        "description": "Pick the entity that holds your hourly prices in an attribute. Defaults are tuned for Strømligning. Found fields: {peek}",
        "data": {
          "price_entity": "Price entity",
          "price_attribute": "Price attribute name",
          "start_field": "Start field",
          "price_field": "Price field",
          "end_field": "End field"
        }
      },
      "charger": {
        "title": "Charger",
        "description": "Pick the switch that turns charging on/off and set the effective charging power.",
        "data": {
          "charger_switch": "Charger switch",
          "charger_kw": "Charging power (kW)"
        }
      },
      "car": {
        "title": "Car (optional)",
        "description": "All fields are optional. Skipping any of them creates a fallback entity instead.",
        "data": {
          "soc_entity": "Current SoC sensor",
          "target_soc_entity": "Target SoC sensor",
          "charging_status_entity": "Charging status sensor",
          "plug_unplugged_values": "Status values that mean unplugged",
          "actively_charging_values": "Status values that mean actively charging",
          "departure_entity": "Departure-time sensor",
          "battery_kwh": "Battery capacity (kWh)"
        }
      },
      "defaults": {
        "title": "Defaults",
        "description": "Default departure time and planning behavior. Editable later via Configure.",
        "data": {
          "default_departure": "Default departure time",
          "min_minutes_left_in_hour": "Skip current hour if less than N minutes remain",
          "auto_replan_on_price_update": "Replan when prices update",
          "auto_replan_on_soc_change": "Replan on every SoC change"
        }
      }
    },
    "error": {
      "name_empty": "Name is required.",
      "entity_not_found": "Entity does not exist or is not exposed.",
      "attribute_not_found": "The attribute was not found on the entity.",
      "attribute_not_a_list": "The attribute exists but isn't a non-empty list of price entries.",
      "entries_not_dicts": "Each price entry must be an object/dict.",
      "field_not_found": "The named field wasn't found in the first price entry."
    },
    "abort": {
      "already_configured": "Another configured EV already uses this name."
    }
  },
  "options": {
    "step": {
      "init": {
        "title": "Smart EV Charging — settings",
        "description": "Update any field. Changes apply on submit without restarting Home Assistant.",
        "data": {
          "price_entity": "Price entity",
          "price_attribute": "Price attribute name",
          "start_field": "Start field",
          "price_field": "Price field",
          "end_field": "End field",
          "charger_switch": "Charger switch",
          "charger_kw": "Charging power (kW)",
          "soc_entity": "Current SoC sensor",
          "target_soc_entity": "Target SoC sensor",
          "charging_status_entity": "Charging status sensor",
          "plug_unplugged_values": "Status values that mean unplugged",
          "actively_charging_values": "Status values that mean actively charging",
          "departure_entity": "Departure-time sensor",
          "battery_kwh": "Battery capacity (kWh)",
          "default_departure": "Default departure time",
          "min_minutes_left_in_hour": "Skip current hour if less than N minutes remain",
          "auto_replan_on_price_update": "Replan when prices update",
          "auto_replan_on_soc_change": "Replan on every SoC change"
        }
      }
    },
    "error": {
      "entity_not_found": "Entity does not exist or is not exposed.",
      "attribute_not_found": "The attribute was not found on the entity.",
      "attribute_not_a_list": "The attribute exists but isn't a non-empty list of price entries.",
      "entries_not_dicts": "Each price entry must be an object/dict.",
      "field_not_found": "The named field wasn't found in the first price entry."
    }
  },
  "services": {
    "replan": {
      "name": "Replan",
      "description": "Recalculate the charging plan now."
    },
    "force_charge_now": {
      "name": "Force charge now",
      "description": "Charge immediately, ignoring the price plan, until target SoC or unplug.",
      "fields": {
        "duration": {
          "name": "Maximum duration",
          "description": "Stop after this duration even if target SoC isn't reached. Optional."
        }
      }
    },
    "skip_until": {
      "name": "Skip until",
      "description": "Don't charge before this time, regardless of plan.",
      "fields": {
        "until": {
          "name": "Skip until",
          "description": "Datetime when normal planning should resume."
        }
      }
    }
  },
  "entity": {
    "sensor": {
      "plan_status": {"name": "Plan status"},
      "planned_hours": {"name": "Planned hours"},
      "slots_needed": {"name": "Slots needed"},
      "active_deadline": {"name": "Active deadline"},
      "effective_departure": {"name": "Effective departure"}
    },
    "binary_sensor": {
      "plugged_in": {"name": "Plugged in"},
      "actively_charging": {"name": "Actively charging"},
      "charge_now": {"name": "Charge now"}
    },
    "switch": {
      "smart_charging_enabled": {"name": "Smart charging enabled"}
    },
    "number": {
      "target_soc": {"name": "Target SoC"},
      "charge_slots_override": {"name": "Charge slots override"}
    },
    "datetime": {
      "departure_fallback": {"name": "Departure (fallback)"}
    }
  }
}
```

- [ ] **Step 2: Create `translations/en.json` (identical to `strings.json`)**

Copy the same content into `custom_components/smart_ev_charging/translations/en.json`.

```bash
mkdir -p custom_components/smart_ev_charging/translations
cp custom_components/smart_ev_charging/strings.json custom_components/smart_ev_charging/translations/en.json
```

- [ ] **Step 3: Sanity-check JSON parses**

Run: `python -m json.tool custom_components/smart_ev_charging/strings.json > /dev/null && python -m json.tool custom_components/smart_ev_charging/translations/en.json > /dev/null && echo OK`
Expected: `OK`.

- [ ] **Step 4: Commit**

```bash
git -c user.name=twarberg -c user.email=tim@tlw.dk add custom_components/smart_ev_charging/strings.json custom_components/smart_ev_charging/translations/en.json
git -c user.name=twarberg -c user.email=tim@tlw.dk commit -m "feat(translations): add canonical strings.json and English translations"
```

---

## Task 13: Coordinator — setup, replan, plug debouncer, heartbeat

**Files:**
- Create: `custom_components/smart_ev_charging/coordinator.py`
- Modify: `custom_components/smart_ev_charging/__init__.py`
- Modify: `tests/test_coordinator.py` (new file)

This task establishes the coordinator skeleton and the data-update path. Charge controller state machine arrives in T14; entity files arrive in T15.

- [ ] **Step 1: Create `custom_components/smart_ev_charging/coordinator.py`**

```python
"""Coordinator for Smart EV Charging."""
from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass, replace
from datetime import datetime, time, timedelta
from math import ceil
from typing import Any, Literal

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import Event, HomeAssistant, callback
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
    DEFAULT_ACTIVELY_CHARGING_VALUES as _DEF_ACT,
    DOMAIN,
    EVENT_PLAN_UPDATED,
    HEARTBEAT_MINUTES,
    UNAVAILABLE_STATES,
)
from .planner import Plan, PlanInput, PriceSlot, make_plan
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
            hass=hass,
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
            plug_unplugged_values=list(self._merged.get(CONF_PLUG_UNPLUGGED_VALUES, DEFAULT_PLUG_UNPLUGGED_VALUES)),
            actively_charging_values=list(self._merged.get(CONF_ACTIVELY_CHARGING_VALUES, _DEF_ACT)),
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
        ids = [
            self._merged.get(CONF_PRICE_ENTITY),
            self._merged.get(CONF_SOC_ENTITY),
            self._merged.get(CONF_TARGET_SOC_ENTITY),
            self._merged.get(CONF_CHARGING_STATUS_ENTITY),
            self._merged.get(CONF_DEPARTURE_ENTITY),
        ]
        watch = [e for e in ids if e]
        if watch:
            self._unsub.append(
                async_track_state_change_event(self.hass, watch, self._handle_state_change)
            )

    @callback
    def _handle_state_change(self, _event: Event) -> None:
        self.hass.async_create_task(self.async_request_refresh())

    async def async_unload(self) -> None:
        for unsub in self._unsub:
            unsub()
        self._unsub.clear()

    async def async_replan(self) -> None:
        await self.async_refresh()

    def set_master_enabled(self, value: bool) -> None:
        self._master_enabled = value
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
        self._override = ChargeOverride(mode=mode, until=until)
        self.hass.async_create_task(self.async_request_refresh())

    def _slots_needed(self, car: CarState) -> int:
        soc = car.soc_percent
        target = car.target_soc_percent if car.target_soc_percent is not None else self._target_soc_override
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
        today = now.replace(hour=time_part.hour, minute=time_part.minute, second=0, microsecond=0)
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

    async def _async_update_data(self) -> CoordinatorData:
        now = dt_util.now()
        car = read_car_state(self.hass, self._car_config)
        debounced_plugged = self._debounce_plug(car)
        prices = self._price_source.get_slots()
        slots_needed = self._slots_needed(car)
        deadline, _src = self._resolve_departure(car, now)
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

        # Compute charge_now (real state machine in T14)
        charge_now = False
        plan_status_label = plan.status
        if not self._master_enabled:
            plan_status_label = "disabled"
        elif not debounced_plugged:
            plan_status_label = "unplugged"

        data = CoordinatorData(
            plan=plan,
            car_state=car,
            last_replan=now,
            override=self._override,
            charge_now=charge_now,
            plan_status_label=plan_status_label,
            debounced_plugged_in=debounced_plugged,
        )

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
```

- [ ] **Step 2: Replace `custom_components/smart_ev_charging/__init__.py`**

```python
"""Smart EV Charging integration."""
from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import DOMAIN, PLATFORMS
from .coordinator import SmartEVCoordinator


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    coordinator = SmartEVCoordinator(hass, entry)
    await coordinator.async_setup()
    await coordinator.async_config_entry_first_refresh()
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_options_updated))
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
```

- [ ] **Step 3: Create minimal `tests/test_coordinator.py` for setup + first refresh**

```python
"""Coordinator tests."""
from __future__ import annotations

from datetime import datetime
from typing import Any

import pytest
from homeassistant.const import CONF_NAME
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.smart_ev_charging.const import (
    CONF_CHARGER_KW,
    CONF_CHARGER_SWITCH,
    CONF_DEFAULT_DEPARTURE,
    CONF_PRICE_ATTRIBUTE,
    CONF_PRICE_ENTITY,
    CONF_PRICE_FIELD,
    CONF_START_FIELD,
    DOMAIN,
    EVENT_PLAN_UPDATED,
)


def _base_entry_data() -> dict[str, Any]:
    return {
        CONF_NAME: "Daily",
        CONF_PRICE_ENTITY: "sensor.fake_prices",
        CONF_PRICE_ATTRIBUTE: "prices",
        CONF_START_FIELD: "start",
        CONF_PRICE_FIELD: "price",
        CONF_CHARGER_SWITCH: "switch.charger",
        CONF_CHARGER_KW: 11.0,
        CONF_DEFAULT_DEPARTURE: "08:00:00",
    }


def _seed_prices(hass: HomeAssistant) -> None:
    hass.states.async_set(
        "sensor.fake_prices",
        "1.45",
        {
            "prices": [
                {"start": "2026-05-10T22:00:00+02:00", "end": "2026-05-10T23:00:00+02:00", "price": 1.80},
                {"start": "2026-05-10T23:00:00+02:00", "end": "2026-05-11T00:00:00+02:00", "price": 1.45},
                {"start": "2026-05-11T00:00:00+02:00", "end": "2026-05-11T01:00:00+02:00", "price": 1.15},
                {"start": "2026-05-11T01:00:00+02:00", "end": "2026-05-11T02:00:00+02:00", "price": 0.95},
                {"start": "2026-05-11T02:00:00+02:00", "end": "2026-05-11T03:00:00+02:00", "price": 0.65},
                {"start": "2026-05-11T03:00:00+02:00", "end": "2026-05-11T04:00:00+02:00", "price": 0.60},
                {"start": "2026-05-11T04:00:00+02:00", "end": "2026-05-11T05:00:00+02:00", "price": 0.62},
                {"start": "2026-05-11T05:00:00+02:00", "end": "2026-05-11T06:00:00+02:00", "price": 0.85},
                {"start": "2026-05-11T06:00:00+02:00", "end": "2026-05-11T07:00:00+02:00", "price": 1.30},
                {"start": "2026-05-11T07:00:00+02:00", "end": "2026-05-11T08:00:00+02:00", "price": 1.75},
            ],
        },
    )
    hass.states.async_set("switch.charger", "off", {})


async def test_coordinator_setup_and_first_refresh(hass: HomeAssistant) -> None:
    _seed_prices(hass)
    entry = MockConfigEntry(domain=DOMAIN, title="Daily", data=_base_entry_data())
    entry.add_to_hass(hass)

    events: list[Any] = []
    hass.bus.async_listen(EVENT_PLAN_UPDATED, events.append)

    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    coordinator = hass.data[DOMAIN][entry.entry_id]
    assert coordinator.data is not None
    assert coordinator.data.plan.status in {"ok", "partial", "extended", "no_data"}
    assert any(e.event_type == EVENT_PLAN_UPDATED for e in events)


async def test_coordinator_unload_cancels_listeners(hass: HomeAssistant) -> None:
    _seed_prices(hass)
    entry = MockConfigEntry(domain=DOMAIN, title="Daily", data=_base_entry_data())
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    assert await hass.config_entries.async_unload(entry.entry_id)
    assert entry.entry_id not in hass.data.get(DOMAIN, {})
```

- [ ] **Step 4: Run setup tests**

Run: `pytest tests/test_coordinator.py -v`
Expected: 2 passed.

> Note: At this point platforms (sensor.py etc.) don't exist yet. `async_forward_entry_setups` for platforms that don't exist will warn but not fail. If it fails, temporarily set `PLATFORMS = []` in `const.py` and revert in T15 once entity files exist. Decision: keep `PLATFORMS` set; if the test fails because of it, change `__init__.py` to `await hass.config_entries.async_forward_entry_setups(entry, [p for p in PLATFORMS if importlib.util.find_spec(...) is not None])`. Cleaner: actually create empty platform stubs in T15. To keep this task green, **temporarily comment out the `async_forward_entry_setups` line in `__init__.py`** and re-enable it in T15.

- [ ] **Step 5: Lint + type-check + commit**

```bash
ruff check custom_components/smart_ev_charging tests
mypy --strict custom_components/smart_ev_charging tests
git -c user.name=twarberg -c user.email=tim@tlw.dk add custom_components/smart_ev_charging/coordinator.py custom_components/smart_ev_charging/__init__.py tests/test_coordinator.py
git -c user.name=twarberg -c user.email=tim@tlw.dk commit -m "feat(coordinator): setup, replan, plug debounce, heartbeat"
```

---

## Task 14: Coordinator — charge controller state machine

**Files:**
- Modify: `custom_components/smart_ev_charging/coordinator.py`, `tests/test_coordinator.py`

The skeleton from T13 always sets `charge_now=False`. This task implements the full priority-ordered state machine, charger toggle calls, and start/stop/target_reached events.

- [ ] **Step 1: Extend `coordinator.py` with the controller and event helpers**

Add these constants and methods to `SmartEVCoordinator`. Replace the `_async_update_data` method body with the version that uses `_evaluate_charge_now`, and add the new helper methods.

```python
# Add at top of file, alongside the existing constants imports
from .const import (
    # ... existing imports ...
    EVENT_STARTED,
    EVENT_STOPPED,
    EVENT_TARGET_REACHED,
)
```

Inside `SmartEVCoordinator`:

```python
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

        target = car.target_soc_percent if car.target_soc_percent is not None else self._target_soc_override
        soc = car.soc_percent
        soc_known = soc is not None and target is not None

        override = self._override
        if override is not None and override.until is not None and now >= override.until:
            override = None
            self._override = None

        if override is not None and override.mode == "force":
            if not soc_known or (soc is not None and target is not None and soc < target):
                return True, plan.status, None

        if override is not None and override.mode == "skip":
            if override.until is not None and now < override.until:
                return False, plan.status, "skip"

        if not debounced_plugged:
            return False, "unplugged", "unplugged"

        if soc_known and soc is not None and target is not None and soc >= target:
            if self._override is not None and self._override.mode == "force":
                self._override = None
            return False, plan.status, "target_reached"

        this_hour = now.replace(minute=0, second=0, microsecond=0)
        if this_hour in plan.selected_starts:
            reason = "force" if (override is not None and override.mode == "force") else "plan"
            return True, plan.status, None
        return False, plan.status, "plan_end"

    def _charge_now_reason_for_start(self, override: ChargeOverride | None) -> str:
        if override is not None and override.mode == "force":
            return "force"
        return "plan"

    async def _apply_charger(self, charge_now: bool, stop_reason: str | None, prev_soc: float | None, car: CarState) -> None:
        switch_id = self._merged[CONF_CHARGER_SWITCH]
        if charge_now and not self._last_charge_now:
            await self.hass.services.async_call(
                "switch", "turn_on", {"entity_id": switch_id}, blocking=False
            )
            self.hass.bus.async_fire(
                EVENT_STARTED,
                {"entry_id": self.entry.entry_id, "reason": self._charge_now_reason_for_start(self._override)},
            )
        elif not charge_now and self._last_charge_now:
            await self.hass.services.async_call(
                "switch", "turn_off", {"entity_id": switch_id}, blocking=False
            )
            self.hass.bus.async_fire(
                EVENT_STOPPED,
                {"entry_id": self.entry.entry_id, "reason": stop_reason or "plan_end"},
            )
        if (
            self._last_charge_now
            and prev_soc is not None
            and car.target_soc_percent is not None
            and car.soc_percent is not None
            and prev_soc < car.target_soc_percent
            and car.soc_percent >= car.target_soc_percent
        ):
            self.hass.bus.async_fire(
                EVENT_TARGET_REACHED,
                {"entry_id": self.entry.entry_id, "final_soc": car.soc_percent},
            )
        self._last_charge_now = charge_now
```

Replace the body of `_async_update_data` with:

```python
    async def _async_update_data(self) -> CoordinatorData:
        now = dt_util.now()
        car = read_car_state(self.hass, self._car_config)
        debounced_plugged = self._debounce_plug(car)
        prices = self._price_source.get_slots()
        slots_needed = self._slots_needed(car)
        deadline, _src = self._resolve_departure(car, now)
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

        prev_soc = self.data.car_state.soc_percent if self.data is not None else None
        charge_now, status_label, stop_reason = self._evaluate_charge_now(plan, car, debounced_plugged, now)
        await self._apply_charger(charge_now, stop_reason, prev_soc, car)

        data = CoordinatorData(
            plan=plan,
            car_state=car,
            last_replan=now,
            override=self._override,
            charge_now=charge_now,
            plan_status_label=status_label,
            debounced_plugged_in=debounced_plugged,
        )

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
```

- [ ] **Step 2: Append controller tests to `tests/test_coordinator.py`**

```python
from datetime import timedelta
from unittest.mock import patch

from freezegun import freeze_time
from pytest_homeassistant_custom_component.common import async_mock_service

from custom_components.smart_ev_charging.const import EVENT_STARTED, EVENT_STOPPED


async def _setup_with_soc(hass: HomeAssistant, soc: float = 30.0, target: float = 80.0) -> Any:
    _seed_prices(hass)
    hass.states.async_set("sensor.car_soc", str(soc))
    hass.states.async_set("sensor.car_target", str(target))
    hass.states.async_set("sensor.car_status", "0")  # Mercedes "actively charging"
    data = _base_entry_data()
    data["soc_entity"] = "sensor.car_soc"
    data["target_soc_entity"] = "sensor.car_target"
    data["charging_status_entity"] = "sensor.car_status"
    data["plug_unplugged_values"] = ["3"]
    data["actively_charging_values"] = ["0"]
    entry = MockConfigEntry(domain=DOMAIN, title="Daily", data=data)
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


@freeze_time("2026-05-11 02:30:00+02:00")
async def test_charge_now_on_during_planned_hour(hass: HomeAssistant) -> None:
    turn_on_calls = async_mock_service(hass, "switch", "turn_on")
    entry = await _setup_with_soc(hass)
    coordinator = hass.data[DOMAIN][entry.entry_id]
    assert coordinator.data.charge_now is True
    assert any(c.data.get("entity_id") == "switch.charger" for c in turn_on_calls)


@freeze_time("2026-05-10 23:30:00+02:00")
async def test_charge_now_off_outside_planned_hour(hass: HomeAssistant) -> None:
    turn_off_calls = async_mock_service(hass, "switch", "turn_off")
    entry = await _setup_with_soc(hass)
    coordinator = hass.data[DOMAIN][entry.entry_id]
    # 23:30 is not the cheapest hour in our small fixture (cheapest are 02-05)
    assert coordinator.data.charge_now is False


@freeze_time("2026-05-11 02:30:00+02:00")
async def test_master_disabled_forces_off(hass: HomeAssistant) -> None:
    turn_off_calls = async_mock_service(hass, "switch", "turn_off")
    entry = await _setup_with_soc(hass)
    coordinator = hass.data[DOMAIN][entry.entry_id]
    coordinator.set_master_enabled(False)
    await hass.async_block_till_done()
    assert coordinator.data.charge_now is False
    assert coordinator.data.plan_status_label == "disabled"


@freeze_time("2026-05-11 02:30:00+02:00")
async def test_unplugged_forces_off(hass: HomeAssistant) -> None:
    entry = await _setup_with_soc(hass)
    coordinator = hass.data[DOMAIN][entry.entry_id]
    hass.states.async_set("sensor.car_status", "3")  # unplugged
    await hass.async_block_till_done()
    await coordinator.async_refresh()
    assert coordinator.data.charge_now is False
    assert coordinator.data.plan_status_label == "unplugged"


@freeze_time("2026-05-11 02:30:00+02:00")
async def test_force_override_overrides_plan(hass: HomeAssistant) -> None:
    _seed_prices(hass)
    hass.states.async_set("sensor.car_soc", "30")
    hass.states.async_set("sensor.car_target", "80")
    hass.states.async_set("sensor.car_status", "0")
    data = _base_entry_data()
    data.update(
        {
            "soc_entity": "sensor.car_soc",
            "target_soc_entity": "sensor.car_target",
            "charging_status_entity": "sensor.car_status",
            "plug_unplugged_values": ["3"],
            "actively_charging_values": ["0"],
        }
    )
    entry = MockConfigEntry(domain=DOMAIN, title="Daily", data=data)
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    coordinator = hass.data[DOMAIN][entry.entry_id]

    # set "now" to 23:30 — not in plan
    with freeze_time("2026-05-10 23:30:00+02:00"):
        await coordinator.async_refresh()
        assert coordinator.data.charge_now is False
        coordinator.apply_override("force", until=None)
        await hass.async_block_till_done()
        await coordinator.async_refresh()
        assert coordinator.data.charge_now is True


@freeze_time("2026-05-11 02:30:00+02:00")
async def test_target_reached_clears_force_override(hass: HomeAssistant) -> None:
    entry = await _setup_with_soc(hass, soc=30.0, target=80.0)
    coordinator = hass.data[DOMAIN][entry.entry_id]
    coordinator.apply_override("force", until=None)
    await hass.async_block_till_done()
    hass.states.async_set("sensor.car_soc", "80")
    await coordinator.async_refresh()
    assert coordinator.data.override is None
    assert coordinator.data.charge_now is False


async def test_plug_debouncer_holds_through_unknown(hass: HomeAssistant) -> None:
    _seed_prices(hass)
    hass.states.async_set("sensor.car_status", "0")
    data = _base_entry_data()
    data.update({"charging_status_entity": "sensor.car_status", "plug_unplugged_values": ["3"], "actively_charging_values": ["0"]})
    entry = MockConfigEntry(domain=DOMAIN, title="Daily", data=data)
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    coordinator = hass.data[DOMAIN][entry.entry_id]
    assert coordinator.data.debounced_plugged_in is True

    hass.states.async_set("sensor.car_status", "unknown")
    await coordinator.async_refresh()
    assert coordinator.data.debounced_plugged_in is True  # held by debouncer

    hass.states.async_set("sensor.car_status", "3")  # explicit unplug
    await coordinator.async_refresh()
    assert coordinator.data.debounced_plugged_in is False
```

- [ ] **Step 3: Run, lint, type-check**

Run:
```bash
pytest tests/test_coordinator.py -v
ruff check custom_components/smart_ev_charging tests
mypy --strict custom_components/smart_ev_charging tests
```
Expected: all coordinator tests pass; ≥85% coverage of `coordinator.py`.

- [ ] **Step 4: Commit**

```bash
git -c user.name=twarberg -c user.email=tim@tlw.dk add custom_components/smart_ev_charging/coordinator.py tests/test_coordinator.py
git -c user.name=twarberg -c user.email=tim@tlw.dk commit -m "feat(coordinator): charge controller, override semantics, plug debouncer"
```

---

## Task 15: Sensor + binary sensor entities

**Files:**
- Create: `custom_components/smart_ev_charging/sensor.py`, `custom_components/smart_ev_charging/binary_sensor.py`
- Modify: `custom_components/smart_ev_charging/__init__.py` (re-enable platform forwarding if commented out in T13)
- Modify: `tests/test_coordinator.py`

- [ ] **Step 1: Re-enable platform forwarding in `__init__.py`**

If you commented out `async_forward_entry_setups` in T13, restore it. The line should read:

```python
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
```

- [ ] **Step 2: Create `sensor.py`**

```python
"""Sensors for Smart EV Charging."""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
)
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
        plan = self.coordinator.data.plan
        return max(1, plan.window_size if plan.window_size > 0 else len(plan.selected_starts))

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return {
            "source": "calculated" if self.coordinator.data.car_state.soc_percent is not None else "override",
        }


class ActiveDeadlineSensor(_Base):
    _attr_device_class = SensorDeviceClass.TIMESTAMP

    @property
    def native_value(self) -> datetime:
        return self.coordinator.data.plan.deadline

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        plan = self.coordinator.data.plan
        return {"was_extended": plan.was_extended, "initial_deadline": plan.initial_deadline.isoformat()}


class EffectiveDepartureSensor(_Base):
    @property
    def native_value(self) -> str:
        deadline = self.coordinator.data.plan.deadline
        return deadline.strftime("%H:%M")

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        car = self.coordinator.data.car_state
        if car.departure is not None:
            source = "car"
        elif self.coordinator._departure_fallback is not None:  # noqa: SLF001
            source = "helper"
        else:
            source = "default"
        return {"source": source}


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
```

- [ ] **Step 3: Create `binary_sensor.py`**

```python
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
        car = self.coordinator.data.car_state
        if self.coordinator._car_config.charging_status_entity is None:  # noqa: SLF001
            return self.coordinator.data.charge_now
        return car.actively_charging


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
```

- [ ] **Step 4: Append entity-presence test to `tests/test_coordinator.py`**

```python
@freeze_time("2026-05-11 02:30:00+02:00")
async def test_expected_entities_exist(hass: HomeAssistant) -> None:
    entry = await _setup_with_soc(hass)
    expected = {
        "sensor.daily_plan_status",
        "sensor.daily_planned_hours",
        "sensor.daily_slots_needed",
        "sensor.daily_active_deadline",
        "sensor.daily_effective_departure",
        "binary_sensor.daily_plugged_in",
        "binary_sensor.daily_actively_charging",
        "binary_sensor.daily_charge_now",
    }
    actual = {s.entity_id for s in hass.states.async_all()}
    missing = expected - actual
    assert not missing, f"missing: {missing}"
```

- [ ] **Step 5: Run, lint, type-check, commit**

```bash
pytest tests/test_coordinator.py -v
ruff check custom_components/smart_ev_charging tests
mypy --strict custom_components/smart_ev_charging tests
git -c user.name=twarberg -c user.email=tim@tlw.dk add custom_components/smart_ev_charging/sensor.py custom_components/smart_ev_charging/binary_sensor.py custom_components/smart_ev_charging/__init__.py tests/test_coordinator.py
git -c user.name=twarberg -c user.email=tim@tlw.dk commit -m "feat(entities): sensor and binary_sensor projections of coordinator data"
```

---

## Task 16: Switch, number, datetime entities

**Files:**
- Create: `custom_components/smart_ev_charging/switch.py`, `custom_components/smart_ev_charging/number.py`, `custom_components/smart_ev_charging/datetime.py`
- Modify: `tests/test_coordinator.py`

- [ ] **Step 1: Create `switch.py`**

```python
"""Master enable switch."""
from __future__ import annotations

from typing import Any

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

    async def async_turn_on(self, **kwargs: Any) -> None:
        self._is_on = True
        self.coordinator.set_master_enabled(True)
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs: Any) -> None:
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
```

- [ ] **Step 2: Create `number.py` with two conditionally-added entities**

```python
"""Conditional fallback number entities."""
from __future__ import annotations

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

    def __init__(self, coordinator: SmartEVCoordinator, key: str, translation_key: str, default: float) -> None:
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
            try:
                self._value = float(last.state)
            except (TypeError, ValueError):
                pass
        self._sync()

    def _sync(self) -> None:
        raise NotImplementedError


class TargetSoCNumber(_NumberBase):
    _attr_native_min_value = 50
    _attr_native_max_value = 100
    _attr_native_step = 5

    def __init__(self, coordinator: SmartEVCoordinator) -> None:
        super().__init__(coordinator, key="target_soc", translation_key="target_soc", default=80.0)

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
        super().__init__(coordinator, key="charge_slots_override", translation_key="charge_slots_override", default=3.0)

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
```

- [ ] **Step 3: Create `datetime.py`**

```python
"""Conditional fallback departure datetime."""
from __future__ import annotations

from datetime import datetime, time

from homeassistant.components.datetime import DateTimeEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import dt as dt_util

from .const import (
    CONF_DEFAULT_DEPARTURE,
    CONF_DEPARTURE_ENTITY,
    DEFAULT_DEPARTURE_TIME,
    DOMAIN,
)
from .coordinator import SmartEVCoordinator


class DepartureFallbackDateTime(CoordinatorEntity[SmartEVCoordinator], DateTimeEntity, RestoreEntity):
    _attr_has_entity_name = True
    _attr_translation_key = "departure_fallback"

    def __init__(self, coordinator: SmartEVCoordinator) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.entry.entry_id}_departure_fallback"
        merged = {**coordinator.entry.data, **coordinator.entry.options}
        default_time = str(merged.get(CONF_DEFAULT_DEPARTURE, DEFAULT_DEPARTURE_TIME))
        parts = default_time.split(":")
        h = int(parts[0])
        m = int(parts[1]) if len(parts) > 1 else 0
        today = dt_util.now().replace(hour=h, minute=m, second=0, microsecond=0)
        self._value: datetime = today

    @property
    def device_info(self) -> DeviceInfo:
        return DeviceInfo(
            identifiers={(DOMAIN, self.coordinator.entry.entry_id)},
            name=self.coordinator.entry.title,
            manufacturer="Smart EV Charging",
            model="Charging planner",
        )

    @property
    def native_value(self) -> datetime:
        return self._value

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        last = await self.async_get_last_state()
        if last is not None:
            try:
                self._value = datetime.fromisoformat(last.state)
            except (TypeError, ValueError):
                pass
        self.coordinator.set_departure_fallback(time(self._value.hour, self._value.minute))

    async def async_set_value(self, value: datetime) -> None:
        self._value = value
        self.coordinator.set_departure_fallback(time(value.hour, value.minute))
        self.async_write_ha_state()


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: SmartEVCoordinator = hass.data[DOMAIN][entry.entry_id]
    merged = {**entry.data, **entry.options}
    if not merged.get(CONF_DEPARTURE_ENTITY):
        async_add_entities([DepartureFallbackDateTime(coordinator)])
```

- [ ] **Step 4: Append tests for switch + number + datetime presence and behavior**

```python
async def test_switch_master_disable_turns_charger_off(hass: HomeAssistant) -> None:
    turn_off_calls = async_mock_service(hass, "switch", "turn_off")
    with freeze_time("2026-05-11 02:30:00+02:00"):
        entry = await _setup_with_soc(hass)
        coordinator = hass.data[DOMAIN][entry.entry_id]
        await hass.services.async_call("switch", "turn_off", {"entity_id": "switch.daily_smart_charging_enabled"}, blocking=True)
        await hass.async_block_till_done()
        assert coordinator.data.charge_now is False


async def test_fallback_number_created_when_no_soc(hass: HomeAssistant) -> None:
    _seed_prices(hass)
    entry = MockConfigEntry(domain=DOMAIN, title="Daily", data=_base_entry_data())
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert hass.states.get("number.daily_charge_slots_override") is not None
    assert hass.states.get("number.daily_target_soc") is not None
    assert hass.states.get("datetime.daily_departure_fallback") is not None


async def test_fallback_entities_skipped_when_real_entities_provided(hass: HomeAssistant) -> None:
    entry = await _setup_with_soc(hass)
    # soc_entity + target_soc_entity + charging_status_entity are configured; departure is not
    assert hass.states.get("number.daily_charge_slots_override") is None
    assert hass.states.get("number.daily_target_soc") is None
    assert hass.states.get("datetime.daily_departure_fallback") is not None  # departure not configured
```

- [ ] **Step 5: Run, lint, type-check, commit**

```bash
pytest tests/test_coordinator.py -v
ruff check custom_components/smart_ev_charging tests
mypy --strict custom_components/smart_ev_charging tests
git -c user.name=twarberg -c user.email=tim@tlw.dk add custom_components/smart_ev_charging/switch.py custom_components/smart_ev_charging/number.py custom_components/smart_ev_charging/datetime.py tests/test_coordinator.py
git -c user.name=twarberg -c user.email=tim@tlw.dk commit -m "feat(entities): switch, number, datetime fallback entities"
```

Coverage of entity files should be ≥80%.

---

## Task 17: End-to-end plan-drives-charger test

**Files:**
- Modify: `tests/test_coordinator.py`

- [ ] **Step 1: Append the e2e timeline test**

```python
async def test_e2e_plan_drives_charger_across_planned_hours(hass: HomeAssistant) -> None:
    turn_on_calls = async_mock_service(hass, "switch", "turn_on")
    turn_off_calls = async_mock_service(hass, "switch", "turn_off")

    with freeze_time("2026-05-10 23:30:00+02:00") as frozen:
        entry = await _setup_with_soc(hass)
        coordinator = hass.data[DOMAIN][entry.entry_id]
        # Outside planned window — charger should not have been turned on
        assert coordinator.data.charge_now is False

        # Advance to 02:30 — should be in the cheapest 3-slot plan (02:00-05:00)
        frozen.move_to("2026-05-11 02:30:00+02:00")
        await coordinator.async_refresh()
        assert coordinator.data.charge_now is True
        assert any(c.data.get("entity_id") == "switch.charger" for c in turn_on_calls)

        # Advance past last planned hour — charger should be off
        frozen.move_to("2026-05-11 06:30:00+02:00")
        await coordinator.async_refresh()
        assert coordinator.data.charge_now is False
        assert any(c.data.get("entity_id") == "switch.charger" for c in turn_off_calls)
```

- [ ] **Step 2: Run + commit**

```bash
pytest tests/test_coordinator.py::test_e2e_plan_drives_charger_across_planned_hours -v
git -c user.name=twarberg -c user.email=tim@tlw.dk add tests/test_coordinator.py
git -c user.name=twarberg -c user.email=tim@tlw.dk commit -m "test(coordinator): e2e plan-drives-charger across timeline"
```

Expected: PASS.

---

## Task 18: Services + handlers + service tests

**Files:**
- Create: `custom_components/smart_ev_charging/services.yaml`
- Modify: `custom_components/smart_ev_charging/__init__.py`, `tests/test_coordinator.py`

- [ ] **Step 1: Create `services.yaml`**

```yaml
replan:
  name: Replan
  description: Recalculate the charging plan now using current conditions.
  target:
    entity:
      integration: smart_ev_charging
  fields: {}

force_charge_now:
  name: Force charge now
  description: Charge immediately, ignoring the price plan, until target SoC or unplug.
  target:
    entity:
      integration: smart_ev_charging
  fields:
    duration:
      name: Maximum duration
      description: Stop after this duration even if target SoC isn't reached. Optional.
      required: false
      selector:
        duration:
          enable_day: false

skip_until:
  name: Skip until
  description: Don't charge before this datetime, regardless of plan.
  target:
    entity:
      integration: smart_ev_charging
  fields:
    until:
      name: Skip until
      description: Datetime when normal planning should resume.
      required: true
      selector:
        datetime:
```

- [ ] **Step 2: Add service registration to `__init__.py`**

Replace the contents with:

```python
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
            until = until.replace(tzinfo=dt_util.DEFAULT_TIME_ZONE)
        for c in _resolve_coordinators(hass, call):
            c.apply_override("skip", until=until)

    hass.services.async_register(DOMAIN, SERVICE_REPLAN, _replan, schema=_REPLAN_SCHEMA)
    hass.services.async_register(DOMAIN, SERVICE_FORCE_CHARGE_NOW, _force, schema=_FORCE_SCHEMA)
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
```

- [ ] **Step 3: Append service tests to `tests/test_coordinator.py`**

```python
async def test_service_replan_runs(hass: HomeAssistant) -> None:
    with freeze_time("2026-05-11 02:30:00+02:00"):
        entry = await _setup_with_soc(hass)
        coordinator = hass.data[DOMAIN][entry.entry_id]
        before = coordinator.data.last_replan
        await hass.services.async_call(DOMAIN, "replan", {}, blocking=True)
        await hass.async_block_till_done()
        assert coordinator.data.last_replan >= before


async def test_service_force_charge_now_overrides_plan(hass: HomeAssistant) -> None:
    with freeze_time("2026-05-10 23:30:00+02:00"):
        entry = await _setup_with_soc(hass)
        coordinator = hass.data[DOMAIN][entry.entry_id]
        assert coordinator.data.charge_now is False
        await hass.services.async_call(DOMAIN, "force_charge_now", {}, blocking=True)
        await hass.async_block_till_done()
        await coordinator.async_refresh()
        assert coordinator.data.charge_now is True


async def test_service_skip_until_blocks_plan(hass: HomeAssistant) -> None:
    with freeze_time("2026-05-11 02:30:00+02:00"):
        entry = await _setup_with_soc(hass)
        coordinator = hass.data[DOMAIN][entry.entry_id]
        until = dt_util.parse_datetime("2026-05-11T05:00:00+02:00")
        await hass.services.async_call(
            DOMAIN, "skip_until", {"until": until.isoformat()}, blocking=True
        )
        await hass.async_block_till_done()
        await coordinator.async_refresh()
        assert coordinator.data.charge_now is False
```

Add `from homeassistant.util import dt as dt_util` near the top of `tests/test_coordinator.py` if not already imported.

- [ ] **Step 4: Run, lint, type-check, commit**

```bash
pytest tests/test_coordinator.py -v
ruff check custom_components/smart_ev_charging tests
mypy --strict custom_components/smart_ev_charging tests
git -c user.name=twarberg -c user.email=tim@tlw.dk add custom_components/smart_ev_charging/services.yaml custom_components/smart_ev_charging/__init__.py tests/test_coordinator.py
git -c user.name=twarberg -c user.email=tim@tlw.dk commit -m "feat(services): replan, force_charge_now, skip_until"
```

---

## Task 19: Danish translation (`translations/da.json`)

**Files:**
- Create: `custom_components/smart_ev_charging/translations/da.json`

- [ ] **Step 1: Create `translations/da.json`** mirroring `en.json` with Danish strings.

```json
{
  "title": "Smart EV-opladning",
  "config": {
    "step": {
      "user": {
        "title": "Smart EV-opladning",
        "description": "Vælg et navn til denne bil. Du kan installere integrationen flere gange for flere biler.",
        "data": {"name": "Navn"}
      },
      "price": {
        "title": "Priskilde",
        "description": "Vælg den entitet, der har timepriser i en attribut. Standardværdierne passer til Strømligning. Fundne felter: {peek}",
        "data": {
          "price_entity": "Prisentitet",
          "price_attribute": "Navn på prisattribut",
          "start_field": "Startfelt",
          "price_field": "Prisfelt",
          "end_field": "Slutfelt"
        }
      },
      "charger": {
        "title": "Lader",
        "description": "Vælg den kontakt, der tænder/slukker for opladning, og angiv den effektive ladeeffekt.",
        "data": {
          "charger_switch": "Laderkontakt",
          "charger_kw": "Ladeeffekt (kW)"
        }
      },
      "car": {
        "title": "Bil (valgfrit)",
        "description": "Alle felter er valgfrie. Spring du et over, oprettes en fallback-entitet i stedet.",
        "data": {
          "soc_entity": "Aktuel SoC-sensor",
          "target_soc_entity": "Mål-SoC-sensor",
          "charging_status_entity": "Ladningsstatus-sensor",
          "plug_unplugged_values": "Statusværdier der betyder \"ikke tilsluttet\"",
          "actively_charging_values": "Statusværdier der betyder \"oplader nu\"",
          "departure_entity": "Afgangstid-sensor",
          "battery_kwh": "Batterikapacitet (kWh)"
        }
      },
      "defaults": {
        "title": "Standardværdier",
        "description": "Standard-afgangstid og planlægningsadfærd. Kan ændres senere via Konfigurer.",
        "data": {
          "default_departure": "Standard-afgangstid",
          "min_minutes_left_in_hour": "Spring nuværende time over hvis under N min. tilbage",
          "auto_replan_on_price_update": "Genplanlæg når priser opdateres",
          "auto_replan_on_soc_change": "Genplanlæg ved enhver SoC-ændring"
        }
      }
    },
    "error": {
      "name_empty": "Navn er påkrævet.",
      "entity_not_found": "Entiteten findes ikke eller er ikke eksponeret.",
      "attribute_not_found": "Attributten blev ikke fundet på entiteten.",
      "attribute_not_a_list": "Attributten findes, men er ikke en ikke-tom liste af pris-objekter.",
      "entries_not_dicts": "Hvert pris-objekt skal være et objekt/dict.",
      "field_not_found": "Det navngivne felt blev ikke fundet i det første pris-objekt."
    },
    "abort": {
      "already_configured": "En anden konfigureret EV bruger allerede dette navn."
    }
  },
  "options": {
    "step": {
      "init": {
        "title": "Smart EV-opladning — indstillinger",
        "description": "Opdater et felt. Ændringer træder i kraft uden genstart af Home Assistant.",
        "data": {
          "price_entity": "Prisentitet",
          "price_attribute": "Navn på prisattribut",
          "start_field": "Startfelt",
          "price_field": "Prisfelt",
          "end_field": "Slutfelt",
          "charger_switch": "Laderkontakt",
          "charger_kw": "Ladeeffekt (kW)",
          "soc_entity": "Aktuel SoC-sensor",
          "target_soc_entity": "Mål-SoC-sensor",
          "charging_status_entity": "Ladningsstatus-sensor",
          "plug_unplugged_values": "Statusværdier der betyder \"ikke tilsluttet\"",
          "actively_charging_values": "Statusværdier der betyder \"oplader nu\"",
          "departure_entity": "Afgangstid-sensor",
          "battery_kwh": "Batterikapacitet (kWh)",
          "default_departure": "Standard-afgangstid",
          "min_minutes_left_in_hour": "Spring nuværende time over hvis under N min. tilbage",
          "auto_replan_on_price_update": "Genplanlæg når priser opdateres",
          "auto_replan_on_soc_change": "Genplanlæg ved enhver SoC-ændring"
        }
      }
    },
    "error": {
      "entity_not_found": "Entiteten findes ikke eller er ikke eksponeret.",
      "attribute_not_found": "Attributten blev ikke fundet på entiteten.",
      "attribute_not_a_list": "Attributten findes, men er ikke en ikke-tom liste af pris-objekter.",
      "entries_not_dicts": "Hvert pris-objekt skal være et objekt/dict.",
      "field_not_found": "Det navngivne felt blev ikke fundet i det første pris-objekt."
    }
  },
  "services": {
    "replan": {
      "name": "Genplanlæg",
      "description": "Genberegn ladeplanen nu."
    },
    "force_charge_now": {
      "name": "Tving opladning nu",
      "description": "Oplad straks, ignorer prisplanen, indtil mål-SoC eller frakobling.",
      "fields": {
        "duration": {
          "name": "Maks. varighed",
          "description": "Stop efter denne varighed selv hvis mål-SoC ikke er nået. Valgfrit."
        }
      }
    },
    "skip_until": {
      "name": "Spring over indtil",
      "description": "Oplad ikke før dette tidspunkt, uanset planen.",
      "fields": {
        "until": {
          "name": "Spring over indtil",
          "description": "Tidspunkt hvor normal planlægning genoptages."
        }
      }
    }
  },
  "entity": {
    "sensor": {
      "plan_status": {"name": "Planstatus"},
      "planned_hours": {"name": "Planlagte timer"},
      "slots_needed": {"name": "Timer behov"},
      "active_deadline": {"name": "Aktiv deadline"},
      "effective_departure": {"name": "Effektiv afgangstid"}
    },
    "binary_sensor": {
      "plugged_in": {"name": "Tilsluttet"},
      "actively_charging": {"name": "Oplader nu"},
      "charge_now": {"name": "Oplad nu"}
    },
    "switch": {
      "smart_charging_enabled": {"name": "Smart opladning aktiveret"}
    },
    "number": {
      "target_soc": {"name": "Mål-SoC"},
      "charge_slots_override": {"name": "Manuel timer-override"}
    },
    "datetime": {
      "departure_fallback": {"name": "Afgang (fallback)"}
    }
  }
}
```

- [ ] **Step 2: Sanity-check JSON**

Run: `python -m json.tool custom_components/smart_ev_charging/translations/da.json > /dev/null && echo OK`
Expected: `OK`.

- [ ] **Step 3: Commit**

```bash
git -c user.name=twarberg -c user.email=tim@tlw.dk add custom_components/smart_ev_charging/translations/da.json
git -c user.name=twarberg -c user.email=tim@tlw.dk commit -m "feat(translations): add Danish translations"
```

---

## Task 20: Final README

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Replace `README.md` with the user-facing content**

```markdown
# Smart EV Charging

Plans your EV charging during the cheapest hours of dynamic electricity pricing
(Strømligning, Nord Pool, Tibber, …) finishing by your departure time. Works with
any HA price sensor, any switchable charger, and (optionally) any car
integration that exposes State of Charge.

## Installation

1. HACS → Integrations → ⋮ → Custom repositories → add
   `https://github.com/twarberg/ev-smart-charging` as Integration.
2. Install **Smart EV Charging**.
3. Restart Home Assistant.
4. Settings → Devices & Services → Add Integration → "Smart EV Charging".

## Configuration

You'll need:

- A **price sensor** with hourly prices in an attribute (Strømligning, Nord Pool, Tibber, …).
- A **switch** that turns your charger on/off (e.g. an OCPP charge-control switch).
- *(Optional)* SoC and charging-status sensors from your car integration.

The 5-step config flow takes about a minute. Defaults are tuned for Mercedes
PHEV + Strømligning + OCPP, but every field can be changed without leaving
the wizard.

## What you get

| Entity | Description |
|---|---|
| `sensor.<n>_plan_status` | `ok` / `partial` / `extended` / `no_data` / `unplugged` / `disabled` |
| `sensor.<n>_planned_hours` | Count + list of planned hours in attributes |
| `sensor.<n>_slots_needed` | Hours needed to reach target SoC |
| `sensor.<n>_active_deadline` | Datetime the plan is targeting |
| `sensor.<n>_effective_departure` | `HH:MM` with `source` attribute (`car`/`helper`/`default`) |
| `binary_sensor.<n>_plugged_in` | `on` when the car is plugged in |
| `binary_sensor.<n>_actively_charging` | `on` when actually drawing power |
| `binary_sensor.<n>_charge_now` | Driving signal — `on` when the integration wants to charge |
| `switch.<n>_smart_charging_enabled` | Master toggle |
| `number.<n>_target_soc` | (only if no target SoC sensor) |
| `number.<n>_charge_slots_override` | (only if no SoC sensor) |
| `datetime.<n>_departure_fallback` | (only if no departure sensor) |

## Recipes

### Strømligning today + tomorrow joiner

Strømligning splits today and tomorrow into two entities. Build a single combined
sensor and point Smart EV Charging at it:

```yaml
template:
  - sensor:
      - name: ev_prices_combined
        unique_id: ev_prices_combined
        state: "{{ states('sensor.stromligning_current_price_vat') }}"
        attributes:
          prices: >
            {% set today = state_attr('sensor.stromligning_current_price_vat', 'prices') or [] %}
            {% set tomorrow = state_attr('binary_sensor.stromligning_tomorrow_spotprice_vat', 'prices') or [] %}
            {{ today + tomorrow }}
```

### Push notification on a partial plan

```yaml
automation:
  - alias: EV — partial plan notification
    trigger:
      - platform: state
        entity_id: sensor.daily_plan_status
        to: "partial"
    action:
      - service: notify.mobile_app
        data:
          message: "EV plan is partial — only {{ state_attr('sensor.daily_planned_hours', 'hours') | length }} hours fit."
```

### Lovelace card

```yaml
type: entities
title: Daily EV
entities:
  - entity: switch.daily_smart_charging_enabled
  - entity: sensor.daily_plan_status
  - entity: sensor.daily_planned_hours
  - entity: sensor.daily_active_deadline
  - entity: binary_sensor.daily_charge_now
```

## Troubleshooting

- **"Field not found" during setup** — the form shows the field names actually
  present in your price entity. Pick from those.
- **Charger doesn't toggle** — verify `binary_sensor.<n>_charge_now` flips at
  the planned hour, then check that your charger switch turns on/off when you
  call it manually from Developer Tools → Services.
- **Plan keeps showing `unplugged`** — check the values you provided for
  "status values that mean unplugged"; some Mercedes setups use `"3"`, others
  use `"unplugged"`.

## Development

```bash
pip install -e ".[dev]"
ruff check .
mypy --strict custom_components tests
pytest --cov --cov-report=term-missing
```

## License

MIT.
```

- [ ] **Step 2: Commit**

```bash
git -c user.name=twarberg -c user.email=tim@tlw.dk add README.md
git -c user.name=twarberg -c user.email=tim@tlw.dk commit -m "docs: write user-facing README with recipes and troubleshooting"
```

---

## Task 21: CI workflow

**Files:**
- Create: `.github/workflows/ci.yml`

- [ ] **Step 1: Create `.github/workflows/ci.yml`**

```yaml
name: CI
on:
  push:
    branches: [main, master]
  pull_request:

jobs:
  lint-test:
    runs-on: ubuntu-latest
    strategy:
      matrix:
        python: ["3.12", "3.13"]
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: ${{ matrix.python }}
      - name: Install
        run: |
          python -m pip install --upgrade pip
          pip install -e ".[dev]"
      - name: Ruff
        run: ruff check .
      - name: Mypy
        run: mypy --strict custom_components tests
      - name: Pytest
        run: pytest --cov --cov-report=term-missing
```

- [ ] **Step 2: Commit**

```bash
mkdir -p .github/workflows
git -c user.name=twarberg -c user.email=tim@tlw.dk add .github/workflows/ci.yml
git -c user.name=twarberg -c user.email=tim@tlw.dk commit -m "ci: add lint+type+test matrix on Python 3.12 and 3.13"
```

---

## Final verification

After all 21 tasks:

```bash
ruff check .
mypy --strict custom_components tests
pytest --cov --cov-report=term-missing
```

All three must be green. Coverage should meet:

- `planner.py`: 100%
- `price_source.py`, `car_state.py`: ≥95%
- `config_flow.py`: ≥90%
- `coordinator.py`: ≥85%
- entity files: ≥80%

Then perform a manual smoke test: install the integration into a real Home
Assistant instance via HACS custom repository, walk the config flow with
the user's actual Mercedes + Strømligning + OCPP entities, observe the
charger toggling at the planned hour for at least one full charge cycle.
That cycle is the v0.1 done criterion.

