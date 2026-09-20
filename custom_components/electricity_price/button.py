"""Button entities for the Electricity Price (ENTSO-E) integration."""

from __future__ import annotations

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, INTEGRATION_NAME, VENDOR
from .coordinator import PriceCoordinator

PARALLEL_UPDATES = 0


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: PriceCoordinator = entry.runtime_data
    async_add_entities([RetryFetchButton(coordinator, entry)])


class RetryFetchButton(CoordinatorEntity[PriceCoordinator], ButtonEntity):  # type: ignore[misc]
    """Forces a price fetch immediately, ignoring the retry backoff."""

    _attr_has_entity_name = True
    _attr_translation_key = "retry_fetch"

    def __init__(self, coordinator: PriceCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator)
        self._entry = entry
        self._attr_unique_id = f"{entry.entry_id}_retry_fetch"

    @property
    def available(self) -> bool:
        # The coordinator marks its entities unavailable after a failed update,
        # which is exactly when a retry is needed.
        return True

    @property
    def device_info(self) -> dict[str, object]:
        return {
            "identifiers": {(DOMAIN, self._entry.entry_id)},
            "name": self._entry.title,
            "manufacturer": VENDOR.capitalize(),
            "model": INTEGRATION_NAME.replace("_", " ").title(),
        }

    async def async_press(self) -> None:
        await self.coordinator.async_retry_now()
