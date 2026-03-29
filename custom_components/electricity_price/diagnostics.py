"""Diagnostics support for the Electricity Price integration."""

from __future__ import annotations

from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import CONF_API_KEY
from .coordinator import PriceCoordinator

TO_REDACT = {CONF_API_KEY}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: ConfigEntry
) -> dict[str, Any]:
    """Return diagnostics for a config entry."""
    coordinator: PriceCoordinator = entry.runtime_data
    data = coordinator.data

    return {
        "config_entry": async_redact_data(entry.as_dict(), TO_REDACT),
        "prices": {
            "today_slots": len(data.today_prices) if data else 0,
            "tomorrow_slots": len(data.tomorrow_prices) if data else 0,
            "tomorrow_available": data.tomorrow_available if data else False,
            "today_date": data.today_date.isoformat() if data else None,
        },
        "raw_prices": {
            "today_slots": len(coordinator._raw_today),
            "tomorrow_slots": len(coordinator._raw_tomorrow),
        },
    }
