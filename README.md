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

### Options

All settings can be re-opened later via **Configure** on the integration tile.
Notable options on the **Defaults** step:

- **Only charge if SoC is below (%)** — minimum-SoC gate (since v0.3.0).
  When the car's current SoC is at or above this threshold, the planner
  returns zero slots and the charger stays off, even if the existing target
  SoC hasn't been reached. Default `100` disables the gate (always plan
  toward target). Useful for skipping top-ups when the car already has
  enough charge for the day, or for capping battery cycling without
  changing the target.
- **Replan when prices update** / **Replan on every SoC change** —
  automatic replanning triggers.
- **Skip current hour if less than N minutes remain** — avoid scheduling a
  near-empty leading slot.

## What you get

| Entity | Description |
|---|---|
| `sensor.<n>_plan_status` | `ok` / `partial` / `extended` / `no_data` / `unplugged` / `disabled` |
| `sensor.<n>_planned_hours` | Count + list of planned hours in attributes |
| `sensor.<n>_slots_needed` | Hours needed to reach target SoC |
| `sensor.<n>_active_deadline` | Datetime the plan is targeting |
| `sensor.<n>_effective_departure` | `HH:MM` with `source` attribute (`car`/`helper`/`default`/`one_off`) |
| `binary_sensor.<n>_plugged_in` | `on` when the car is plugged in |
| `binary_sensor.<n>_actively_charging` | `on` when actually drawing power |
| `binary_sensor.<n>_charge_now` | Driving signal — `on` when the integration wants to charge |
| `switch.<n>_smart_charging_enabled` | Master toggle |
| `number.<n>_target_soc` | (only if no target SoC sensor) |
| `number.<n>_charge_slots_override` | (only if no SoC sensor) |
| `datetime.<n>_departure_fallback` | (only if no departure sensor) |

### Discovery attributes on `sensor.<n>_plan_status`

For downstream consumers (notably the companion Lovelace card) the plan-status
sensor also publishes the upstream entity ids and current behavior flags as
state attributes:

| Attribute | Description |
|---|---|
| `source_price_entity` | The price entity feeding the planner |
| `charger_kw` | Effective charging power configured for this device |
| `soc_entity` / `target_soc_entity` | The car's SoC + target SoC entity (if configured) |
| `min_soc_threshold` | The minimum-SoC gate ceiling, 0–100 (`100` = gate disabled) |
| `min_soc_gate_active` | `true` while SoC is known and ≥ `min_soc_threshold` |
| `override_mode` / `override_until` | `force` / `skip` and its expiry, if active |

### Per-slot energy on `sensor.<n>_planned_hours`

`hour_kwh` in the attributes is a list parallel to `hours`. The first slots
draw the full `charger_kw`; the **last slot may be partial** because the
integration stops the moment target SoC is reached. `estimated_cost` is
`Σ hour_prices[i] × hour_kwh[i]`, so it matches what the car actually bills.

## Services

- `smart_ev_charging.replan` — recalculate the plan now.
- `smart_ev_charging.force_charge_now` — charge immediately, ignoring the price
  plan, until target SoC or unplug. Optional `duration` field.
- `smart_ev_charging.skip_until` — don't charge before the given datetime.
- `smart_ev_charging.set_one_off_departure` — override the departure deadline
  for the next charge cycle only. Takes `departure_time` (HH:MM); auto-reverts
  after the targeted deadline passes. Call with no fields to clear an active
  override immediately.

## Events

The integration fires these for downstream automations:

- `smart_ev_charging_plan_updated` — every replan.
- `smart_ev_charging_started` / `smart_ev_charging_stopped` — when `charge_now` flips.
  `reason` for `started` is `plan` / `force`. `reason` for `stopped` is
  `plan_end` / `target_reached` / `unplugged` / `disabled` / `skip` /
  `override_expired`.
- `smart_ev_charging_target_reached` — SoC crosses target while charging.

## Recipes

### Strømligning today + tomorrow joiner

Strømligning splits today and tomorrow into two entities. Build a single combined
sensor and point Smart EV Charging at it. Strømligning publishes `start` and
`end` as `datetime` objects, so the template normalizes them to ISO strings
(otherwise the price source can't read them after HA serializes the template
state):

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
            {% set ns = namespace(items=[]) %}
            {% for p in (today + tomorrow) %}
              {% set ns.items = ns.items + [{
                'price': p.price,
                'start': p.start.isoformat() if p.start is not string else p.start,
                'end': p.end.isoformat() if p.end is not string else p.end
              }] %}
            {% endfor %}
            {{ ns.items }}
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
          message: >
            EV plan is partial — only
            {{ state_attr('sensor.daily_planned_hours', 'hours') | length }}
            hours fit before departure.
```

### Lovelace card

The recommended way to use this integration is the companion
[Smart EV Charging Card](https://github.com/twarberg/lovelace-ev-smart-charging-card)
— a custom card with status, a 24h price/plan timeline, history,
SoC trend, and inline controls. Install it from HACS → Frontend.

The legacy built-in-cards-only recipe below still works if you'd rather
avoid a custom card.

```yaml
type: vertical-stack
title: Daily EV
cards:
  - type: entities
    entities:
      - entity: switch.daily_smart_charging_enabled
        name: Smart charging
      - entity: sensor.daily_plan_status
      - entity: sensor.daily_active_deadline
      - entity: binary_sensor.daily_charge_now
      - entity: input_datetime.ev_one_off_departure
        name: One-off departure (changes apply automatically)

  - type: markdown
    content: >-
      {% set hours = state_attr('sensor.daily_planned_hours', 'hours') or [] %}
      {% set prices = state_attr('sensor.daily_planned_hours', 'hour_prices') or [] %}
      {% set total = state_attr('sensor.daily_planned_hours', 'estimated_cost') %}
      {% set unit = state_attr('sensor.daily_planned_hours', 'cost_unit') or '' %}
      {% set dep_source = state_attr('sensor.daily_effective_departure', 'source') %}
      {% set dep_time = states('sensor.daily_effective_departure') %}

      **Departure:** {{ dep_time }}{% if dep_source == 'one_off' %} _(one-off override)_{% endif %}

      **Charge window**

      {% if hours %}
      | Time | Price/kWh |
      |---|---:|
      {% for i in range(hours | length) -%}
      | {{ as_local(hours[i] | as_datetime).strftime('%H:%M') }} | {{ "%.2f" | format(prices[i]) }} {{ unit }} |
      {% endfor %}

      **Estimated cost:** {{ "%.2f" | format(total) }} {{ unit }}
      {% else %}
      _No charging planned._
      {% endif %}

  - type: horizontal-stack
    cards:
      - type: button
        name: Replan
        icon: mdi:refresh
        tap_action:
          action: call-service
          service: smart_ev_charging.replan
          target:
            device_id: REPLACE_WITH_DEVICE_ID
      - type: button
        name: Force charge
        icon: mdi:flash
        tap_action:
          action: call-service
          service: smart_ev_charging.force_charge_now
          target:
            device_id: REPLACE_WITH_DEVICE_ID
      - type: button
        name: Clear override
        icon: mdi:close-circle-outline
        tap_action:
          action: call-service
          service: smart_ev_charging.set_one_off_departure
          target:
            device_id: REPLACE_WITH_DEVICE_ID
          data: {}
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
- **Plan doesn't refresh when tomorrow's prices arrive** — the integration
  has a 30-minute heartbeat that covers this. If your price sensor publishes
  via attribute mutation rather than entity-state change, the heartbeat is
  what'll pick it up.

## Development

```bash
pip install -e ".[dev]"
ruff check .
mypy --strict custom_components tests
pytest --cov --cov-report=term-missing
```

## License

MIT.
