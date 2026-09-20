---
title: "VAT and transfer fee number entities"
date: 2026-09-20
type: feat
area: entities
status: draft
refs: []
---

## Background

The VAT percentage and the transfer fee addition are the two pricing settings a
user is most likely to change after setup — a VAT rate change, a new grid
contract, a move to a different transfer tariff. Both are already adjustable in
two ways: through the options flow, and through the `set_vat` and
`set_transfer_fee` services that automations target by device.

The device page is the one place a user naturally goes to look at the
integration, and there both values appear as read-only diagnostic sensors. To
change either one the user has to leave the page for the options flow, or hand-
build a service call. The setting is visible where it cannot be edited, and
editable only where it is not visible.

Adding editable controls to the device page closes that gap. It also gives
automations a second, more idiomatic path — `number.set_value` — without taking
the existing services away.

## Current behavior

The VAT percentage and transfer fee are stored in `entry.options` under
`vat_percent` and `transfer_fee`. Three things read or write them:

- The options flow writes both, which triggers a full config entry reload.
- The `set_vat` and `set_transfer_fee` services each take a required `device_id`
  and the new value, resolve the device to its config entries, read the sibling
  value out of `entry.options`, and call
  `PriceCoordinator.async_update_vat_fee(vat, transfer_fee)`. That method
  recomputes final prices from the cached raw prices, persists both values to
  the entry options, and pushes the new data to listeners — no API fetch and no
  reload.
- Two diagnostic sensors, `VatSensor` and `TransferFeeSensor`, expose the
  current values as read-only states.

`async_update_vat_fee` returns early, before persisting anything, when both raw
price caches are empty. A value set in that window — after a restart but before
the first successful fetch, or while the API is failing — is silently discarded:
the service reports success and nothing changes.

## Expected behavior

### New number entities

A `number` platform is added, creating two entities per config entry:

| Entity | Unit | Min | Max | Step | Mode |
|---|---|---|---|---|---|
| VAT | `%` | 0 | 100 | 0.1 | box |
| Transfer fee | `c/kWh` | -100 | 100 | 0.01 | box |

The ranges and step sizes are identical to those the `set_vat` and
`set_transfer_fee` service schemas already enforce, so the same values are
accepted whichever path is used.

Both entities are assigned `EntityCategory.CONFIG`, which places them in the
Configuration section of the device page rather than among the sensors. Both
read their state from `entry.options`, falling back to the module defaults when
a key is absent.

Setting either entity reads the sibling value from `entry.options` and calls
`PriceCoordinator.async_update_vat_fee(vat, transfer_fee)` — the same method the
services call. Prices are recomputed from the cached raw prices and pushed to
all entities immediately. No API request is made and the config entry is not
reloaded.

### The existing controls are unchanged

The `set_vat` and `set_transfer_fee` services keep working exactly as they do
today, with the same names, fields and behaviour. The options flow keeps both
fields. The `VatSensor` and `TransferFeeSensor` diagnostic sensors stay in place
as read-only mirrors.

All four entities plus the options flow read the same stored values, so a change
made through any path is reflected everywhere: the coordinator notifies its
listeners after recomputing, and the options flow path reloads the entry.

### Early return fix

`async_update_vat_fee` persists the new VAT and transfer fee to the entry
options unconditionally. Only the price recomputation and the push to listeners
are skipped when both raw price caches are empty, because in that state there is
nothing to recompute. The stored values are then picked up by the next
coordinator refresh, which reads VAT and transfer fee from the options before
applying them to freshly fetched prices.

The reload suppression that `_pricing_update_in_progress` provides applies to
this path too: writing the options must not trigger a full entry reload,
regardless of whether prices were recomputed.

## Acceptance criteria

1. The device page for an Electricity Price device shows a VAT control and a
   transfer fee control in its Configuration section, each displaying the
   currently applied value.
2. Typing a new VAT percentage into the VAT control updates the current price,
   next price, today/tomorrow min, max and average, and the price level within
   one refresh of the page, without the integration reloading and without a new
   request to ENTSO-E.
3. The same holds for the transfer fee control.
4. After changing either control, the corresponding read-only diagnostic sensor
   shows the new value.
5. After changing either control, reopening the options flow shows the new value
   as the pre-filled default.
6. Calling `electricity_price.set_vat` or `electricity_price.set_transfer_fee`
   updates the matching control on the device page.
7. Changing a value through the options flow updates both the control and the
   diagnostic sensor.
8. The VAT control rejects values below 0 and above 100; the transfer fee
   control rejects values below -100 and above 100.
9. Setting VAT or the transfer fee while no price data has been fetched yet —
   for example immediately after a restart with the ENTSO-E API unreachable —
   persists the value: it survives a restart, and it is applied to prices once a
   fetch succeeds.
10. Both controls are available in English and Finnish.

## Constraints and edge cases

- The new entities must never trigger a config entry reload. Recomputing from
  the cached raw prices is the whole reason the service path exists, and the
  controls have to match it.
- The two number entities and the two diagnostic sensors coexist deliberately.
  Entity IDs do not collide because the registry scopes uniqueness per domain,
  so `{entry_id}_vat` can serve both a `sensor` and a `number` entity. The
  display names do collide — each value appears twice on the device page under
  the same label, separated only by the Configuration and Diagnostic section
  headers. This is accepted as the cost of not breaking existing references to
  the sensor entity IDs.
- Because the transfer fee is added after VAT is applied, the fee is entered
  VAT-inclusive. The control's description must say so, matching the wording the
  options flow and the service field already use.
- Both values are written together on every update: `async_update_vat_fee` takes
  both, so each entity reads its sibling's current value from the options before
  calling. A partial write would reset the other value to its default.
- Out of scope: editing the price tiers or thresholds from the device page,
  removing or deprecating the `set_vat` and `set_transfer_fee` services, any
  change to the options flow, and any change to the Lovelace card.
