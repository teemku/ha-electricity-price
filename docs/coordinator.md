# Coordinator (`coordinator.py`)

## `PriceData`

Immutable snapshot of prices for a single calendar day. All values are in **c/kWh** with VAT and transfer fee applied.

| Field | Type | Description |
|---|---|---|
| `today_prices` | `dict[str, float]` | UTC ISO-8601 slot → final price |
| `tomorrow_prices` | `dict[str, float]` | Same for tomorrow; empty `{}` until published |
| `today_date` | `date` | The local calendar date these prices belong to |
| `thresholds` | `list[dict]` | Active price tiers (name, color, below) |

Price keys are rounded to 15-minute boundaries, e.g. `"2026-03-31T10:00:00Z"`.

### `tomorrow_available`

`True` when `tomorrow_prices` contains at least 88 slots. 88 is the minimum for a full day — DST spring-forward days have 92 slots (23 h × 4), standard days 96. Used by device triggers to determine whether all tomorrow data is ready.

---

## `PriceCoordinator`

Extends `DataUpdateCoordinator[PriceData]`. One instance per config entry.

### Update schedule

| Trigger | What happens |
|---|---|
| Hourly (`UPDATE_INTERVAL = 1 h`) | Full `_async_update_data` run — loads from cache or fetches from API |
| Every 15 min (`async_track_utc_time_change`) | `_handle_slot_boundary` — pushes the existing `PriceData` to all listeners so sensors update at slot boundaries without an API call. If tomorrow prices are missing and local hour ≥ 13, requests a full refresh instead. |

### `_async_update_data`

Fetch priority for each day:

1. **On-disk store** — if `today_date` matches and slot count ≥ 88, use stored raw prices.
2. **In-memory cache** (`_raw_tomorrow`) — for tomorrow only, if it's already complete and the date hasn't rolled over.
3. **ENTSO-E API** — falls back to a live fetch.

After fetching, raw prices (EUR/MWh ÷ 10, no VAT/fee) are stored to both `_raw_today`/`_raw_tomorrow` and the on-disk store. Final prices are computed by `_apply_pricing`.

### `async_update_vat_fee(vat, transfer_fee)`

Recomputes `PriceData` from the in-memory raw prices with the new VAT/fee values and pushes it immediately to all listeners — no API call, no reload. Sets `_pricing_update_in_progress = True` before writing to entry options so the options-change listener skips the normal full reload.

### On-disk storage

Managed by `_Store` (a `homeassistant.helpers.storage.Store` subclass). Stores a dict:

```json
{
  "today_date": "2026-03-31",
  "today_prices": { "2026-03-30T22:00:00Z": 1.2345, ... },
  "tomorrow_prices": { "2026-03-31T22:00:00Z": 0.9876, ... }
}
```

`_Store._async_migrate_func` returns `None` for older schema versions (1 and 2), causing HA to treat the file as empty and triggering a fresh API fetch. This was needed because versions 1–2 stored final prices (VAT already applied) which could not be reused after the schema change.

### Pricing formula

```
final_price = base_price × (1 + vat / 100) + transfer_fee
```

Where `base_price` is EUR/MWh ÷ 10 (i.e. c/kWh before VAT and fee).
