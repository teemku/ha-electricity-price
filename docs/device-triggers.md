# Device triggers (`device_trigger.py`)

Registers five automation trigger types that appear in the HA automation editor under **Device → \<Electricity Price device\>**.

## Trigger types

| Type constant | Editor label | Description |
|---|---|---|
| `price_level_change` | Price level changed | Fires when the current slot's tier changes |
| `price_below` | Price below threshold | Fires when the current price drops below a value |
| `price_above` | Price above threshold | Fires when the current price rises above a value |
| `tomorrow_available` | Tomorrow prices available | Fires once when `PriceData.tomorrow_available` becomes True |
| `optimal_start` | Optimal start | Fires at the start of the cheapest window for a given duration |

## Schema

All triggers include the standard `DEVICE_TRIGGER_BASE_SCHEMA` fields (`device_id`, `domain`, `type`) plus:

| Field | Used by | Description |
|---|---|---|
| `duration` | `optimal_start` | Programme length in hours (0.25–24) |
| `window_start` | `optimal_start` | Earliest allowed start time (HH:MM string, optional) |
| `window_end` | `optimal_start` | Latest allowed end time (HH:MM string, optional) |
| `threshold` | `price_below`, `price_above` | Price limit in c/kWh |

## How triggers attach

`async_attach_trigger` is the HA entry point. It resolves the `device_id` to a `PriceCoordinator` via `_resolve_coordinator`, then delegates to one of five `_attach_*` functions:

### `_attach_price_level_change`

Adds a coordinator listener that runs on every `PriceData` update. Compares the current tier name to the previous one and fires the callback on change.

### `_attach_price_threshold` (used for both below/above)

Adds a coordinator listener. On each update, checks whether the current price is below (or above) the threshold. Fires only on the transition — i.e. when the condition was not met last update but is now.

### `_attach_tomorrow_available`

Adds a coordinator listener that fires once when `PriceData.tomorrow_available` transitions from `False` to `True`.

### `_attach_optimal_start`

Computes the optimal start time on each coordinator update (using `_find_optimal_start` from `sensor.py`). Schedules a one-shot `async_track_point_in_time` callback for that time. If the computed start time changes on the next coordinator update (because new prices arrived), the old scheduled callback is cancelled and a new one is set.

The optional `window_start` / `window_end` filter is applied by restricting the prices dict to slots within the allowed time window before passing it to `_find_optimal_start`.

## `_resolve_coordinator(hass, device_id)`

Walks the entity registry to find an entity belonging to `device_id` with `platform == DOMAIN`, retrieves its config entry, and returns `entry.runtime_data` (the `PriceCoordinator`). Returns `None` if the device has no matching entry.

## Capabilities

`async_get_trigger_capabilities` returns a `vol.Schema` with the fields relevant to the selected trigger type:

- `optimal_start` — `duration` (required), `window_start`, `window_end`
- `price_below` / `price_above` — `threshold` (required)
- Others — no extra fields
