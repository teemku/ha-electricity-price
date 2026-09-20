"""Tests for the retry button entity."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from custom_components.electricity_price.button import RetryFetchButton


def _make_button():
    coordinator = MagicMock()
    coordinator.async_retry_now = AsyncMock()
    entry = MagicMock()
    entry.entry_id = "test_entry"
    entry.title = "Electricity Price"
    return RetryFetchButton(coordinator, entry), coordinator


def test_unique_id_is_derived_from_the_entry():
    button, _ = _make_button()
    assert button._attr_unique_id == "test_entry_retry_fetch"


def test_is_available_after_a_failed_update():
    button, coordinator = _make_button()
    coordinator.last_update_success = False
    assert button.available is True


@pytest.mark.asyncio
async def test_press_forces_a_retry():
    button, coordinator = _make_button()
    await button.async_press()
    coordinator.async_retry_now.assert_awaited_once()
