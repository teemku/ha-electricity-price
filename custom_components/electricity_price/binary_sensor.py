"""Binary sensor entities for the Electricity Price (ENTSO-E) integration."""

from __future__ import annotations

from typing import cast

from homeassistant.components.binary_sensor import BinarySensorDeviceClass, BinarySensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, INTEGRATION_NAME, VENDOR
from .coordinator import PriceCoordinator, PriceData

PARALLEL_UPDATES = 0


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: PriceCoordinator = entry.runtime_data
    async_add_entities(
        [
            FetchFailingBinarySensor(coordinator, entry),
            TomorrowAvailableBinarySensor(coordinator, entry),
        ]
    )


class _PriceBinarySensor(CoordinatorEntity[PriceCoordinator], BinarySensorEntity):  # type: ignore[misc]
    """Base class for the diagnostic binary sensors."""

    _attr_has_entity_name = True
    _attr_entity_category = EntityCategory.DIAGNOSTIC

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


class FetchFailingBinarySensor(_PriceBinarySensor):
    """On while fetching today's or tomorrow's prices from ENTSO-E is failing."""

    _attr_device_class = BinarySensorDeviceClass.PROBLEM

    def __init__(self, coordinator: PriceCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry, "fetch_failing")

    @property
    def available(self) -> bool:
        # The coordinator marks its entities unavailable after a failed update,
        # which is exactly when this value is needed.
        return True

    @property
    def is_on(self) -> bool:
        return bool(self.coordinator.fetch_errors)

    @property
    def extra_state_attributes(self) -> dict[str, str | None]:
        errors = self.coordinator.fetch_errors
        if not errors:
            return {"scope": None, "error": None}
        # Each update re-records a failing scope at the end of the mapping, so
        # the last key is the scope whose failure was recorded most recently.
        scope = list(errors)[-1]
        return {"scope": scope, "error": errors[scope]}


class TomorrowAvailableBinarySensor(_PriceBinarySensor):
    """On while a complete set of tomorrow's prices is available."""

    def __init__(self, coordinator: PriceCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry, "tomorrow_available")

    @property
    def is_on(self) -> bool:
        return cast(PriceData, self.coordinator.data).tomorrow_available
