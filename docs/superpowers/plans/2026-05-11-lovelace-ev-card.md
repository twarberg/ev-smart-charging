# Lovelace EV Smart Charging Card Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship `twarberg/lovelace-ev-smart-charging-card` v0.1.0 — a HACS Plugin custom card that visualizes the Smart EV Charging integration with a responsive six-tile grid (status, 24h price/plan timeline, charge window, 30d history, 7d SoC trend, actions), GUI editor, and click-to-act on the timeline.

**Architecture:** Lit 3 web component with sub-components per tile. CSS-grid `auto-fit` for responsiveness. Entity discovery from a single `device_id` via `hass.entities`. History from HA recorder WebSocket API, cached client-side with stale-while-revalidate and event-driven invalidation. Pure-function library code (`discover`, `format`, `history` session-detection) unit-tested with Vitest; components smoke-tested for DOM output + emitted events. Hand-rolled SVG (no charting deps) to keep bundle < 150 KB.

**Tech Stack:** TypeScript (strict), Lit 3, Rollup, Vitest + happy-dom, ESLint + Prettier. Node 20+ for dev. Bundle target ES2020, single ES-module file.

**Spec:** [`docs/superpowers/specs/2026-05-11-lovelace-ev-card-design.md`](../specs/2026-05-11-lovelace-ev-card-design.md)

**Two repos:**

- Phase A lives in `twarberg/ev-smart-charging` (this repo) — small integration PR to expose discovery hints.
- Phases B–F live in `twarberg/lovelace-ev-smart-charging-card` (new repo).

---

## File structure

### Phase A — `twarberg/ev-smart-charging` (this repo)

| File | Change | Task |
|---|---|---|
| `custom_components/smart_ev_charging/sensor.py` | Extend `PlanStatusSensor.extra_state_attributes` + `PlannedHoursSensor.extra_state_attributes` | A1, A2 |
| `tests/test_sensor.py` | New file — assertions for the two extended dicts | A1, A2 |
| `custom_components/smart_ev_charging/manifest.json` | Bump `version` to `0.2.0` | A3 |

### Phase B–F — `twarberg/lovelace-ev-smart-charging-card` (new repo)

| File | Responsibility | Task |
|---|---|---|
| `package.json` | npm scripts + deps | B1 |
| `tsconfig.json` | strict TS, ES2020 target | B1 |
| `rollup.config.mjs` | Single ES-module bundle | B1 |
| `vitest.config.ts` | happy-dom env | B3 |
| `.eslintrc.cjs` | TypeScript + Lit rules | B3 |
| `.prettierrc.json` | Style config | B3 |
| `.gitignore` | Node + dist | B1 |
| `LICENSE` | MIT | B2 |
| `README.md` | User docs | B2 (skeleton), F2 (full) |
| `info.md` | HACS install page | B2 |
| `hacs.json` | HACS Plugin metadata | B2 |
| `src/types.ts` | `CardConfig`, narrowed HA types | C1 |
| `src/lib/format.ts` | Currency, time, kWh formatters | C2 |
| `src/lib/discover.ts` | `device_id` → `DeviceEntities` | C3 |
| `src/lib/history.ts` | Recorder fetch + session detection + buckets | C4 |
| `src/lib/theme.ts` | HA CSS-var helpers | C5 |
| `src/components/ev-status.ts` | Status pill + toggle + SoC bar | D1 |
| `src/components/ev-timeline.ts` | 24h price/plan SVG + slot-click events | D2 |
| `src/components/ev-window.ts` | Planned-hour table + cost | D3 |
| `src/components/ev-history.ts` | 30d cost bars + drawer | D4 |
| `src/components/ev-soc-trend.ts` | 7d SoC line | D5 |
| `src/components/ev-deadline-picker.ts` | Time picker dialog | D6 |
| `src/components/ev-actions.ts` | Button row + dialogs | D7 |
| `src/ev-smart-charging-card.ts` | Main element, grid, hass propagation, subscriptions | E1 |
| `src/editor.ts` | `getConfigElement`, `ha-form` schema | E2 |
| `src/lang/en.json` | English strings | E3 |
| `src/lang/da.json` | Danish strings | E3 |
| `src/lang/index.ts` | `localize` mixin | E3 |
| `tests/format.test.ts` | Pure formatter tests | C2 |
| `tests/discover.test.ts` | Discovery from stubbed hass | C3 |
| `tests/history.test.ts` | Session detection + buckets | C4 |
| `tests/timeline.test.ts` | Slot-click CustomEvent shape | D2 |
| `tests/editor.test.ts` | Editor renders + emits valid config | E2 |
| `tests/helpers/stub-hass.ts` | Shared stub for tests | C3 |
| `.github/workflows/ci.yml` | lint + typecheck + test + build + hacs validate | B4 |
| `.github/workflows/release.yml` | Build + attach dist to tagged release | F1 |
| `dist/ev-smart-charging-card.js` | Built bundle (committed for HACS) | F1 |

---

# Phase A — Integration discovery hints

Work in the current `twarberg/ev-smart-charging` repo on a fresh branch.
Three tiny tasks; merge before Phase B starts so the card has stable data
to read.

## Task A1: Expose discovery hints on `PlanStatusSensor`

**Files:**
- Modify: `custom_components/smart_ev_charging/sensor.py` (lines 45–60)
- Create: `tests/test_sensor.py`

- [ ] **Step 1: Branch off master**

```bash
cd /home/tlw/dev/ev-smart-charging
git fetch origin master
git checkout master && git pull
git checkout -b feat/card-discovery-attrs
```

- [ ] **Step 2: Write the failing test**

Create `tests/test_sensor.py` with:

```python
"""Sensor-attribute tests for Smart EV Charging."""
from __future__ import annotations

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.smart_ev_charging.const import (
    CONF_CHARGER_KW,
    CONF_PRICE_ENTITY,
    CONF_SOC_ENTITY,
    CONF_TARGET_SOC_ENTITY,
    DOMAIN,
)


@pytest.fixture
def entry(hass):
    e = MockConfigEntry(
        domain=DOMAIN,
        title="Daily",
        data={
            CONF_PRICE_ENTITY: "sensor.test_prices",
            CONF_CHARGER_KW: 11.0,
            CONF_SOC_ENTITY: "sensor.test_soc",
            CONF_TARGET_SOC_ENTITY: "number.test_target_soc",
        },
    )
    e.add_to_hass(hass)
    return e


async def test_plan_status_attrs_include_discovery_hints(hass, entry):
    """PlanStatusSensor.extra_state_attributes must expose hints the card needs."""
    from custom_components.smart_ev_charging.coordinator import SmartEVCoordinator
    from custom_components.smart_ev_charging.sensor import PlanStatusSensor

    coord = SmartEVCoordinator(hass, entry)
    # avoid a full refresh — only attribute keys matter here
    coord.data = coord._empty_data()  # type: ignore[attr-defined]

    sensor = PlanStatusSensor(coord, "plan_status", "plan_status")
    attrs = sensor.extra_state_attributes

    assert attrs["source_price_entity"] == "sensor.test_prices"
    assert attrs["charger_kw"] == 11.0
    assert attrs["soc_entity"] == "sensor.test_soc"
    assert attrs["target_soc_entity"] == "number.test_target_soc"
    assert "override_mode" in attrs
    assert "override_until" in attrs
```

- [ ] **Step 3: Run test to verify it fails**

```bash
source .venv/bin/activate
pytest tests/test_sensor.py::test_plan_status_attrs_include_discovery_hints -v
```

Expected: FAIL — `KeyError: 'source_price_entity'`.

- [ ] **Step 4: Implement the change**

Edit `custom_components/smart_ev_charging/sensor.py` — replace the `extra_state_attributes` method on `PlanStatusSensor`:

```python
    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        ov = self.coordinator.data.override
        entry = self.coordinator.entry
        opts = {**entry.data, **entry.options}
        return {
            "override_mode": ov.mode if ov else None,
            "override_until": ov.until.isoformat() if ov and ov.until else None,
            "source_price_entity": opts.get(CONF_PRICE_ENTITY),
            "charger_kw": float(opts.get(CONF_CHARGER_KW, DEFAULT_CHARGER_KW)),
            "soc_entity": opts.get(CONF_SOC_ENTITY),
            "target_soc_entity": opts.get(CONF_TARGET_SOC_ENTITY),
        }
```

Add to the import block at the top of the file:

```python
from .const import (
    CONF_CHARGER_KW,
    CONF_PRICE_ENTITY,
    CONF_SOC_ENTITY,
    CONF_TARGET_SOC_ENTITY,
    DEFAULT_CHARGER_KW,
    DOMAIN,
)
```

- [ ] **Step 5: Run test to verify it passes**

```bash
pytest tests/test_sensor.py::test_plan_status_attrs_include_discovery_hints -v
```

Expected: PASS.

- [ ] **Step 6: Run full test suite — nothing else regressed**

```bash
pytest -q
```

Expected: all existing tests pass.

- [ ] **Step 7: Commit**

```bash
git add custom_components/smart_ev_charging/sensor.py tests/test_sensor.py
git -c user.name=twarberg -c user.email=tim@tlw.dk commit -m "$(cat <<'EOF'
feat(sensor): expose discovery hints on PlanStatusSensor for custom card

Adds source_price_entity, charger_kw, soc_entity, target_soc_entity to
PlanStatusSensor.extra_state_attributes so a frontend card can resolve
the integration's upstream entities from a device_id alone (without
needing access to the config entry).

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task A2: Add `hour_kwh` to `PlannedHoursSensor`

**Files:**
- Modify: `custom_components/smart_ev_charging/sensor.py` (PlannedHoursSensor.extra_state_attributes)
- Modify: `tests/test_sensor.py` (new test)

- [ ] **Step 1: Add failing test**

Append to `tests/test_sensor.py`:

```python
async def test_planned_hours_attrs_include_hour_kwh(hass, entry):
    """PlannedHoursSensor.extra_state_attributes must expose hour_kwh parallel to hours."""
    from datetime import UTC, datetime, timedelta

    from custom_components.smart_ev_charging.coordinator import SmartEVCoordinator
    from custom_components.smart_ev_charging.planner import Plan
    from custom_components.smart_ev_charging.sensor import PlannedHoursSensor

    coord = SmartEVCoordinator(hass, entry)
    empty = coord._empty_data()  # type: ignore[attr-defined]
    start = datetime(2026, 5, 11, 2, 0, tzinfo=UTC)
    empty.plan = Plan(
        selected_starts=(start, start + timedelta(hours=1)),
        selected_prices=(0.65, 0.60),
        deadline=start + timedelta(hours=4),
        initial_deadline=start + timedelta(hours=4),
        status_label="ok",
        was_extended=False,
        window_size=2,
    )
    coord.data = empty

    sensor = PlannedHoursSensor(coord, "planned_hours", "planned_hours")
    attrs = sensor.extra_state_attributes

    assert attrs["hours"] == [start.isoformat(), (start + timedelta(hours=1)).isoformat()]
    assert attrs["hour_kwh"] == [11.0, 11.0]
    assert len(attrs["hour_kwh"]) == len(attrs["hours"])
```

- [ ] **Step 2: Run — verify FAIL**

```bash
pytest tests/test_sensor.py::test_planned_hours_attrs_include_hour_kwh -v
```

Expected: FAIL — `KeyError: 'hour_kwh'`.

- [ ] **Step 3: Implement**

Edit `PlannedHoursSensor.extra_state_attributes` in `sensor.py`:

```python
    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        data = self.coordinator.data
        starts = data.plan.selected_starts
        entry = self.coordinator.entry
        opts = {**entry.data, **entry.options}
        charger_kw = float(opts.get(CONF_CHARGER_KW, DEFAULT_CHARGER_KW))
        return {
            "hours": [s.isoformat() for s in starts],
            "hour_prices": list(data.plan.selected_prices),
            "hour_kwh": [charger_kw] * len(starts),
            "estimated_cost": data.estimated_cost,
            "cost_unit": data.cost_unit,
            "next_charge_start": starts[0].isoformat() if starts else None,
            "next_charge_end": (starts[-1] + timedelta(hours=1)).isoformat() if starts else None,
        }
```

- [ ] **Step 4: Run — verify PASS**

```bash
pytest tests/test_sensor.py -v
```

Expected: both tests pass.

- [ ] **Step 5: Run full suite + lint + typecheck**

```bash
pytest -q && ruff check custom_components tests && mypy --strict custom_components tests
```

Expected: clean.

- [ ] **Step 6: Commit**

```bash
git add custom_components/smart_ev_charging/sensor.py tests/test_sensor.py
git -c user.name=twarberg -c user.email=tim@tlw.dk commit -m "$(cat <<'EOF'
feat(sensor): add hour_kwh to PlannedHoursSensor

Parallel-array to `hours` exposing per-slot kWh (charger_kw × 1h). Lets
a frontend card render an estimated-kWh column without re-deriving
charger power from the config entry.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task A3: Bump version + open PR

**Files:**
- Modify: `custom_components/smart_ev_charging/manifest.json`

- [ ] **Step 1: Bump manifest version**

Edit `custom_components/smart_ev_charging/manifest.json`. Locate the `"version"` key and change its value to `"0.2.0"`. Leave all other keys untouched.

- [ ] **Step 2: Commit**

```bash
git add custom_components/smart_ev_charging/manifest.json
git -c user.name=twarberg -c user.email=tim@tlw.dk commit -m "$(cat <<'EOF'
chore(manifest): bump version to 0.2.0

Carries the new sensor discovery attributes (source_price_entity,
charger_kw, soc_entity, target_soc_entity, hour_kwh) for the upcoming
lovelace-ev-smart-charging-card.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

- [ ] **Step 3: Push + PR**

```bash
git push -u origin feat/card-discovery-attrs
gh pr create --title "feat: expose discovery hints for custom Lovelace card" --body "$(cat <<'EOF'
## Summary

- `PlanStatusSensor` exposes `source_price_entity`, `charger_kw`, `soc_entity`, `target_soc_entity`
- `PlannedHoursSensor` exposes `hour_kwh` parallel to `hours`
- Manifest bumped to 0.2.0

Enables the upcoming `twarberg/lovelace-ev-smart-charging-card` to resolve the integration's upstream entities and per-slot kWh from a device_id alone, without needing config-entry access.

## Test plan

- [x] New \`tests/test_sensor.py\` covers both extended attribute dicts
- [x] Full suite green (\`pytest -q\`)
- [x] \`ruff check\` and \`mypy --strict\` clean

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

- [ ] **Step 4: Wait for CI green + merge**

```bash
gh pr checks --watch
gh pr merge --squash --delete-branch
git checkout master && git pull
```

---

# Phase B — Card repo bootstrap

All Phase B–F work happens in a **new repository**.
Working directory below: `~/dev/lovelace-ev-smart-charging-card`.

## Task B1: Create repo + Node scaffold

**Files:**
- Create: `package.json`, `tsconfig.json`, `rollup.config.mjs`, `.gitignore`, `src/.gitkeep`, `tests/.gitkeep`

- [ ] **Step 1: Create directory + git repo**

```bash
mkdir -p ~/dev/lovelace-ev-smart-charging-card
cd ~/dev/lovelace-ev-smart-charging-card
git init -b main
```

- [ ] **Step 2: Create `package.json`**

```json
{
  "name": "lovelace-ev-smart-charging-card",
  "version": "0.1.0",
  "description": "Lovelace custom card for the Smart EV Charging Home Assistant integration.",
  "type": "module",
  "main": "dist/ev-smart-charging-card.js",
  "scripts": {
    "build": "rollup -c",
    "watch": "rollup -c -w",
    "test": "vitest run",
    "test:watch": "vitest",
    "lint": "eslint src tests",
    "format": "prettier --write src tests",
    "format:check": "prettier --check src tests",
    "typecheck": "tsc --noEmit"
  },
  "dependencies": {
    "lit": "^3.2.0"
  },
  "devDependencies": {
    "@rollup/plugin-commonjs": "^28.0.0",
    "@rollup/plugin-node-resolve": "^15.3.0",
    "@rollup/plugin-terser": "^0.4.4",
    "@rollup/plugin-typescript": "^12.1.0",
    "@types/node": "^20.0.0",
    "@typescript-eslint/eslint-plugin": "^7.0.0",
    "@typescript-eslint/parser": "^7.0.0",
    "@vitest/coverage-v8": "^2.0.0",
    "eslint": "^8.57.0",
    "eslint-plugin-lit": "^1.13.0",
    "happy-dom": "^15.0.0",
    "prettier": "^3.3.0",
    "rollup": "^4.20.0",
    "tslib": "^2.6.0",
    "typescript": "^5.5.0",
    "vitest": "^2.0.0"
  },
  "engines": {
    "node": ">=20"
  },
  "license": "MIT"
}
```

- [ ] **Step 3: Create `tsconfig.json`**

```json
{
  "compilerOptions": {
    "target": "ES2020",
    "module": "ESNext",
    "moduleResolution": "Bundler",
    "lib": ["ES2020", "DOM", "DOM.Iterable"],
    "strict": true,
    "noImplicitOverride": true,
    "noUncheckedIndexedAccess": true,
    "noUnusedLocals": true,
    "noUnusedParameters": true,
    "experimentalDecorators": true,
    "useDefineForClassFields": false,
    "sourceMap": true,
    "declaration": false,
    "resolveJsonModule": true,
    "esModuleInterop": true,
    "isolatedModules": true,
    "skipLibCheck": true,
    "outDir": "dist"
  },
  "include": ["src/**/*.ts", "tests/**/*.ts"]
}
```

- [ ] **Step 4: Create `rollup.config.mjs`**

```js
import nodeResolve from "@rollup/plugin-node-resolve";
import commonjs from "@rollup/plugin-commonjs";
import typescript from "@rollup/plugin-typescript";
import terser from "@rollup/plugin-terser";

export default {
  input: "src/ev-smart-charging-card.ts",
  output: {
    file: "dist/ev-smart-charging-card.js",
    format: "es",
    sourcemap: false,
    inlineDynamicImports: true,
  },
  plugins: [
    nodeResolve(),
    commonjs(),
    typescript({ tsconfig: "./tsconfig.json" }),
    terser({ format: { comments: false } }),
  ],
};
```

- [ ] **Step 5: Create `.gitignore`**

```
node_modules/
dist/*.map
.vitest/
coverage/
.DS_Store
*.log
```

(Note: `dist/ev-smart-charging-card.js` is committed for HACS; only sourcemaps + coverage are ignored.)

- [ ] **Step 6: Install + first commit**

```bash
npm install
git add .
git commit -m "chore: bootstrap card repo (Node + TS + Rollup + Lit)"
```

Expected: clean install, lockfile generated.

---

## Task B2: HACS metadata + LICENSE + README skeleton

**Files:**
- Create: `LICENSE`, `hacs.json`, `info.md`, `README.md`

- [ ] **Step 1: Create `LICENSE`** (MIT, holder "twarberg")

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

- [ ] **Step 2: Create `hacs.json`**

```json
{
  "name": "Smart EV Charging Card",
  "filename": "ev-smart-charging-card.js",
  "render_readme": true,
  "homeassistant": "2025.1"
}
```

- [ ] **Step 3: Create `info.md`** (HACS install page — short)

```markdown
# Smart EV Charging Card

A Lovelace custom card for the [Smart EV Charging](https://github.com/twarberg/ev-smart-charging) Home Assistant integration.

## Features

- Status pill, master toggle, SoC bar
- 24-hour price-and-plan timeline (click slots to skip / force-charge)
- Charge-window table with per-hour price and estimated total cost
- 30-day cost history with per-day session drawer
- 7-day SoC trend
- Action buttons (Replan, Force, Skip-until, Set deadline)
- Visual GUI editor — picks the integration's device from a dropdown
- Fully theme-aware (light / dark / community themes)
- en + da translations

Requires the `smart_ev_charging` integration (>= 0.2.0).

See the [project README](https://github.com/twarberg/lovelace-ev-smart-charging-card) for setup and screenshots.
```

- [ ] **Step 4: Create `README.md` skeleton** (will be filled out in F2)

```markdown
# Smart EV Charging Card

Lovelace custom card for the [Smart EV Charging](https://github.com/twarberg/ev-smart-charging) Home Assistant integration.

## Status

Pre-release. See [docs/superpowers/plans](https://github.com/twarberg/ev-smart-charging/tree/master/docs/superpowers/plans) for development progress.

## License

MIT.
```

- [ ] **Step 5: Commit**

```bash
git add LICENSE hacs.json info.md README.md
git commit -m "chore: HACS metadata + LICENSE + README skeleton"
```

---

## Task B3: Test + lint + format tooling

**Files:**
- Create: `vitest.config.ts`, `.eslintrc.cjs`, `.prettierrc.json`, `.prettierignore`

- [ ] **Step 1: Create `vitest.config.ts`**

```ts
import { defineConfig } from "vitest/config";

export default defineConfig({
  test: {
    environment: "happy-dom",
    include: ["tests/**/*.test.ts"],
    coverage: {
      provider: "v8",
      reporter: ["text", "html"],
      include: ["src/lib/**/*.ts", "src/components/**/*.ts"],
    },
  },
});
```

- [ ] **Step 2: Create `.eslintrc.cjs`**

```js
module.exports = {
  root: true,
  parser: "@typescript-eslint/parser",
  parserOptions: { ecmaVersion: 2022, sourceType: "module" },
  plugins: ["@typescript-eslint", "lit"],
  extends: [
    "eslint:recommended",
    "plugin:@typescript-eslint/recommended",
    "plugin:lit/recommended",
  ],
  rules: {
    "@typescript-eslint/no-unused-vars": ["error", { argsIgnorePattern: "^_" }],
    "@typescript-eslint/explicit-module-boundary-types": "off",
  },
  ignorePatterns: ["dist/", "node_modules/"],
};
```

- [ ] **Step 3: Create `.prettierrc.json`**

```json
{
  "printWidth": 100,
  "singleQuote": false,
  "trailingComma": "all",
  "semi": true,
  "arrowParens": "always"
}
```

- [ ] **Step 4: Create `.prettierignore`**

```
dist/
node_modules/
coverage/
package-lock.json
```

- [ ] **Step 5: Sanity-check tooling**

```bash
npm run typecheck  # should pass (no .ts files yet)
npm run lint       # should pass (nothing to lint)
npm test           # should pass (no tests found)
```

All three commands exit 0 with informative "no files" messages.

- [ ] **Step 6: Commit**

```bash
git add vitest.config.ts .eslintrc.cjs .prettierrc.json .prettierignore
git commit -m "chore: Vitest + ESLint + Prettier configs"
```

---

## Task B4: Push to GitHub + add CI workflow

**Files:**
- Create: `.github/workflows/ci.yml`

- [ ] **Step 1: Create GitHub repo + push**

```bash
gh repo create twarberg/lovelace-ev-smart-charging-card --public \
  --description "Lovelace custom card for the Smart EV Charging integration" \
  --source=. --remote=origin --push
```

- [ ] **Step 2: Add CI workflow**

Create `.github/workflows/ci.yml`:

```yaml
name: CI

on:
  push:
    branches: [main]
  pull_request:

jobs:
  lint-test-build:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with:
          node-version: "20"
          cache: "npm"
      - run: npm ci
      - run: npm run lint
      - run: npm run typecheck
      - run: npm test -- --coverage
      - run: npm run build
      - name: Check bundle size budget
        run: |
          size=$(stat -c%s dist/ev-smart-charging-card.js)
          echo "Bundle size: $size bytes"
          if [ "$size" -gt 153600 ]; then
            echo "FAIL: bundle exceeds 150 KB"
            exit 1
          fi

  hacs:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: hacs/action@main
        with:
          category: plugin
```

- [ ] **Step 3: Protect main branch**

```bash
gh api -X PUT \
  -H "Accept: application/vnd.github+json" \
  repos/twarberg/lovelace-ev-smart-charging-card/branches/main/protection \
  -F required_status_checks.strict=true \
  -F required_status_checks.contexts[]=lint-test-build \
  -F enforce_admins=false \
  -F required_pull_request_reviews.required_approving_review_count=0 \
  -F restrictions= \
  -F allow_force_pushes=false \
  -F allow_deletions=false
```

(If this fails because GitHub considers main empty until CI runs once, run it
again after Task B4 step 4.)

- [ ] **Step 4: Branch + commit + PR (every change goes via PR now)**

```bash
git checkout -b chore/ci-workflow
git add .github/workflows/ci.yml
git commit -m "ci: lint + typecheck + test + build + HACS validate"
git push -u origin chore/ci-workflow
gh pr create --title "ci: initial workflow" --body "$(cat <<'EOF'
## Summary
- Lint, typecheck, test, build, bundle-size budget (<150 KB)
- HACS plugin validation

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
gh pr checks --watch
gh pr merge --squash --delete-branch
git checkout main && git pull
```

CI on this PR will validate the toolchain end-to-end (nothing to lint, no tests, but build will fail because `src/ev-smart-charging-card.ts` doesn't exist yet — see workaround below).

- [ ] **Step 5: Add a minimal entry point so build passes**

CI fails Task B4 on the build step because the entry point doesn't exist.
Land it on the same PR by adding before push:

```bash
mkdir -p src
cat > src/ev-smart-charging-card.ts <<'EOF'
// Bootstrap entry — real implementation in later tasks.
console.info("%c ev-smart-charging-card%c v0.1.0-dev ", "color:white;background:#3b82f6;font-weight:700", "color:#3b82f6");
EOF
git add src/ev-smart-charging-card.ts
git commit --amend --no-edit
git push --force-with-lease
gh pr checks --watch
gh pr merge --squash --delete-branch
git checkout main && git pull
```

(Force-push is OK on the topic branch before merge.)

---

# Phase C — Library code (TDD)

## Task C1: `src/types.ts`

**Files:**
- Create: `src/types.ts`
- Create branch: `feat/types`

- [ ] **Step 1: Branch**

```bash
git checkout -b feat/types
```

- [ ] **Step 2: Create `src/types.ts`**

```ts
// Subset of the Home Assistant frontend API the card relies on.
// We deliberately keep this self-contained (no @types/home-assistant)
// because HA's frontend types aren't published as a package.

export type HassEntityAttribute = Record<string, unknown>;

export interface HassEntity {
  entity_id: string;
  state: string;
  attributes: HassEntityAttribute;
  last_changed: string;
  last_updated: string;
}

export interface HassEntityRegistryEntry {
  entity_id: string;
  device_id: string | null;
  config_entry_id: string | null;
  translation_key: string | null;
  platform: string;
  unique_id: string;
  original_name: string | null;
}

export interface HassConnection {
  subscribeEvents<T = unknown>(
    callback: (event: { event_type: string; data: T }) => void,
    eventType: string,
  ): Promise<() => Promise<void>>;
}

export interface HassLocale {
  language: string;
}

export interface HomeAssistant {
  states: Record<string, HassEntity>;
  entities: Record<string, HassEntityRegistryEntry>;
  connection: HassConnection;
  locale: HassLocale;
  callService(domain: string, service: string, serviceData?: Record<string, unknown>, target?: { entity_id?: string; device_id?: string }): Promise<void>;
  callWS<T = unknown>(msg: Record<string, unknown>): Promise<T>;
}

export type ShowTile = "status" | "timeline" | "window" | "history" | "soc" | "actions";

export interface CardConfig {
  type: string;
  device_id: string;
  name?: string;
  show?: ShowTile[];
  history_days?: number;
  soc_days?: number;
  theme?: "auto" | "light" | "dark";
  helper_entity?: string;
  language?: "auto" | "en" | "da";
}

export interface DeviceEntities {
  planStatus: string;
  plannedHours: string;
  slotsNeeded: string;
  activeDeadline: string;
  effectiveDeparture: string;
  pluggedIn: string;
  activelyCharging: string;
  chargeNow: string;
  smartCharging: string;
  socEntity?: string;
  targetSocEntity?: string;
  priceEntity?: string;
  chargerKw?: number;
}
```

- [ ] **Step 3: Typecheck**

```bash
npm run typecheck
```

Expected: PASS.

- [ ] **Step 4: Commit + PR + merge**

```bash
git add src/types.ts
git commit -m "feat(types): card config + HA frontend type surface"
git push -u origin feat/types
gh pr create --fill
gh pr checks --watch
gh pr merge --squash --delete-branch
git checkout main && git pull
```

---

## Task C2: `src/lib/format.ts` + tests

**Files:**
- Create: `src/lib/format.ts`
- Create: `tests/format.test.ts`
- Branch: `feat/lib-format`

- [ ] **Step 1: Branch**

```bash
git checkout -b feat/lib-format
```

- [ ] **Step 2: Write failing tests**

Create `tests/format.test.ts`:

```ts
import { describe, expect, it } from "vitest";
import { formatCurrency, formatHourMinute, formatKwh, stripPerKwh } from "../src/lib/format.js";

describe("formatCurrency", () => {
  it("formats DKK with two decimals", () => {
    expect(formatCurrency(20.567, "DKK", "en")).toBe("20.57 DKK");
  });
  it("falls back to raw when unit is null", () => {
    expect(formatCurrency(20.567, null, "en")).toBe("20.57");
  });
  it("returns em-dash for null amount", () => {
    expect(formatCurrency(null, "DKK", "en")).toBe("—");
  });
});

describe("formatHourMinute", () => {
  it("local-time HH:mm from ISO", () => {
    const iso = new Date(Date.UTC(2026, 4, 11, 2, 0)).toISOString();
    expect(formatHourMinute(iso)).toMatch(/^\d{2}:\d{2}$/);
  });
});

describe("formatKwh", () => {
  it("one decimal + unit", () => {
    expect(formatKwh(11)).toBe("11.0 kWh");
    expect(formatKwh(11.456)).toBe("11.5 kWh");
  });
});

describe("stripPerKwh", () => {
  it.each([
    ["DKK/kWh", "DKK"],
    ["EUR/kWh", "EUR"],
    ["DKK / kWh", "DKK"],
    ["DKK", "DKK"],
    [null, null],
    [undefined, null],
  ])("strips %s -> %s", (input, expected) => {
    expect(stripPerKwh(input as string | null | undefined)).toBe(expected);
  });
});
```

- [ ] **Step 3: Run — verify FAIL**

```bash
npm test
```

Expected: FAIL with `Cannot find module '../src/lib/format.js'`.

- [ ] **Step 4: Implement `src/lib/format.ts`**

```ts
export function formatCurrency(amount: number | null | undefined, unit: string | null, _locale: string): string {
  if (amount == null) return "—";
  const fixed = amount.toFixed(2);
  return unit ? `${fixed} ${unit}` : fixed;
}

export function formatHourMinute(iso: string): string {
  const d = new Date(iso);
  return d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", hour12: false });
}

export function formatKwh(value: number): string {
  return `${value.toFixed(1)} kWh`;
}

export function stripPerKwh(unit: string | null | undefined): string | null {
  if (unit == null) return null;
  const m = /^(.+?)\s*\/\s*kwh$/i.exec(unit.trim());
  return m ? m[1].trim() : unit;
}
```

- [ ] **Step 5: Run — verify PASS**

```bash
npm test
```

Expected: all tests in `format.test.ts` pass.

- [ ] **Step 6: Commit + PR + merge**

```bash
git add src/lib/format.ts tests/format.test.ts
git commit -m "feat(lib): currency/time/kWh formatters"
git push -u origin feat/lib-format
gh pr create --fill
gh pr checks --watch
gh pr merge --squash --delete-branch
git checkout main && git pull
```

---

## Task C3: `src/lib/discover.ts` + stub-hass helper + tests

**Files:**
- Create: `src/lib/discover.ts`
- Create: `tests/helpers/stub-hass.ts`
- Create: `tests/discover.test.ts`
- Branch: `feat/lib-discover`

- [ ] **Step 1: Branch**

```bash
git checkout -b feat/lib-discover
```

- [ ] **Step 2: Create stub-hass helper**

`tests/helpers/stub-hass.ts`:

```ts
import type { HassEntity, HassEntityRegistryEntry, HomeAssistant } from "../../src/types.js";

export interface StubOpts {
  deviceId?: string;
  entries?: Partial<Record<string, Partial<HassEntityRegistryEntry>>>;
  states?: Partial<Record<string, Partial<HassEntity>>>;
}

const DEFAULT_DEVICE = "test_dev";
const KEYS = [
  "plan_status",
  "planned_hours",
  "slots_needed",
  "active_deadline",
  "effective_departure",
  "plugged_in",
  "actively_charging",
  "charge_now",
  "smart_charging_enabled",
];

export function stubHass(opts: StubOpts = {}): HomeAssistant {
  const deviceId = opts.deviceId ?? DEFAULT_DEVICE;
  const entries: Record<string, HassEntityRegistryEntry> = {};
  const states: Record<string, HassEntity> = {};
  for (const key of KEYS) {
    const platform = key === "smart_charging_enabled" ? "switch" : key.endsWith("_in") || key === "actively_charging" || key === "charge_now" ? "binary_sensor" : "sensor";
    const entityId = `${platform}.daily_${key}`;
    entries[entityId] = {
      entity_id: entityId,
      device_id: deviceId,
      config_entry_id: "entry_x",
      translation_key: key,
      platform: "smart_ev_charging",
      unique_id: `entry_x_${key}`,
      original_name: null,
      ...opts.entries?.[entityId],
    };
    states[entityId] = {
      entity_id: entityId,
      state: "ok",
      attributes: {},
      last_changed: new Date(0).toISOString(),
      last_updated: new Date(0).toISOString(),
      ...opts.states?.[entityId],
    };
  }
  // PlanStatusSensor carries the discovery hints
  states["sensor.daily_plan_status"] = {
    ...states["sensor.daily_plan_status"],
    attributes: {
      source_price_entity: "sensor.test_prices",
      charger_kw: 11.0,
      soc_entity: "sensor.test_soc",
      target_soc_entity: "number.test_target",
      ...(opts.states?.["sensor.daily_plan_status"]?.attributes ?? {}),
    },
  };
  return {
    states,
    entities: entries,
    connection: { subscribeEvents: async () => async () => {} },
    locale: { language: "en" },
    callService: async () => {},
    callWS: async () => ({}),
  };
}
```

- [ ] **Step 3: Write failing test**

`tests/discover.test.ts`:

```ts
import { describe, expect, it } from "vitest";
import { discover } from "../src/lib/discover.js";
import { stubHass } from "./helpers/stub-hass.js";

describe("discover", () => {
  it("resolves all required entities from a device id", () => {
    const hass = stubHass();
    const d = discover(hass, "test_dev");
    expect(d.planStatus).toBe("sensor.daily_plan_status");
    expect(d.plannedHours).toBe("sensor.daily_planned_hours");
    expect(d.smartCharging).toBe("switch.daily_smart_charging_enabled");
    expect(d.chargeNow).toBe("binary_sensor.daily_charge_now");
  });

  it("reads optional source entities from plan_status attributes", () => {
    const hass = stubHass();
    const d = discover(hass, "test_dev");
    expect(d.priceEntity).toBe("sensor.test_prices");
    expect(d.chargerKw).toBe(11.0);
    expect(d.socEntity).toBe("sensor.test_soc");
    expect(d.targetSocEntity).toBe("number.test_target");
  });

  it("returns undefined source entities when plan_status attrs missing", () => {
    const hass = stubHass({
      states: { "sensor.daily_plan_status": { attributes: {} } },
    });
    const d = discover(hass, "test_dev");
    expect(d.priceEntity).toBeUndefined();
    expect(d.chargerKw).toBeUndefined();
    expect(d.socEntity).toBeUndefined();
  });

  it("throws when device has no integration entities", () => {
    const hass = stubHass({ deviceId: "other" });
    expect(() => discover(hass, "test_dev")).toThrow(/no entities/i);
  });
});
```

- [ ] **Step 4: Run — verify FAIL**

```bash
npm test
```

Expected: `Cannot find module '../src/lib/discover.js'`.

- [ ] **Step 5: Implement `src/lib/discover.ts`**

```ts
import type { DeviceEntities, HassEntityRegistryEntry, HomeAssistant } from "../types.js";

const KEY_TO_FIELD: Record<string, keyof DeviceEntities> = {
  plan_status: "planStatus",
  planned_hours: "plannedHours",
  slots_needed: "slotsNeeded",
  active_deadline: "activeDeadline",
  effective_departure: "effectiveDeparture",
  plugged_in: "pluggedIn",
  actively_charging: "activelyCharging",
  charge_now: "chargeNow",
  smart_charging_enabled: "smartCharging",
};

export function discover(hass: HomeAssistant, deviceId: string): DeviceEntities {
  const ours: HassEntityRegistryEntry[] = Object.values(hass.entities).filter(
    (e) => e.device_id === deviceId && e.platform === "smart_ev_charging",
  );
  if (ours.length === 0) {
    throw new Error(`discover: no entities found for device ${deviceId}`);
  }
  const partial: Partial<DeviceEntities> = {};
  for (const entry of ours) {
    const key = entry.translation_key ?? deriveKey(entry.unique_id);
    if (!key) continue;
    const field = KEY_TO_FIELD[key];
    if (field) partial[field] = entry.entity_id as DeviceEntities[typeof field] & string;
  }
  const required: (keyof DeviceEntities)[] = [
    "planStatus", "plannedHours", "slotsNeeded", "activeDeadline",
    "effectiveDeparture", "pluggedIn", "activelyCharging", "chargeNow", "smartCharging",
  ];
  for (const r of required) {
    if (!partial[r]) throw new Error(`discover: missing entity for ${r} on device ${deviceId}`);
  }

  // hints from plan_status attributes
  const planStatusState = hass.states[partial.planStatus!];
  const attrs = planStatusState?.attributes ?? {};
  const priceEntity = pickString(attrs.source_price_entity);
  const chargerKw = pickNumber(attrs.charger_kw);
  const socEntity = pickString(attrs.soc_entity);
  const targetSocEntity = pickString(attrs.target_soc_entity);

  return {
    ...partial,
    ...(priceEntity ? { priceEntity } : {}),
    ...(chargerKw !== undefined ? { chargerKw } : {}),
    ...(socEntity ? { socEntity } : {}),
    ...(targetSocEntity ? { targetSocEntity } : {}),
  } as DeviceEntities;
}

function deriveKey(uniqueId: string): string | null {
  // unique_id is "<entry_id>_<key>". Take the part after the first "_".
  const idx = uniqueId.indexOf("_");
  return idx >= 0 ? uniqueId.slice(idx + 1) : null;
}

function pickString(v: unknown): string | undefined {
  return typeof v === "string" && v.length > 0 ? v : undefined;
}

function pickNumber(v: unknown): number | undefined {
  return typeof v === "number" && Number.isFinite(v) ? v : undefined;
}
```

- [ ] **Step 6: Run — verify PASS**

```bash
npm test
```

Expected: all `discover.test.ts` tests pass.

- [ ] **Step 7: Commit + PR + merge**

```bash
git add src/lib/discover.ts tests/helpers/stub-hass.ts tests/discover.test.ts
git commit -m "feat(lib): discover() — device_id -> DeviceEntities"
git push -u origin feat/lib-discover
gh pr create --fill
gh pr checks --watch
gh pr merge --squash --delete-branch
git checkout main && git pull
```

---

## Task C4: `src/lib/history.ts` + tests

**Files:**
- Create: `src/lib/history.ts`
- Create: `tests/history.test.ts`
- Branch: `feat/lib-history`

- [ ] **Step 1: Branch**

```bash
git checkout -b feat/lib-history
```

- [ ] **Step 2: Failing tests**

`tests/history.test.ts`:

```ts
import { describe, expect, it } from "vitest";
import { detectSessions, rollupByDay } from "../src/lib/history.js";

describe("detectSessions", () => {
  it("groups contiguous on-runs of charge_now into sessions", () => {
    const series = [
      { state: "off", t: "2026-05-01T00:00:00Z" },
      { state: "on", t: "2026-05-01T02:00:00Z" },
      { state: "on", t: "2026-05-01T03:00:00Z" },
      { state: "off", t: "2026-05-01T05:00:00Z" },
      { state: "on", t: "2026-05-02T02:00:00Z" },
      { state: "off", t: "2026-05-02T04:00:00Z" },
    ];
    const sessions = detectSessions(series);
    expect(sessions).toHaveLength(2);
    expect(sessions[0]).toMatchObject({
      start: "2026-05-01T02:00:00Z",
      end: "2026-05-01T05:00:00Z",
      durationHours: 3,
    });
    expect(sessions[1].durationHours).toBe(2);
  });

  it("handles an unfinished trailing session as ending at the series end", () => {
    const series = [
      { state: "off", t: "2026-05-01T00:00:00Z" },
      { state: "on", t: "2026-05-01T02:00:00Z" },
    ];
    const sessions = detectSessions(series, "2026-05-01T04:00:00Z");
    expect(sessions[0]).toMatchObject({ durationHours: 2 });
  });

  it("returns empty array when never charged", () => {
    expect(detectSessions([{ state: "off", t: "x" }])).toEqual([]);
  });
});

describe("rollupByDay", () => {
  it("buckets sessions by local-day start date", () => {
    const buckets = rollupByDay([
      { start: "2026-05-01T02:00:00Z", end: "2026-05-01T05:00:00Z", durationHours: 3, cost: 9.0 },
      { start: "2026-05-01T22:00:00Z", end: "2026-05-02T02:00:00Z", durationHours: 4, cost: 5.0 },
      { start: "2026-05-02T03:00:00Z", end: "2026-05-02T05:00:00Z", durationHours: 2, cost: 4.5 },
    ]);
    expect(buckets.find((b) => b.date === "2026-05-01")?.cost).toBeCloseTo(9.0 + 5.0, 5);
    expect(buckets.find((b) => b.date === "2026-05-02")?.cost).toBeCloseTo(4.5, 5);
  });
});
```

- [ ] **Step 3: Run — verify FAIL**

```bash
npm test
```

Expected: module not found.

- [ ] **Step 4: Implement `src/lib/history.ts`**

```ts
import type { HomeAssistant } from "../types.js";

export interface StateSample {
  state: string;
  t: string;
}

export interface Session {
  start: string;
  end: string;
  durationHours: number;
  cost?: number;
  kwh?: number;
}

export interface DayBucket {
  date: string;
  cost: number;
  sessions: Session[];
}

export interface PricePoint {
  start: string;
  end: string;
  price: number;
}

export function detectSessions(series: StateSample[], seriesEnd?: string): Session[] {
  const out: Session[] = [];
  let runStart: string | null = null;
  for (const s of series) {
    if (s.state === "on" && runStart === null) {
      runStart = s.t;
    } else if (s.state !== "on" && runStart !== null) {
      out.push(makeSession(runStart, s.t));
      runStart = null;
    }
  }
  if (runStart !== null) {
    const end = seriesEnd ?? new Date().toISOString();
    out.push(makeSession(runStart, end));
  }
  return out;
}

function makeSession(start: string, end: string): Session {
  const ms = new Date(end).getTime() - new Date(start).getTime();
  const durationHours = Math.max(0, ms / 3_600_000);
  return { start, end, durationHours };
}

export function priceOverRun(prices: PricePoint[], start: string, end: string): number {
  const a = new Date(start).getTime();
  const b = new Date(end).getTime();
  let weighted = 0;
  let totalHours = 0;
  for (const p of prices) {
    const ps = new Date(p.start).getTime();
    const pe = new Date(p.end).getTime();
    const overlapMs = Math.max(0, Math.min(b, pe) - Math.max(a, ps));
    if (overlapMs === 0) continue;
    const h = overlapMs / 3_600_000;
    weighted += p.price * h;
    totalHours += h;
  }
  return totalHours > 0 ? weighted / totalHours : 0;
}

export function attachCost(sessions: Session[], prices: PricePoint[], chargerKw: number): Session[] {
  return sessions.map((s) => {
    const avgPrice = priceOverRun(prices, s.start, s.end);
    const kwh = s.durationHours * chargerKw;
    return { ...s, kwh, cost: kwh * avgPrice };
  });
}

export function rollupByDay(sessions: Session[]): DayBucket[] {
  const map = new Map<string, DayBucket>();
  for (const s of sessions) {
    const date = new Date(s.start).toISOString().slice(0, 10);
    const bucket = map.get(date) ?? { date, cost: 0, sessions: [] };
    bucket.cost += s.cost ?? 0;
    bucket.sessions.push(s);
    map.set(date, bucket);
  }
  return [...map.values()].sort((a, b) => a.date.localeCompare(b.date));
}

export async function fetchHistory(
  hass: HomeAssistant,
  entityIds: string[],
  start: Date,
  end: Date,
): Promise<Record<string, StateSample[]>> {
  const res = await hass.callWS<Record<string, Array<{ s: string; lu: number }>>>({
    type: "history/history_during_period",
    start_time: start.toISOString(),
    end_time: end.toISOString(),
    entity_ids: entityIds,
    minimal_response: true,
    no_attributes: true,
  });
  const out: Record<string, StateSample[]> = {};
  for (const [eid, items] of Object.entries(res)) {
    out[eid] = items.map((it) => ({ state: it.s, t: new Date(it.lu * 1000).toISOString() }));
  }
  return out;
}
```

- [ ] **Step 5: Run — verify PASS**

```bash
npm test
```

- [ ] **Step 6: Commit + PR + merge**

```bash
git add src/lib/history.ts tests/history.test.ts
git commit -m "feat(lib): history — fetch, session detection, daily rollup"
git push -u origin feat/lib-history
gh pr create --fill
gh pr checks --watch
gh pr merge --squash --delete-branch
git checkout main && git pull
```

---

## Task C5: `src/lib/theme.ts`

**Files:**
- Create: `src/lib/theme.ts`
- Branch: `feat/lib-theme`

- [ ] **Step 1: Branch**

```bash
git checkout -b feat/lib-theme
```

- [ ] **Step 2: Implement `src/lib/theme.ts`** (no test — single-line helpers)

```ts
// Centralized list of HA CSS variables we depend on. Used by components to keep
// theming consistent. Any value not present in the active theme falls back to
// the second argument.

export const VARS = {
  primary: "--primary-color",
  primaryText: "--primary-text-color",
  secondaryText: "--secondary-text-color",
  divider: "--divider-color",
  cardBg: "--card-background-color",
  success: "--success-color",
  warning: "--warning-color",
  error: "--error-color",
} as const;

export function cssVar(name: keyof typeof VARS, fallback: string): string {
  return `var(${VARS[name]}, ${fallback})`;
}
```

- [ ] **Step 3: Typecheck + lint**

```bash
npm run typecheck && npm run lint
```

- [ ] **Step 4: Commit + PR + merge**

```bash
git add src/lib/theme.ts
git commit -m "feat(lib): theme helpers (HA CSS-var aliases)"
git push -u origin feat/lib-theme
gh pr create --fill
gh pr checks --watch
gh pr merge --squash --delete-branch
git checkout main && git pull
```

---

# Phase D — Components

Each component is a Lit element. Style with `static styles = css\`...\`` per
component. Use HA CSS variables via `cssVar()`. Each task: write a smoke
test (DOM rendered, events emitted), then implement.

## Task D1: `ev-status`

**Files:**
- Create: `src/components/ev-status.ts`
- Branch: `feat/ev-status`

- [ ] **Step 1: Branch**

```bash
git checkout -b feat/ev-status
```

- [ ] **Step 2: Implement `src/components/ev-status.ts`**

```ts
import { LitElement, css, html } from "lit";
import { customElement, property } from "lit/decorators.js";
import { cssVar } from "../lib/theme.js";
import type { DeviceEntities, HomeAssistant } from "../types.js";

const STATUS_COLORS: Record<string, string> = {
  ok: cssVar("success", "#22c55e"),
  partial: cssVar("warning", "#f59e0b"),
  extended: cssVar("warning", "#f59e0b"),
  no_data: cssVar("secondaryText", "#94a3b8"),
  unplugged: cssVar("secondaryText", "#94a3b8"),
  disabled: cssVar("secondaryText", "#94a3b8"),
};

@customElement("ev-status")
export class EvStatus extends LitElement {
  @property({ attribute: false }) hass!: HomeAssistant;
  @property({ attribute: false }) entities!: DeviceEntities;

  static styles = css`
    :host { display: block; }
    .tile { background: ${cssVar("cardBg", "#fff")}; border-radius: 12px; padding: 12px; }
    .header { display: flex; justify-content: space-between; align-items: center; gap: 8px; }
    .name { font-weight: 600; font-size: 1.05em; }
    .pill { padding: 2px 10px; border-radius: 999px; color: white; font-size: 0.85em; }
    .row { display: flex; justify-content: space-between; align-items: center; padding-top: 8px; font-size: 0.9em; color: ${cssVar("secondaryText", "#475569")}; }
    .soc-track { height: 8px; background: ${cssVar("divider", "#e5e7eb")}; border-radius: 999px; overflow: hidden; margin-top: 6px; position: relative; }
    .soc-fill { height: 100%; background: ${cssVar("primary", "#3b82f6")}; transition: width .3s; }
    .soc-target { position: absolute; top: -2px; width: 2px; height: 12px; background: ${cssVar("primaryText", "#0f172a")}; }
    .toggle-btn { background: none; border: 1px solid ${cssVar("divider", "#e5e7eb")}; padding: 4px 10px; border-radius: 8px; cursor: pointer; }
  `;

  override render() {
    const planStatus = this.hass.states[this.entities.planStatus];
    const smart = this.hass.states[this.entities.smartCharging];
    const departure = this.hass.states[this.entities.effectiveDeparture];
    const status = planStatus?.state ?? "no_data";
    const color = STATUS_COLORS[status] ?? STATUS_COLORS.no_data;
    const oneOff = (departure?.attributes.source ?? "default") === "one_off";

    const soc = this.entities.socEntity ? Number(this.hass.states[this.entities.socEntity]?.state) : NaN;
    const target = this.entities.targetSocEntity ? Number(this.hass.states[this.entities.targetSocEntity]?.state) : NaN;
    const hasSoC = Number.isFinite(soc);

    return html`
      <div class="tile">
        <div class="header">
          <span class="name">${this.entities.planStatus.split(".")[1].replace(/_/g, " ").replace(/plan status$/, "")}</span>
          <span class="pill" style="background:${color}">${status}</span>
          <button class="toggle-btn" @click=${this._toggle}>
            ${smart?.state === "on" ? "Smart: ON" : "Smart: OFF"}
          </button>
        </div>
        <div class="row">
          <span>Deadline: ${departure?.state ?? "—"}</span>
          ${oneOff ? html`<span title="one-off override active">★</span>` : ""}
        </div>
        ${hasSoC
          ? html`
              <div class="soc-track">
                <div class="soc-fill" style="width:${Math.max(0, Math.min(100, soc))}%"></div>
                ${Number.isFinite(target) ? html`<div class="soc-target" style="left:${target}%"></div>` : ""}
              </div>
              <div class="row"><span>SoC ${soc.toFixed(0)}% → ${Number.isFinite(target) ? target.toFixed(0) + "%" : "—"}</span></div>
            `
          : ""}
      </div>
    `;
  }

  private _toggle = () => {
    this.hass.callService("switch", "toggle", undefined, { entity_id: this.entities.smartCharging });
  };
}

declare global {
  interface HTMLElementTagNameMap {
    "ev-status": EvStatus;
  }
}
```

- [ ] **Step 3: Typecheck + lint**

```bash
npm run typecheck && npm run lint
```

- [ ] **Step 4: Commit + PR + merge**

```bash
git add src/components/ev-status.ts
git commit -m "feat(comp): ev-status (pill + master toggle + SoC bar)"
git push -u origin feat/ev-status
gh pr create --fill
gh pr checks --watch
gh pr merge --squash --delete-branch
git checkout main && git pull
```

---

## Task D2: `ev-timeline` + slot-click event + tests

**Files:**
- Create: `src/components/ev-timeline.ts`
- Create: `tests/timeline.test.ts`
- Branch: `feat/ev-timeline`

- [ ] **Step 1: Branch**

```bash
git checkout -b feat/ev-timeline
```

- [ ] **Step 2: Failing test**

`tests/timeline.test.ts`:

```ts
import { describe, expect, it, vi } from "vitest";
import "../src/components/ev-timeline.js";
import type { EvTimeline } from "../src/components/ev-timeline.js";
import { stubHass } from "./helpers/stub-hass.js";
import { discover } from "../src/lib/discover.js";

function makePrices() {
  const out = [];
  for (let h = 0; h < 24; h++) {
    const start = new Date(Date.UTC(2026, 4, 11, h, 0));
    const end = new Date(Date.UTC(2026, 4, 11, h + 1, 0));
    out.push({ start: start.toISOString(), end: end.toISOString(), price: 0.5 + (h % 4) * 0.1 });
  }
  return out;
}

describe("ev-timeline", () => {
  it("emits slot-click with isPlanned=true for a planned hour", async () => {
    const hass = stubHass({
      states: {
        "sensor.daily_planned_hours": {
          attributes: {
            hours: [new Date(Date.UTC(2026, 4, 11, 2, 0)).toISOString()],
            hour_prices: [0.6],
          },
        },
        "sensor.test_prices": { attributes: { prices: makePrices() } },
      },
    });
    const ents = discover(hass, "test_dev");
    const el = document.createElement("ev-timeline") as EvTimeline;
    el.hass = hass;
    el.entities = ents;
    document.body.appendChild(el);
    await el.updateComplete;

    const handler = vi.fn();
    el.addEventListener("slot-click", handler as EventListener);

    const rect = el.shadowRoot!.querySelector<SVGElement>("[data-slot-hour='2']");
    expect(rect).toBeTruthy();
    rect!.dispatchEvent(new MouseEvent("click", { bubbles: true, composed: true }));

    expect(handler).toHaveBeenCalledOnce();
    const detail = (handler.mock.calls[0][0] as CustomEvent).detail;
    expect(detail.isPlanned).toBe(true);
    expect(detail.start).toMatch(/T02:00/);
  });
});
```

- [ ] **Step 3: Run — verify FAIL**

```bash
npm test
```

Expected: module not found.

- [ ] **Step 4: Implement `src/components/ev-timeline.ts`**

```ts
import { LitElement, css, html, svg } from "lit";
import { customElement, property } from "lit/decorators.js";
import { cssVar } from "../lib/theme.js";
import type { DeviceEntities, HomeAssistant } from "../types.js";

interface PricePoint {
  start: string;
  end: string;
  price: number;
}

export interface SlotClickDetail {
  start: string;
  end: string;
  isPlanned: boolean;
  price: number;
}

const W = 480;
const H = 80;

@customElement("ev-timeline")
export class EvTimeline extends LitElement {
  @property({ attribute: false }) hass!: HomeAssistant;
  @property({ attribute: false }) entities!: DeviceEntities;

  static styles = css`
    :host { display: block; }
    .tile { background: ${cssVar("cardBg", "#fff")}; border-radius: 12px; padding: 12px; }
    h3 { margin: 0 0 8px; font-size: 0.95em; color: ${cssVar("secondaryText", "#475569")}; font-weight: 600; letter-spacing: 0.04em; text-transform: uppercase; }
    svg { width: 100%; height: auto; display: block; }
    .slot { cursor: pointer; }
    .slot:hover { fill: ${cssVar("primary", "#3b82f6")}; opacity: 0.15; }
    .planned-rect { fill: ${cssVar("success", "#22c55e")}; opacity: 0.35; pointer-events: none; }
    .now-line { stroke: ${cssVar("primaryText", "#0f172a")}; stroke-width: 1; stroke-dasharray: 2 2; }
    .empty { color: ${cssVar("secondaryText", "#94a3b8"); }; font-style: italic; }
  `;

  override render() {
    const prices = this._prices();
    if (prices.length === 0) {
      return html`<div class="tile"><h3>Price &amp; plan</h3><div class="empty">No price data yet</div></div>`;
    }
    const plannedAttr = this.hass.states[this.entities.plannedHours]?.attributes;
    const plannedISO = new Set<string>((plannedAttr?.hours as string[] | undefined) ?? []);

    const min = Math.min(...prices.map((p) => p.price));
    const max = Math.max(...prices.map((p) => p.price));
    const span = max - min || 1;
    const slotW = W / prices.length;
    const linePts = prices.map((p, i) => {
      const y = H - 8 - ((p.price - min) / span) * (H - 16);
      const x = i * slotW + slotW / 2;
      return `${x.toFixed(1)},${y.toFixed(1)}`;
    }).join(" ");

    const now = new Date();
    const nowIdx = prices.findIndex((p) => new Date(p.start) <= now && now < new Date(p.end));
    const nowX = nowIdx >= 0 ? nowIdx * slotW + slotW * ((now.getTime() - new Date(prices[nowIdx].start).getTime()) / 3_600_000) : -1;

    return html`
      <div class="tile">
        <h3>Price &amp; plan — next ${prices.length}h</h3>
        <svg viewBox="0 0 ${W} ${H}" role="img" aria-label="24h price curve with planned hours">
          ${prices.map((p, i) => {
            const planned = plannedISO.has(p.start);
            return svg`
              <rect class="slot" x="${i * slotW}" y="0" width="${slotW}" height="${H}"
                fill="transparent" stroke="${cssVar("divider", "#e5e7eb")}" stroke-width="0.25"
                data-slot-hour="${i}"
                @click=${() => this._emitSlot(p, planned)}>
                <title>${new Date(p.start).toLocaleString()} · ${p.price.toFixed(2)}</title>
              </rect>
              ${planned ? svg`<rect class="planned-rect" x="${i * slotW}" y="8" width="${slotW}" height="${H - 16}" />` : ""}
            `;
          })}
          <polyline points="${linePts}" fill="none" stroke="${cssVar("primary", "#3b82f6")}" stroke-width="1.5" />
          ${nowX >= 0 ? svg`<line class="now-line" x1="${nowX}" y1="0" x2="${nowX}" y2="${H}" />` : ""}
        </svg>
      </div>
    `;
  }

  private _emitSlot = (p: PricePoint, isPlanned: boolean) => {
    const detail: SlotClickDetail = { start: p.start, end: p.end, isPlanned, price: p.price };
    this.dispatchEvent(new CustomEvent("slot-click", { detail, bubbles: true, composed: true }));
  };

  private _prices(): PricePoint[] {
    if (!this.entities.priceEntity) return [];
    const raw = this.hass.states[this.entities.priceEntity]?.attributes.prices;
    if (!Array.isArray(raw)) return [];
    return (raw as PricePoint[]).filter((p) => p && typeof p.start === "string" && typeof p.end === "string" && typeof p.price === "number");
  }
}

declare global {
  interface HTMLElementTagNameMap {
    "ev-timeline": EvTimeline;
  }
}
```

- [ ] **Step 5: Run — verify PASS**

```bash
npm test
```

- [ ] **Step 6: Commit + PR + merge**

```bash
git add src/components/ev-timeline.ts tests/timeline.test.ts
git commit -m "feat(comp): ev-timeline (24h SVG + slot-click events)"
git push -u origin feat/ev-timeline
gh pr create --fill
gh pr checks --watch
gh pr merge --squash --delete-branch
git checkout main && git pull
```

---

## Task D3: `ev-window`

**Files:**
- Create: `src/components/ev-window.ts`
- Branch: `feat/ev-window`

- [ ] **Step 1: Branch**

```bash
git checkout -b feat/ev-window
```

- [ ] **Step 2: Implement `src/components/ev-window.ts`**

```ts
import { LitElement, css, html } from "lit";
import { customElement, property } from "lit/decorators.js";
import { formatCurrency, formatHourMinute, formatKwh } from "../lib/format.js";
import { cssVar } from "../lib/theme.js";
import type { DeviceEntities, HomeAssistant } from "../types.js";

@customElement("ev-window")
export class EvWindow extends LitElement {
  @property({ attribute: false }) hass!: HomeAssistant;
  @property({ attribute: false }) entities!: DeviceEntities;

  static styles = css`
    :host { display: block; }
    .tile { background: ${cssVar("cardBg", "#fff")}; border-radius: 12px; padding: 12px; }
    h3 { margin: 0 0 8px; font-size: 0.95em; color: ${cssVar("secondaryText", "#475569")}; font-weight: 600; letter-spacing: 0.04em; text-transform: uppercase; }
    table { width: 100%; border-collapse: collapse; font-size: 0.9em; }
    th, td { padding: 4px 6px; border-bottom: 1px solid ${cssVar("divider", "#eee")}; text-align: right; }
    th:first-child, td:first-child { text-align: left; }
    tfoot td { font-weight: 600; border-top: 2px solid ${cssVar("divider", "#eee")}; border-bottom: none; padding-top: 8px; }
    .empty { color: ${cssVar("secondaryText", "#94a3b8")}; font-style: italic; }
  `;

  override render() {
    const attrs = this.hass.states[this.entities.plannedHours]?.attributes ?? {};
    const hours = (attrs.hours as string[] | undefined) ?? [];
    const prices = (attrs.hour_prices as number[] | undefined) ?? [];
    const kwh = (attrs.hour_kwh as number[] | undefined) ?? [];
    const unit = (attrs.cost_unit as string | null) ?? null;
    const total = (attrs.estimated_cost as number | null) ?? null;
    const language = this.hass.locale.language;

    if (hours.length === 0) {
      return html`<div class="tile"><h3>Charge window</h3><div class="empty">No charging planned</div></div>`;
    }
    let cumulative = 0;
    return html`
      <div class="tile">
        <h3>Charge window</h3>
        <table>
          <thead><tr><th>Time</th><th>Price/kWh</th><th>kWh</th><th>Cumulative</th></tr></thead>
          <tbody>
            ${hours.map((h, i) => {
              const price = prices[i] ?? 0;
              const slotKwh = kwh[i] ?? 0;
              cumulative += price * slotKwh;
              return html`
                <tr>
                  <td>${formatHourMinute(h)}</td>
                  <td>${price.toFixed(2)}</td>
                  <td>${formatKwh(slotKwh)}</td>
                  <td>${formatCurrency(cumulative, unit, language)}</td>
                </tr>
              `;
            })}
          </tbody>
          <tfoot><tr><td colspan="3">Estimated total</td><td>${formatCurrency(total, unit, language)}</td></tr></tfoot>
        </table>
      </div>
    `;
  }
}

declare global {
  interface HTMLElementTagNameMap {
    "ev-window": EvWindow;
  }
}
```

- [ ] **Step 3: Typecheck + lint**

```bash
npm run typecheck && npm run lint
```

- [ ] **Step 4: Commit + PR + merge**

```bash
git add src/components/ev-window.ts
git commit -m "feat(comp): ev-window (planned-hour table + cost)"
git push -u origin feat/ev-window
gh pr create --fill
gh pr checks --watch
gh pr merge --squash --delete-branch
git checkout main && git pull
```

---

## Task D4: `ev-history`

**Files:**
- Create: `src/components/ev-history.ts`
- Branch: `feat/ev-history`

- [ ] **Step 1: Branch**

```bash
git checkout -b feat/ev-history
```

- [ ] **Step 2: Implement `src/components/ev-history.ts`**

```ts
import { LitElement, css, html, svg } from "lit";
import { customElement, property, state } from "lit/decorators.js";
import { attachCost, detectSessions, fetchHistory, rollupByDay } from "../lib/history.js";
import type { DayBucket, PricePoint } from "../lib/history.js";
import { formatCurrency } from "../lib/format.js";
import { cssVar } from "../lib/theme.js";
import type { DeviceEntities, HomeAssistant } from "../types.js";

@customElement("ev-history")
export class EvHistory extends LitElement {
  @property({ attribute: false }) hass!: HomeAssistant;
  @property({ attribute: false }) entities!: DeviceEntities;
  @property({ type: Number }) days = 30;

  @state() private _buckets?: DayBucket[];
  @state() private _expanded: string | null = null;
  @state() private _error: string | null = null;
  private _lastFetchKey = "";

  static styles = css`
    :host { display: block; }
    .tile { background: ${cssVar("cardBg", "#fff")}; border-radius: 12px; padding: 12px; }
    h3 { margin: 0 0 8px; font-size: 0.95em; color: ${cssVar("secondaryText", "#475569")}; font-weight: 600; letter-spacing: 0.04em; text-transform: uppercase; }
    .header { display: flex; justify-content: space-between; font-size: 0.85em; color: ${cssVar("secondaryText", "#475569")}; margin-bottom: 6px; }
    svg { width: 100%; height: 80px; display: block; }
    .bar { cursor: pointer; }
    .bar:hover { opacity: 0.7; }
    .drawer { margin-top: 8px; font-size: 0.85em; }
    .drawer ul { list-style: none; padding: 0; margin: 0; }
    .drawer li { padding: 2px 0; border-bottom: 1px solid ${cssVar("divider", "#eee")}; }
    .empty { color: ${cssVar("secondaryText", "#94a3b8")}; font-style: italic; }
  `;

  override updated() {
    const key = `${this.entities?.chargeNow}|${this.days}`;
    if (key !== this._lastFetchKey && this.hass && this.entities) {
      this._lastFetchKey = key;
      this._fetch();
    }
  }

  override render() {
    const language = this.hass.locale.language;
    const unit = this.hass.states[this.entities.planStatus]?.attributes.cost_unit as string | null ?? null;
    const buckets = this._buckets ?? [];
    const total = buckets.reduce((a, b) => a + b.cost, 0);
    const sessionCount = buckets.reduce((a, b) => a + b.sessions.length, 0);
    const maxCost = Math.max(0, ...buckets.map((b) => b.cost));

    return html`
      <div class="tile">
        <h3>History — ${this.days}d</h3>
        <div class="header">
          <span>Total ${formatCurrency(total, unit, language)}</span>
          <span>${sessionCount} sessions</span>
        </div>
        ${this._error
          ? html`<div class="empty">${this._error}</div>`
          : buckets.length === 0
          ? html`<div class="empty">Loading…</div>`
          : svg`
              <svg viewBox="0 0 ${buckets.length * 8} 80">
                ${buckets.map((b, i) => {
                  const h = maxCost > 0 ? (b.cost / maxCost) * 76 : 0;
                  return svg`<rect class="bar" x="${i * 8}" y="${80 - h}" width="7" height="${h}"
                    fill="${cssVar("primary", "#3b82f6")}"
                    @click=${() => (this._expanded = this._expanded === b.date ? null : b.date)}>
                    <title>${b.date}: ${b.cost.toFixed(2)} ${unit ?? ""}</title></rect>`;
                })}
              </svg>
              ${this._expanded
                ? html`<div class="drawer">
                    <strong>${this._expanded}</strong>
                    <ul>
                      ${buckets.find((b) => b.date === this._expanded)?.sessions.map(
                        (s) => html`<li>${new Date(s.start).toLocaleTimeString()}–${new Date(s.end).toLocaleTimeString()} · ${(s.kwh ?? 0).toFixed(1)} kWh · ${formatCurrency(s.cost ?? null, unit, language)}</li>`,
                      )}
                    </ul>
                  </div>`
                : ""}
            `}
      </div>
    `;
  }

  private async _fetch() {
    this._error = null;
    try {
      const end = new Date();
      const start = new Date(end.getTime() - this.days * 86_400_000);
      const ids: string[] = [this.entities.chargeNow];
      if (this.entities.priceEntity) ids.push(this.entities.priceEntity);
      const history = await fetchHistory(this.hass, ids, start, end);
      const chargeSeries = history[this.entities.chargeNow] ?? [];
      const sessions = detectSessions(chargeSeries, end.toISOString());
      // Price points: extract from current state's `prices` attribute (single-step approx;
      // for v0.1 we use the present prices array projected back, which is close enough
      // for daily-aggregate cost.
      const pricesAttr = this.entities.priceEntity
        ? (this.hass.states[this.entities.priceEntity]?.attributes.prices as PricePoint[] | undefined) ?? []
        : [];
      const kw = this.entities.chargerKw ?? 11.0;
      this._buckets = rollupByDay(attachCost(sessions, pricesAttr, kw));
    } catch (e) {
      this._error = `History fetch failed: ${(e as Error).message}`;
    }
  }
}

declare global {
  interface HTMLElementTagNameMap {
    "ev-history": EvHistory;
  }
}
```

- [ ] **Step 3: Typecheck + lint + test (no new test — covered indirectly by lib tests)**

```bash
npm run typecheck && npm run lint && npm test
```

- [ ] **Step 4: Commit + PR + merge**

```bash
git add src/components/ev-history.ts
git commit -m "feat(comp): ev-history (30d cost bars + day drawer)"
git push -u origin feat/ev-history
gh pr create --fill
gh pr checks --watch
gh pr merge --squash --delete-branch
git checkout main && git pull
```

---

## Task D5: `ev-soc-trend`

**Files:**
- Create: `src/components/ev-soc-trend.ts`
- Branch: `feat/ev-soc-trend`

- [ ] **Step 1: Branch**

```bash
git checkout -b feat/ev-soc-trend
```

- [ ] **Step 2: Implement `src/components/ev-soc-trend.ts`**

```ts
import { LitElement, css, html, svg } from "lit";
import { customElement, property, state } from "lit/decorators.js";
import { fetchHistory } from "../lib/history.js";
import type { StateSample } from "../lib/history.js";
import { cssVar } from "../lib/theme.js";
import type { DeviceEntities, HomeAssistant } from "../types.js";

@customElement("ev-soc-trend")
export class EvSocTrend extends LitElement {
  @property({ attribute: false }) hass!: HomeAssistant;
  @property({ attribute: false }) entities!: DeviceEntities;
  @property({ type: Number }) days = 7;

  @state() private _series?: StateSample[];
  @state() private _error: string | null = null;
  private _lastKey = "";

  static styles = css`
    :host { display: block; }
    .tile { background: ${cssVar("cardBg", "#fff")}; border-radius: 12px; padding: 12px; }
    h3 { margin: 0 0 8px; font-size: 0.95em; color: ${cssVar("secondaryText", "#475569")}; font-weight: 600; letter-spacing: 0.04em; text-transform: uppercase; }
    svg { width: 100%; height: 60px; display: block; }
    .empty { color: ${cssVar("secondaryText", "#94a3b8")}; font-style: italic; }
  `;

  override updated() {
    if (!this.entities?.socEntity) return;
    const key = `${this.entities.socEntity}|${this.days}`;
    if (key !== this._lastKey) {
      this._lastKey = key;
      this._fetch();
    }
  }

  override render() {
    if (!this.entities?.socEntity) {
      return html`<div class="tile"><h3>SoC — ${this.days}d</h3><div class="empty">No SoC entity configured</div></div>`;
    }
    if (this._error) {
      return html`<div class="tile"><h3>SoC — ${this.days}d</h3><div class="empty">${this._error}</div></div>`;
    }
    const samples = (this._series ?? []).filter((s) => Number.isFinite(Number(s.state)));
    if (samples.length < 2) {
      return html`<div class="tile"><h3>SoC — ${this.days}d</h3><div class="empty">Loading…</div></div>`;
    }
    const tStart = new Date(samples[0].t).getTime();
    const tEnd = new Date(samples[samples.length - 1].t).getTime();
    const span = tEnd - tStart || 1;
    const W = 200, H = 50;
    const pts = samples.map((s) => {
      const x = ((new Date(s.t).getTime() - tStart) / span) * W;
      const y = H - (Number(s.state) / 100) * H;
      return `${x.toFixed(1)},${y.toFixed(1)}`;
    }).join(" ");

    return html`
      <div class="tile">
        <h3>SoC — ${this.days}d</h3>
        <svg viewBox="0 0 ${W} ${H}">
          <polyline points="${pts}" fill="none" stroke="${cssVar("success", "#22c55e")}" stroke-width="1.5" />
        </svg>
      </div>
    `;
  }

  private async _fetch() {
    if (!this.entities.socEntity) return;
    try {
      this._error = null;
      const end = new Date();
      const start = new Date(end.getTime() - this.days * 86_400_000);
      const h = await fetchHistory(this.hass, [this.entities.socEntity], start, end);
      this._series = h[this.entities.socEntity] ?? [];
    } catch (e) {
      this._error = `SoC fetch failed: ${(e as Error).message}`;
    }
  }
}

declare global {
  interface HTMLElementTagNameMap {
    "ev-soc-trend": EvSocTrend;
  }
}
```

- [ ] **Step 3: Typecheck + lint**

```bash
npm run typecheck && npm run lint
```

- [ ] **Step 4: Commit + PR + merge**

```bash
git add src/components/ev-soc-trend.ts
git commit -m "feat(comp): ev-soc-trend (7d line)"
git push -u origin feat/ev-soc-trend
gh pr create --fill
gh pr checks --watch
gh pr merge --squash --delete-branch
git checkout main && git pull
```

---

## Task D6: `ev-deadline-picker` (helper dialog)

**Files:**
- Create: `src/components/ev-deadline-picker.ts`
- Branch: `feat/ev-deadline-picker`

- [ ] **Step 1: Branch**

```bash
git checkout -b feat/ev-deadline-picker
```

- [ ] **Step 2: Implement `src/components/ev-deadline-picker.ts`**

```ts
import { LitElement, css, html } from "lit";
import { customElement, property, state } from "lit/decorators.js";
import { cssVar } from "../lib/theme.js";

@customElement("ev-deadline-picker")
export class EvDeadlinePicker extends LitElement {
  @property({ type: String }) initialTime = "06:00";
  @property({ type: Boolean, reflect: true }) open = false;

  @state() private _value = "06:00";

  static styles = css`
    :host { display: contents; }
    .backdrop {
      position: fixed; inset: 0; background: rgba(0, 0, 0, 0.4);
      display: flex; align-items: center; justify-content: center; z-index: 100;
    }
    .dialog {
      background: ${cssVar("cardBg", "#fff")}; padding: 16px; border-radius: 12px;
      min-width: 240px; max-width: 90vw;
    }
    .row { display: flex; gap: 8px; margin-top: 12px; justify-content: flex-end; }
    button { background: none; border: 1px solid ${cssVar("divider", "#e5e7eb")}; padding: 6px 12px; border-radius: 8px; cursor: pointer; }
    button.primary { background: ${cssVar("primary", "#3b82f6")}; color: white; border-color: transparent; }
    input[type=time] { font-size: 1.2em; padding: 4px; }
  `;

  override willUpdate(changed: Map<string, unknown>) {
    if (changed.has("initialTime") || changed.has("open")) this._value = this.initialTime;
  }

  override render() {
    if (!this.open) return html``;
    return html`
      <div class="backdrop" @click=${this._onBackdrop}>
        <div class="dialog" @click=${(e: Event) => e.stopPropagation()}>
          <strong>Set one-off departure</strong>
          <div style="margin-top: 12px">
            <input type="time" .value=${this._value} @change=${this._onChange} />
          </div>
          <div class="row">
            <button @click=${this._cancel}>Cancel</button>
            <button class="primary" @click=${this._confirm}>Set</button>
          </div>
        </div>
      </div>
    `;
  }

  private _onChange = (e: Event) => {
    this._value = (e.target as HTMLInputElement).value;
  };

  private _onBackdrop = () => this._cancel();

  private _cancel = () => {
    this.dispatchEvent(new CustomEvent("deadline-cancel", { bubbles: true, composed: true }));
    this.open = false;
  };

  private _confirm = () => {
    this.dispatchEvent(new CustomEvent("deadline-confirm", {
      detail: { time: this._value },
      bubbles: true,
      composed: true,
    }));
    this.open = false;
  };
}

declare global {
  interface HTMLElementTagNameMap {
    "ev-deadline-picker": EvDeadlinePicker;
  }
}
```

- [ ] **Step 3: Typecheck + lint**

```bash
npm run typecheck && npm run lint
```

- [ ] **Step 4: Commit + PR + merge**

```bash
git add src/components/ev-deadline-picker.ts
git commit -m "feat(comp): ev-deadline-picker (modal time-picker dialog)"
git push -u origin feat/ev-deadline-picker
gh pr create --fill
gh pr checks --watch
gh pr merge --squash --delete-branch
git checkout main && git pull
```

---

## Task D7: `ev-actions`

**Files:**
- Create: `src/components/ev-actions.ts`
- Branch: `feat/ev-actions`

- [ ] **Step 1: Branch**

```bash
git checkout -b feat/ev-actions
```

- [ ] **Step 2: Implement `src/components/ev-actions.ts`**

```ts
import { LitElement, css, html } from "lit";
import { customElement, property, state } from "lit/decorators.js";
import { cssVar } from "../lib/theme.js";
import "./ev-deadline-picker.js";
import type { DeviceEntities, HomeAssistant } from "../types.js";

@customElement("ev-actions")
export class EvActions extends LitElement {
  @property({ attribute: false }) hass!: HomeAssistant;
  @property({ attribute: false }) entities!: DeviceEntities;
  @property({ type: String }) helperEntity = "";

  @state() private _deadlineOpen = false;

  static styles = css`
    :host { display: block; }
    .tile { background: ${cssVar("cardBg", "#fff")}; border-radius: 12px; padding: 12px; display: flex; gap: 8px; flex-wrap: wrap; justify-content: space-around; }
    button { background: none; border: 1px solid ${cssVar("divider", "#e5e7eb")}; padding: 8px 12px; border-radius: 8px; cursor: pointer; font-size: 0.9em; }
    button:hover { background: ${cssVar("primary", "#3b82f6")}; color: white; border-color: transparent; }
  `;

  override render() {
    const initial = this.hass.states[this.entities.effectiveDeparture]?.state ?? "06:00";
    return html`
      <div class="tile">
        <button @click=${this._replan}>Replan</button>
        <button @click=${this._force}>Force charge (2h)</button>
        <button @click=${this._skip}>Skip 1h</button>
        <button @click=${this._openDeadline}>Set deadline</button>
        <button @click=${this._clearOverride}>Clear override</button>
      </div>
      <ev-deadline-picker
        .initialTime=${initial}
        .open=${this._deadlineOpen}
        @deadline-confirm=${this._onDeadlineConfirm}
        @deadline-cancel=${() => (this._deadlineOpen = false)}
      ></ev-deadline-picker>
    `;
  }

  private _replan = () => this.hass.callService("smart_ev_charging", "replan", {}, this._target());
  private _force = () => this.hass.callService("smart_ev_charging", "force_charge_now", { duration: { hours: 2 } }, this._target());
  private _skip = () => {
    const until = new Date(Date.now() + 3_600_000).toISOString();
    this.hass.callService("smart_ev_charging", "skip_until", { until }, this._target());
  };
  private _clearOverride = () => this.hass.callService("smart_ev_charging", "set_one_off_departure", {}, this._target());
  private _openDeadline = () => (this._deadlineOpen = true);

  private _onDeadlineConfirm = (e: CustomEvent<{ time: string }>) => {
    const time = e.detail.time;
    if (this.helperEntity) {
      this.hass.callService("input_datetime", "set_datetime", { time }, { entity_id: this.helperEntity });
    } else {
      this.hass.callService("smart_ev_charging", "set_one_off_departure", { departure_time: time }, this._target());
    }
  };

  private _target() {
    // Service can be targeted via any entity from the device.
    return { entity_id: this.entities.planStatus };
  }
}

declare global {
  interface HTMLElementTagNameMap {
    "ev-actions": EvActions;
  }
}
```

- [ ] **Step 3: Typecheck + lint**

```bash
npm run typecheck && npm run lint
```

- [ ] **Step 4: Commit + PR + merge**

```bash
git add src/components/ev-actions.ts
git commit -m "feat(comp): ev-actions (button row + deadline dialog)"
git push -u origin feat/ev-actions
gh pr create --fill
gh pr checks --watch
gh pr merge --squash --delete-branch
git checkout main && git pull
```

---

# Phase E — Main card + editor

## Task E1: `ev-smart-charging-card.ts` (main element)

**Files:**
- Modify: `src/ev-smart-charging-card.ts`
- Branch: `feat/main-card`

- [ ] **Step 1: Branch**

```bash
git checkout -b feat/main-card
```

- [ ] **Step 2: Replace `src/ev-smart-charging-card.ts`**

```ts
import { LitElement, css, html } from "lit";
import { customElement, property, state } from "lit/decorators.js";
import { discover } from "./lib/discover.js";
import { cssVar } from "./lib/theme.js";
import type { CardConfig, DeviceEntities, HomeAssistant } from "./types.js";
import "./components/ev-status.js";
import "./components/ev-timeline.js";
import "./components/ev-window.js";
import "./components/ev-history.js";
import "./components/ev-soc-trend.js";
import "./components/ev-actions.js";

const DEFAULT_SHOW: NonNullable<CardConfig["show"]> = [
  "status", "timeline", "window", "history", "soc", "actions",
];

@customElement("ev-smart-charging-card")
export class EvSmartChargingCard extends LitElement {
  @property({ attribute: false }) hass!: HomeAssistant;
  @state() private _config?: CardConfig;
  @state() private _entities?: DeviceEntities;
  @state() private _error?: string;
  private _unsubscribe?: () => Promise<void>;

  static getStubConfig(): Partial<CardConfig> {
    return { device_id: "" };
  }

  static async getConfigElement() {
    await import("./editor.js");
    return document.createElement("ev-smart-charging-card-editor");
  }

  setConfig(config: CardConfig) {
    if (!config?.device_id) {
      throw new Error("device_id is required");
    }
    this._config = config;
    this._entities = undefined;
    this._error = undefined;
  }

  getCardSize() {
    return 6;
  }

  override connectedCallback() {
    super.connectedCallback();
    this._maybeSubscribe();
  }

  override disconnectedCallback() {
    super.disconnectedCallback();
    this._unsubscribe?.();
    this._unsubscribe = undefined;
  }

  static styles = css`
    :host { display: block; }
    .grid {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
      gap: 8px;
      padding: 8px;
    }
    .span2 { grid-column: span 2; }
    .full { grid-column: 1 / -1; }
    .error { padding: 12px; color: ${cssVar("error", "#ef4444")}; }
    @media (max-width: 600px) {
      .span2 { grid-column: span 1; }
    }
  `;

  override render() {
    if (!this._config) return html``;
    if (this.hass && !this._entities && !this._error) {
      try {
        this._entities = discover(this.hass, this._config.device_id);
        this._maybeSubscribe();
      } catch (e) {
        this._error = (e as Error).message;
      }
    }
    if (this._error || !this._entities) {
      return html`<div class="error">${this._error ?? "Loading…"}</div>`;
    }
    const show = new Set(this._config.show ?? DEFAULT_SHOW);
    return html`
      <ha-card>
        <div class="grid">
          ${show.has("status") ? html`<ev-status .hass=${this.hass} .entities=${this._entities}></ev-status>` : ""}
          ${show.has("timeline") ? html`<ev-timeline class="span2"
            .hass=${this.hass} .entities=${this._entities}
            @slot-click=${this._onSlotClick}></ev-timeline>` : ""}
          ${show.has("window") ? html`<ev-window .hass=${this.hass} .entities=${this._entities}></ev-window>` : ""}
          ${show.has("history") ? html`<ev-history .hass=${this.hass} .entities=${this._entities}
            .days=${this._config.history_days ?? 30}></ev-history>` : ""}
          ${show.has("soc") ? html`<ev-soc-trend .hass=${this.hass} .entities=${this._entities}
            .days=${this._config.soc_days ?? 7}></ev-soc-trend>` : ""}
          ${show.has("actions") ? html`<ev-actions class="full"
            .hass=${this.hass} .entities=${this._entities}
            .helperEntity=${this._config.helper_entity ?? ""}></ev-actions>` : ""}
        </div>
      </ha-card>
    `;
  }

  private async _maybeSubscribe() {
    if (this._unsubscribe || !this.hass) return;
    this._unsubscribe = await this.hass.connection.subscribeEvents(
      () => this.requestUpdate(),
      "smart_ev_charging_plan_updated",
    );
  }

  private _onSlotClick = (e: CustomEvent<{ start: string; end: string; isPlanned: boolean }>) => {
    if (!this._entities) return;
    const target = { entity_id: this._entities.planStatus };
    if (e.detail.isPlanned) {
      this.hass.callService("smart_ev_charging", "skip_until", { until: e.detail.end }, target);
    } else {
      this.hass.callService("smart_ev_charging", "force_charge_now", { duration: { hours: 1 } }, target);
    }
  };
}

// Register with HA's card picker.
(window as unknown as { customCards?: unknown[] }).customCards ||= [];
(window as unknown as { customCards: Array<Record<string, unknown>> }).customCards.push({
  type: "ev-smart-charging-card",
  name: "Smart EV Charging",
  description: "Status, plan timeline, history and actions for the Smart EV Charging integration.",
  preview: false,
});

declare global {
  interface HTMLElementTagNameMap {
    "ev-smart-charging-card": EvSmartChargingCard;
  }
}

console.info(
  "%c ev-smart-charging-card%c v0.1.0 ",
  "color:white;background:#3b82f6;font-weight:700",
  "color:#3b82f6",
);
```

- [ ] **Step 3: Build — verify bundle compiles + size budget**

```bash
npm run build
ls -la dist/ev-smart-charging-card.js
```

Expected: bundle exists, size < 150 KB. If over budget, audit imports.

- [ ] **Step 4: Typecheck + lint**

```bash
npm run typecheck && npm run lint
```

- [ ] **Step 5: Commit + PR + merge**

```bash
git add src/ev-smart-charging-card.ts
git commit -m "feat: main card element (grid layout, subscriptions, slot-click routing)"
git push -u origin feat/main-card
gh pr create --fill
gh pr checks --watch
gh pr merge --squash --delete-branch
git checkout main && git pull
```

---

## Task E2: `editor.ts` + tests

**Files:**
- Create: `src/editor.ts`
- Create: `tests/editor.test.ts`
- Branch: `feat/editor`

- [ ] **Step 1: Branch**

```bash
git checkout -b feat/editor
```

- [ ] **Step 2: Failing test**

`tests/editor.test.ts`:

```ts
import { describe, expect, it } from "vitest";
import "../src/editor.js";
import type { CardConfig } from "../src/types.js";

describe("editor", () => {
  it("emits a config-changed event with valid CardConfig", async () => {
    const el = document.createElement("ev-smart-charging-card-editor") as HTMLElement & { setConfig: (c: Partial<CardConfig>) => void };
    el.setConfig({ device_id: "abc" });
    document.body.appendChild(el);
    await (el as unknown as { updateComplete: Promise<void> }).updateComplete;

    let detail: Partial<CardConfig> | null = null;
    el.addEventListener("config-changed", (e) => {
      detail = (e as CustomEvent<{ config: Partial<CardConfig> }>).detail.config;
    });
    const nameInput = el.shadowRoot!.querySelector<HTMLInputElement>('input[name="name"]')!;
    nameInput.value = "Daily";
    nameInput.dispatchEvent(new Event("input", { bubbles: true, composed: true }));
    expect(detail).toMatchObject({ device_id: "abc", name: "Daily" });
  });
});
```

- [ ] **Step 3: Run — verify FAIL**

```bash
npm test
```

- [ ] **Step 4: Implement `src/editor.ts`** (minimal form; HA's `ha-form`
  isn't available in tests, so use plain inputs for v0.1)

```ts
import { LitElement, css, html } from "lit";
import { customElement, property, state } from "lit/decorators.js";
import type { CardConfig, ShowTile } from "./types.js";

const ALL_TILES: ShowTile[] = ["status", "timeline", "window", "history", "soc", "actions"];

@customElement("ev-smart-charging-card-editor")
export class EvSmartChargingCardEditor extends LitElement {
  @property({ attribute: false }) hass?: unknown;
  @state() private _config: Partial<CardConfig> = {};

  setConfig(config: Partial<CardConfig>) {
    this._config = { ...config };
  }

  static styles = css`
    :host { display: block; padding: 12px; }
    label { display: block; margin-top: 8px; font-size: 0.9em; }
    input[type="text"], input[type="number"], select { width: 100%; padding: 4px; margin-top: 2px; box-sizing: border-box; }
    fieldset { border: 1px solid #ddd; padding: 8px; margin-top: 8px; }
    legend { font-size: 0.85em; }
    label.inline { display: inline-flex; align-items: center; gap: 4px; margin-right: 8px; }
  `;

  override render() {
    return html`
      <label>Device ID
        <input type="text" name="device_id" .value=${this._config.device_id ?? ""}
          @input=${this._setField("device_id")} />
      </label>
      <label>Name (optional)
        <input type="text" name="name" .value=${this._config.name ?? ""}
          @input=${this._setField("name")} />
      </label>
      <label>History days (7–90)
        <input type="number" name="history_days" min="7" max="90"
          .value=${String(this._config.history_days ?? 30)}
          @input=${this._setNumber("history_days")} />
      </label>
      <label>SoC days (1–30)
        <input type="number" name="soc_days" min="1" max="30"
          .value=${String(this._config.soc_days ?? 7)}
          @input=${this._setNumber("soc_days")} />
      </label>
      <label>Helper entity (optional)
        <input type="text" name="helper_entity" .value=${this._config.helper_entity ?? ""}
          @input=${this._setField("helper_entity")} />
      </label>
      <fieldset>
        <legend>Show tiles</legend>
        ${ALL_TILES.map((t) => html`
          <label class="inline">
            <input type="checkbox" name="show_${t}"
              .checked=${(this._config.show ?? ALL_TILES).includes(t)}
              @change=${this._toggleTile(t)} /> ${t}
          </label>
        `)}
      </fieldset>
    `;
  }

  private _emit() {
    this.dispatchEvent(new CustomEvent("config-changed", { detail: { config: this._config }, bubbles: true, composed: true }));
  }

  private _setField = (key: keyof CardConfig) => (e: Event) => {
    const v = (e.target as HTMLInputElement).value;
    this._config = { ...this._config, [key]: v || undefined };
    this._emit();
  };

  private _setNumber = (key: keyof CardConfig) => (e: Event) => {
    const v = Number((e.target as HTMLInputElement).value);
    this._config = { ...this._config, [key]: Number.isFinite(v) ? v : undefined };
    this._emit();
  };

  private _toggleTile = (tile: ShowTile) => (e: Event) => {
    const checked = (e.target as HTMLInputElement).checked;
    const current = new Set(this._config.show ?? ALL_TILES);
    if (checked) current.add(tile);
    else current.delete(tile);
    this._config = { ...this._config, show: [...current] };
    this._emit();
  };
}

declare global {
  interface HTMLElementTagNameMap {
    "ev-smart-charging-card-editor": EvSmartChargingCardEditor;
  }
}
```

- [ ] **Step 5: Run — verify PASS**

```bash
npm test
```

- [ ] **Step 6: Commit + PR + merge**

```bash
git add src/editor.ts tests/editor.test.ts
git commit -m "feat(editor): GUI card editor with device_id, tiles, day ranges"
git push -u origin feat/editor
gh pr create --fill
gh pr checks --watch
gh pr merge --squash --delete-branch
git checkout main && git pull
```

---

## Task E3: i18n stub

**Files:**
- Create: `src/lang/en.json`, `src/lang/da.json`, `src/lang/index.ts`
- Branch: `feat/i18n`

- [ ] **Step 1: Branch**

```bash
git checkout -b feat/i18n
```

- [ ] **Step 2: Create `src/lang/en.json`**

```json
{
  "tiles": {
    "status": "Status",
    "timeline": "Price & plan",
    "window": "Charge window",
    "history": "History",
    "soc": "State of charge",
    "actions": "Actions"
  },
  "actions": {
    "replan": "Replan",
    "force": "Force charge",
    "skip": "Skip 1h",
    "set_deadline": "Set deadline",
    "clear_override": "Clear override"
  },
  "labels": {
    "smart_on": "Smart: ON",
    "smart_off": "Smart: OFF",
    "deadline": "Deadline",
    "one_off_active": "one-off override active",
    "no_charging_planned": "No charging planned",
    "no_price_data": "No price data yet",
    "no_soc_entity": "No SoC entity configured",
    "loading": "Loading…",
    "estimated_total": "Estimated total",
    "total": "Total",
    "sessions": "sessions"
  }
}
```

- [ ] **Step 3: Create `src/lang/da.json`**

```json
{
  "tiles": {
    "status": "Status",
    "timeline": "Pris & plan",
    "window": "Ladevindue",
    "history": "Historik",
    "soc": "Batteriniveau",
    "actions": "Handlinger"
  },
  "actions": {
    "replan": "Genplanlæg",
    "force": "Tving opladning",
    "skip": "Spring 1t over",
    "set_deadline": "Sæt afgangstid",
    "clear_override": "Ryd override"
  },
  "labels": {
    "smart_on": "Smart: TIL",
    "smart_off": "Smart: FRA",
    "deadline": "Frist",
    "one_off_active": "engangs-override aktiv",
    "no_charging_planned": "Ingen opladning planlagt",
    "no_price_data": "Ingen prisdata endnu",
    "no_soc_entity": "Ingen SoC-entitet konfigureret",
    "loading": "Indlæser…",
    "estimated_total": "Estimeret total",
    "total": "Total",
    "sessions": "sessioner"
  }
}
```

- [ ] **Step 4: Create `src/lang/index.ts`**

```ts
import en from "./en.json" with { type: "json" };
import da from "./da.json" with { type: "json" };

const TABLES: Record<string, typeof en> = { en, da };

export function t(language: string, key: string): string {
  const lang = TABLES[language] ?? en;
  return key.split(".").reduce<unknown>((acc, k) => (acc as Record<string, unknown> | undefined)?.[k], lang) as string ?? key;
}
```

- [ ] **Step 5: Typecheck + build + lint**

```bash
npm run typecheck && npm run lint && npm run build
```

Expected: clean.

- [ ] **Step 6: Commit + PR + merge**

```bash
git add src/lang/
git commit -m "feat(i18n): en + da string tables + t() helper"
git push -u origin feat/i18n
gh pr create --fill
gh pr checks --watch
gh pr merge --squash --delete-branch
git checkout main && git pull
```

Note: components currently render English literals directly. A follow-up
issue ("threadi18n strings through components") tracks the swap. v0.1
ships English-only labels in the UI but with the table infra in place.

---

# Phase F — Release

## Task F1: Release workflow + first build commit

**Files:**
- Create: `.github/workflows/release.yml`
- Modify: `dist/ev-smart-charging-card.js` (build output, committed)
- Branch: `chore/release-pipeline`

- [ ] **Step 1: Branch**

```bash
git checkout -b chore/release-pipeline
```

- [ ] **Step 2: Create `.github/workflows/release.yml`**

```yaml
name: Release

on:
  push:
    tags: ["v*"]

jobs:
  build-and-release:
    runs-on: ubuntu-latest
    permissions:
      contents: write
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with:
          node-version: "20"
          cache: "npm"
      - run: npm ci
      - run: npm test
      - run: npm run build
      - name: Create GitHub release
        uses: softprops/action-gh-release@v2
        with:
          files: dist/ev-smart-charging-card.js
          generate_release_notes: true
```

- [ ] **Step 3: Build + commit dist bundle**

```bash
npm run build
git add .github/workflows/release.yml dist/ev-smart-charging-card.js
git commit -m "chore(release): release workflow + initial dist bundle"
git push -u origin chore/release-pipeline
gh pr create --fill
gh pr checks --watch
gh pr merge --squash --delete-branch
git checkout main && git pull
```

---

## Task F2: README + integration repo cross-link + v0.1.0 tag

**Files:**
- Modify: `README.md`
- Modify (in integration repo): `README.md`
- Branch (card repo): `docs/readme-v0.1`

- [ ] **Step 1: Card-repo README — full version**

In card repo, branch + edit:

```bash
git checkout -b docs/readme-v0.1
```

Replace `README.md` with:

```markdown
# Smart EV Charging Card

A Lovelace custom card for the [Smart EV Charging](https://github.com/twarberg/ev-smart-charging) Home Assistant integration.

![status](https://github.com/twarberg/lovelace-ev-smart-charging-card/actions/workflows/ci.yml/badge.svg)

## Features

- Status pill, master toggle, SoC bar
- 24-hour price-and-plan timeline (click slots to skip / force-charge)
- Charge-window table with per-hour price and estimated total cost
- 30-day cost history with per-day session drawer
- 7-day SoC trend
- Action buttons (Replan, Force, Skip-until, Set deadline)
- Visual GUI editor — picks the integration's device from a dropdown
- Fully theme-aware (light / dark / community themes)
- en + da translations (string table in place; v0.1 ships English UI)

Requires `smart_ev_charging` integration version 0.2.0+.

## Install

### HACS (recommended)

1. HACS → Frontend → ⋮ → Custom repositories.
2. Add `https://github.com/twarberg/lovelace-ev-smart-charging-card` as Plugin.
3. Install **Smart EV Charging Card**.
4. Reload your dashboard.

### Manual

1. Download `ev-smart-charging-card.js` from the [latest release](https://github.com/twarberg/lovelace-ev-smart-charging-card/releases/latest).
2. Copy to `<config>/www/`.
3. Settings → Dashboards → ⋮ → Resources → Add `/local/ev-smart-charging-card.js` as a JavaScript Module.

## Configure

Edit a dashboard → Add Card → search "Smart EV Charging" → pick the device. The
GUI editor handles the rest.

YAML form:

```yaml
type: custom:ev-smart-charging-card
device_id: 7f3a9d2c...
name: Daily EV
history_days: 30
soc_days: 7
```

Find your `device_id` at Settings → Devices & Services → Smart EV Charging →
click the device. The URL ends in `…&device=<id>`.

## Development

```bash
npm install
npm test
npm run build
```

Bundle output at `dist/ev-smart-charging-card.js`. Symlink to your dev HA's
`<config>/www/` directory for live iteration.

## License

MIT.
```

- [ ] **Step 2: Commit + PR + merge**

```bash
git add README.md
git commit -m "docs(readme): full v0.1 README"
git push -u origin docs/readme-v0.1
gh pr create --fill
gh pr checks --watch
gh pr merge --squash --delete-branch
git checkout main && git pull
```

- [ ] **Step 3: Tag v0.1.0 + push (triggers release workflow)**

```bash
git tag -a v0.1.0 -m "v0.1.0 — first public release"
git push origin v0.1.0
gh run watch
```

Verify: a GitHub release appears with `ev-smart-charging-card.js` attached.

- [ ] **Step 4: Integration repo — recommend the card in README**

```bash
cd /home/tlw/dev/ev-smart-charging
git fetch origin master && git checkout master && git pull
git checkout -b docs/recommend-card
```

In integration repo `README.md`, find the "### Lovelace card" section
(line ~116) and replace its header paragraph with:

```markdown
### Lovelace card

The recommended way to use this integration is the companion
[Smart EV Charging Card](https://github.com/twarberg/lovelace-ev-smart-charging-card)
— a custom card with status, a 24h price/plan timeline, history,
SoC trend, and inline controls. Install it from HACS → Frontend.

The legacy built-in-cards-only recipe below still works if you'd rather
avoid a custom card.
```

Leave the rest of the section as-is.

- [ ] **Step 5: Commit + PR + merge**

```bash
git add README.md
git -c user.name=twarberg -c user.email=tim@tlw.dk commit -m "$(cat <<'EOF'
docs(README): recommend the new Smart EV Charging Card

Points users at twarberg/lovelace-ev-smart-charging-card as the primary
dashboard option; keeps the built-in-cards recipe as a fallback.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
git push -u origin docs/recommend-card
gh pr create --title "docs(README): recommend the new Smart EV Charging Card" --body "$(cat <<'EOF'
## Summary
- Adds a recommendation block pointing to the new card repo
- Keeps the built-in-cards recipe as a fallback

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
gh pr checks --watch
gh pr merge --squash --delete-branch
git checkout master && git pull
```

- [ ] **Step 6: Verify**

- Install card via HACS in dev HA instance.
- Add to a dashboard via Add Card → Smart EV Charging.
- Walk the manual E2E smoke checklist from the spec (six tiles render,
  slot click triggers `charge_now` flip, editor shows device, theme swap,
  resize to 400px).
- Open issues for anything broken.

---

## Self-Review

**Spec coverage:**

- Repo + bundle ✅ B1, B2, B4, F1
- Card config schema ✅ E1.setConfig, E2 editor
- Discovery ✅ C3, plus A1/A2 enable the discovery hints
- Data flow + history + subscriptions ✅ C4, D4, D5, E1
- Sub-components (status, timeline, window, history, soc, actions, picker) ✅ D1–D7
- Integration changes ✅ A1, A2, A3
- Testing (Vitest + manual smoke) ✅ C2–C4 + D2 + E2 + F2
- CI + release pipeline ✅ B4, F1
- Theming ✅ C5 + per-component `cssVar()`
- i18n ✅ E3

**Placeholders:** none — every code step contains the full content.

**Type consistency:** `CardConfig` defined in C1 (`src/types.ts`); used in
E1 and E2 with the same shape. `DeviceEntities` defined in C1; consumed by
all components and main card. `Session`/`DayBucket`/`PricePoint`/`StateSample`
defined in C4 and re-used by D4 and D5. `SlotClickDetail` from D2 matched
by main card `_onSlotClick` handler in E1.

---

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-05-11-lovelace-ev-card.md`. Two execution options:

**1. Subagent-Driven (recommended)** — fresh subagent per task, review between tasks, fast iteration. Important caveats:
   - Tasks B1–F2 run in a **different repo** (`twarberg/lovelace-ev-smart-charging-card`); subagents will need `cd ~/dev/lovelace-ev-smart-charging-card` (and the repo created by Task B4 step 1).
   - Tasks A1–A3 run in this repo on a feature branch + PR (memory rule: master is protected).
   - Each PR waits for CI and is merged before the next task starts; this is the workflow this repo uses already.

**2. Inline Execution** — execute tasks in this session using executing-plans, batch execution with checkpoints. Same caveats apply about working directory.

Which approach?
