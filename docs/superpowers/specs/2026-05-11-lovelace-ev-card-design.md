# Lovelace EV Smart Charging Card — Design

**Status:** draft v0.1
**Date:** 2026-05-11
**Companion to:** `2026-05-10-smart-ev-charging-design.md`
**Target repo:** `twarberg/lovelace-ev-smart-charging-card` (new, HACS Plugin)

## Context

The `twarberg/ev-smart-charging` integration ships a 4-block Lovelace recipe
built from HA's built-in cards (`vertical-stack`, `entities`, `markdown`,
buttons). It works, but the experience hits real limits:

- The markdown block can't draw a price/plan timeline.
- Per-slot click-to-skip/force isn't expressible without a `card-mod`-style
  hack and templated `tap_action.data`, which Lovelace doesn't process.
- No room for historical data (cost-this-month, past sessions, SoC trend).
- The recipe is ~70 lines of YAML the user has to paste and edit.

A purpose-built custom card replaces the recipe with a single, polished card
that exposes the same data plus history, with click-to-act on the timeline
and a GUI editor that resolves entities from a device picker. The card is
distributed as a HACS Plugin, decoupled from the integration's release
cycle so frontend iteration can move independently.

This spec covers v0.1 — feature-complete to replace the README recipe and
add the deferred "Phase 2" items from the integration spec (timeline +
history + inline controls). It does not cover later refinements (drag
handles to extend the planned window, multi-device aggregator card, energy-
dashboard integration).

## Goals

- **Replace the README recipe** with a single `type: custom:ev-smart-charging-card`.
- **Visualize 24h price curve with planned hours highlighted**, current-time
  marker, click-to-act on hour rects.
- **Surface history** — last 30 days of session cost bars, 7 days of SoC line.
- **Stay zero-config beyond `device_id`** — the editor's device picker is
  enough for the common case.
- **Be HACS-quality** — visual editor, theme variables, i18n (en + da),
  CI-validated bundle, < 150 KB.

## Non-goals

- Drag handles on the planned window (deferred).
- Multi-device "all my EVs" overview card (deferred).
- HA Energy dashboard registration (separate workstream).
- Server-side history aggregation (recorder API client-side is enough for v0.1).

## Architecture

### Repository

New public MIT-licensed repo `twarberg/lovelace-ev-smart-charging-card`.

```
.
├── src/
│   ├── ev-smart-charging-card.ts        # main custom element
│   ├── editor.ts                        # GUI card editor (getConfigElement)
│   ├── components/
│   │   ├── ev-status.ts                 # status pill + master toggle + SoC bar
│   │   ├── ev-timeline.ts               # 24h price curve + planned-slot rects
│   │   ├── ev-window.ts                 # planned-hour table + estimated cost
│   │   ├── ev-history.ts                # 30d cost bars + day drawer
│   │   ├── ev-soc-trend.ts              # 7d SoC line
│   │   ├── ev-actions.ts                # Replan/Force/Skip/Set buttons + dialogs
│   │   └── ev-deadline-picker.ts        # time picker dialog
│   ├── lib/
│   │   ├── discover.ts                  # device_id → DeviceEntities map
│   │   ├── history.ts                   # recorder API + session detection
│   │   ├── format.ts                    # currency/time/kWh formatters
│   │   └── theme.ts                     # HA CSS var helpers
│   ├── types.ts                         # CardConfig, narrowed HA types
│   └── lang/{en,da}.json
├── tests/
│   ├── discover.test.ts
│   ├── history.test.ts
│   ├── format.test.ts
│   ├── timeline.test.ts
│   └── editor.test.ts
├── dist/                                # built bundle (committed for HACS)
│   └── ev-smart-charging-card.js
├── hacs.json
├── info.md                              # HACS install page
├── package.json
├── rollup.config.mjs
├── tsconfig.json
├── .github/workflows/{ci,release}.yml
└── README.md
```

### Build

- **TypeScript** strict mode, target `ES2020`.
- **Lit 3** for components.
- **Rollup** producing a single ES module (`ev-smart-charging-card.js`) plus
  a hash-suffixed copy. Lit is bundled in. No runtime dependencies.
- **Vitest + happy-dom** for tests.
- **Size budget:** 150 KB minified. Hand-rolled SVG for timeline/bars to
  avoid pulling in a charting library.

### Distribution

- GitHub Action on tag `v*` builds, attaches `dist/ev-smart-charging-card.js`
  to the release.
- `hacs.json` declares `filename: ev-smart-charging-card.js` and `homeassistant: 2025.1`.
- HACS Plugin entry resolves to release asset.

## Card configuration

```yaml
type: custom:ev-smart-charging-card
device_id: 7f3a9d2c...               # required; only mandatory field
name: "Daily EV"                     # optional, defaults to device name
show:                                # optional; six tiles, default = all
  - status
  - timeline
  - window
  - history
  - soc
  - actions
history_days: 30                     # 7..90, default 30
soc_days: 7                          # 1..30, default 7
theme: auto                          # auto | light | dark
helper_entity: input_datetime.ev_one_off_departure
                                     # optional; if set, "Set deadline" writes
                                     # to the helper (lets the user's existing
                                     # automation handle the service call).
                                     # If omitted, card calls service directly.
language: auto                       # auto | en | da
```

The GUI editor (`getConfigElement`) renders an `ha-form` with:

- Device selector scoped to `integration: smart_ev_charging`.
- `name`, theme, language selectors.
- Multi-toggle for the six `show` tiles.
- Number sliders for `history_days` and `soc_days`.
- Optional helper entity selector (filtered to `input_datetime` domain).

## Entity discovery

The card stores `device_id` plus optional knobs from §"Card configuration".
All sibling entities are resolved at runtime from `device_id` alone.

```ts
// src/lib/discover.ts
export type DeviceEntities = {
  planStatus: string;              // sensor.<n>_plan_status
  plannedHours: string;
  slotsNeeded: string;
  activeDeadline: string;
  effectiveDeparture: string;
  pluggedIn: string;
  activelyCharging: string;
  chargeNow: string;
  smartCharging: string;
  socEntity?: string;              // from planStatus attribute
  targetSocEntity?: string;
  priceEntity?: string;
  chargerKw?: number;
};

export function discover(hass: HomeAssistant, deviceId: string): DeviceEntities;
```

Algorithm:

1. Walk `Object.values(hass.entities)`, filter by `device_id`.
2. Key by `entity_id` suffix (e.g. `plan_status`, `planned_hours`, …) since
   the integration's `unique_id` is `<entry_id>_<key>` and the HA-generated
   `entity_id` mirrors the translation key.
3. For optional source entities not in the device, read them from the
   `sensor.<n>_plan_status` attributes — see **integration changes** below.

If `device_id` resolves to a device with no Smart EV Charging entities, the
card renders a single error tile: "Device not found or not a Smart EV Charging device."

## Data flow

Lit's reactive properties handle state propagation. The main element receives
`hass` from Lovelace and forwards it (plus discovered entity ids) to each
sub-component.

```ts
@property({ attribute: false }) hass!: HomeAssistant;
@state() private _entities?: DeviceEntities;
@state() private _history?: HistoryBuckets;
@state() private _socTrend?: SocPoint[];

set hass(h: HomeAssistant) {
  this._hass = h;
  if (!this._entities) this._entities = discover(h, this.config.device_id);
}
```

### Live entity state

No explicit subscription — Lovelace re-assigns `hass` on every state change,
which triggers a Lit re-render. The diff is cheap; sub-components read only
the attributes they need from the new `hass`.

### History fetch

`history.ts` calls the recorder WebSocket API:

```ts
hass.callWS({
  type: "history/history_during_period",
  start_time: ISO,
  end_time: ISO,
  entity_ids: [chargeNow, priceEntity, socEntity],
  minimal_response: false,
  no_attributes: false,
});
```

- First fetch on initial render; cached in `@state()` fields with a 5-minute
  stale-while-revalidate window.
- Re-fetched on `smart_ev_charging_plan_updated` event (subscribed via
  `hass.connection.subscribeEvents`), unsubscribed in `disconnectedCallback`.
- Manual refresh button in `ev-actions` forces a re-fetch.
- On fetch error: cached value persists, components render a small retry
  icon. No crash.

### Session detection

From the `charge_now` history series, iterate state changes and group
contiguous `on` runs into sessions. For each session:

```ts
session.kwh = duration_hours * charger_kw
session.cost = sum_over_run(price[t] * (overlap_hours_in_t)) * charger_kw
```

Rolled up into daily buckets for `ev-history`.

## Sub-components

### `ev-status`

Title + master toggle + status pill + active deadline + SoC bar.

- Status pill colors: `ok` = `--success-color`, `partial` / `extended` =
  `--warning-color`, `no_data` / `unplugged` / `disabled` = `--secondary-text-color`.
- SoC bar: filled segment to current SoC %, faint vertical marker at target
  SoC. Hidden if `socEntity` absent.
- Master toggle calls `hass.callService("switch", "toggle", { entity_id: smartCharging })`.
- "One-off override active" badge when `effective_departure.source == "one_off"`,
  with × icon → `set_one_off_departure` with no fields (clears).

### `ev-timeline`

24h SVG band, "now" → "now + 24h".

- Y axis: price (auto-scaled to `[min, max]` of window).
- Line: price curve over the next 24h. Points derived from `priceEntity`
  attribute (the integration spec already supports any `(start, price, end)`
  schema; the card uses the same source-of-truth attribute resolved through
  discovery).
- Filled rects on planned hours (from `planned_hours.hours` attr).
- Vertical "now" marker.
- Slot click:
  - Hour ∈ planned → popover "Skip this hour" → `skip_until(until = slot_end)`.
  - Hour ∉ planned → popover "Force charge this hour" → `force_charge_now(duration = 1h)`.
  - Long-press / hover: tooltip with `HH:MM` (local) + price + unit.
- Empty state: "No price data yet" when no upstream prices.
- Emits typed `CustomEvent<{ start; end; isPlanned; price }>` for testability.

### `ev-window`

Table of planned hours.

| Time (local) | Price/kWh | Slot kWh | Cumulative |
|---|---:|---:|---:|
| 02:00 | 0.65 | 11.0 | 7.15 |
| 03:00 | 0.60 | 11.0 | 13.75 |
| 04:00 | 0.62 | 11.0 | 20.57 |

Footer: **Estimated total** + cost unit + "until 06:00" deadline reference.

Empty state: "No charging planned — already at target SoC."

### `ev-history`

30d cost-per-day bars (configurable via `history_days`).

- Header: total month + session count + avg-per-day.
- Bars use `--primary-color` faded; tallest bar gets full opacity.
- Tap a bar → drawer expands below with that day's sessions
  (`HH:MM – HH:MM · X kWh · Y DKK`).
- Range chips: 7d / 30d / 90d (re-fetches if exceeds cache window).

### `ev-soc-trend`

7d SoC line (configurable via `soc_days`).

- Y axis: SoC % (0..100, with explicit min/max ticks at observed range).
- Day markers on X axis (rotated 90° on narrow widths).
- Hidden if `socEntity` absent.

### `ev-actions`

Button row.

- **Replan** → `smart_ev_charging.replan`.
- **Force** → opens dialog with hours slider (default 2h) → `force_charge_now`.
- **Skip** → opens datetime picker → `skip_until`.
- **Set deadline** → opens time picker:
  - If `helper_entity` set: writes `input_datetime.set_datetime` so the
    user's existing automation triggers `set_one_off_departure`.
  - Otherwise: calls `set_one_off_departure` directly.
- **Refresh history** (icon-only).

## Layout

CSS Grid with `grid-template-columns: repeat(auto-fit, minmax(280px, 1fr))`.
Wide screens: 2–3 columns. Narrow: 1 column. No tabs, no breakpoint JS.

Per-tile spans:

- `ev-status`: 1 col, top.
- `ev-timeline`: 2 cols when ≥ 2 cols, 1 col otherwise.
- `ev-window`: 1 col.
- `ev-history`: 1 col.
- `ev-soc-trend`: 1 col.
- `ev-actions`: spans full width at bottom.

Each tile is a Lit `<div class="tile">` with a consistent header/body
treatment using HA CSS variables. No external theming library.

## i18n

Lit `localize` mixin loads `lang/en.json` and `lang/da.json` lazily. Picks
from `hass.locale.language`. Card config `language: en` overrides. Strings
follow the integration's translation conventions (mirrored keys where
practical).

## Integration changes (separate PR, lands first)

Three small additions to `twarberg/ev-smart-charging`. All backward-compatible.

### 1. `PlanStatusSensor.extra_state_attributes` adds discovery hints

`custom_components/smart_ev_charging/sensor.py`:

```python
return {
    "override_mode": data.override_mode,
    "override_until": data.override_until.isoformat() if data.override_until else None,
    "source_price_entity": _entry_get(self.coordinator.entry, CONF_PRICE_ENTITY),
    "charger_kw": float(_entry_get(self.coordinator.entry, CONF_CHARGER_KW, DEFAULT_CHARGER_KW)),
    "soc_entity": _entry_get(self.coordinator.entry, CONF_SOC_ENTITY),
    "target_soc_entity": _entry_get(self.coordinator.entry, CONF_TARGET_SOC_ENTITY),
}
```

`_entry_get(entry, key, default=None)` is a thin helper reading
`entry.options` falling back to `entry.data`.

### 2. `PlannedHoursSensor` adds `hour_kwh`

Same length as `hours`. Cheap (`charger_kw × 1` per slot). Card uses it
directly so cost recomputation isn't needed.

### 3. No event-payload change

The four events from the integration spec already carry everything the card
needs.

Test impact: two new assertions in `tests/test_sensor.py`; no coordinator
change.

## Testing

### Card-side (Vitest + happy-dom)

| File | Asserts |
|---|---|
| `tests/discover.test.ts` | Returns full entity map for stubbed hass; gracefully drops optionals when absent. |
| `tests/history.test.ts` | Session detection from synthetic `charge_now` series; daily roll-up sums match by-hand calculation. |
| `tests/format.test.ts` | Currency (DKK, EUR, USD) + time + kWh formatters; locale-aware. |
| `tests/timeline.test.ts` | Slot click emits typed `CustomEvent` with correct `(start, end, isPlanned, price)`. |
| `tests/editor.test.ts` | GUI editor renders, device selector + show toggles produce valid `CardConfig`. |

Coverage target: 85%+ on `lib/` and event-handler code. Lit render output is
not unit-tested (visual smoke covers it).

### Manual E2E smoke (CONTRIBUTING.md checklist)

1. Install card via HACS in a dev HA instance; add to dashboard.
2. All six tiles render against the real `Daily` device.
3. Click a planned slot → confirm `binary_sensor.charge_now` flips at that
   hour in Developer Tools → States.
4. Edit-card pane: GUI editor shows the integration's devices in the picker.
5. Toggle theme (light/dark) → colors swap, no hard-coded values.
6. Resize browser to 400px → grid collapses to single column cleanly.

## CI

`.github/workflows/ci.yml`:

- `lint` — ESLint + Prettier check.
- `typecheck` — `tsc --noEmit`.
- `test` — Vitest.
- `build` — Rollup; fail if bundle > 150 KB.
- `validate-hacs` — `hacs/action@main` with `category: plugin`.

`.github/workflows/release.yml`:

- Trigger: push tag `v*`.
- Build, attach `dist/ev-smart-charging-card.js` to GitHub release.

## Release plan

1. **Integration PR** (this repo) — adds three sensor attrs + `hour_kwh`.
   Small, fast review. Lands first so the card has stable data to read.
2. **Card repo scaffold** — bootstrap, `hacs.json`, CI.
3. **Card features** in this order:
   - T1 `discover` + `types`.
   - T2 `ev-status` (smallest, validates discovery + theming).
   - T3 `ev-timeline` (visual, validates SVG approach).
   - T4 `ev-window`.
   - T5 `ev-history` (validates recorder API path).
   - T6 `ev-soc-trend`.
   - T7 `ev-actions` + dialogs.
   - T8 `editor` + `getConfigElement`.
   - T9 i18n.
   - T10 release tooling + first `v0.1.0` tag.
4. **README update** in the integration repo to recommend the card and
   reduce the inline-YAML recipe to a "fallback" section.

## Out of scope (deferred)

- Drag handles to extend/shrink the planned window.
- Multi-device overview card.
- HA Energy dashboard integration.
- Server-side aggregator sensors (`sensor.<n>_total_cost_this_month` etc.).
  Decision deferred until v0.1 proves recorder client-path is fast enough.
- Custom price-curve display (e.g. surface-area shading for relative
  cheapness) — only line + planned rects in v0.1.
