"""Electricity Price (ENTSO-E) integration."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import ServiceValidationError
import homeassistant.helpers.entity_registry as er

import voluptuous as vol
from homeassistant.helpers import config_validation as cv

from .const import CONF_TRANSFER_FEE, CONF_VAT, DOMAIN, PLATFORMS
from .coordinator import PriceCoordinator

SERVICE_SET_VAT = "set_vat"
SERVICE_SET_TRANSFER_FEE = "set_transfer_fee"

_SET_VAT_SCHEMA = vol.Schema({
    vol.Required(CONF_VAT): vol.All(vol.Coerce(float), vol.Range(min=0, max=100)),
}, extra=vol.ALLOW_EXTRA)
_SET_TRANSFER_FEE_SCHEMA = vol.Schema({
    vol.Required(CONF_TRANSFER_FEE): vol.All(vol.Coerce(float), vol.Range(min=-100, max=100)),
}, extra=vol.ALLOW_EXTRA)

_LOGGER = logging.getLogger(__name__)


async def async_migrate_entry(hass: HomeAssistant, config_entry: ConfigEntry) -> bool:
    """Migrate old config entry to current version."""
    _LOGGER.debug(
        "Migrating config entry %s from version %s",
        config_entry.entry_id,
        config_entry.version,
    )
    # Version 1 is the only version — nothing to migrate yet.
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up a config entry: create coordinator and register platforms."""
    coordinator = PriceCoordinator(hass, entry)
    await coordinator.async_config_entry_first_refresh()

    entry.runtime_data = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # Reload when the user changes options so prices update immediately.
    entry.async_on_unload(entry.add_update_listener(_async_reload_entry))

    # Register services once — guard against multiple entries.
    if not hass.services.has_service(DOMAIN, SERVICE_SET_VAT):
        hass.services.async_register(
            DOMAIN, SERVICE_SET_VAT, _handle_set_vat, schema=_SET_VAT_SCHEMA
        )
    if not hass.services.has_service(DOMAIN, SERVICE_SET_TRANSFER_FEE):
        hass.services.async_register(
            DOMAIN, SERVICE_SET_TRANSFER_FEE, _handle_set_transfer_fee,
            schema=_SET_TRANSFER_FEE_SCHEMA,
        )

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        # Remove services when this is the last loaded entry for the domain.
        remaining = [
            e for e in hass.config_entries.async_entries(DOMAIN)
            if e.entry_id != entry.entry_id
        ]
        if not remaining:
            hass.services.async_remove(DOMAIN, SERVICE_SET_VAT)
            hass.services.async_remove(DOMAIN, SERVICE_SET_TRANSFER_FEE)
    return bool(unloaded)


def _target_entry_ids(hass: HomeAssistant, call: ServiceCall) -> list[str]:
    """Resolve the required device_id field to a config entry ID list."""
    device_id: str = call.data["device_id"]
    ent_reg = er.async_get(hass)
    found: set[str] = set()
    for entity_entry in ent_reg.entities.values():
        if (entity_entry.platform == DOMAIN
                and entity_entry.config_entry_id
                and entity_entry.device_id == device_id):
            found.add(entity_entry.config_entry_id)
    return list(found)


async def _handle_set_vat(call: ServiceCall) -> None:
    """Service handler: update VAT on targeted (or all) config entries."""
    vat = call.data[CONF_VAT]
    hass = call.hass
    entry_ids = _target_entry_ids(hass, call)
    if not entry_ids:
        raise ServiceValidationError("No matching Electricity Price device found")
    for entry_id in entry_ids:
        entry = hass.config_entries.async_get_entry(entry_id)
        coordinator: PriceCoordinator | None = getattr(entry, "runtime_data", None)
        if coordinator is not None:
            transfer_fee = coordinator.entry.options.get(CONF_TRANSFER_FEE, 0.0)
            await coordinator.async_update_vat_fee(vat, transfer_fee)


async def _handle_set_transfer_fee(call: ServiceCall) -> None:
    """Service handler: update transfer fee on targeted (or all) config entries."""
    fee = call.data[CONF_TRANSFER_FEE]
    hass = call.hass
    entry_ids = _target_entry_ids(hass, call)
    if not entry_ids:
        raise ServiceValidationError("No matching Electricity Price device found")
    for entry_id in entry_ids:
        entry = hass.config_entries.async_get_entry(entry_id)
        coordinator: PriceCoordinator | None = getattr(entry, "runtime_data", None)
        if coordinator is not None:
            vat = coordinator.entry.options.get(CONF_VAT, 0.0)
            await coordinator.async_update_vat_fee(vat, fee)


async def _async_reload_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload the entry when options change, unless a pricing update caused the change."""
    coordinator: PriceCoordinator = entry.runtime_data
    if coordinator._pricing_update_in_progress:
        return
    await hass.config_entries.async_reload(entry.entry_id)
