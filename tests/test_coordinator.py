"""Tests for PriceCoordinator static methods."""

import pytest
from datetime import date
from unittest.mock import MagicMock

from custom_components.electricity_price.coordinator import PriceCoordinator, PriceData, _Store
from custom_components.electricity_price.const import (
    CONF_TRANSFER_FEE,
    CONF_VAT,
    DEFAULT_THRESHOLDS,
)


def _make_coordinator(raw_today=None, raw_tomorrow=None, data=None, entry_options=None):
    """Create a coordinator with mocked hass/entry, bypassing __init__."""
    hass = MagicMock()
    entry = MagicMock()
    entry.entry_id = "test_entry"
    entry.options = entry_options or {}

    coord = object.__new__(PriceCoordinator)
    coord.hass = hass
    coord.entry = entry
    coord._raw_today = raw_today or {}
    coord._raw_tomorrow = raw_tomorrow or {}
    coord.data = data
    coord._pricing_update_in_progress = False
    coord.async_set_updated_data = MagicMock()
    return coord


class TestToRawPrices:
    """_to_raw_prices converts EUR/MWh → base c/kWh (no VAT or transfer fee)."""

    def test_basic_conversion(self):
        raw = {"2026-03-29T12:00:00Z": 100.0}  # EUR/MWh
        result = PriceCoordinator._to_raw_prices(raw)
        # 100 EUR/MWh / 10 = 10 c/kWh
        assert result["2026-03-29T12:00:00Z"] == pytest.approx(10.0)

    def test_multiple_slots(self):
        raw = {
            "2026-03-29T00:00:00Z": 100.0,
            "2026-03-29T01:00:00Z": 200.0,
        }
        result = PriceCoordinator._to_raw_prices(raw)
        assert len(result) == 2
        assert result["2026-03-29T00:00:00Z"] == pytest.approx(10.0)
        assert result["2026-03-29T01:00:00Z"] == pytest.approx(20.0)

    def test_result_is_rounded_to_4_decimals(self):
        raw = {"2026-03-29T12:00:00Z": 1.0}
        result = PriceCoordinator._to_raw_prices(raw)
        value = result["2026-03-29T12:00:00Z"]
        assert round(value, 4) == value

    def test_zero_price(self):
        raw = {"2026-03-29T12:00:00Z": 0.0}
        result = PriceCoordinator._to_raw_prices(raw)
        assert result["2026-03-29T12:00:00Z"] == pytest.approx(0.0)

    def test_negative_price(self):
        raw = {"2026-03-29T12:00:00Z": -50.0}
        result = PriceCoordinator._to_raw_prices(raw)
        assert result["2026-03-29T12:00:00Z"] == pytest.approx(-5.0)


class TestApplyPricing:
    """_apply_pricing applies VAT and transfer fee to base c/kWh prices."""

    def test_no_vat_no_fee(self):
        raw = {"2026-03-29T12:00:00Z": 10.0}
        result = PriceCoordinator._apply_pricing(raw, vat=0.0, transfer_fee=0.0)
        assert result["2026-03-29T12:00:00Z"] == pytest.approx(10.0)

    def test_vat_applied(self):
        raw = {"2026-03-29T12:00:00Z": 10.0}
        result = PriceCoordinator._apply_pricing(raw, vat=24.0, transfer_fee=0.0)
        # 10 × 1.24 = 12.4
        assert result["2026-03-29T12:00:00Z"] == pytest.approx(12.4)

    def test_transfer_fee_added(self):
        raw = {"2026-03-29T12:00:00Z": 10.0}
        result = PriceCoordinator._apply_pricing(raw, vat=0.0, transfer_fee=3.5)
        assert result["2026-03-29T12:00:00Z"] == pytest.approx(13.5)

    def test_vat_and_fee_combined(self):
        raw = {"2026-03-29T12:00:00Z": 20.0}
        result = PriceCoordinator._apply_pricing(raw, vat=10.0, transfer_fee=2.0)
        # 20 × 1.10 + 2 = 24
        assert result["2026-03-29T12:00:00Z"] == pytest.approx(24.0)

    def test_result_is_rounded_to_4_decimals(self):
        raw = {"2026-03-29T12:00:00Z": 0.1}
        result = PriceCoordinator._apply_pricing(raw, vat=0.0, transfer_fee=0.0)
        value = result["2026-03-29T12:00:00Z"]
        assert round(value, 4) == value

    def test_multiple_slots(self):
        raw = {
            "2026-03-29T00:00:00Z": 10.0,
            "2026-03-29T01:00:00Z": 20.0,
        }
        result = PriceCoordinator._apply_pricing(raw, vat=0.0, transfer_fee=0.0)
        assert len(result) == 2
        assert result["2026-03-29T00:00:00Z"] == pytest.approx(10.0)
        assert result["2026-03-29T01:00:00Z"] == pytest.approx(20.0)

    def test_negative_price_with_vat(self):
        raw = {"2026-03-29T12:00:00Z": -5.0}
        result = PriceCoordinator._apply_pricing(raw, vat=24.0, transfer_fee=0.0)
        # -5 × 1.24 = -6.2
        assert result["2026-03-29T12:00:00Z"] == pytest.approx(-6.2)

    def test_roundtrip_from_raw_prices(self):
        """_to_raw_prices followed by _apply_pricing should match old combined behaviour."""
        fetched = {"2026-03-29T12:00:00Z": 200.0}  # EUR/MWh
        raw = PriceCoordinator._to_raw_prices(fetched)
        final = PriceCoordinator._apply_pricing(raw, vat=10.0, transfer_fee=2.0)
        # 200/10 = 20, × 1.10 = 22, + 2 = 24
        assert final["2026-03-29T12:00:00Z"] == pytest.approx(24.0)


class TestLoadThresholds:
    """_load_thresholds parses options and falls back to defaults."""

    def test_returns_defaults_when_key_missing(self):
        result = PriceCoordinator._load_thresholds({})
        assert result == DEFAULT_THRESHOLDS

    def test_returns_defaults_when_value_is_none(self):
        result = PriceCoordinator._load_thresholds({"thresholds": None})
        assert result == DEFAULT_THRESHOLDS

    def test_accepts_list_directly(self):
        tiers = [{"name": "Low", "below": 5.0}, {"name": "High", "below": None}]
        result = PriceCoordinator._load_thresholds({"thresholds": tiers})
        assert result == tiers

    def test_accepts_valid_json_string(self):
        import json
        tiers = [{"name": "Low", "below": 5.0}, {"name": "High", "below": None}]
        result = PriceCoordinator._load_thresholds({"thresholds": json.dumps(tiers)})
        assert result == tiers

    def test_invalid_json_string_returns_defaults(self):
        result = PriceCoordinator._load_thresholds({"thresholds": "not valid json {{"})
        assert result == DEFAULT_THRESHOLDS

    def test_empty_list_returns_defaults(self):
        result = PriceCoordinator._load_thresholds({"thresholds": []})
        assert result == DEFAULT_THRESHOLDS

    def test_empty_json_array_returns_defaults(self):
        result = PriceCoordinator._load_thresholds({"thresholds": "[]"})
        assert result == DEFAULT_THRESHOLDS

    def test_preserves_all_tier_fields(self):
        tiers = [
            {"name": "Cheap", "below": 5.0, "color": "#22c55e"},
            {"name": "Expensive", "below": None, "color": "#ef4444"},
        ]
        result = PriceCoordinator._load_thresholds({"thresholds": tiers})
        assert result[0]["color"] == "#22c55e"
        assert result[1]["color"] == "#ef4444"


class TestStoreMigration:
    """_Store discards old data on version mismatch instead of raising."""

    @pytest.mark.asyncio
    async def test_migrate_returns_none_for_old_version(self):
        # _async_migrate_func doesn't use self; pass a dummy to call it unbound.
        result = await _Store._async_migrate_func(None, 1, 1, {"today_prices": {"k": 1.0}})
        assert result is None

    @pytest.mark.asyncio
    async def test_migrate_returns_none_for_version_2(self):
        result = await _Store._async_migrate_func(None, 2, 1, {"today_prices": {}})
        assert result is None

    @pytest.mark.asyncio
    async def test_migrate_returns_none_regardless_of_data_content(self):
        result = await _Store._async_migrate_func(None, 1, 99, {"anything": "here"})
        assert result is None


class TestAsyncUpdateVatFee:
    """async_update_vat_fee recomputes prices and notifies listeners without API fetch."""

    @pytest.mark.asyncio
    async def test_returns_early_when_no_raw_prices(self):
        coord = _make_coordinator()
        await coord.async_update_vat_fee(24.0, 3.5)
        coord.async_set_updated_data.assert_not_called()

    @pytest.mark.asyncio
    async def test_recomputes_today_prices_with_new_vat(self):
        raw_today = {"2026-03-29T12:00:00Z": 10.0}
        data = PriceData(today_prices={}, tomorrow_prices={},
                           today_date=date(2026, 3, 29), thresholds=[])
        coord = _make_coordinator(raw_today=raw_today, data=data)

        await coord.async_update_vat_fee(vat=24.0, transfer_fee=0.0)

        new_data = coord.async_set_updated_data.call_args[0][0]
        assert new_data.today_prices["2026-03-29T12:00:00Z"] == pytest.approx(12.4)

    @pytest.mark.asyncio
    async def test_recomputes_prices_with_transfer_fee(self):
        raw_today = {"2026-03-29T12:00:00Z": 10.0}
        data = PriceData(today_prices={}, tomorrow_prices={},
                           today_date=date(2026, 3, 29), thresholds=[])
        coord = _make_coordinator(raw_today=raw_today, data=data)

        await coord.async_update_vat_fee(vat=0.0, transfer_fee=3.5)

        new_data = coord.async_set_updated_data.call_args[0][0]
        assert new_data.today_prices["2026-03-29T12:00:00Z"] == pytest.approx(13.5)

    @pytest.mark.asyncio
    async def test_recomputes_tomorrow_prices(self):
        raw_tomorrow = {"2026-03-30T08:00:00Z": 20.0}
        data = PriceData(today_prices={}, tomorrow_prices={},
                           today_date=date(2026, 3, 29), thresholds=[])
        coord = _make_coordinator(raw_tomorrow=raw_tomorrow, data=data)

        await coord.async_update_vat_fee(vat=10.0, transfer_fee=0.0)

        new_data = coord.async_set_updated_data.call_args[0][0]
        assert new_data.tomorrow_prices["2026-03-30T08:00:00Z"] == pytest.approx(22.0)

    @pytest.mark.asyncio
    async def test_sets_pricing_update_in_progress(self):
        raw_today = {"2026-03-29T12:00:00Z": 10.0}
        data = PriceData(today_prices={}, tomorrow_prices={},
                           today_date=date(2026, 3, 29), thresholds=[])
        coord = _make_coordinator(raw_today=raw_today, data=data)

        await coord.async_update_vat_fee(24.0, 0.0)

        assert coord._pricing_update_in_progress is True

    @pytest.mark.asyncio
    async def test_persists_new_options_to_entry(self):
        raw_today = {"2026-03-29T12:00:00Z": 10.0}
        data = PriceData(today_prices={}, tomorrow_prices={},
                           today_date=date(2026, 3, 29), thresholds=[])
        coord = _make_coordinator(raw_today=raw_today, data=data)

        await coord.async_update_vat_fee(vat=15.0, transfer_fee=2.0)

        coord.hass.config_entries.async_update_entry.assert_called_once()
        call_kwargs = coord.hass.config_entries.async_update_entry.call_args
        saved_options = call_kwargs[1]["options"]
        assert saved_options[CONF_VAT] == 15.0
        assert saved_options[CONF_TRANSFER_FEE] == 2.0

    @pytest.mark.asyncio
    async def test_preserves_existing_thresholds(self):
        raw_today = {"2026-03-29T12:00:00Z": 10.0}
        thresholds = [{"name": "Cheap", "below": 5.0}]
        data = PriceData(today_prices={}, tomorrow_prices={},
                           today_date=date(2026, 3, 29), thresholds=thresholds)
        coord = _make_coordinator(raw_today=raw_today, data=data)

        await coord.async_update_vat_fee(0.0, 0.0)

        new_data = coord.async_set_updated_data.call_args[0][0]
        assert new_data.thresholds == thresholds

    @pytest.mark.asyncio
    async def test_raw_tomorrow_empty_produces_empty_tomorrow(self):
        raw_today = {"2026-03-29T12:00:00Z": 10.0}
        data = PriceData(today_prices={}, tomorrow_prices={},
                           today_date=date(2026, 3, 29), thresholds=[])
        coord = _make_coordinator(raw_today=raw_today, data=data)

        await coord.async_update_vat_fee(0.0, 0.0)

        new_data = coord.async_set_updated_data.call_args[0][0]
        assert new_data.tomorrow_prices == {}
