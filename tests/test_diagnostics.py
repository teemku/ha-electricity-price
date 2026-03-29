"""Tests for diagnostics.py."""

import asyncio
from datetime import date
from unittest.mock import MagicMock

from custom_components.electricity_price.diagnostics import async_get_config_entry_diagnostics


def _make_entry(today_prices, tomorrow_prices, tomorrow_available, today_date, raw_today=None, raw_tomorrow=None):
    entry = MagicMock()
    entry.as_dict.return_value = {"entry_id": "test"}

    data = MagicMock()
    data.today_prices = today_prices
    data.tomorrow_prices = tomorrow_prices
    data.tomorrow_available = tomorrow_available
    data.today_date = today_date

    coordinator = MagicMock()
    coordinator.data = data
    coordinator._raw_today = raw_today if raw_today is not None else {}
    coordinator._raw_tomorrow = raw_tomorrow if raw_tomorrow is not None else {}

    entry.runtime_data = coordinator
    return entry


class TestDiagnosticsFullData:
    def test_slot_counts_reflect_price_dict_lengths(self):
        entry = _make_entry(
            today_prices={"k1": 5.0, "k2": 6.0},
            tomorrow_prices={"k3": 4.0},
            tomorrow_available=True,
            today_date=date(2026, 3, 29),
            raw_today={"r1": 1.0, "r2": 2.0, "r3": 3.0},
            raw_tomorrow={"r4": 4.0},
        )
        result = asyncio.run(async_get_config_entry_diagnostics(MagicMock(), entry))

        assert result["prices"]["today_slots"] == 2
        assert result["prices"]["tomorrow_slots"] == 1
        assert result["prices"]["tomorrow_available"] is True
        assert result["prices"]["today_date"] == "2026-03-29"
        assert result["raw_prices"]["today_slots"] == 3
        assert result["raw_prices"]["tomorrow_slots"] == 1

    def test_config_entry_key_present(self):
        entry = _make_entry({}, {}, False, date(2026, 3, 29))
        result = asyncio.run(async_get_config_entry_diagnostics(MagicMock(), entry))
        assert "config_entry" in result

    def test_empty_prices(self):
        entry = _make_entry({}, {}, False, date(2026, 3, 29))
        result = asyncio.run(async_get_config_entry_diagnostics(MagicMock(), entry))

        assert result["prices"]["today_slots"] == 0
        assert result["prices"]["tomorrow_slots"] == 0
        assert result["prices"]["tomorrow_available"] is False
        assert result["raw_prices"]["today_slots"] == 0
        assert result["raw_prices"]["tomorrow_slots"] == 0


class TestDiagnosticsNullData:
    def test_null_coordinator_data_returns_zeros(self):
        entry = MagicMock()
        entry.as_dict.return_value = {}

        coordinator = MagicMock()
        coordinator.data = None
        coordinator._raw_today = {}
        coordinator._raw_tomorrow = {}
        entry.runtime_data = coordinator

        result = asyncio.run(async_get_config_entry_diagnostics(MagicMock(), entry))

        assert result["prices"]["today_slots"] == 0
        assert result["prices"]["tomorrow_slots"] == 0
        assert result["prices"]["tomorrow_available"] is False
        assert result["prices"]["today_date"] is None
