# API Client (`api.py`)

Thin async wrapper around the [ENTSO-E Transparency Platform REST API](https://transparency.entsoe.eu/content/static_content/Static%20content/web%20api/Guide.html). Only day-ahead (A44) prices are used.

## `fetch_day_ahead_prices(session, api_key, area_eic, date, timezone)`

Fetches all 15-minute price slots for a single local calendar day.

| Parameter | Type | Description |
|---|---|---|
| `session` | `aiohttp.ClientSession` | Shared HA HTTP session |
| `api_key` | `str` | ENTSO-E security token |
| `area_eic` | `str` | Bidding zone EIC code (e.g. `10YFI-1--------U`) |
| `date` | `datetime.date` | The local calendar date to fetch |
| `timezone` | `datetime.tzinfo` | The HA configured timezone (used to define midnight) |

**Returns** `dict[str, float]` — UTC ISO-8601 slot keys → price in EUR/MWh.

**Raises**

| Exception | When |
|---|---|
| `EntsoEAuthError` | HTTP 401 — invalid or expired API key |
| `EntsoEConnectionError` | Network error or unexpected HTTP status |
| `EntsoENoDataError` | ENTSO-E returned an Acknowledgement (no data for the requested period) |

### Period calculation

The local calendar date is converted to a UTC range `[utc_start, utc_end)`. The actual API request window is expanded by **−25 h** at the start and **+2 h** at the end. This guarantees that the CET-aligned ENTSO-E period covering the first hours of the local day (which may start before CET midnight) is included in the response regardless of the HA timezone offset.

The parser then filters strictly to slots within `[local_midnight, local_midnight + 1 day)`.

## `_parse_xml(xml_text, timezone, local_midnight)`

Parses the ENTSO-E Publication_MarketDocument XML response.

- Supports PT15M, PT30M, and PT60M resolutions. Coarser resolutions are expanded into 15-minute sub-slots, each inheriting the parent price.
- If multiple TimeSeries cover the same slot (rare), their prices are averaged.
- Slots outside the requested local calendar day are discarded.
- Returns an empty-dict error (`EntsoENoDataError`) if the response contains an Acknowledgement document or if no slots fall within the local day after filtering.

## Error types

All three exception classes (`EntsoEAuthError`, `EntsoEConnectionError`, `EntsoENoDataError`) extend `Exception`. They carry a human-readable message string as the first argument.

The coordinator treats `EntsoENoDataError` for tomorrow as a soft failure (prices not yet published) and `EntsoEAuthError`/`EntsoEConnectionError` for today as hard failures that abort the update.
