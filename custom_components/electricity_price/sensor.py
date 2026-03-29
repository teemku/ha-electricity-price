"""Sensor entities for the Electricity Price (ENTSO-E) integration."""

from __future__ import annotations

import logging
import math
from datetime import datetime, time, timedelta, timezone

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.const import EntityCategory
from homeassistant.util import dt as dt_util

from .const import CONF_TRANSFER_FEE, CONF_VAT, DEFAULT_TRANSFER_FEE, DEFAULT_VAT, DOMAIN, INTEGRATION_NAME, VENDOR
from .coordinator import PriceCoordinator, PriceData

_LOGGER = logging.getLogger(__name__)

UNIT = "c/kWh"


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: PriceCoordinator = entry.runtime_data
    async_add_entities(
        [
            CurrentPriceSensor(coordinator, entry),
            NextHourPriceSensor(coordinator, entry),
            TodayMinSensor(coordinator, entry),
            TodayMaxSensor(coordinator, entry),
            TodayAverageSensor(coordinator, entry),
            TomorrowMinSensor(coordinator, entry),
            TomorrowMaxSensor(coordinator, entry),
            TomorrowAverageSensor(coordinator, entry),
            PriceLevelSensor(coordinator, entry),
            CheapestTimeSensor(coordinator, entry),
            VatSensor(coordinator, entry),
            TransferFeeSensor(coordinator, entry),
        ]
    )


class _PriceSensor(CoordinatorEntity[PriceCoordinator], SensorEntity):
    """Base class for all Electricity Price sensors."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: PriceCoordinator,
        entry: ConfigEntry,
        key: str,
    ) -> None:
        super().__init__(coordinator)
        self._entry = entry
        self._attr_unique_id = f"{entry.entry_id}_{key}"
        self._attr_translation_key = key

    @property
    def _data(self) -> PriceData:
        return self.coordinator.data

    @property
    def _current_key(self) -> str:
        """UTC ISO key for the current 15-minute slot."""
        return _utc_key(dt_util.utcnow())

    @property
    def device_info(self):
        return {
            "identifiers": {(DOMAIN, self._entry.entry_id)},
            "name": self._entry.title,
            "manufacturer": VENDOR.capitalize(),
            "model": INTEGRATION_NAME.replace("_", " ").title(),
        }


class CurrentPriceSensor(_PriceSensor):
    """Current 15-minute slot electricity price."""

    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_icon = "mdi:lightning-bolt"

    def __init__(self, coordinator: PriceCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry, "current_price")
        self._attr_native_unit_of_measurement = UNIT

    @property
    def native_value(self) -> float | None:
        return self._data.today_prices.get(self._current_key)

    @property
    def extra_state_attributes(self) -> dict:
        data = self._data
        current_key = self._current_key
        return {
            "today_prices": data.today_prices,
            "tomorrow_prices": data.tomorrow_prices,
            "thresholds": data.thresholds,
            "current_key": current_key,
            "today_date": data.today_date.isoformat(),
            "tomorrow_available": data.tomorrow_available,
            "unit": UNIT,
        }


class NextHourPriceSensor(_PriceSensor):
    """Price for the next 15-minute slot."""

    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_icon = "mdi:lightning-bolt-outline"

    def __init__(self, coordinator: PriceCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry, "next_hour_price")
        self._attr_native_unit_of_measurement = UNIT

    @property
    def native_value(self) -> float | None:
        next_key = _utc_key(dt_util.utcnow() + timedelta(minutes=15))
        price = self._data.today_prices.get(next_key)
        if price is not None:
            return price
        return self._data.tomorrow_prices.get(next_key)


class TodayMinSensor(_PriceSensor):
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_icon = "mdi:arrow-down-bold"

    def __init__(self, coordinator: PriceCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry, "today_min")
        self._attr_native_unit_of_measurement = UNIT

    @property
    def native_value(self) -> float | None:
        values = list(self._data.today_prices.values())
        return round(min(values), 4) if values else None


class TodayMaxSensor(_PriceSensor):
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_icon = "mdi:arrow-up-bold"

    def __init__(self, coordinator: PriceCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry, "today_max")
        self._attr_native_unit_of_measurement = UNIT

    @property
    def native_value(self) -> float | None:
        values = list(self._data.today_prices.values())
        return round(max(values), 4) if values else None


class TodayAverageSensor(_PriceSensor):
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_icon = "mdi:calculator-variant"

    def __init__(self, coordinator: PriceCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry, "today_average")
        self._attr_native_unit_of_measurement = UNIT

    @property
    def native_value(self) -> float | None:
        values = list(self._data.today_prices.values())
        return round(sum(values) / len(values), 4) if values else None


class TomorrowMinSensor(_PriceSensor):
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_icon = "mdi:arrow-down-bold"

    def __init__(self, coordinator: PriceCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry, "tomorrow_min")
        self._attr_native_unit_of_measurement = UNIT

    @property
    def native_value(self) -> float | None:
        values = list(self._data.tomorrow_prices.values())
        return round(min(values), 4) if values else None


class TomorrowMaxSensor(_PriceSensor):
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_icon = "mdi:arrow-up-bold"

    def __init__(self, coordinator: PriceCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry, "tomorrow_max")
        self._attr_native_unit_of_measurement = UNIT

    @property
    def native_value(self) -> float | None:
        values = list(self._data.tomorrow_prices.values())
        return round(max(values), 4) if values else None


class TomorrowAverageSensor(_PriceSensor):
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_icon = "mdi:calculator-variant"

    def __init__(self, coordinator: PriceCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry, "tomorrow_average")
        self._attr_native_unit_of_measurement = UNIT

    @property
    def native_value(self) -> float | None:
        values = list(self._data.tomorrow_prices.values())
        return round(sum(values) / len(values), 4) if values else None


class PriceLevelSensor(_PriceSensor):
    """Human-readable price level based on configured thresholds (e.g. 'Cheap')."""

    _attr_device_class = SensorDeviceClass.ENUM
    _attr_icon = "mdi:tag-outline"

    def __init__(self, coordinator: PriceCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry, "price_level")

    @property
    def options(self) -> list[str]:
        return [t["name"] for t in self._data.thresholds]

    @property
    def native_value(self) -> str | None:
        current = self._data.today_prices.get(self._current_key)
        if current is None:
            return None
        return _get_price_level(current, self._data.thresholds)


class CheapestTimeSensor(_PriceSensor):
    """Local time of the cheapest 15-minute slot today."""

    _attr_icon = "mdi:clock-outline"
    _attr_device_class = SensorDeviceClass.TIMESTAMP

    def __init__(self, coordinator: PriceCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry, "cheapest_time")

    @property
    def native_value(self):
        prices = self._data.today_prices
        if not prices:
            return None
        cheapest_key = min(prices, key=prices.__getitem__)
        from datetime import datetime, timezone
        return datetime.strptime(cheapest_key, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)


class VatSensor(_PriceSensor):
    """Current VAT percentage applied to electricity prices."""

    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = "%"
    _attr_icon = "mdi:percent"

    def __init__(self, coordinator: PriceCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry, "vat")

    @property
    def native_value(self) -> float:
        return self.coordinator.entry.options.get(CONF_VAT, DEFAULT_VAT)


class TransferFeeSensor(_PriceSensor):
    """Current transfer fee addition applied to electricity prices."""

    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = UNIT
    _attr_icon = "mdi:transmission-tower"

    def __init__(self, coordinator: PriceCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry, "transfer_fee")

    @property
    def native_value(self) -> float:
        return self.coordinator.entry.options.get(CONF_TRANSFER_FEE, DEFAULT_TRANSFER_FEE)


def _utc_key(utc_dt) -> str:
    """Round a UTC datetime down to the nearest 15-min and format as ISO string."""
    minute = (utc_dt.minute // 15) * 15
    rounded = utc_dt.replace(minute=minute, second=0, microsecond=0)
    return rounded.strftime("%Y-%m-%dT%H:%M:%SZ")


def _find_optimal_start(
    prices: dict[str, float], duration_hours: float
) -> datetime | None:
    """Return the UTC start time of the cheapest contiguous window.

    Considers only slots at or after the current 15-minute boundary so the
    result is always actionable. Returns None when fewer future slots remain
    than the requested window size.
    """
    n = math.ceil(duration_hours * 4)
    now_key = _utc_key(dt_util.utcnow())
    # ISO-8601 zero-padded strings sort lexicographically in chronological order.
    items = sorted(
        [(k, v) for k, v in prices.items() if k >= now_key],
        key=lambda x: x[0],
    )
    if len(items) < n:
        return None
    keys = [k for k, _ in items]
    values = [v for _, v in items]
    window = sum(values[:n])
    best, best_i = window, 0
    for i in range(1, len(values) - n + 1):
        window += values[i + n - 1] - values[i - 1]
        if window < best:
            best, best_i = window, i
    return datetime.strptime(keys[best_i], "%Y-%m-%dT%H:%M:%SZ").replace(
        tzinfo=timezone.utc
    )


def _get_price_level(price: float, thresholds: list[dict]) -> str:
    """Return the threshold name that the price falls into."""
    for threshold in thresholds:
        below = threshold.get("below")
        if below is None or price < below:
            return threshold["name"]
    return thresholds[-1]["name"]
