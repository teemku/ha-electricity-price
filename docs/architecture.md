# Architecture

## Overview

```
ENTSO-E API
    │
    ▼
api.py  ──────────────────────────────────────────────────────────────────
    fetch_day_ahead_prices()   Fetches XML for one calendar day, parses it
    _parse_xml()               into {utc_iso: EUR/MWh}. Raises typed errors
                               (auth, connection, no-data) so callers can
    │                          react differently.
    ▼
coordinator.py ───────────────────────────────────────────────────────────
    PriceCoordinator           DataUpdateCoordinator subclass. Runs _async_
                               update_data() hourly. Holds raw base prices
                               (no VAT/fee) in memory and on disk so pricing
                               can be recomputed without an API call.

    PriceData                  Frozen snapshot pushed to all listeners: today/
                               tomorrow prices in c/kWh, today's date, tiers.
    │
    ├──► sensor.py             12 CoordinatorEntity sensors read from PriceData.
    │
    └──► device_trigger.py     5 device trigger types attach coordinator
                               listeners that fire when their condition is met.

__init__.py ──────────────────────────────────────────────────────────────
    async_setup_entry()        Creates a PriceCoordinator per config entry,
                               registers set_vat / set_transfer_fee services
                               (guarded against duplicate registration).
    _target_entry_ids()        Maps a service call's device_id to one or more
                               config entry IDs via the entity registry.

config_flow.py ───────────────────────────────────────────────────────────
    ElectricityPriceConfigFlow   Initial setup (API key + area).
    ElectricityPriceOptionsFlow  Two-step options: pricing → tiers.

diagnostics.py ───────────────────────────────────────────────────────────
    Returns slot counts, dates, and redacted config for the HA diagnostics
    download.
```

## Data flow

1. `PriceCoordinator._async_update_data` runs hourly.
2. It loads raw prices from the on-disk store if still valid for today; otherwise fetches from ENTSO-E.
3. Raw prices (EUR/MWh ÷ 10, no VAT or fee) are stored separately from the final prices. This lets `async_update_vat_fee` instantly recompute the display values without hitting the API.
4. `PriceData` is pushed to all listeners via `async_set_updated_data`.
5. `_handle_slot_boundary` fires at every 15-minute mark to re-push the same data, keeping sensors current at slot boundaries without an extra API call. If tomorrow prices are missing and the local hour is ≥ 13, it requests a full refresh instead to catch newly published ENTSO-E data.

## Key design decisions

**Raw prices kept in memory and on disk.** VAT and transfer fee are applied at read time, not at fetch time. This means changing pricing options takes effect immediately — `async_update_vat_fee` recomputes `PriceData` from `_raw_today`/`_raw_tomorrow` and bypasses the options-change reload.

**Storage versioning.** `_Store` discards data from schema versions 1 and 2 (which stored final prices). Version 3 stores raw base prices so the integration can recompute without an API call after an options change.

**Services use a `device_id` data field, not HA's `target:` mechanism.** `target:` always shows all four selector tabs (entity, device, area, label) in the UI with no way to hide the entity tab. A plain `device` selector field provides a clean single-device picker.

**Thresholds stored as JSON in entry options.** HA's config-entry options are a flat `dict[str, Any]`. A variable-length list of tier objects can't be represented directly, so it is serialised to a JSON string under the `thresholds` key.
