"""Tests for sensor helper functions and entity native_value properties."""

import datetime
from unittest.mock import MagicMock

import pytest

import homeassistant.util.dt as dt_mock
from custom_components.electricity_price.const import DEFAULT_TRANSFER_FEE, DEFAULT_VAT
from custom_components.electricity_price.sensor import (
    CheapestTimeSensor,
    CurrentPriceSensor,
    NextPriceSensor,
    PriceLevelSensor,
    TodayAverageSensor,
    TodayMaxSensor,
    TodayMinSensor,
    TomorrowAverageSensor,
    TomorrowMaxSensor,
    TomorrowMinSensor,
    TransferFeeSensor,
    VatSensor,
    _find_optimal_start,
    _get_price_level,
    _utc_key,
)

UTC = datetime.timezone.utc


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_sensor(cls, today_prices=None, tomorrow_prices=None, thresholds=None):
    coord = MagicMock()
    coord.data.today_prices = today_prices or {}
    coord.data.tomorrow_prices = tomorrow_prices or {}
    coord.data.thresholds = thresholds or [
        {"name": "Cheap", "below": 5.0},
        {"name": "Normal", "below": 12.0},
        {"name": "Expensive", "below": None},
    ]
    entry = MagicMock()
    entry.entry_id = "test_entry"
    return cls(coord, entry)


def _make_options_sensor(cls, options=None):
    """Create a sensor whose coordinator exposes entry.options as a real dict."""
    coord = MagicMock()
    coord.entry.options = options or {}
    entry = MagicMock()
    entry.entry_id = "test_entry"
    return cls(coord, entry)


# ---------------------------------------------------------------------------
# _utc_key
# ---------------------------------------------------------------------------


class TestUtcKey:
    def test_already_on_15min_boundary(self):
        dt = datetime.datetime(2026, 3, 29, 12, 0, 0, tzinfo=UTC)
        assert _utc_key(dt) == "2026-03-29T12:00:00Z"

    def test_rounds_down_1_to_00(self):
        dt = datetime.datetime(2026, 3, 29, 12, 1, 30, tzinfo=UTC)
        assert _utc_key(dt) == "2026-03-29T12:00:00Z"

    def test_rounds_down_14_to_00(self):
        dt = datetime.datetime(2026, 3, 29, 12, 14, 59, tzinfo=UTC)
        assert _utc_key(dt) == "2026-03-29T12:00:00Z"

    def test_rounds_down_15_to_15(self):
        dt = datetime.datetime(2026, 3, 29, 12, 15, 0, tzinfo=UTC)
        assert _utc_key(dt) == "2026-03-29T12:15:00Z"

    def test_rounds_down_29_to_15(self):
        dt = datetime.datetime(2026, 3, 29, 12, 29, 59, tzinfo=UTC)
        assert _utc_key(dt) == "2026-03-29T12:15:00Z"

    def test_rounds_down_30_to_30(self):
        dt = datetime.datetime(2026, 3, 29, 12, 30, 0, tzinfo=UTC)
        assert _utc_key(dt) == "2026-03-29T12:30:00Z"

    def test_rounds_down_45_to_45(self):
        dt = datetime.datetime(2026, 3, 29, 12, 45, 0, tzinfo=UTC)
        assert _utc_key(dt) == "2026-03-29T12:45:00Z"

    def test_strips_seconds_and_microseconds(self):
        dt = datetime.datetime(2026, 3, 29, 8, 17, 42, 999999, tzinfo=UTC)
        assert _utc_key(dt) == "2026-03-29T08:15:00Z"

    def test_format_is_iso8601_with_z(self):
        key = _utc_key(datetime.datetime(2026, 1, 5, 3, 0, 0, tzinfo=UTC))
        assert key == "2026-01-05T03:00:00Z"


# ---------------------------------------------------------------------------
# _get_price_level
# ---------------------------------------------------------------------------

_THRESHOLDS = [
    {"name": "Cheap", "below": 5.0},
    {"name": "Normal", "below": 12.0},
    {"name": "Expensive", "below": None},
]


class TestGetPriceLevel:
    def test_below_first_threshold(self):
        assert _get_price_level(3.0, _THRESHOLDS) == "Cheap"

    def test_at_first_threshold_boundary(self):
        # below=5.0 means price < 5.0 is Cheap; 5.0 is Normal
        assert _get_price_level(4.99, _THRESHOLDS) == "Cheap"
        assert _get_price_level(5.0, _THRESHOLDS) == "Normal"

    def test_in_middle_tier(self):
        assert _get_price_level(8.0, _THRESHOLDS) == "Normal"

    def test_at_second_threshold_boundary(self):
        assert _get_price_level(11.99, _THRESHOLDS) == "Normal"
        assert _get_price_level(12.0, _THRESHOLDS) == "Expensive"

    def test_above_all_thresholds_returns_last(self):
        assert _get_price_level(100.0, _THRESHOLDS) == "Expensive"

    def test_negative_price_returns_first(self):
        assert _get_price_level(-5.0, _THRESHOLDS) == "Cheap"

    def test_single_tier_catch_all(self):
        tiers = [{"name": "Any", "below": None}]
        assert _get_price_level(999.0, tiers) == "Any"


# ---------------------------------------------------------------------------
# _find_optimal_start
# ---------------------------------------------------------------------------

# conftest.py pins dt_util.utcnow() to 2026-03-29T12:00:00Z.
# Slots at or after 12:00 are "future"; those before are ignored.

_PRICES = {
    # past (should be ignored)
    "2026-03-29T10:00:00Z": 1.0,
    "2026-03-29T10:15:00Z": 1.0,
    "2026-03-29T11:45:00Z": 1.0,
    # future
    "2026-03-29T12:00:00Z": 8.0,
    "2026-03-29T12:15:00Z": 6.0,
    "2026-03-29T12:30:00Z": 2.0,
    "2026-03-29T12:45:00Z": 3.0,
    "2026-03-29T13:00:00Z": 7.0,
    "2026-03-29T13:15:00Z": 9.0,
}


class TestFindOptimalStart:
    def test_returns_start_of_cheapest_window(self):
        # 30 min = n=2 slots.  Cheapest pair: [12:30, 12:45] = 2+3=5
        result = _find_optimal_start(_PRICES, 0.5)
        assert result == datetime.datetime(2026, 3, 29, 12, 30, 0, tzinfo=UTC)

    def test_ignores_past_slots(self):
        # Even though 10:00/10:15 are cheaper, they're in the past.
        result = _find_optimal_start(_PRICES, 0.5)
        assert result is not None
        assert result >= datetime.datetime(2026, 3, 29, 12, 0, 0, tzinfo=UTC)

    def test_single_slot_duration(self):
        # 15 min = n=1. Cheapest single future slot is 12:30 (price=2.0).
        result = _find_optimal_start(_PRICES, 0.25)
        assert result == datetime.datetime(2026, 3, 29, 12, 30, 0, tzinfo=UTC)

    def test_returns_none_when_insufficient_future_data(self):
        short_prices = {
            "2026-03-29T12:00:00Z": 5.0,
            "2026-03-29T12:15:00Z": 3.0,
        }
        # 1 hour = n=4, only 2 slots available
        assert _find_optimal_start(short_prices, 1.0) is None

    def test_fractional_hours_ceiling(self, monkeypatch):
        # 1.1 hours → ceil(1.1*4) = 5 slots
        result = _find_optimal_start(_PRICES, 1.1)
        # 5 slots starting at 12:00: 8+6+2+3+7=26; at 12:15: 6+2+3+7+9=27 → best is 12:00
        assert result == datetime.datetime(2026, 3, 29, 12, 0, 0, tzinfo=UTC)

    def test_selects_globally_cheapest_not_first(self):
        prices = {
            "2026-03-29T12:00:00Z": 10.0,
            "2026-03-29T12:15:00Z": 10.0,
            "2026-03-29T12:30:00Z": 1.0,
            "2026-03-29T12:45:00Z": 1.0,
            "2026-03-29T13:00:00Z": 10.0,
            "2026-03-29T13:15:00Z": 10.0,
        }
        # n=2: [12:00,12:15]=20, [12:15,12:30]=11, [12:30,12:45]=2, [12:45,13:00]=11, [13:00,13:15]=20
        result = _find_optimal_start(prices, 0.5)
        assert result == datetime.datetime(2026, 3, 29, 12, 30, 0, tzinfo=UTC)

    def test_returns_utc_aware_datetime(self):
        result = _find_optimal_start(_PRICES, 0.25)
        assert result is not None
        assert result.tzinfo == UTC

    def test_current_slot_is_eligible(self):
        # The slot exactly at utcnow (12:00) should be considered.
        prices = {"2026-03-29T12:00:00Z": 1.0, "2026-03-29T12:15:00Z": 99.0}
        result = _find_optimal_start(prices, 0.25)
        assert result == datetime.datetime(2026, 3, 29, 12, 0, 0, tzinfo=UTC)


# ---------------------------------------------------------------------------
# Sensor entity — native_value
# ---------------------------------------------------------------------------


class TestCurrentPriceSensor:
    def test_returns_price_for_current_slot(self):
        # conftest pins utcnow to 12:00 → current key = "2026-03-29T12:00:00Z"
        sensor = _make_sensor(CurrentPriceSensor,
                              today_prices={"2026-03-29T12:00:00Z": 7.5})
        assert sensor.native_value == pytest.approx(7.5)

    def test_returns_none_when_slot_missing(self):
        sensor = _make_sensor(CurrentPriceSensor, today_prices={})
        assert sensor.native_value is None

    def test_returns_none_when_prices_empty(self):
        sensor = _make_sensor(CurrentPriceSensor, today_prices={})
        assert sensor.native_value is None


class TestNextPriceSensor:
    def test_returns_price_for_next_slot(self, monkeypatch):
        # utcnow = 12:00, next slot = 12:15
        monkeypatch.setattr(dt_mock, "utcnow",
                            lambda: datetime.datetime(2026, 3, 29, 12, 0, 0, tzinfo=UTC))
        sensor = _make_sensor(NextPriceSensor,
                              today_prices={"2026-03-29T12:15:00Z": 4.2})
        assert sensor.native_value == pytest.approx(4.2)

    def test_falls_back_to_tomorrow_prices(self, monkeypatch):
        monkeypatch.setattr(dt_mock, "utcnow",
                            lambda: datetime.datetime(2026, 3, 29, 12, 0, 0, tzinfo=UTC))
        sensor = _make_sensor(
            NextPriceSensor,
            today_prices={},
            tomorrow_prices={"2026-03-29T12:15:00Z": 3.3},
        )
        assert sensor.native_value == pytest.approx(3.3)

    def test_returns_none_when_no_next_slot(self, monkeypatch):
        monkeypatch.setattr(dt_mock, "utcnow",
                            lambda: datetime.datetime(2026, 3, 29, 12, 0, 0, tzinfo=UTC))
        sensor = _make_sensor(NextPriceSensor, today_prices={}, tomorrow_prices={})
        assert sensor.native_value is None


class TestTodayMinMaxAverage:
    def test_today_min(self):
        sensor = _make_sensor(TodayMinSensor,
                              today_prices={"a": 5.0, "b": 2.0, "c": 8.0})
        assert sensor.native_value == pytest.approx(2.0)

    def test_today_max(self):
        sensor = _make_sensor(TodayMaxSensor,
                              today_prices={"a": 5.0, "b": 2.0, "c": 8.0})
        assert sensor.native_value == pytest.approx(8.0)

    def test_today_average(self):
        sensor = _make_sensor(TodayAverageSensor,
                              today_prices={"a": 2.0, "b": 4.0, "c": 6.0})
        assert sensor.native_value == pytest.approx(4.0)

    def test_returns_none_when_no_prices(self):
        assert _make_sensor(TodayMinSensor).native_value is None
        assert _make_sensor(TodayMaxSensor).native_value is None
        assert _make_sensor(TodayAverageSensor).native_value is None


class TestTomorrowMinMaxAverage:
    def test_tomorrow_min(self):
        sensor = _make_sensor(TomorrowMinSensor,
                              tomorrow_prices={"a": 3.0, "b": 1.0})
        assert sensor.native_value == pytest.approx(1.0)

    def test_tomorrow_max(self):
        sensor = _make_sensor(TomorrowMaxSensor,
                              tomorrow_prices={"a": 3.0, "b": 1.0})
        assert sensor.native_value == pytest.approx(3.0)

    def test_tomorrow_average(self):
        sensor = _make_sensor(TomorrowAverageSensor,
                              tomorrow_prices={"a": 2.0, "b": 8.0})
        assert sensor.native_value == pytest.approx(5.0)

    def test_returns_none_when_no_prices(self):
        assert _make_sensor(TomorrowMinSensor).native_value is None
        assert _make_sensor(TomorrowMaxSensor).native_value is None
        assert _make_sensor(TomorrowAverageSensor).native_value is None


class TestPriceLevelSensor:
    def test_returns_level_for_current_price(self):
        sensor = _make_sensor(PriceLevelSensor,
                              today_prices={"2026-03-29T12:00:00Z": 3.0})
        assert sensor.native_value == "Cheap"

    def test_returns_none_when_no_current_price(self):
        sensor = _make_sensor(PriceLevelSensor, today_prices={})
        assert sensor.native_value is None

    def test_options_match_threshold_names(self):
        sensor = _make_sensor(PriceLevelSensor)
        assert sensor.options == ["Cheap", "Normal", "Expensive"]


class TestCheapestTimeSensor:
    def test_returns_utc_datetime_of_cheapest_slot(self):
        sensor = _make_sensor(CheapestTimeSensor, today_prices={
            "2026-03-29T06:00:00Z": 2.0,
            "2026-03-29T12:00:00Z": 8.0,
            "2026-03-29T18:00:00Z": 5.0,
        })
        result = sensor.native_value
        assert result == datetime.datetime(2026, 3, 29, 6, 0, 0, tzinfo=UTC)

    def test_returns_none_when_no_prices(self):
        sensor = _make_sensor(CheapestTimeSensor, today_prices={})
        assert sensor.native_value is None

    def test_result_is_utc_aware(self):
        sensor = _make_sensor(CheapestTimeSensor,
                              today_prices={"2026-03-29T10:00:00Z": 1.0})
        result = sensor.native_value
        assert result is not None
        assert result.tzinfo is not None


class TestVatSensor:
    def test_returns_vat_from_options(self):
        sensor = _make_options_sensor(VatSensor, options={"vat_percent": 24.0})
        assert sensor.native_value == pytest.approx(24.0)

    def test_defaults_to_zero_when_not_set(self):
        sensor = _make_options_sensor(VatSensor, options={})
        assert sensor.native_value == pytest.approx(DEFAULT_VAT)

    def test_unit_is_percent(self):
        sensor = _make_options_sensor(VatSensor)
        assert sensor._attr_native_unit_of_measurement == "%"

    def test_reflects_updated_options(self):
        sensor = _make_options_sensor(VatSensor, options={"vat_percent": 10.0})
        assert sensor.native_value == pytest.approx(10.0)
        sensor.coordinator.entry.options["vat_percent"] = 25.5
        assert sensor.native_value == pytest.approx(25.5)


class TestTransferFeeSensor:
    def test_returns_fee_from_options(self):
        sensor = _make_options_sensor(TransferFeeSensor, options={"transfer_fee": 3.5})
        assert sensor.native_value == pytest.approx(3.5)

    def test_defaults_to_zero_when_not_set(self):
        sensor = _make_options_sensor(TransferFeeSensor, options={})
        assert sensor.native_value == pytest.approx(DEFAULT_TRANSFER_FEE)

    def test_allows_negative_fee(self):
        sensor = _make_options_sensor(TransferFeeSensor, options={"transfer_fee": -1.5})
        assert sensor.native_value == pytest.approx(-1.5)

    def test_unit_is_cents_per_kwh(self):
        sensor = _make_options_sensor(TransferFeeSensor)
        assert sensor._attr_native_unit_of_measurement == "c/kWh"

    def test_reflects_updated_options(self):
        sensor = _make_options_sensor(TransferFeeSensor, options={"transfer_fee": 2.0})
        assert sensor.native_value == pytest.approx(2.0)
        sensor.coordinator.entry.options["transfer_fee"] = 4.0
        assert sensor.native_value == pytest.approx(4.0)
