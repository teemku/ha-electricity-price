"""Config flow for the Electricity Price (ENTSO-E) integration."""

from __future__ import annotations

import json
import logging
from typing import Any

import voluptuous as vol
from homeassistant.config_entries import ConfigEntry, ConfigFlow, OptionsFlow
from homeassistant.core import callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.selector import (
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
)

from .api import EntsoEAuthError, EntsoEConnectionError, EntsoENoDataError, fetch_day_ahead_prices
from .const import (
    CONF_API_KEY,
    CONF_PRICE_AREA,
    CONF_THRESHOLDS,
    CONF_TRANSFER_FEE,
    CONF_VAT,
    DEFAULT_THRESHOLDS,
    DEFAULT_TRANSFER_FEE,
    DEFAULT_VAT,
    DOMAIN,
    PRICE_AREAS,
)

_LOGGER = logging.getLogger(__name__)

_AREA_OPTIONS = list(PRICE_AREAS.keys())

# Fallback below values used when adding a new tier that has no prior value.
_BELOW_FALLBACKS = [5.0, 12.0, 20.0, 30.0]


def _thresholds_to_str(thresholds: list[dict]) -> str:
    return json.dumps(thresholds, indent=2)


def _load_tiers(opts: dict) -> list[dict]:
    """Return the current tiers from stored options, falling back to defaults."""
    raw = opts.get(CONF_THRESHOLDS)
    if raw:
        try:
            candidate = json.loads(raw) if isinstance(raw, str) else raw
            if isinstance(candidate, list) and candidate:
                return candidate
        except (json.JSONDecodeError, ValueError):
            pass
    return list(DEFAULT_THRESHOLDS)


def _build_thresholds(user_input: dict, num_tiers: int) -> list[dict]:
    """Reconstruct the thresholds list from the flat tier form fields.

    Raises ValueError when the input is inconsistent.
    """
    tiers = []
    for i in range(1, num_tiers + 1):
        name = user_input.get(f"tier_{i}_name", "").strip()
        if not name:
            raise ValueError(f"Tier {i} name is required")
        color = user_input.get(f"tier_{i}_color", "#94a3b8")
        below = user_input.get(f"tier_{i}_below") if i < num_tiers else None
        tiers.append({"name": name, "color": color, "below": below})

    # Validate that below values are strictly increasing.
    prev = None
    for t in tiers[:-1]:
        v = t["below"]
        if v is None:
            raise ValueError(f"Tier '{t['name']}' is missing an upper limit")
        if prev is not None and v <= prev:
            raise ValueError(
                f"Tier '{t['name']}' upper limit must be greater than the previous tier"
            )
        prev = v

    return tiers


class ElectricityPriceConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle the initial setup UI."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> dict:
        errors: dict[str, str] = {}

        if user_input is not None:
            api_key = user_input[CONF_API_KEY].strip()
            area_label = user_input[CONF_PRICE_AREA]

            await self.async_set_unique_id(area_label)
            self._abort_if_unique_id_configured()

            errors = await self._validate_api(api_key, area_label)

            if not errors:
                return self.async_create_entry(
                    title=area_label,
                    data={
                        CONF_API_KEY: api_key,
                        CONF_PRICE_AREA: area_label,
                    },
                    options={
                        CONF_VAT: DEFAULT_VAT,
                        CONF_TRANSFER_FEE: DEFAULT_TRANSFER_FEE,
                        CONF_THRESHOLDS: _thresholds_to_str(DEFAULT_THRESHOLDS),
                    },
                )

        schema = vol.Schema(
            {
                vol.Required(CONF_API_KEY): TextSelector(
                    TextSelectorConfig(type=TextSelectorType.PASSWORD)
                ),
                vol.Required(CONF_PRICE_AREA): SelectSelector(
                    SelectSelectorConfig(
                        options=_AREA_OPTIONS,
                        mode=SelectSelectorMode.DROPDOWN,
                    )
                ),
            }
        )

        return self.async_show_form(
            step_id="user",
            data_schema=schema,
            errors=errors,
        )

    async def _validate_api(
        self, api_key: str, area_label: str
    ) -> dict[str, str]:
        from homeassistant.util import dt as dt_util

        area_eic = PRICE_AREAS[area_label]
        session = async_get_clientsession(self.hass)
        now = dt_util.now()

        try:
            await fetch_day_ahead_prices(session, api_key, area_eic, now.date(), now.tzinfo)
        except EntsoEAuthError:
            return {"base": "auth_failed"}
        except EntsoENoDataError:
            return {}
        except EntsoEConnectionError:
            return {"base": "cannot_connect"}

        return {}

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> dict:
        errors: dict[str, str] = {}
        entry = self._get_reconfigure_entry()

        if user_input is not None:
            api_key = user_input[CONF_API_KEY].strip()
            errors = await self._validate_api(api_key, entry.data[CONF_PRICE_AREA])
            if not errors:
                return self.async_update_reload_and_abort(
                    entry,
                    data_updates={CONF_API_KEY: api_key},
                )

        schema = vol.Schema(
            {
                vol.Required(CONF_API_KEY): TextSelector(
                    TextSelectorConfig(type=TextSelectorType.PASSWORD)
                ),
            }
        )

        return self.async_show_form(
            step_id="reconfigure",
            data_schema=schema,
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> "ElectricityPriceOptionsFlow":
        return ElectricityPriceOptionsFlow(config_entry)


class ElectricityPriceOptionsFlow(OptionsFlow):
    """Handle the options UI (reconfigure after setup)."""

    def __init__(self, config_entry: ConfigEntry) -> None:
        self._entry = config_entry
        self._vat: float = DEFAULT_VAT
        self._transfer_fee: float = DEFAULT_TRANSFER_FEE
        self._num_tiers: int = 3

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> dict:
        opts = self._entry.options

        if user_input is not None:
            self._vat = user_input[CONF_VAT]
            self._transfer_fee = user_input[CONF_TRANSFER_FEE]
            self._num_tiers = int(user_input["num_tiers"])
            return await self.async_step_tiers()

        current_tiers = _load_tiers(opts)
        current_tier_count = min(max(len(current_tiers), 2), 5)

        schema = vol.Schema(
            {
                vol.Required(
                    CONF_VAT, default=opts.get(CONF_VAT, DEFAULT_VAT)
                ): NumberSelector(
                    NumberSelectorConfig(min=0, max=100, step=0.1, mode=NumberSelectorMode.BOX)
                ),
                vol.Required(
                    CONF_TRANSFER_FEE,
                    default=opts.get(CONF_TRANSFER_FEE, DEFAULT_TRANSFER_FEE),
                ): NumberSelector(
                    NumberSelectorConfig(min=0, max=100, step=0.01, mode=NumberSelectorMode.BOX)
                ),
                vol.Required("num_tiers", default=current_tier_count): NumberSelector(
                    NumberSelectorConfig(min=2, max=5, step=1, mode=NumberSelectorMode.BOX)
                ),
            }
        )

        return self.async_show_form(step_id="init", data_schema=schema)

    async def async_step_tiers(
        self, user_input: dict[str, Any] | None = None
    ) -> dict:
        errors: dict[str, str] = {}
        opts = self._entry.options
        n = self._num_tiers

        if user_input is not None:
            try:
                thresholds = _build_thresholds(user_input, n)
            except ValueError as err:
                errors["base"] = "invalid_thresholds"
                _LOGGER.debug("Threshold validation error: %s", err)
            else:
                return self.async_create_entry(
                    data={
                        CONF_VAT: self._vat,
                        CONF_TRANSFER_FEE: self._transfer_fee,
                        CONF_THRESHOLDS: _thresholds_to_str(thresholds),
                    }
                )

        current_tiers = _load_tiers(opts)
        schema_fields: dict = {}

        for i in range(1, n + 1):
            t = current_tiers[i - 1] if i - 1 < len(current_tiers) else {}
            name_default  = t.get("name", "")
            color_default = t.get("color", "#94a3b8")
            below_default = t.get("below") if t.get("below") is not None else _BELOW_FALLBACKS[i - 1] if i - 1 < len(_BELOW_FALLBACKS) else float(i * 10)

            schema_fields[vol.Required(f"tier_{i}_name", default=name_default)] = TextSelector()
            schema_fields[vol.Required(f"tier_{i}_color", default=color_default)] = TextSelector(
                TextSelectorConfig(type=TextSelectorType.COLOR)
            )
            if i < n:
                # Last tier has no upper limit — it is the catch-all.
                schema_fields[vol.Required(f"tier_{i}_below", default=below_default)] = NumberSelector(
                    NumberSelectorConfig(min=-100, max=10000, step=0.01, mode=NumberSelectorMode.BOX)
                )

        return self.async_show_form(
            step_id="tiers",
            data_schema=vol.Schema(schema_fields),
            errors=errors,
        )
