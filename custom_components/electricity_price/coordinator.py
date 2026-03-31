"""DataUpdateCoordinator for the Electricity Price integration."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import date, timedelta

from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.event import async_track_utc_time_change
from homeassistant.helpers.storage import Store as _BaseStore
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from . import api
from .api import EntsoEAuthError, EntsoEConnectionError, EntsoENoDataError
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
    MIN_TOMORROW_SLOTS,
    PRICE_AREAS,
    SLOT_MINUTES,
)

_LOGGER = logging.getLogger(__name__)

UPDATE_INTERVAL = timedelta(hours=1)
# Version 3: storage now holds raw base prices (EUR/MWh ÷ 10, no VAT or
# transfer fee) so that pricing can be recomputed without an API fetch.
STORAGE_VERSION = 3


class _Store(_BaseStore):
    """Store subclass that discards data from older storage versions.

    Versions 1 and 2 stored prices with VAT and transfer fee already applied,
    so they cannot be reused after the schema change to raw prices.
    Returning None here causes HA to treat the stored file as empty and the
    integration re-fetches fresh data from the API.
    """

    async def _async_migrate_func(
        self,
        old_major_version: int,
        old_minor_version: int,
        old_data: dict,
    ) -> dict | None:
        return None


@dataclass
class PriceData:
    today_prices: dict[str, float]    # UTC ISO string -> c/kWh (VAT + fee applied)
    tomorrow_prices: dict[str, float] # UTC ISO string -> c/kWh; empty dict until ~13:00 CET
    today_date: date
    thresholds: list[dict] = field(default_factory=list)

    @property
    def tomorrow_available(self) -> bool:
        # DST transition days have 23 h (92 slots) or 25 h (100 slots).
        return len(self.tomorrow_prices) >= MIN_TOMORROW_SLOTS


class PriceCoordinator(DataUpdateCoordinator[PriceData]):
    """Fetches and processes ENTSO-E day-ahead electricity prices."""

    def __init__(self, hass: HomeAssistant, entry) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=UPDATE_INTERVAL,
        )
        self.entry = entry
        self._store: _Store = _Store(
            hass,
            STORAGE_VERSION,
            f"{DOMAIN}.{entry.entry_id}",
        )
        # Raw base prices (EUR/MWh ÷ 10, no VAT/fee) kept in memory so that
        # a pricing update can recompute final prices without hitting the API.
        self._raw_today: dict[str, float] = {}
        self._raw_tomorrow: dict[str, float] = {}
        # Set to True before updating entry options from async_update_vat_fee
        # so the options-change reload listener can skip the full reload.
        self._pricing_update_in_progress: bool = False

        # Push cached data to entities at exact slot boundaries without an API call.
        entry.async_on_unload(
            async_track_utc_time_change(
                hass,
                self._handle_slot_boundary,
                minute=list(range(0, 60, SLOT_MINUTES)),
                second=0,
            )
        )

    async def _handle_slot_boundary(self, now) -> None:
        """Notify all listeners at each 15-minute price slot boundary.

        Also requests a full refresh when tomorrow's prices are absent and the
        local time is past 13:00 — ENTSO-E publishes day-ahead prices around
        that time, so polling at quarter-hour intervals keeps the delay under
        15 minutes rather than up to 60 minutes.
        """
        if self.data is None:
            return

        if not self.data.tomorrow_available and dt_util.as_local(now).hour >= 13:
            await self.async_request_refresh()

        # Always push current data to entities at each slot boundary.
        # async_request_refresh only notifies listeners when data changes;
        # this call ensures sensors reflect the new 15-minute slot even when
        # the refresh returned identical data (e.g. tomorrow still unavailable).
        self.async_set_updated_data(self.data)

    async def _async_update_data(self) -> PriceData:
        options = self.entry.options
        api_key = self.entry.data[CONF_API_KEY]
        area_label = self.entry.data[CONF_PRICE_AREA]
        area_eic = PRICE_AREAS[area_label]
        vat = options.get(CONF_VAT, DEFAULT_VAT)
        transfer_fee = options.get(CONF_TRANSFER_FEE, DEFAULT_TRANSFER_FEE)
        thresholds = self._load_thresholds(options)

        now = dt_util.now()
        tz = now.tzinfo
        today = now.date()
        tomorrow = today + timedelta(days=1)

        stored = await self._load_stored(today)

        session = async_get_clientsession(self.hass)

        # ── Today's prices ────────────────────────────────────────────────────
        if stored and stored.get("today_prices") and len(stored["today_prices"]) >= 88:
            raw_today = stored["today_prices"]
            _LOGGER.debug("Using stored prices for today (%s)", today)
        else:
            try:
                fetched_today = await api.fetch_day_ahead_prices(
                    session, api_key, area_eic, today, tz
                )
            except EntsoEAuthError as err:
                raise UpdateFailed(f"Authentication failed: {err}") from err
            except (EntsoEConnectionError, EntsoENoDataError) as err:
                raise UpdateFailed(f"Could not fetch today's prices: {err}") from err
            raw_today = self._to_raw_prices(fetched_today)

        # ── Tomorrow's prices ─────────────────────────────────────────────────
        cached_raw_tomorrow = (
            self._raw_tomorrow
            if self._raw_tomorrow
            and self.data is not None
            and self.data.tomorrow_available
            and self.data.today_date == today
            else None
        )

        if stored and stored.get("tomorrow_prices") and len(stored["tomorrow_prices"]) >= 88:
            raw_tomorrow = stored["tomorrow_prices"]
            _LOGGER.debug("Using stored prices for tomorrow (%s)", tomorrow)
        elif cached_raw_tomorrow is not None:
            raw_tomorrow = cached_raw_tomorrow
        else:
            try:
                fetched_tomorrow = await api.fetch_day_ahead_prices(
                    session, api_key, area_eic, tomorrow, tz
                )
                raw_tomorrow = (
                    self._to_raw_prices(fetched_tomorrow)
                    if len(fetched_tomorrow) >= 88
                    else {}
                )
            except EntsoENoDataError:
                raw_tomorrow = {}
            except (EntsoEAuthError, EntsoEConnectionError) as err:
                _LOGGER.warning("Could not fetch tomorrow's prices: %s", err)
                raw_tomorrow = {}

        self._raw_today = raw_today
        self._raw_tomorrow = raw_tomorrow

        result = PriceData(
            today_prices=self._apply_pricing(raw_today, vat, transfer_fee),
            tomorrow_prices=self._apply_pricing(raw_tomorrow, vat, transfer_fee),
            today_date=today,
            thresholds=thresholds,
        )

        await self._save_stored()
        return result

    async def async_update_vat_fee(self, vat: float, transfer_fee: float) -> None:
        """Recompute final prices from stored raw prices with new VAT/fee settings.

        Updates all listeners immediately without an API fetch or full reload.
        Persists the new values to config entry options; the options-change
        reload listener is skipped via _pricing_update_in_progress.
        """
        if not self._raw_today and not self._raw_tomorrow:
            return

        thresholds = self.data.thresholds if self.data is not None else []
        today_date = self.data.today_date if self.data is not None else dt_util.now().date()

        new_data = PriceData(
            today_prices=self._apply_pricing(self._raw_today, vat, transfer_fee),
            tomorrow_prices=self._apply_pricing(self._raw_tomorrow, vat, transfer_fee),
            today_date=today_date,
            thresholds=thresholds,
        )

        # Flag must be set before async_update_entry because the options-change
        # listener is scheduled for the next event-loop iteration — it will
        # still be True when the listener fires. The finally block clears it
        # after both calls so an exception cannot leave it stuck as True.
        self._pricing_update_in_progress = True
        try:
            self.hass.config_entries.async_update_entry(
                self.entry,
                options={**self.entry.options, CONF_VAT: vat, CONF_TRANSFER_FEE: transfer_fee},
            )
            self.async_set_updated_data(new_data)
        finally:
            self._pricing_update_in_progress = False

    async def _load_stored(self, today: date) -> dict | None:
        """Load persisted raw price data, discarding it if it's from a different day."""
        stored = await self._store.async_load()
        if not stored:
            return None
        if stored.get("today_date") != today.isoformat():
            return None
        return stored

    async def _save_stored(self) -> None:
        """Persist today's and tomorrow's raw prices to disk."""
        await self._store.async_save(
            {
                "today_date": dt_util.now().date().isoformat(),
                "today_prices": self._raw_today,
                "tomorrow_prices": self._raw_tomorrow,
            }
        )

    @staticmethod
    def _to_raw_prices(fetched: dict[str, float]) -> dict[str, float]:
        """Convert {utc_iso: eur_per_mwh} to base {utc_iso: c/kWh} with no VAT or fee."""
        return {k: round(v / 10.0, 4) for k, v in fetched.items()}

    @staticmethod
    def _apply_pricing(
        raw_prices: dict[str, float], vat: float, transfer_fee: float
    ) -> dict[str, float]:
        """Apply VAT and transfer fee to base c/kWh prices.

        Formula: final = base * (1 + vat/100) + transfer_fee
        """
        result: dict[str, float] = {}
        for utc_key, base in raw_prices.items():
            result[utc_key] = round(base * (1 + vat / 100.0) + transfer_fee, 4)
        return result

    @staticmethod
    def _load_thresholds(options: dict) -> list[dict]:
        raw = options.get(CONF_THRESHOLDS)
        if raw is None:
            return DEFAULT_THRESHOLDS

        if isinstance(raw, str):
            try:
                parsed = json.loads(raw)
            except (json.JSONDecodeError, ValueError):
                _LOGGER.warning("Invalid thresholds JSON, using defaults")
                return DEFAULT_THRESHOLDS
        else:
            parsed = raw

        if isinstance(parsed, list) and parsed:
            return parsed

        return DEFAULT_THRESHOLDS
