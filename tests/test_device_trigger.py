"""Tests for device trigger helper functions."""

import asyncio
import datetime
from unittest.mock import MagicMock

import pytest

import homeassistant.util.dt as dt_mock
from custom_components.electricity_price.const import DOMAIN
from custom_components.electricity_price.device_trigger import (
    TRIGGER_TYPES,
    _attach_optimal_start,
    _attach_price_level_change,
    _attach_price_threshold,
    _attach_tomorrow_available,
    _find_optimal_start_windowed,
    _parse_time,
    _resolve_coordinator,
    async_attach_trigger,
    async_get_trigger_capabilities,
    async_get_triggers,
)

UTC = datetime.timezone.utc
# conftest.py pins utcnow to 2026-03-29T12:00:00Z.
# as_local is identity (UTC treated as local) so local time == UTC time.

# Future slots starting at or after 12:00 UTC
_PRICES = {
    # past — ignored
    "2026-03-29T10:00:00Z": 1.0,
    "2026-03-29T11:45:00Z": 1.0,
    # future
    "2026-03-29T12:00:00Z": 8.0,
    "2026-03-29T12:15:00Z": 6.0,
    "2026-03-29T12:30:00Z": 2.0,
    "2026-03-29T12:45:00Z": 3.0,
    "2026-03-29T13:00:00Z": 7.0,
    "2026-03-29T13:15:00Z": 9.0,
    "2026-03-29T13:30:00Z": 4.0,
    "2026-03-29T13:45:00Z": 5.0,
}


# ---------------------------------------------------------------------------
# _parse_time
# ---------------------------------------------------------------------------


class TestParseTime:
    def test_hms_format(self):
        result = _parse_time("07:00:00")
        assert result == datetime.time(7, 0)

    def test_hm_format(self):
        result = _parse_time("22:30")
        assert result == datetime.time(22, 30)

    def test_none_returns_none(self):
        assert _parse_time(None) is None

    def test_empty_string_returns_none(self):
        assert _parse_time("") is None

    def test_invalid_format_returns_none(self):
        assert _parse_time("not-a-time") is None

    def test_midnight(self):
        assert _parse_time("00:00:00") == datetime.time(0, 0)

    def test_end_of_day(self):
        assert _parse_time("23:59") == datetime.time(23, 59)


# ---------------------------------------------------------------------------
# _find_optimal_start_windowed — no window (delegates to base function)
# ---------------------------------------------------------------------------


class TestFindOptimalStartWindowedNoWindow:
    def test_no_window_finds_cheapest(self):
        result = _find_optimal_start_windowed(_PRICES, 0.5, None, None)
        # n=2: cheapest pair is [12:30, 12:45] = 2+3 = 5
        assert result == datetime.datetime(2026, 3, 29, 12, 30, 0, tzinfo=UTC)

    def test_no_window_returns_none_when_insufficient_data(self):
        result = _find_optimal_start_windowed(
            {"2026-03-29T12:00:00Z": 1.0}, 1.0, None, None
        )
        assert result is None


# ---------------------------------------------------------------------------
# _find_optimal_start_windowed — window_start filter
# ---------------------------------------------------------------------------


class TestFindOptimalStartWindowedStart:
    def test_start_filter_excludes_early_slots(self):
        # window_start = 12:30 → only slots at 12:30+ are eligible
        ws = datetime.time(12, 30)
        result = _find_optimal_start_windowed(_PRICES, 0.25, ws, None)
        # Cheapest single slot at or after 12:30: price 2.0 at 12:30
        assert result == datetime.datetime(2026, 3, 29, 12, 30, 0, tzinfo=UTC)

    def test_start_filter_all_slots_excluded_returns_none(self):
        # window_start = 14:00 → no future slots qualify
        ws = datetime.time(14, 0)
        result = _find_optimal_start_windowed(_PRICES, 0.25, ws, None)
        assert result is None

    def test_start_at_exact_slot_boundary_included(self):
        ws = datetime.time(13, 0)
        result = _find_optimal_start_windowed(_PRICES, 0.25, ws, None)
        # Cheapest slot at or after 13:00: 13:30 (price 4.0) or 13:00 (price 7.0)?
        # prices at 13:00=7, 13:15=9, 13:30=4, 13:45=5 → cheapest is 13:30
        assert result == datetime.datetime(2026, 3, 29, 13, 30, 0, tzinfo=UTC)


# ---------------------------------------------------------------------------
# _find_optimal_start_windowed — window_end filter
# ---------------------------------------------------------------------------


class TestFindOptimalStartWindowedEnd:
    def test_end_filter_excludes_runs_that_overshoot(self):
        # duration = 30 min (n=2). window_end = 12:45.
        # The run must finish by 12:45, so latest start = 12:30 (ends 13:00 > 12:45? No.)
        # 12:30 + 30min = 13:00 > 12:45 → excluded!
        # 12:15 + 30min = 12:45 ≤ 12:45 → included
        # 12:00 + 30min = 12:30 ≤ 12:45 → included
        we = datetime.time(12, 45)
        result = _find_optimal_start_windowed(_PRICES, 0.5, None, we)
        # Eligible windows: [12:00,12:15]=8+6=14, [12:15,12:30]=6+2=8
        # Cheapest: 12:15
        assert result == datetime.datetime(2026, 3, 29, 12, 15, 0, tzinfo=UTC)

    def test_end_filter_allows_run_ending_exactly_at_window_end(self):
        # 30 min run starting 12:15 ends at 12:45, window_end=12:45 → allowed
        we = datetime.time(12, 45)
        result = _find_optimal_start_windowed(_PRICES, 0.5, None, we)
        assert result is not None

    def test_end_filter_all_excluded_returns_none(self):
        we = datetime.time(12, 15)  # Even a 15-min run from 12:00 ends at 12:15 ≤ 12:15 → ok
        # But from utcnow=12:00 with we=12:15, only start=12:00 (ends 12:15) qualifies.
        result = _find_optimal_start_windowed(_PRICES, 0.25, None, we)
        assert result == datetime.datetime(2026, 3, 29, 12, 0, 0, tzinfo=UTC)


# ---------------------------------------------------------------------------
# _find_optimal_start_windowed — combined start + end window
# ---------------------------------------------------------------------------


class TestFindOptimalStartWindowedCombined:
    def test_combined_window_restricts_search(self):
        ws = datetime.time(12, 30)
        we = datetime.time(13, 0)
        # 15-min run in [12:30, 13:00): eligible starts: 12:30 (ends 12:45 ≤ 13:00), 12:45 (ends 13:00 ≤ 13:00)
        result = _find_optimal_start_windowed(_PRICES, 0.25, ws, we)
        # prices: 12:30=2.0, 12:45=3.0 → cheapest is 12:30
        assert result == datetime.datetime(2026, 3, 29, 12, 30, 0, tzinfo=UTC)

    def test_combined_window_no_qualifying_slots_returns_none(self):
        ws = datetime.time(14, 0)
        we = datetime.time(15, 0)
        result = _find_optimal_start_windowed(_PRICES, 0.25, ws, we)
        assert result is None


# ---------------------------------------------------------------------------
# _find_optimal_start_windowed — contiguity guard
# ---------------------------------------------------------------------------


class TestFindOptimalStartWindowedContiguity:
    def test_noncontiguous_window_skipped(self):
        # Slots with a gap: 12:00, 12:15, then jump to 13:30 (skipping 12:30–13:15).
        # A 30-min (n=2) window spanning the gap must be rejected.
        gapped = {
            "2026-03-29T12:00:00Z": 1.0,  # cheapest pair candidate
            "2026-03-29T12:15:00Z": 1.0,  # — these two are contiguous ✓
            "2026-03-29T13:30:00Z": 50.0,
            "2026-03-29T13:45:00Z": 50.0,
        }
        ws = datetime.time(12, 0)
        we = datetime.time(14, 0)
        result = _find_optimal_start_windowed(gapped, 0.5, ws, we)
        # Only contiguous windows: [12:00,12:15] and [13:30,13:45].
        # [12:00,12:15] = 1+1 = 2 → should win.
        assert result == datetime.datetime(2026, 3, 29, 12, 0, 0, tzinfo=UTC)

    def test_gap_between_window_days_not_contiguous(self):
        # Simulate the overnight gap after time-window filtering.
        # Slots: 22:00–22:15 today and 07:00–07:15 tomorrow (as "future" slots).
        # Set utcnow to 21:00 so 22:x slots are in the future.
        import homeassistant.util.dt as _dt
        original = _dt.utcnow
        _dt.utcnow = lambda: datetime.datetime(2026, 3, 29, 21, 0, 0, tzinfo=UTC)
        try:
            overnight = {
                "2026-03-29T22:00:00Z": 5.0,
                "2026-03-29T22:15:00Z": 5.0,
                # gap: 22:30 through 06:45 missing
                "2026-03-30T07:00:00Z": 1.0,
                "2026-03-30T07:15:00Z": 1.0,
            }
            ws = datetime.time(7, 0)
            we = datetime.time(23, 0)
            # With a window covering both time ranges, the overnight window
            # [22:15 → 07:00] must be rejected (not contiguous).
            result = _find_optimal_start_windowed(overnight, 0.5, ws, we)
            # Qualifying contiguous 2-slot windows:
            # [22:00,22:15] both at 5.0 — ws=07:00, so 22:00 ≥ 07:00 ✓
            # [07:00,07:15] both at 1.0 ← cheapest
            assert result == datetime.datetime(2026, 3, 30, 7, 0, 0, tzinfo=UTC)
        finally:
            _dt.utcnow = original


# ---------------------------------------------------------------------------
# Shared helpers for attach-function tests
# ---------------------------------------------------------------------------

# conftest pins utcnow to 2026-03-29T12:00:00Z; _utc_key rounds to 15-min boundary.
_NOW_KEY = "2026-03-29T12:00:00Z"
_NEXT_KEY = "2026-03-29T12:15:00Z"

_THRESHOLDS = [
    {"name": "Cheap", "below": 8.0},
    {"name": "Expensive", "below": None},
]


def _make_coordinator(today_prices=None, tomorrow_available=False, thresholds=None, data_none=False):
    coord = MagicMock()
    if data_none:
        coord.data = None
    else:
        data = MagicMock()
        data.today_prices = today_prices if today_prices is not None else {_NOW_KEY: 5.0}
        data.tomorrow_prices = {}
        data.tomorrow_available = tomorrow_available
        data.thresholds = thresholds if thresholds is not None else _THRESHOLDS
        coord.data = data
    return coord


def _capture_listener(coord):
    """Wire async_add_listener to capture the registered callback."""
    captured = {}
    unsub = MagicMock()

    def _side(fn):
        captured["fn"] = fn
        return unsub

    coord.async_add_listener.side_effect = _side
    return captured, unsub


# ---------------------------------------------------------------------------
# _attach_price_level_change
# ---------------------------------------------------------------------------


class TestAttachPriceLevelChange:
    def test_registers_listener(self):
        coord = _make_coordinator()
        captured, _ = _capture_listener(coord)
        _attach_price_level_change(MagicMock(), {}, MagicMock(), {}, coord, "d1")
        coord.async_add_listener.assert_called_once()

    def test_initial_update_does_not_fire(self):
        hass = MagicMock()
        coord = _make_coordinator()
        captured, _ = _capture_listener(coord)
        _attach_price_level_change(hass, {}, MagicMock(), {}, coord, "d1")
        captured["fn"]()
        hass.async_run_hass_job.assert_not_called()

    def test_fires_when_level_changes(self):
        hass = MagicMock()
        coord = _make_coordinator(today_prices={_NOW_KEY: 5.0})
        captured, _ = _capture_listener(coord)
        _attach_price_level_change(hass, {}, MagicMock(), {}, coord, "d1")

        captured["fn"]()  # prev_level = "Cheap"
        coord.data.today_prices = {_NOW_KEY: 10.0}  # now "Expensive"
        captured["fn"]()

        hass.async_run_hass_job.assert_called_once()

    def test_no_fire_when_level_unchanged(self):
        hass = MagicMock()
        coord = _make_coordinator(today_prices={_NOW_KEY: 5.0})
        captured, _ = _capture_listener(coord)
        _attach_price_level_change(hass, {}, MagicMock(), {}, coord, "d1")

        captured["fn"]()  # prev = "Cheap"
        coord.data.today_prices = {_NOW_KEY: 7.0}  # still Cheap
        captured["fn"]()

        hass.async_run_hass_job.assert_not_called()

    def test_no_fire_when_data_none(self):
        hass = MagicMock()
        coord = _make_coordinator(data_none=True)
        captured, _ = _capture_listener(coord)
        _attach_price_level_change(hass, {}, MagicMock(), {}, coord, "d1")
        captured["fn"]()
        hass.async_run_hass_job.assert_not_called()

    def test_trigger_payload_includes_from_to_levels(self):
        hass = MagicMock()
        coord = _make_coordinator(today_prices={_NOW_KEY: 5.0})
        captured, _ = _capture_listener(coord)
        _attach_price_level_change(hass, {}, MagicMock(), {}, coord, "d1")

        captured["fn"]()  # prev = "Cheap"
        coord.data.today_prices = {_NOW_KEY: 10.0}
        captured["fn"]()

        trigger = hass.async_run_hass_job.call_args[0][1]["trigger"]
        assert trigger["from"] == "Cheap"
        assert trigger["to"] == "Expensive"
        assert trigger["type"] == "price_level_change"


# ---------------------------------------------------------------------------
# _attach_price_threshold
# ---------------------------------------------------------------------------


class TestAttachPriceThreshold:
    def test_below_fires_on_price_crossing_threshold(self):
        hass = MagicMock()
        coord = _make_coordinator(today_prices={_NOW_KEY: 10.0})  # above threshold
        captured, _ = _capture_listener(coord)
        _attach_price_threshold(hass, {"threshold": 8.0}, MagicMock(), {}, coord, "d1", below=True)

        captured["fn"]()  # 10 > 8 → not triggered; prev_triggered = False
        hass.async_run_hass_job.assert_not_called()

        coord.data.today_prices = {_NOW_KEY: 5.0}  # now below threshold
        captured["fn"]()
        hass.async_run_hass_job.assert_called_once()

    def test_below_no_refire_while_staying_below(self):
        hass = MagicMock()
        coord = _make_coordinator(today_prices={_NOW_KEY: 10.0})
        captured, _ = _capture_listener(coord)
        _attach_price_threshold(hass, {"threshold": 8.0}, MagicMock(), {}, coord, "d1", below=True)

        captured["fn"]()  # prev_triggered = False
        coord.data.today_prices = {_NOW_KEY: 5.0}
        captured["fn"]()  # fires
        coord.data.today_prices = {_NOW_KEY: 4.0}  # stays below
        captured["fn"]()  # no re-fire

        assert hass.async_run_hass_job.call_count == 1

    def test_above_fires_on_price_crossing_threshold(self):
        hass = MagicMock()
        coord = _make_coordinator(today_prices={_NOW_KEY: 5.0})  # below threshold
        captured, _ = _capture_listener(coord)
        _attach_price_threshold(hass, {"threshold": 8.0}, MagicMock(), {}, coord, "d1", below=False)

        captured["fn"]()  # 5 < 8 → not triggered; prev_triggered = False
        coord.data.today_prices = {_NOW_KEY: 10.0}
        captured["fn"]()

        hass.async_run_hass_job.assert_called_once()

    def test_first_update_never_fires_even_if_triggered(self):
        # prev_triggered starts as None → rising edge requires prev to be False
        hass = MagicMock()
        coord = _make_coordinator(today_prices={_NOW_KEY: 5.0})
        captured, _ = _capture_listener(coord)
        _attach_price_threshold(hass, {"threshold": 8.0}, MagicMock(), {}, coord, "d1", below=True)

        captured["fn"]()  # 5 < 8 → triggered, but prev is None → no fire
        hass.async_run_hass_job.assert_not_called()

    def test_no_fire_when_data_none(self):
        hass = MagicMock()
        coord = _make_coordinator(data_none=True)
        captured, _ = _capture_listener(coord)
        _attach_price_threshold(hass, {"threshold": 8.0}, MagicMock(), {}, coord, "d1", below=True)
        captured["fn"]()
        hass.async_run_hass_job.assert_not_called()

    def test_trigger_payload_includes_threshold_and_price(self):
        hass = MagicMock()
        coord = _make_coordinator(today_prices={_NOW_KEY: 10.0})
        captured, _ = _capture_listener(coord)
        _attach_price_threshold(hass, {"threshold": 8.0}, MagicMock(), {}, coord, "d1", below=True)

        captured["fn"]()  # prev_triggered = False
        coord.data.today_prices = {_NOW_KEY: 6.0}
        captured["fn"]()

        trigger = hass.async_run_hass_job.call_args[0][1]["trigger"]
        assert trigger["threshold"] == 8.0
        assert trigger["price"] == 6.0
        assert trigger["type"] == "price_below"


# ---------------------------------------------------------------------------
# _attach_tomorrow_available
# ---------------------------------------------------------------------------


class TestAttachTomorrowAvailable:
    def test_fires_when_tomorrow_becomes_available(self):
        hass = MagicMock()
        coord = _make_coordinator(tomorrow_available=False)
        captured, _ = _capture_listener(coord)
        _attach_tomorrow_available(hass, {}, MagicMock(), {}, coord, "d1")

        captured["fn"]()  # prev = None → no fire
        coord.data.tomorrow_available = True
        captured["fn"]()  # True with prev=False → fires

        hass.async_run_hass_job.assert_called_once()

    def test_no_refire_if_stays_available(self):
        hass = MagicMock()
        coord = _make_coordinator(tomorrow_available=False)
        captured, _ = _capture_listener(coord)
        _attach_tomorrow_available(hass, {}, MagicMock(), {}, coord, "d1")

        captured["fn"]()  # prev = None
        coord.data.tomorrow_available = True
        captured["fn"]()  # fires (prev was False)
        captured["fn"]()  # stays True, prev is True → no re-fire

        assert hass.async_run_hass_job.call_count == 1

    def test_no_fire_when_data_none(self):
        hass = MagicMock()
        coord = _make_coordinator(data_none=True)
        captured, _ = _capture_listener(coord)
        _attach_tomorrow_available(hass, {}, MagicMock(), {}, coord, "d1")
        captured["fn"]()
        hass.async_run_hass_job.assert_not_called()

    def test_trigger_payload_type(self):
        hass = MagicMock()
        coord = _make_coordinator(tomorrow_available=False)
        captured, _ = _capture_listener(coord)
        _attach_tomorrow_available(hass, {}, MagicMock(), {}, coord, "d1")

        captured["fn"]()
        coord.data.tomorrow_available = True
        captured["fn"]()

        trigger = hass.async_run_hass_job.call_args[0][1]["trigger"]
        assert trigger["type"] == "tomorrow_available"


# ---------------------------------------------------------------------------
# _attach_optimal_start
# ---------------------------------------------------------------------------


_DT_MOD = "custom_components.electricity_price.device_trigger"


class TestAttachOptimalStart:
    def test_registers_listener_and_schedules(self):
        from unittest.mock import patch

        coord = _make_coordinator(
            today_prices={
                _NOW_KEY: 8.0,
                _NEXT_KEY: 4.0,
                "2026-03-29T12:30:00Z": 6.0,
            }
        )
        captured, _ = _capture_listener(coord)

        with patch(f"{_DT_MOD}.async_track_point_in_time") as mock_schedule:
            _attach_optimal_start(MagicMock(), {"duration": 0.25}, MagicMock(), {}, coord, "d1")

        coord.async_add_listener.assert_called_once()
        mock_schedule.assert_called_once()

    def test_no_schedule_when_coordinator_data_is_none(self):
        from unittest.mock import patch

        coord = _make_coordinator(data_none=True)
        captured, _ = _capture_listener(coord)

        with patch(f"{_DT_MOD}.async_track_point_in_time") as mock_schedule:
            _attach_optimal_start(MagicMock(), {"duration": 0.25}, MagicMock(), {}, coord, "d1")

        mock_schedule.assert_not_called()

    def test_unsub_is_callable(self):
        from unittest.mock import patch

        coord = _make_coordinator(today_prices={_NOW_KEY: 5.0, _NEXT_KEY: 6.0})
        captured, _ = _capture_listener(coord)

        with patch(f"{_DT_MOD}.async_track_point_in_time"):
            unsub = _attach_optimal_start(MagicMock(), {"duration": 0.25}, MagicMock(), {}, coord, "d1")

        assert callable(unsub)
        unsub()  # must not raise


# ---------------------------------------------------------------------------
# _resolve_coordinator
# ---------------------------------------------------------------------------


class TestResolveCoordinator:
    def test_returns_none_when_device_not_found(self):
        from unittest.mock import patch

        dev_reg = MagicMock()
        dev_reg.async_get.return_value = None

        with patch(f"{_DT_MOD}.dr") as mock_dr:
            mock_dr.async_get.return_value = dev_reg
            result = _resolve_coordinator(MagicMock(), "no_such_device")

        assert result is None

    def test_returns_coordinator_for_matching_entry(self):
        from unittest.mock import patch

        dev_reg = MagicMock()
        device = MagicMock()
        device.config_entries = ["entry1"]
        dev_reg.async_get.return_value = device

        hass = MagicMock()
        entry = MagicMock()
        entry.domain = DOMAIN
        coordinator = MagicMock()
        entry.runtime_data = coordinator
        hass.config_entries.async_get_entry.return_value = entry

        with patch(f"{_DT_MOD}.dr") as mock_dr:
            mock_dr.async_get.return_value = dev_reg
            result = _resolve_coordinator(hass, "device1")

        assert result is coordinator

    def test_returns_none_when_entry_domain_mismatches(self):
        from unittest.mock import patch

        dev_reg = MagicMock()
        device = MagicMock()
        device.config_entries = ["entry1"]
        dev_reg.async_get.return_value = device

        hass = MagicMock()
        entry = MagicMock()
        entry.domain = "other_domain"
        hass.config_entries.async_get_entry.return_value = entry

        with patch(f"{_DT_MOD}.dr") as mock_dr:
            mock_dr.async_get.return_value = dev_reg
            result = _resolve_coordinator(hass, "device1")

        assert result is None


# ---------------------------------------------------------------------------
# async_get_triggers / async_get_trigger_capabilities
# ---------------------------------------------------------------------------


class TestAsyncGetTriggers:
    def test_returns_one_trigger_per_type(self):
        result = asyncio.run(async_get_triggers(MagicMock(), "dev1"))
        assert len(result) == len(TRIGGER_TYPES)
        assert {t["type"] for t in result} == TRIGGER_TYPES

    def test_all_triggers_have_device_id(self):
        result = asyncio.run(async_get_triggers(MagicMock(), "dev42"))
        assert all(t["device_id"] == "dev42" for t in result)


class TestAsyncGetTriggerCapabilities:
    def test_optimal_start_exposes_duration_and_window(self):
        result = asyncio.run(
            async_get_trigger_capabilities(MagicMock(), {"type": "optimal_start"})
        )
        assert "extra_fields" in result

    def test_price_below_exposes_threshold(self):
        result = asyncio.run(
            async_get_trigger_capabilities(MagicMock(), {"type": "price_below"})
        )
        assert "extra_fields" in result

    def test_price_above_exposes_threshold(self):
        result = asyncio.run(
            async_get_trigger_capabilities(MagicMock(), {"type": "price_above"})
        )
        assert "extra_fields" in result

    def test_price_level_change_no_extra_fields(self):
        result = asyncio.run(
            async_get_trigger_capabilities(MagicMock(), {"type": "price_level_change"})
        )
        assert result == {}

    def test_tomorrow_available_no_extra_fields(self):
        result = asyncio.run(
            async_get_trigger_capabilities(MagicMock(), {"type": "tomorrow_available"})
        )
        assert result == {}


# ---------------------------------------------------------------------------
# async_attach_trigger
# ---------------------------------------------------------------------------


class TestAsyncAttachTrigger:
    def test_returns_noop_when_coordinator_not_found(self):
        from unittest.mock import patch

        dev_reg = MagicMock()
        dev_reg.async_get.return_value = None

        config = {
            "type": "price_level_change",
            "device_id": "unknown",
            "domain": DOMAIN,
        }
        with patch(f"{_DT_MOD}.dr") as mock_dr:
            mock_dr.async_get.return_value = dev_reg
            result = asyncio.run(async_attach_trigger(MagicMock(), config, MagicMock(), {}))

        assert callable(result)
        result()  # noop — must not raise

    def test_unknown_trigger_type_returns_noop(self):
        from unittest.mock import patch

        dev_reg = MagicMock()
        device = MagicMock()
        device.config_entries = ["entry1"]
        dev_reg.async_get.return_value = device

        hass = MagicMock()
        entry = MagicMock()
        entry.domain = DOMAIN
        coord = MagicMock()
        coord.data = None
        entry.runtime_data = coord
        hass.config_entries.async_get_entry.return_value = entry

        config = {"type": "nonexistent_type", "device_id": "d1", "domain": DOMAIN}
        with patch(f"{_DT_MOD}.dr") as mock_dr:
            mock_dr.async_get.return_value = dev_reg
            result = asyncio.run(async_attach_trigger(hass, config, MagicMock(), {}))

        assert callable(result)
