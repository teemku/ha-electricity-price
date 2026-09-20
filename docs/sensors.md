# Sensors (`sensor.py`)

All sensors extend `_PriceSensor`, which extends `CoordinatorEntity[PriceCoordinator]`. They share a single device per config entry and update whenever the coordinator pushes new `PriceData`.

## Base class — `_PriceSensor`

Provides two shared helpers used by subclasses:

- **`_data`** — returns `coordinator.data` (`PriceData`).
- **`_current_key`** — returns the UTC ISO-8601 key for the current 15-minute slot, used to look up the active price in the `today_prices` dict.

## Sensor list

| Class | Translation key | Description |
|---|---|---|
| `CurrentPriceSensor` | `current_price` | Price for the current 15-min slot. Exposes `today_prices`, `tomorrow_prices`, `thresholds`, and `resolution_minutes` as state attributes for the dashboard card. |
| `NextPriceSensor` | `next_price` | Price for the next 15-min slot. Falls back to `tomorrow_prices` near midnight. |
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
| `ResolutionSensor` | `resolution` | Native ENTSO-E price resolution in minutes (15, 30, or 60). Updated on each live API fetch. `EntityCategory.DIAGNOSTIC`. Disabled by default. |
| `LastSuccessfulFetchSensor` | `last_successful_fetch` | Time of the last request to ENTSO-E that completed successfully, from the coordinator's `last_success`. Device class `TIMESTAMP`, `EntityCategory.DIAGNOSTIC`. Unknown until the first successful request. Always available (see below). |

### Availability during an outage

`CoordinatorEntity` reports an entity unavailable whenever the last coordinator update failed. `LastSuccessfulFetchSensor` overrides this and stays available, because the time of the last success is most useful during an outage.

## Helper functions

### `_utc_key(utc_dt)`

Rounds a UTC datetime down to the nearest 15-minute boundary and formats it as `"YYYY-MM-DDTHH:MM:SSZ"`. Used to look up the current slot in price dicts.

### `_find_optimal_start(prices, duration_hours)`

Finds the cheapest contiguous window of `duration_hours` in the given price dict, considering only future slots (≥ current 15-min boundary). Uses a sliding-window sum over the sorted slot list. Returns the UTC `datetime` of the window start, or `None` if there are not enough future slots.

Used by the `optimal_start` device trigger.

### `_get_price_level(price, thresholds)`

Returns the tier name for a given price by walking the threshold list and returning the first tier whose `below` value exceeds the price. The last tier (no `below` limit) always matches.

## Binary sensors (`binary_sensor.py`)

A separate platform with its own base class, `_PriceBinarySensor`, which also extends `CoordinatorEntity[PriceCoordinator]` and shares the same device. Both sensors use `EntityCategory.DIAGNOSTIC`.

| Class | Translation key | Description |
|---|---|---|
| `FetchFailingBinarySensor` | `fetch_failing` | On while fetching today's or tomorrow's prices is failing, from `PriceCoordinator.fetch_errors`. Device class `PROBLEM`. Attributes `scope` (`today` or `tomorrow`) and `error` (the error text) describe the most recently recorded failure and are `None` while off. Always available. |
| `TomorrowAvailableBinarySensor` | `tomorrow_available` | On while `PriceData.tomorrow_available` is true, the same rule the `tomorrow_available` device trigger uses. Turns off at the change of day until the next day's prices are fetched. |

`FetchFailingBinarySensor` overrides availability like `LastSuccessfulFetchSensor` does. `TomorrowAvailableBinarySensor` keeps the default, so it becomes unavailable together with the price sensors after a failed update: it describes the price data, which is stale at that point.

The error text is an attribute and not a state, because Home Assistant does not store a state longer than 255 characters.
