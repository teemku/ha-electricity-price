# Electricity Price

A Home Assistant custom integration that fetches day-ahead electricity prices from the [ENTSO-E Transparency Platform](https://transparency.entsoe.eu/) and exposes them as sensors and device automation triggers.

## Features

- **Real-time price sensors** — current price, next slot, today/tomorrow min/max/average, cheapest time, and price level (e.g. *Cheap*, *Normal*, *Expensive*)
- **Device automation triggers** — fire automations when the price drops below a threshold, changes tier, or the cheapest window for a given duration starts
- **VAT and transfer fee** — applied on top of the ENTSO-E base price; adjustable at runtime via services without a full reload
- **Configurable price tiers** — 2–5 named tiers with custom colours and thresholds
- **Diagnostics** — downloadable debug data from the HA diagnostics panel

## Supported price areas

Finland, Sweden (SE1–SE4), Norway (NO1–NO5), Denmark (DK1–DK2), Estonia, Latvia, Lithuania, Germany/Luxembourg, France, Netherlands, Belgium, Austria, Poland, Czech Republic, Slovakia, Hungary, Slovenia, Croatia, Romania, Bulgaria, Serbia, Portugal, Spain, Italy North, Great Britain, Switzerland, and Greece.

## Requirements

- Home Assistant 2024.1 or newer
- A free [ENTSO-E API key](https://transparency.entsoe.eu/usrm/user/createPublicUser)

## Installation

### HACS (recommended)

1. Open HACS in Home Assistant.
2. Go to **Integrations** and click the **⋮** menu → **Custom repositories**.
3. Add this repository URL and select category **Integration**.
4. Search for **Electricity Price** and click **Download**.
5. Restart Home Assistant.
6. Go to **Settings → Devices & Services → Add Integration** and search for *Electricity Price*.

### Manual

1. Copy `custom_components/electricity_price/` into your HA `config/custom_components/` directory.
2. Restart Home Assistant.
3. Go to **Settings → Devices & Services → Add Integration** and search for *Electricity Price*.

## Configuration

During setup you provide:

| Field | Description |
|---|---|
| API key | Your ENTSO-E security token |
| Price area | The bidding zone for your location (e.g. *FI - Finland*) |

After setup, open the integration's **Configure** dialog to set:

| Option | Default | Description |
|---|---|---|
| VAT % | 0 | Added on top of the base price |
| Transfer fee (c/kWh) | 0 | Fixed fee added to every slot |
| Number of tiers | 3 | How many price tiers to define (2–5) |
| Tier names, colours, limits | Cheap / Normal / Expensive | Per-tier configuration |

## Sensors

| Entity | Description |
|---|---|
| Current price | Price for the current 15-minute slot (c/kWh) |
| Next price | Price for the next 15-minute slot |
| Today min / max / average | Daily price statistics |
| Tomorrow min / max / average | Next-day statistics (available after ~13:00 CET) |
| Price level | Current tier name, e.g. *Cheap* |
| Cheapest time today | Timestamp of the cheapest slot today |
| VAT | Currently applied VAT % (diagnostic) |
| Transfer fee | Currently applied transfer fee (diagnostic) |

## Services

| Service | Description |
|---|---|
| `electricity_price.set_vat` | Update VAT without reloading the integration |
| `electricity_price.set_transfer_fee` | Update transfer fee without reloading |

Both services require a `device_id` field (the Electricity Price device) and the new numeric value.

## Documentation

| Document | Description |
|---|---|
| [User guide](docs/user-guide.md) | Setup, automation examples, troubleshooting |
| [Architecture](docs/architecture.md) | How the components fit together |
| [API client](docs/api-client.md) | ENTSO-E API wrapper details |
| [Coordinator](docs/coordinator.md) | Data fetching, caching, and pricing logic |
| [Sensors](docs/sensors.md) | All sensor entities and helper functions |
| [Device triggers](docs/device-triggers.md) | Automation trigger types |
| [Config & options flow](docs/config-flow.md) | Setup and options UI |
