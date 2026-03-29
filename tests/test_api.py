"""Tests for the ENTSO-E API client — XML parsing and HTTP error handling."""

import datetime
import re

import aiohttp
import pytest
from aioresponses import aioresponses as mock_aiohttp

from custom_components.electricity_price.api import (
    EntsoEAuthError,
    EntsoEConnectionError,
    EntsoENoDataError,
    _parse_xml,
    _resolution_to_minutes,
    fetch_day_ahead_prices,
)
from custom_components.electricity_price.const import ENTSOE_BASE_URL, ENTSOE_XML_NS

NS = ENTSOE_XML_NS
UTC = datetime.timezone.utc
MIDNIGHT = datetime.datetime(2026, 3, 29, 0, 0, 0, tzinfo=UTC)
AREA = "10YFI-1--------U"


# ---------------------------------------------------------------------------
# XML builder helpers
# ---------------------------------------------------------------------------


def _pub_xml(body: str) -> str:
    return f'<Publication_MarketDocument xmlns="{NS}">{body}</Publication_MarketDocument>'


def _ack_xml(reason: str = "No matching data found") -> str:
    return (
        f'<Acknowledgement_MarketDocument xmlns="{NS}">'
        f"<Reason><text>{reason}</text></Reason>"
        f"</Acknowledgement_MarketDocument>"
    )


def _timeseries(resolution: str, start: str, points: list[tuple[int, float]]) -> str:
    pts = "".join(
        f"<Point>"
        f"<position>{pos}</position>"
        f"<price.amount>{price}</price.amount>"
        f"</Point>"
        for pos, price in points
    )
    return (
        f"<TimeSeries>"
        f"<Period>"
        f"<timeInterval><start>{start}</start></timeInterval>"
        f"<resolution>{resolution}</resolution>"
        f"{pts}"
        f"</Period>"
        f"</TimeSeries>"
    )


# ---------------------------------------------------------------------------
# _resolution_to_minutes
# ---------------------------------------------------------------------------


class TestResolutionToMinutes:
    def test_pt15m(self):
        assert _resolution_to_minutes("PT15M") == 15

    def test_pt30m(self):
        assert _resolution_to_minutes("PT30M") == 30

    def test_pt60m(self):
        assert _resolution_to_minutes("PT60M") == 60

    def test_unknown_returns_none(self):
        assert _resolution_to_minutes("PT1H") is None

    def test_empty_returns_none(self):
        assert _resolution_to_minutes("") is None


# ---------------------------------------------------------------------------
# _parse_xml — resolution expansion
# ---------------------------------------------------------------------------


class TestParseXmlExpansion:
    def test_pt60m_expands_to_four_slots(self):
        xml = _pub_xml(_timeseries("PT60M", "2026-03-29T00:00Z", [(1, 100.0)]))
        result = _parse_xml(xml, UTC, MIDNIGHT)
        assert "2026-03-29T00:00:00Z" in result
        assert "2026-03-29T00:15:00Z" in result
        assert "2026-03-29T00:30:00Z" in result
        assert "2026-03-29T00:45:00Z" in result
        # All four sub-slots carry the parent price
        for key in ["2026-03-29T00:00:00Z", "2026-03-29T00:15:00Z",
                    "2026-03-29T00:30:00Z", "2026-03-29T00:45:00Z"]:
            assert result[key] == pytest.approx(100.0)

    def test_pt30m_expands_to_two_slots(self):
        xml = _pub_xml(_timeseries("PT30M", "2026-03-29T00:00Z", [(1, 50.0)]))
        result = _parse_xml(xml, UTC, MIDNIGHT)
        assert result["2026-03-29T00:00:00Z"] == pytest.approx(50.0)
        assert result["2026-03-29T00:15:00Z"] == pytest.approx(50.0)
        assert "2026-03-29T00:30:00Z" not in result

    def test_pt15m_not_expanded(self):
        xml = _pub_xml(_timeseries("PT15M", "2026-03-29T00:00Z", [(1, 30.0)]))
        result = _parse_xml(xml, UTC, MIDNIGHT)
        assert "2026-03-29T00:00:00Z" in result
        assert "2026-03-29T00:15:00Z" not in result

    def test_multiple_points_in_one_period(self):
        xml = _pub_xml(_timeseries("PT15M", "2026-03-29T00:00Z", [
            (1, 10.0), (2, 20.0), (3, 30.0),
        ]))
        result = _parse_xml(xml, UTC, MIDNIGHT)
        assert result["2026-03-29T00:00:00Z"] == pytest.approx(10.0)
        assert result["2026-03-29T00:15:00Z"] == pytest.approx(20.0)
        assert result["2026-03-29T00:30:00Z"] == pytest.approx(30.0)


# ---------------------------------------------------------------------------
# _parse_xml — day filtering
# ---------------------------------------------------------------------------


class TestParseXmlDayFiltering:
    def test_slots_before_midnight_excluded(self):
        # Period starts 2 hours before UTC midnight — those slots fall on March 28.
        xml = _pub_xml(_timeseries("PT60M", "2026-03-28T22:00Z", [
            (1, 99.0),  # 22:00–23:00 UTC March 28 → excluded
            (2, 88.0),  # 23:00–00:00 UTC March 28 → excluded
            (3, 77.0),  # 00:00–01:00 UTC March 29 → included
        ]))
        result = _parse_xml(xml, UTC, MIDNIGHT)
        assert not any(k.startswith("2026-03-28") for k in result)
        assert "2026-03-29T00:00:00Z" in result

    def test_slot_exactly_at_midnight_included(self):
        xml = _pub_xml(_timeseries("PT15M", "2026-03-29T00:00Z", [(1, 5.0)]))
        result = _parse_xml(xml, UTC, MIDNIGHT)
        assert "2026-03-29T00:00:00Z" in result

    def test_full_day_pt60m_produces_96_slots(self):
        points = [(i + 1, float(i)) for i in range(24)]
        xml = _pub_xml(_timeseries("PT60M", "2026-03-29T00:00Z", points))
        result = _parse_xml(xml, UTC, MIDNIGHT)
        assert len(result) == 96

    def test_full_day_pt15m_produces_96_slots(self):
        points = [(i + 1, float(i % 10)) for i in range(96)]
        xml = _pub_xml(_timeseries("PT15M", "2026-03-29T00:00Z", points))
        result = _parse_xml(xml, UTC, MIDNIGHT)
        assert len(result) == 96


# ---------------------------------------------------------------------------
# _parse_xml — multiple TimeSeries averaging
# ---------------------------------------------------------------------------


class TestParseXmlAveraging:
    def test_two_series_same_slot_averaged(self):
        ts1 = _timeseries("PT15M", "2026-03-29T00:00Z", [(1, 80.0)])
        ts2 = _timeseries("PT15M", "2026-03-29T00:00Z", [(1, 40.0)])
        result = _parse_xml(_pub_xml(ts1 + ts2), UTC, MIDNIGHT)
        assert result["2026-03-29T00:00:00Z"] == pytest.approx(60.0)

    def test_two_series_different_slots_merged(self):
        ts1 = _timeseries("PT15M", "2026-03-29T00:00Z", [(1, 10.0)])
        ts2 = _timeseries("PT15M", "2026-03-29T00:15Z", [(1, 20.0)])
        result = _parse_xml(_pub_xml(ts1 + ts2), UTC, MIDNIGHT)
        assert result["2026-03-29T00:00:00Z"] == pytest.approx(10.0)
        assert result["2026-03-29T00:15:00Z"] == pytest.approx(20.0)


# ---------------------------------------------------------------------------
# _parse_xml — error cases
# ---------------------------------------------------------------------------


class TestParseXmlErrors:
    def test_acknowledgement_raises_no_data_error(self):
        with pytest.raises(EntsoENoDataError):
            _parse_xml(_ack_xml(), UTC, MIDNIGHT)

    def test_invalid_xml_raises_connection_error(self):
        with pytest.raises(EntsoEConnectionError):
            _parse_xml("<<< not xml >>>", UTC, MIDNIGHT)

    def test_empty_document_raises_no_data_error(self):
        with pytest.raises(EntsoENoDataError):
            _parse_xml(_pub_xml(""), UTC, MIDNIGHT)

    def test_wrong_root_tag_raises_no_data_error(self):
        xml = f'<UnknownDocument xmlns="{NS}"></UnknownDocument>'
        with pytest.raises(EntsoENoDataError):
            _parse_xml(xml, UTC, MIDNIGHT)

    def test_all_slots_outside_day_raises_no_data_error(self):
        # Period is entirely in the previous day
        xml = _pub_xml(_timeseries("PT15M", "2026-03-28T00:00Z", [(1, 1.0)]))
        with pytest.raises(EntsoENoDataError):
            _parse_xml(xml, UTC, MIDNIGHT)


# ---------------------------------------------------------------------------
# fetch_day_ahead_prices — HTTP layer
# ---------------------------------------------------------------------------


class TestFetchDayAheadPrices:
    @pytest.mark.asyncio
    async def test_401_raises_auth_error(self):
        with mock_aiohttp() as m:
            m.get(re.compile(r".*"), status=401)
            async with aiohttp.ClientSession() as session:
                with pytest.raises(EntsoEAuthError):
                    await fetch_day_ahead_prices(
                        session, "bad_key", AREA,
                        datetime.date(2026, 3, 29), UTC,
                    )

    @pytest.mark.asyncio
    async def test_500_raises_connection_error(self):
        with mock_aiohttp() as m:
            m.get(re.compile(r".*"), status=500)
            async with aiohttp.ClientSession() as session:
                with pytest.raises(EntsoEConnectionError):
                    await fetch_day_ahead_prices(
                        session, "key", AREA,
                        datetime.date(2026, 3, 29), UTC,
                    )

    @pytest.mark.asyncio
    async def test_success_returns_price_dict(self):
        points = [(i + 1, float(i * 5)) for i in range(24)]
        xml_body = _pub_xml(_timeseries("PT60M", "2026-03-29T00:00Z", points))
        with mock_aiohttp() as m:
            m.get(re.compile(r".*"), status=200, body=xml_body)
            async with aiohttp.ClientSession() as session:
                result = await fetch_day_ahead_prices(
                    session, "valid_key", AREA,
                    datetime.date(2026, 3, 29), UTC,
                )
        assert len(result) == 96
        assert all(isinstance(v, float) for v in result.values())

    @pytest.mark.asyncio
    async def test_acknowledgement_response_raises_no_data_error(self):
        with mock_aiohttp() as m:
            m.get(re.compile(r".*"), status=200, body=_ack_xml())
            async with aiohttp.ClientSession() as session:
                with pytest.raises(EntsoENoDataError):
                    await fetch_day_ahead_prices(
                        session, "key", AREA,
                        datetime.date(2026, 3, 29), UTC,
                    )
