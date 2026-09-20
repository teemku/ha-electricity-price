"""Number entities for the Electricity Price (ENTSO-E) integration."""

from __future__ import annotations

from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    CONF_TRANSFER_FEE,
    CONF_VAT,
    DEFAULT_TRANSFER_FEE,
    DEFAULT_VAT,
    DOMAIN,
    INTEGRATION_NAME,
    VENDOR,
)
from .coordinator import PriceCoordinator

PARALLEL_UPDATES = 0


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: PriceCoordinator = entry.runtime_data
    async_add_entities(
        [
            VatNumber(coordinator, entry),
            TransferFeeNumber(coordinator, entry),
        ]
    )


class _PricingNumber(CoordinatorEntity[PriceCoordinator], NumberEntity):  # type: ignore[misc]
    """Base class for the editable pricing settings."""

    _attr_has_entity_name = True
    _attr_entity_category = EntityCategory.CONFIG
    _attr_mode = NumberMode.BOX

    def __init__(self, coordinator: PriceCoordinator, entry: ConfigEntry, key: str) -> None:
        super().__init__(coordinator)
        self._entry = entry
        self._attr_unique_id = f"{entry.entry_id}_{key}"
        self._attr_translation_key = key

    @property
    def device_info(self) -> dict[str, object]:
        return {
            "identifiers": {(DOMAIN, self._entry.entry_id)},
            "name": self._entry.title,
            "manufacturer": VENDOR.capitalize(),
            "model": INTEGRATION_NAME.replace("_", " ").title(),
        }


class VatNumber(_PricingNumber):
    """VAT percentage applied to electricity prices."""

    _attr_native_min_value = 0
    _attr_native_max_value = 100
    _attr_native_step = 0.1
    _attr_native_unit_of_measurement = "%"

    def __init__(self, coordinator: PriceCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry, "vat")

    @property
    def native_value(self) -> float:
        return float(self.coordinator.entry.options.get(CONF_VAT, DEFAULT_VAT))

    async def async_set_native_value(self, value: float) -> None:
        transfer_fee = self.coordinator.entry.options.get(CONF_TRANSFER_FEE, DEFAULT_TRANSFER_FEE)
        await self.coordinator.async_update_vat_fee(value, transfer_fee)
        self.async_write_ha_state()


class TransferFeeNumber(_PricingNumber):
    """Transfer fee addition applied to electricity prices."""

    _attr_native_min_value = -100
    _attr_native_max_value = 100
    _attr_native_step = 0.01
    _attr_native_unit_of_measurement = "c/kWh"

    def __init__(self, coordinator: PriceCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry, "transfer_fee")

    @property
    def native_value(self) -> float:
        return float(self.coordinator.entry.options.get(CONF_TRANSFER_FEE, DEFAULT_TRANSFER_FEE))

    async def async_set_native_value(self, value: float) -> None:
        vat = self.coordinator.entry.options.get(CONF_VAT, DEFAULT_VAT)
        await self.coordinator.async_update_vat_fee(vat, value)
        self.async_write_ha_state()
