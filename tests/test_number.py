"""Tests for the VAT and transfer fee number entities."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from custom_components.electricity_price.const import (
    CONF_TRANSFER_FEE,
    CONF_VAT,
    DEFAULT_TRANSFER_FEE,
    DEFAULT_VAT,
)
from custom_components.electricity_price.number import TransferFeeNumber, VatNumber


def _make_number(cls, options=None):
    coord = MagicMock()
    coord.entry.options = options or {}
    coord.async_update_vat_fee = AsyncMock()
    entry = MagicMock()
    entry.entry_id = "test_entry"
    number = cls(coord, entry)
    number.async_write_ha_state = MagicMock()
    return number, coord


class TestVatNumber:
    def test_defaults_when_option_missing(self):
        number, _ = _make_number(VatNumber)
        assert number.native_value == DEFAULT_VAT

    def test_reads_value_from_options(self):
        number, _ = _make_number(VatNumber, {CONF_VAT: 25.5})
        assert number.native_value == 25.5

    def test_unique_id_is_scoped_by_entry(self):
        number, _ = _make_number(VatNumber)
        assert number._attr_unique_id == "test_entry_vat"

    @pytest.mark.asyncio
    async def test_set_value_keeps_current_transfer_fee(self):
        number, coord = _make_number(VatNumber, {CONF_TRANSFER_FEE: 3.5})

        await number.async_set_native_value(24.0)

        coord.async_update_vat_fee.assert_awaited_once_with(24.0, 3.5)
        number.async_write_ha_state.assert_called_once()

    @pytest.mark.asyncio
    async def test_set_value_falls_back_to_default_transfer_fee(self):
        number, coord = _make_number(VatNumber)

        await number.async_set_native_value(24.0)

        coord.async_update_vat_fee.assert_awaited_once_with(24.0, DEFAULT_TRANSFER_FEE)

    def test_bounds_match_service_schema(self):
        number, _ = _make_number(VatNumber)
        assert (number._attr_native_min_value, number._attr_native_max_value) == (0, 100)


class TestTransferFeeNumber:
    def test_defaults_when_option_missing(self):
        number, _ = _make_number(TransferFeeNumber)
        assert number.native_value == DEFAULT_TRANSFER_FEE

    def test_reads_negative_value_from_options(self):
        number, _ = _make_number(TransferFeeNumber, {CONF_TRANSFER_FEE: -1.25})
        assert number.native_value == -1.25

    def test_unique_id_is_scoped_by_entry(self):
        number, _ = _make_number(TransferFeeNumber)
        assert number._attr_unique_id == "test_entry_transfer_fee"

    @pytest.mark.asyncio
    async def test_set_value_keeps_current_vat(self):
        number, coord = _make_number(TransferFeeNumber, {CONF_VAT: 25.5})

        await number.async_set_native_value(4.0)

        coord.async_update_vat_fee.assert_awaited_once_with(25.5, 4.0)
        number.async_write_ha_state.assert_called_once()

    @pytest.mark.asyncio
    async def test_set_value_falls_back_to_default_vat(self):
        number, coord = _make_number(TransferFeeNumber)

        await number.async_set_native_value(4.0)

        coord.async_update_vat_fee.assert_awaited_once_with(DEFAULT_VAT, 4.0)

    def test_bounds_match_service_schema(self):
        number, _ = _make_number(TransferFeeNumber)
        assert (number._attr_native_min_value, number._attr_native_max_value) == (-100, 100)
