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

## Services

- `smart_ev_charging.replan` — recalculate the plan now.
- `smart_ev_charging.force_charge_now` — charge immediately, ignoring the price
  plan, until target SoC or unplug. Optional `duration` field.
- `smart_ev_charging.skip_until` — don't charge before the given datetime.

## Events

The integration fires these for downstream automations:

- `smart_ev_charging_plan_updated` — every replan.
- `smart_ev_charging_started` / `smart_ev_charging_stopped` — when `charge_now` flips.
  `reason` is `plan` / `force` / `manual` / `plan_end` / `target_reached` /
  `unplugged` / `disabled` / `skip` / `override_expired`.
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
