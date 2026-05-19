# Contiguous charge window — design

**Status:** approved
**Date:** 2026-05-19
**Author:** brainstorm session with @tlw

## Problem

The current planner picks the `slots_needed` globally-cheapest hours within the
window before departure. The selected hours may be scattered, which causes the
charger to toggle on/off multiple times per session. Some chargers and cars
prefer one uninterrupted session (less relay wear, fewer charging-curve
warm-ups, simpler mental model for the user looking at the timeline).

## Goal

Add an option that makes the planner pick **one contiguous block of
`slots_needed` consecutive hours** with the lowest summed price, rather than N
scattered cheapest hours. Default: **on** for both new entries and existing
entries that don't carry the new key in their stored options.

Non-goals:
- No per-call override via service. Single config flag is enough for v1.
- No partial-block fallback heuristic ("take some scatter when no contiguous
  block fits"). If the window is shorter than `slots_needed` the whole window
  is returned (already contiguous by definition); status is `partial`.

## User-visible behavior

- New option on the **Defaults** step: `contiguous_block` (boolean, default
  `true`). Re-openable via **Configure**.
- `sensor.<n>_plan_status` exposes a new state attribute `contiguous_block`
  (`true` / `false`) so the companion card and any automation can branch on it.
- README updated: row in the plan-status discovery table, short paragraph in
  the **Options** section, mention in the release notes.

## Algorithm

### Inputs
- `window`: existing chronologically-sorted list of `PriceSlot` whose
  `effective_start <= s.start < deadline` (current planner already produces
  this).
- `N = max(0, slots_needed)`.

### When `contiguous = True`

```
if N == 0:
    return empty Plan with status mapping unchanged
if len(window) == 0:
    status = no_data; return empty
if len(window) < N:
    selected = window  # entire window, still contiguous
    status = "partial"
else:
    best_i = argmin over i in [0 .. len(window) - N] of
             sum(window[i:i+N].price)
    # Tie-breaker: earliest start (lowest i wins; argmin naturally does this
    # when iterated in order with strict `<`).
    selected = window[best_i : best_i + N]
    status = "extended" if was_extended else "ok"
```

`selected_starts` / `selected_prices` follow the same chronological-tuple
contract as today.

### When `contiguous = False`
Existing cheapest-N behavior, byte-for-byte.

## Code changes

### `planner.py`
- Add `contiguous: bool = True` to `PlanInput`.
- Branch inside `make_plan` after the `window` is built. Contiguous branch
  implemented as a single pass: maintain a rolling sum, track `best_i` /
  `best_sum`, update only on `current_sum < best_sum` (strict `<` preserves
  the earliest-start tie-breaker).
- Status assignment unchanged (already keyed off `window_size` vs
  `slots_needed` and `was_extended`).

### `const.py`
```python
CONF_CONTIGUOUS_BLOCK: Final = "contiguous_block"
DEFAULT_CONTIGUOUS_BLOCK: Final = True
```

### `coordinator.py`
- Read `self._merged.get(CONF_CONTIGUOUS_BLOCK, DEFAULT_CONTIGUOUS_BLOCK)`.
- Pass into `PlanInput(contiguous=...)`.
- Add `contiguous_block: bool` field to `CoordinatorData` and populate it from
  the same value (sensor reads from `CoordinatorData`, not from `_merged`,
  to stay consistent with the existing `min_soc_threshold` pattern).

### `config_flow.py`
- Add to `_DEFAULTS_SCHEMA` (initial flow) and the options-flow defaults
  schema, mirroring how `CONF_MIN_SOC_THRESHOLD` is wired:
  ```python
  vol.Optional(
      CONF_CONTIGUOUS_BLOCK, default=DEFAULT_CONTIGUOUS_BLOCK
  ): selector.BooleanSelector(),
  ```
- Options-flow uses `d(CONF_CONTIGUOUS_BLOCK, DEFAULT_CONTIGUOUS_BLOCK)`.

### `translations/en.json`, `strings.json`
- Label: "Charge in one contiguous block"
- Help: "When on, the planner picks one back-to-back block of cheap hours
  finishing before departure. When off, it picks the N cheapest scattered
  hours regardless of order."

### `sensor.py`
- `PlanStatusSensor.extra_state_attributes` adds `"contiguous_block":
  data.contiguous_block`.

### `README.md`
- New row in the **Discovery attributes on `sensor.<n>_plan_status`** table.
- Bullet in the **Options** section explaining the trade-off.

## Testing

### `tests/test_planner.py` (new cases)
- `test_contiguous_picks_cheapest_block`: 24h fixture, `slots_needed=3`,
  expect the cheapest 3-hour run (which on the existing fixture happens to be
  02-04, but with a fixture where the global cheapest 3 are NOT contiguous,
  assert that the contiguous algorithm picks the cheapest 3-in-a-row, not the
  scattered cheapest).
- `test_contiguous_tie_breaker_earliest`: build prices where two windows tie
  on sum; assert earlier window wins.
- `test_contiguous_partial_returns_whole_window`: window of length 2 with
  `slots_needed=5`; expect 2 slots returned, `status == "partial"`.
- `test_contiguous_extended_when_was_extended`: deadline within 1h triggers
  extension; the contiguous block must still come from the extended window.
- `test_contiguous_false_matches_legacy`: contiguous=False produces the same
  output as today's tests.
- Property test: a parametrized variant of `test_picker_optimality` with
  `contiguous=True` that asserts `selected_sum <= every other contiguous
  window's sum` (NOT every combination).

### Existing tests
- `test_picks_three_cheapest_overnight`: today's fixture's cheapest 3 are
  02/03/04, which are already contiguous, so the assertion still holds.
  Verify by running the suite.
- `test_picker_optimality`: pass `contiguous=False` explicitly to keep its
  global-optimum invariant.

### `tests/test_coordinator.py`
- Pass-through: set `contiguous_block: False` in entry options, assert
  the resulting `Plan` matches scatter behavior. Default omitted → contiguous.

### `tests/test_config_flow.py`
- Option appears with default `True` in the defaults schema.
- Round-trip through the options flow preserves a flipped value.

### `tests/test_sensor.py`
- `PlanStatusSensor` exposes `contiguous_block` attribute.

## Migration

No schema migration. Entries without the key fall through to
`DEFAULT_CONTIGUOUS_BLOCK = True`, which matches the user-requested
"default on".

## Backwards compatibility

A user who relied on scatter behavior (e.g. to harvest a single
extremely-cheap negative-price hour buried in an otherwise expensive day) can
flip the option off in **Configure**. No code path changes when the flag is
off — that branch is the existing implementation untouched.

## Cost trade-off (documented)

A contiguous block can be more expensive than the scattered cheapest. On
typical Danish day-ahead curves the night trough is several hours wide, so
the contiguous block and the scattered cheapest usually overlap. On unusual
days (e.g. one cheap hour at 04:00 plus another at 14:00) the contiguous
mode will pick whichever 3-hour block is cheapest in aggregate, which is
intentional.

## Out of scope

- A "soft contiguous" mode that allows up to K gaps.
- Per-service override (`smart_ev_charging.replan` with `contiguous=...`).
- Automatic fallback ("scatter if contiguous costs >X% more").

If these become needs they can extend `PlanInput` later without re-shaping
the option.
