# Config and options flow (`config_flow.py`)

## Setup flow — `ElectricityPriceConfigFlow`

Single step: **user**.

Collects the ENTSO-E API key (password field) and the price area (dropdown). Before creating the entry, `_validate_api` makes a live fetch for today's prices to verify the key and connectivity. `EntsoENoDataError` is treated as success — it means the key is valid but prices are not yet published.

The price area label is used as the unique ID, preventing duplicate entries for the same bidding zone.

Stored in `entry.data` (not editable after setup without reconfigure):
- `api_key`
- `price_area`

Default options are written at creation time:
- `vat_percent = 0.0`
- `transfer_fee = 0.0`
- `thresholds = <JSON of default three-tier config>`

### Reconfigure step

Allows replacing the API key without deleting and recreating the entry. The price area is not reconfigurable here — the entry would need to be removed and re-added.

---

## Options flow — `ElectricityPriceOptionsFlow`

Two steps: **init** → **tiers**.

### Step 1 — init

Collects VAT %, transfer fee, and the number of tiers (2–5). The tier count determines how many fields appear in step 2. Values are held on `self` between steps.

### Step 2 — tiers

Dynamically builds a form with `num_tiers` groups of fields:

| Field | Last tier? | Description |
|---|---|---|
| `tier_N_name` | Yes | Display name |
| `tier_N_color` | Yes | Hex colour (colour picker) |
| `tier_N_below` | No | Upper price limit (c/kWh) |

The last tier has no upper limit — it is the catch-all for any price above the previous tier's limit.

`_build_thresholds` validates that tier names are non-empty and that `below` values are strictly increasing. On error, `errors["base"] = "invalid_thresholds"` is set and the form is re-shown.

The completed options dict is stored in `entry.options`. The coordinator's options-change listener reloads the entry, applying the new settings.

---

## Helper functions

### `_thresholds_to_str(thresholds)`

Serialises the tier list to a JSON string. Thresholds are stored as a string in entry options because HA's flat `dict[str, Any]` options schema cannot hold a variable-length list of objects directly.

### `_load_tiers(opts)`

Parses the stored JSON string back to a list. Falls back to `DEFAULT_THRESHOLDS` if the value is missing, unparseable, or empty.

### `_build_thresholds(user_input, num_tiers)`

Reconstructs the thresholds list from the flat form fields (`tier_1_name`, `tier_1_color`, `tier_1_below`, …). Raises `ValueError` with a descriptive message on validation failure.
