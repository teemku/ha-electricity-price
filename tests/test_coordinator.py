"""Tests for PriceCoordinator static methods."""

import pytest
from datetime import date, datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

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
    async def test_clears_pricing_update_flag_after_completion(self):
        raw_today = {"2026-03-29T12:00:00Z": 10.0}
        data = PriceData(today_prices={}, tomorrow_prices={},
                           today_date=date(2026, 3, 29), thresholds=[])
        coord = _make_coordinator(raw_today=raw_today, data=data)

        await coord.async_update_vat_fee(24.0, 0.0)

        assert coord._pricing_update_in_progress is False

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


class TestHandleSlotBoundary:
    """_handle_slot_boundary promotes tomorrow→today at day rollover."""

    def _make_midnight_coordinator(self):
        """Coordinator whose data is from yesterday with tomorrow prices loaded."""
        tomorrow_prices = {"2026-03-29T22:00:00Z": 8.0, "2026-03-29T22:15:00Z": 9.0}
        raw_tomorrow = {"2026-03-29T22:00:00Z": 6.0, "2026-03-29T22:15:00Z": 7.0}
        data = PriceData(
            today_prices={"2026-03-29T00:00:00Z": 5.0},
            tomorrow_prices=tomorrow_prices,
            today_date=date(2026, 3, 29),
            thresholds=[{"name": "Cheap", "below": 5.0}],
        )
        coord = _make_coordinator(
            raw_today={"2026-03-29T00:00:00Z": 4.0},
            raw_tomorrow=raw_tomorrow,
            data=data,
        )
        coord.async_request_refresh = AsyncMock()
        return coord

    @pytest.mark.asyncio
    async def test_promotes_tomorrow_to_today_at_rollover(self):
        coord = self._make_midnight_coordinator()
        # Midnight of the new day — local date (UTC in tests) differs from today_date.
        new_day = datetime(2026, 3, 30, 0, 0, 0, tzinfo=timezone.utc)

        await coord._handle_slot_boundary(new_day)

        promoted = coord.async_set_updated_data.call_args[0][0]
        assert promoted.today_prices == {"2026-03-29T22:00:00Z": 8.0,
                                         "2026-03-29T22:15:00Z": 9.0}
        assert promoted.tomorrow_prices == {}
        assert promoted.today_date == date(2026, 3, 30)

    @pytest.mark.asyncio
    async def test_updates_raw_caches_at_rollover(self):
        coord = self._make_midnight_coordinator()
        new_day = datetime(2026, 3, 30, 0, 0, 0, tzinfo=timezone.utc)

        await coord._handle_slot_boundary(new_day)

        assert coord._raw_today == {"2026-03-29T22:00:00Z": 6.0,
                                    "2026-03-29T22:15:00Z": 7.0}
        assert coord._raw_tomorrow == {}

    @pytest.mark.asyncio
    async def test_triggers_refresh_at_rollover(self):
        coord = self._make_midnight_coordinator()
        new_day = datetime(2026, 3, 30, 0, 0, 0, tzinfo=timezone.utc)

        await coord._handle_slot_boundary(new_day)

        coord.async_request_refresh.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_preserves_thresholds_at_rollover(self):
        coord = self._make_midnight_coordinator()
        new_day = datetime(2026, 3, 30, 0, 0, 0, tzinfo=timezone.utc)

        await coord._handle_slot_boundary(new_day)

        promoted = coord.async_set_updated_data.call_args[0][0]
        assert promoted.thresholds == [{"name": "Cheap", "below": 5.0}]

    @pytest.mark.asyncio
    async def test_no_rollover_pushes_current_data(self):
        """On a normal slot boundary (same day) only async_set_updated_data is called."""
        data = PriceData(
            today_prices={"2026-03-29T12:00:00Z": 5.0},
            tomorrow_prices={},
            today_date=date(2026, 3, 29),
            thresholds=[],
        )
        coord = _make_coordinator(data=data)
        coord.async_request_refresh = AsyncMock()
        same_day = datetime(2026, 3, 29, 12, 15, 0, tzinfo=timezone.utc)

        await coord._handle_slot_boundary(same_day)

        coord.async_request_refresh.assert_not_awaited()
        coord.async_set_updated_data.assert_called_once_with(data)


def _make_update_coordinator(raw_today=None, raw_tomorrow=None, data=None, today=None):
    """Coordinator wired for _async_update_data testing."""
    today = today or date(2026, 4, 4)
    hass = MagicMock()
    entry = MagicMock()
    entry.entry_id = "test_entry"
    entry.data = {"api_key": "key", "price_area": "FI - Finland"}
    entry.options = {CONF_VAT: 0.0, CONF_TRANSFER_FEE: 0.0}

    coord = object.__new__(PriceCoordinator)
    coord.hass = hass
    coord.entry = entry
    coord._raw_today = raw_today or {}
    coord._raw_tomorrow = raw_tomorrow or {}
    coord.data = data
    coord._pricing_update_in_progress = False
    coord.async_set_updated_data = MagicMock()

    store = AsyncMock()
    store.async_load = AsyncMock(return_value=None)
    store.async_save = AsyncMock()
    coord._store = store

    return coord, today


class TestAsyncUpdateDataTodayCache:
    """_async_update_data uses in-memory _raw_today when today_date already matches.

    This prevents the API re-fetch at the midnight rollover from overwriting the
    correctly-promoted today prices with a response that may be missing the first
    slot of the new local day.
    """

    @pytest.mark.asyncio
    async def test_skips_api_for_today_when_cache_matches(self):
        """When _raw_today is populated and today_date matches, no API call for today."""
        today = date(2026, 4, 4)
        raw_today = {f"2026-04-03T21:{m:02d}:00Z": 5.0 for m in range(0, 60, 15)}
        # Pad to 88 slots so the >= 88 guard passes.
        for h in range(1, 22):
            for m in range(0, 60, 15):
                raw_today[f"2026-04-{3 + (h >= 21):02d}T{h % 24:02d}:{m:02d}:00Z"] = 5.0

        data = PriceData(
            today_prices={k: 5.0 for k in raw_today},
            tomorrow_prices={},
            today_date=today,
            thresholds=[],
        )
        coord, _ = _make_update_coordinator(raw_today=raw_today, data=data, today=today)

        local_now = datetime(2026, 4, 4, 0, 0, 0, tzinfo=timezone.utc)

        with (
            patch(
                "custom_components.electricity_price.coordinator.dt_util.now",
                return_value=local_now,
            ),
            patch(
                "custom_components.electricity_price.coordinator.async_get_clientsession",
            ),
            patch(
                "custom_components.electricity_price.coordinator.api.fetch_day_ahead_prices",
                new_callable=AsyncMock,
            ) as mock_fetch,
            patch.object(coord, "_save_stored", new_callable=AsyncMock),
        ):
            # tomorrow fetch raises NoDataError (not published yet)
            from custom_components.electricity_price.api import EntsoENoDataError
            mock_fetch.side_effect = EntsoENoDataError("no data")

            result = await coord._async_update_data()

        # The in-memory cache was used; no API call should have been made for today
        # (the only call allowed is for tomorrow, which is also silenced here).
        for call_args in mock_fetch.call_args_list:
            fetched_date = call_args.args[3] if len(call_args.args) > 3 else call_args.kwargs.get("date")
            assert fetched_date != today, (
                f"API was called for today ({today}) but should have used in-memory cache"
            )

        assert result.today_prices == {k: 5.0 for k in raw_today}
        assert result.today_date == today

    @pytest.mark.asyncio
    async def test_falls_through_to_api_when_cache_is_empty(self):
        """When _raw_today is empty, the API is called for today's prices."""
        today = date(2026, 4, 4)
        data = PriceData(
            today_prices={},
            tomorrow_prices={},
            today_date=today,
            thresholds=[],
        )
        coord, _ = _make_update_coordinator(raw_today={}, data=data, today=today)

        api_prices = {f"2026-04-03T{h:02d}:{m:02d}:00Z": float(h * 4 + m // 15)
                      for h in range(21, 24) for m in range(0, 60, 15)}
        for h in range(0, 21):
            for m in range(0, 60, 15):
                api_prices[f"2026-04-04T{h:02d}:{m:02d}:00Z"] = float(h * 4 + m // 15)

        local_now = datetime(2026, 4, 4, 0, 0, 0, tzinfo=timezone.utc)

        with (
            patch(
                "custom_components.electricity_price.coordinator.dt_util.now",
                return_value=local_now,
            ),
            patch(
                "custom_components.electricity_price.coordinator.async_get_clientsession",
            ),
            patch(
                "custom_components.electricity_price.coordinator.api.fetch_day_ahead_prices",
                new_callable=AsyncMock,
            ) as mock_fetch,
            patch.object(coord, "_save_stored", new_callable=AsyncMock),
        ):
            from custom_components.electricity_price.api import EntsoENoDataError

            def _side_effect(session, api_key, area_eic, d, tz):
                if d == today:
                    return api_prices
                raise EntsoENoDataError("no tomorrow data")

            mock_fetch.side_effect = _side_effect

            result = await coord._async_update_data()

        today_calls = [
            c for c in mock_fetch.call_args_list
            if (c.args[3] if len(c.args) > 3 else c.kwargs.get("date")) == today
        ]
        assert len(today_calls) == 1, "Expected exactly one API call for today when cache is empty"
        assert result.today_date == today
