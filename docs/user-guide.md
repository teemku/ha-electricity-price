# User Guide

## Table of contents

1. [Getting an ENTSO-E API key](#getting-an-entso-e-api-key)
2. [Installation](#installation)
   - [HACS (recommended)](#hacs-recommended)
   - [Manual](#manual)
3. [Setting up the integration](#setting-up-the-integration)
4. [Configuring options](#configuring-options)
5. [Automation triggers](#automation-triggers)
6. [Services](#services)
7. [Known limitations](#known-limitations)
8. [Removal](#removal)
9. [Troubleshooting](#troubleshooting)

---

## Getting an ENTSO-E API key

1. Register a free account at [transparency.entsoe.eu](https://transparency.entsoe.eu/usrm/user/createPublicUser).
2. After logging in, go to **My Account Settings → Web API Security Token**.
3. Click **Generate a new token** and copy the token — you will need it during integration setup.

The token gives read access to day-ahead price data. There is no usage cost.

---

## Installation

### HACS (recommended)

[HACS](https://hacs.xyz/) lets you install and update custom integrations directly from the Home Assistant UI.

1. Install HACS if you haven't already — follow the [HACS installation guide](https://hacs.xyz/docs/use/download/download/).
2. Open **HACS** in the Home Assistant sidebar.
3. Go to **Integrations** and click the **⋮** menu → **Custom repositories**.
4. Enter this repository's URL and select **Integration** as the category, then click **Add**.
5. Search for **Electricity Price** in HACS and click **Download**.
6. Restart Home Assistant.
7. Continue with [Setting up the integration](#setting-up-the-integration).

### Manual

1. Download or clone this repository.
2. Copy the `custom_components/electricity_price/` folder into your Home Assistant configuration directory under `custom_components/`:
   ```
   config/
   └── custom_components/
       └── electricity_price/
           ├── __init__.py
           ├── manifest.json
           └── ...
   ```
3. Restart Home Assistant.

---

## Setting up the integration

1. Go to **Settings → Devices & Services → Add Integration**.
2. Search for **Electricity Price** and select it.
3. Enter your ENTSO-E API key and choose your price area (bidding zone).
4. Click **Submit**. The integration validates the API key and creates the device.

Each price area is set up as a separate device, so you can add multiple integrations if you need prices for more than one area.

---

## Configuring options

Open **Settings → Devices & Services**, find the Electricity Price integration, and click **Configure**.

### Step 1 — Pricing

| Field | Description |
|---|---|
| VAT % | Value-added tax percentage applied to the base price. Set to 0 if your prices already include VAT or if VAT does not apply. |
| Transfer fee (c/kWh) | Fixed network transfer fee added to every price slot. |
| Number of tiers | How many price tiers to define (2–5). |

### Step 2 — Price tiers

Each tier has a name, a colour, and (except the last) an upper price limit.

| Field | Description |
|---|---|
| Name | Displayed in the *Price level* sensor (e.g. *Cheap*). |
| Colour | Hex colour associated with this tier. |
| Upper limit (c/kWh) | Prices below this value fall into this tier. Leave blank for the last tier — it catches everything above the previous limit. |

**Example — three tiers:**

| Tier | Colour | Upper limit |
|---|---|---|
| Cheap | `#22c55e` (green) | 5.0 c/kWh |
| Normal | `#f59e0b` (amber) | 12.0 c/kWh |
| Expensive | `#ef4444` (red) | *(none)* |

---

## Automation triggers

The integration registers device triggers that appear in the automation editor under **Device → \<your device\> → \<trigger type\>**.

### Price level changed

Fires whenever the current price moves from one tier to another (e.g. from *Normal* to *Cheap*). No extra configuration needed.

**Example use:** Turn on a water heater when electricity becomes cheap.

### Price below / above threshold

Fires when the current price crosses a fixed threshold (c/kWh).

| Field | Description |
|---|---|
| Threshold | The price value to watch. |

**Example use:** Send a notification when the price exceeds 20 c/kWh.

### Tomorrow prices available

Fires once per day when tomorrow's complete price data has been fetched from ENTSO-E (typically between 13:00 and 15:00 CET).

**Example use:** Recalculate a scheduled programme once tomorrow's prices are known.

### Optimal start

Fires at the beginning of the cheapest contiguous time window of a given duration. Optionally restricts the search to a time window.

| Field | Description |
|---|---|
| Duration (hours) | Length of the programme to schedule (e.g. `2` for a two-hour window). |
| Window start | Earliest allowed start time (optional, e.g. `06:00`). |
| Window end | Latest allowed end time (optional, e.g. `22:00`). |

**Example use:** Start a dishwasher at the cheapest two-hour window between 22:00 and 07:00.

---

## Services

Both services update the integration's pricing in real time — no reload or restart required.

### `electricity_price.set_vat`

Updates the VAT percentage for a device.

```yaml
service: electricity_price.set_vat
data:
  device_id: <your device id>
  vat_percent: 25.5
```

### `electricity_price.set_transfer_fee`

Updates the transfer fee for a device.

```yaml
service: electricity_price.set_transfer_fee
data:
  device_id: <your device id>
  transfer_fee: 3.72
```

The `device_id` can be found in **Settings → Devices & Services → \<your device\> → Device info**.

---

## Known limitations

- **Tomorrow prices are unavailable until ENTSO-E publishes them** — typically between 13:00 and 15:00 CET. Before that window all tomorrow sensors correctly show *Unknown*. The integration polls every 15 minutes after 13:00 local time to minimise the delay.
- **Price granularity depends on the area** — ENTSO-E may publish 15-minute, 30-minute, or 60-minute slots depending on the bidding zone. All resolutions are normalised internally to 15-minute slots.
- **Historical prices are not exposed** — only today's and tomorrow's prices are available. Past prices are not stored or surfaced as sensor state.
- **ENTSO-E API rate limits** — the free API key has undocumented rate limits. Running many integration instances for different areas from the same key may eventually be rate-limited.
- **Prices are day-ahead spot prices only** — the integration does not account for capacity tariffs, taxes beyond VAT, or any grid fees other than the flat transfer fee you configure.

---

## Removal

1. Go to **Settings → Devices & Services**.
2. Find the **Electricity Price** integration and click on it.
3. Click the **⋮** menu next to the entry and select **Delete**.
4. Restart Home Assistant.

This removes the integration entry and all its entities. A small cache file (`config/.storage/electricity_price.<entry_id>`) that holds today's raw prices is left on disk; you can safely delete it manually if needed.

---

## Troubleshooting

### Sensors show *Unavailable*

The coordinator failed to fetch today's prices. Check:
- Your ENTSO-E API key is correct. Try reconfiguring the integration (**⋮ → Reconfigure**).
- Home Assistant has outbound internet access.
- The ENTSO-E API is operational ([status page](https://transparency.entsoe.eu/)).

### Tomorrow prices stay *Unknown*

ENTSO-E publishes next-day prices between 13:00 and 15:00 CET. Before that window the sensors correctly show *Unknown*. If they remain unknown after 15:00 CET, check the HA logs for warnings from `custom_components.electricity_price`.

### Prices seem wrong

Open **Settings → Devices & Services → \<your device\> → Download diagnostics**. The file shows the number of price slots fetched for today and tomorrow, the raw slot counts, and your current VAT/fee settings — useful when reporting an issue.
