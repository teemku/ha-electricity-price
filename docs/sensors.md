# Sensors (`sensor.py`)

All sensors extend `_PriceSensor`, which extends `CoordinatorEntity[PriceCoordinator]`. They share a single device per config entry and update whenever the coordinator pushes new `PriceData`.

## Base class — `_PriceSensor`

Provides two shared helpers used by subclasses:

- **`_data`** — returns `coordinator.data` (`PriceData`).
- **`_current_key`** — returns the UTC ISO-8601 key for the current 15-minute slot, used to look up the active price in the `today_prices` dict.

## Sensor list

| Class | Translation key | Description |
|---|---|---|
| `CurrentPriceSensor` | `current_price` | Price for the current 15-min slot. |
| `NextHourPriceSensor` | `next_hour_price` | Price for the next 15-min slot. Falls back to `tomorrow_prices` near midnight. |
| `TodayMinSensor` | `today_min` | Minimum of all today's slot prices. |
| `TodayMaxSensor` | `today_max` | Maximum of all today's slot prices. |
| `TodayAverageSensor` | `today_average` | Mean of all today's slot prices. |
| `TomorrowMinSensor` | `tomorrow_min` | Minimum of tomorrow's slot prices. Unknown until ENTSO-E publishes. |
| `TomorrowMaxSensor` | `tomorrow_max` | Maximum of tomorrow's slot prices. Unknown until ENTSO-E publishes. |
| `TomorrowAverageSensor` | `tomorrow_average` | Mean of tomorrow's slot prices. Unknown until ENTSO-E publishes. |
| `PriceLevelSensor` | `price_level` | Current tier name (e.g. *Cheap*) based on the configured thresholds. Device class `ENUM`. |
| `CheapestTimeSensor` | `cheapest_time` | UTC timestamp of the cheapest 15-min slot today. Device class `TIMESTAMP`. |
| `VatSensor` | `vat` | Currently applied VAT %. Read from entry options. `EntityCategory.DIAGNOSTIC`. |
| `TransferFeeSensor` | `transfer_fee` | Currently applied transfer fee. Read from entry options. `EntityCategory.DIAGNOSTIC`. |

## Helper functions

### `_utc_key(utc_dt)`

Rounds a UTC datetime down to the nearest 15-minute boundary and formats it as `"YYYY-MM-DDTHH:MM:SSZ"`. Used to look up the current slot in price dicts.

### `_find_optimal_start(prices, duration_hours)`

Finds the cheapest contiguous window of `duration_hours` in the given price dict, considering only future slots (≥ current 15-min boundary). Uses a sliding-window sum over the sorted slot list. Returns the UTC `datetime` of the window start, or `None` if there are not enough future slots.

Used by the `optimal_start` device trigger.

### `_get_price_level(price, thresholds)`

Returns the tier name for a given price by walking the threshold list and returning the first tier whose `below` value exceeds the price. The last tier (no `below` limit) always matches.
