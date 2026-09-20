"""Tests for the diagnostic binary sensors."""

from unittest.mock import MagicMock

import pytest

from homeassistant.components.binary_sensor import BinarySensorDeviceClass
from homeassistant.const import EntityCategory
from custom_components.electricity_price.binary_sensor import (
    FetchFailingBinarySensor,
    TomorrowAvailableBinarySensor,
    async_setup_entry,
)
from custom_components.electricity_price.const import DOMAIN


def _make_sensor(cls, fetch_errors=None, tomorrow_available=False, update_succeeded=True):
    coord = MagicMock()
    coord.fetch_errors = fetch_errors if fetch_errors is not None else {}
    coord.data.tomorrow_available = tomorrow_available
    coord.last_update_success = update_succeeded
    entry = MagicMock()
    entry.entry_id = "test_entry"
    entry.title = "Electricity Price"
    return cls(coord, entry)


class TestFetchFailingBinarySensor:
    def test_off_when_nothing_is_failing(self):
        sensor = _make_sensor(FetchFailingBinarySensor)
        assert sensor.is_on is False

    def test_attributes_are_empty_when_off(self):
        sensor = _make_sensor(FetchFailingBinarySensor)
        assert sensor.extra_state_attributes == {"scope": None, "error": None}

    def test_on_with_scope_and_error_when_today_fails(self):
        sensor = _make_sensor(FetchFailingBinarySensor, fetch_errors={"today": "Request timed out"})
        assert sensor.is_on is True
        assert sensor.extra_state_attributes == {"scope": "today", "error": "Request timed out"}

    def test_on_with_scope_and_error_when_tomorrow_fails(self):
        sensor = _make_sensor(FetchFailingBinarySensor, fetch_errors={"tomorrow": "ENTSO-E returned HTTP 503"})
        assert sensor.is_on is True
        assert sensor.extra_state_attributes == {"scope": "tomorrow", "error": "ENTSO-E returned HTTP 503"}

    def test_attributes_show_the_most_recently_recorded_failure_when_both_fail(self):
        sensor = _make_sensor(
            FetchFailingBinarySensor,
            fetch_errors={"tomorrow": "tomorrow error", "today": "today error"},
        )
        assert sensor.extra_state_attributes == {"scope": "today", "error": "today error"}

        sensor = _make_sensor(
            FetchFailingBinarySensor,
            fetch_errors={"today": "today error", "tomorrow": "tomorrow error"},
        )
        assert sensor.extra_state_attributes == {"scope": "tomorrow", "error": "tomorrow error"}

    def test_reflects_changes_in_the_coordinator(self):
        sensor = _make_sensor(FetchFailingBinarySensor)
        sensor.coordinator.fetch_errors = {"today": "boom"}
        assert sensor.is_on is True
        sensor.coordinator.fetch_errors = {}
        assert sensor.is_on is False

    def test_stays_available_when_the_last_update_failed(self):
        sensor = _make_sensor(
            FetchFailingBinarySensor, fetch_errors={"today": "boom"}, update_succeeded=False
        )
        assert sensor.available is True

    def test_is_a_diagnostic_problem_sensor(self):
        sensor = _make_sensor(FetchFailingBinarySensor)
        assert sensor._attr_device_class == BinarySensorDeviceClass.PROBLEM
        assert sensor._attr_entity_category == EntityCategory.DIAGNOSTIC

    def test_unique_id_and_translation_key(self):
        sensor = _make_sensor(FetchFailingBinarySensor)
        assert sensor._attr_unique_id == "test_entry_fetch_failing"
        assert sensor._attr_translation_key == "fetch_failing"


class TestTomorrowAvailableBinarySensor:
    def test_off_before_tomorrows_prices_are_available(self):
        sensor = _make_sensor(TomorrowAvailableBinarySensor, tomorrow_available=False)
        assert sensor.is_on is False

    def test_on_once_tomorrows_prices_are_available(self):
        sensor = _make_sensor(TomorrowAvailableBinarySensor, tomorrow_available=True)
        assert sensor.is_on is True

    def test_turns_off_again_when_the_day_rolls_over(self):
        sensor = _make_sensor(TomorrowAvailableBinarySensor, tomorrow_available=True)
        sensor.coordinator.data.tomorrow_available = False
        assert sensor.is_on is False

    def test_keeps_the_default_availability(self):
        # It describes the price data, so it must go unavailable together with
        # the price entities instead of overriding availability like the
        # fetch status entities do.
        assert "available" not in TomorrowAvailableBinarySensor.__dict__

    def test_is_a_diagnostic_sensor(self):
        sensor = _make_sensor(TomorrowAvailableBinarySensor)
        assert sensor._attr_entity_category == EntityCategory.DIAGNOSTIC

    def test_unique_id_and_translation_key(self):
        sensor = _make_sensor(TomorrowAvailableBinarySensor)
        assert sensor._attr_unique_id == "test_entry_tomorrow_available"
        assert sensor._attr_translation_key == "tomorrow_available"


class TestDeviceInfo:
    def test_entities_share_the_price_device(self):
        for cls in (FetchFailingBinarySensor, TomorrowAvailableBinarySensor):
            info = _make_sensor(cls).device_info
            assert info["identifiers"] == {(DOMAIN, "test_entry")}
            assert info["name"] == "Electricity Price"


class TestSetup:
    @pytest.mark.asyncio
    async def test_adds_both_entities(self):
        entry = MagicMock()
        entry.entry_id = "test_entry"
        add_entities = MagicMock()

        await async_setup_entry(MagicMock(), entry, add_entities)

        [entities] = add_entities.call_args.args
        assert [type(e) for e in entities] == [FetchFailingBinarySensor, TomorrowAvailableBinarySensor]
