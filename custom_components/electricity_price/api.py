"""ENTSO-E Transparency Platform API client."""

from __future__ import annotations

import datetime
import logging
from xml.etree import ElementTree

import aiohttp

from .const import ENTSOE_BASE_URL, ENTSOE_DOCUMENT_TYPE, ENTSOE_XML_NS, SLOT_MINUTES

_LOGGER = logging.getLogger(__name__)

_NS = ENTSOE_XML_NS
_ACK_TAG = f"{{{_NS}}}Acknowledgement_MarketDocument"
_PUB_TAG = f"{{{_NS}}}Publication_MarketDocument"


class EntsoEAuthError(Exception):
    """Raised when the API key is rejected."""


class EntsoENoDataError(Exception):
    """Raised when no price data is available for the requested period."""


class EntsoEConnectionError(Exception):
    """Raised on network or HTTP errors."""


async def fetch_day_ahead_prices(
    session: aiohttp.ClientSession,
    api_key: str,
    area_eic: str,
    date: datetime.date,
    timezone: datetime.tzinfo,
) -> dict[str, float]:
    """Fetch day-ahead prices for a local calendar date.

    Returns a mapping of UTC ISO-8601 timestamp strings to price in EUR/MWh.
    Each key is the start of a 15-minute interval, e.g. "2026-03-28T23:00:00Z".
    Raises EntsoEAuthError, EntsoENoDataError, or EntsoEConnectionError.
    """
    local_midnight = datetime.datetime(
        date.year, date.month, date.day, tzinfo=timezone
    )
    utc_start = local_midnight.astimezone(datetime.timezone.utc)
    utc_end   = (local_midnight + datetime.timedelta(days=1)).astimezone(datetime.timezone.utc)

    # Look back 25 h to guarantee the previous CET-aligned period (which
    # contains the first local-midnight slots for east-of-CET timezones) is
    # included in the response. _parse_xml filters strictly to the local day.
    period_start = (utc_start - datetime.timedelta(hours=25)).strftime("%Y%m%d%H%M")
    period_end   = (utc_end   + datetime.timedelta(hours=2)).strftime("%Y%m%d%H%M")

    params = {
        "documentType": ENTSOE_DOCUMENT_TYPE,
        "in_Domain": area_eic,
        "out_Domain": area_eic,
        "periodStart": period_start,
        "periodEnd": period_end,
        "securityToken": api_key,
    }

    try:
        async with session.get(
            ENTSOE_BASE_URL,
            params=params,
            timeout=aiohttp.ClientTimeout(total=30),
        ) as response:
            text = await response.text()
            if response.status == 401:
                raise EntsoEAuthError("Invalid API key (HTTP 401)")
            if response.status != 200:
                _LOGGER.debug(
                    "ENTSO-E error response (HTTP %d): %s",
                    response.status,
                    text[:500],
                )
                raise EntsoEConnectionError(
                    f"ENTSO-E returned HTTP {response.status}"
                )
    except aiohttp.ClientError as err:
        raise EntsoEConnectionError(f"Network error: {err}") from err

    return _parse_xml(text, timezone, local_midnight)


def _parse_xml(
    xml_text: str,
    timezone: datetime.tzinfo,
    local_midnight: datetime.datetime,
) -> dict[str, float]:
    """Parse the ENTSO-E XML response into {utc_iso: eur_per_mwh}.

    Keys are UTC ISO-8601 strings ("2026-03-28T23:00:00Z") for each
    15-minute interval start that falls within the local calendar day.
    Coarser resolutions (PT30M, PT60M) are expanded to 15-min sub-slots,
    each carrying the same price as the parent data point.
    """
    try:
        root = ElementTree.fromstring(xml_text)
    except ElementTree.ParseError as err:
        raise EntsoEConnectionError(f"Failed to parse XML: {err}") from err

    # Acknowledgement means an error was returned (e.g. no data, bad params).
    if root.tag == _ACK_TAG:
        reason_el = root.find(f".//{{{_NS}}}Reason/{{{_NS}}}text")
        reason = reason_el.text if reason_el is not None else "Unknown reason"
        _LOGGER.debug("ENTSO-E acknowledgement: %s", reason)
        raise EntsoENoDataError(reason)

    if root.tag != _PUB_TAG:
        raise EntsoENoDataError(f"Unexpected root element: {root.tag}")

    # Multiple TimeSeries can rarely cover the same slot; average them.
    slot_buckets: dict[str, list[float]] = {}
    local_day_end = local_midnight + datetime.timedelta(days=1)

    for timeseries in root.findall(f"{{{_NS}}}TimeSeries"):
        for period in timeseries.findall(f"{{{_NS}}}Period"):
            resolution = _get_text(period, f"{{{_NS}}}resolution")
            start_str = _get_text(
                period, f"{{{_NS}}}timeInterval/{{{_NS}}}start"
            )
            if not resolution or not start_str:
                continue

            res_minutes = _resolution_to_minutes(resolution)
            if res_minutes is None:
                _LOGGER.warning("Unsupported resolution: %s", resolution)
                continue

            period_start_utc = datetime.datetime.fromisoformat(
                start_str.replace("Z", "+00:00")
            )

            for point in period.findall(f"{{{_NS}}}Point"):
                pos_el = point.find(f"{{{_NS}}}position")
                price_el = point.find(f"{{{_NS}}}price.amount")
                if pos_el is None or price_el is None:
                    continue

                pos_text = pos_el.text
                price_text = price_el.text
                if pos_text is None or price_text is None:
                    continue
                try:
                    position = int(pos_text)
                    price_mwh = float(price_text)
                except ValueError:
                    _LOGGER.warning(
                        "Skipping malformed price point: position=%r, price=%r",
                        pos_text,
                        price_text,
                    )
                    continue

                point_utc = period_start_utc + datetime.timedelta(
                    minutes=(position - 1) * res_minutes
                )

                # Expand PT30M / PT60M points to 15-min sub-slots.
                for offset_min in range(0, res_minutes, SLOT_MINUTES):
                    sub_utc = point_utc + datetime.timedelta(minutes=offset_min)
                    sub_local = sub_utc.astimezone(timezone)
                    if not (local_midnight <= sub_local < local_day_end):
                        continue
                    key = sub_utc.strftime("%Y-%m-%dT%H:%M:%SZ")
                    slot_buckets.setdefault(key, []).append(price_mwh)

    if not slot_buckets:
        raise EntsoENoDataError(
            f"No price points found for {local_midnight.date()}"
        )

    result = {
        key: sum(prices) / len(prices)
        for key, prices in slot_buckets.items()
    }

    result = fill_gaps(result)
    _LOGGER.debug("Parsed %d slots for %s", len(result), local_midnight.date())
    return result


def fill_gaps(prices: dict[str, float]) -> dict[str, float]:
    """Forward-fill missing 15-minute slots (A03 variable-sized block convention).

    When ENTSO-E omits a position it means the preceding price continues.
    Operates over the range spanned by the existing keys.
    """
    if len(prices) < 2:
        return prices
    keys = sorted(prices)
    start = datetime.datetime.fromisoformat(keys[0].replace("Z", "+00:00"))
    end = datetime.datetime.fromisoformat(keys[-1].replace("Z", "+00:00"))
    filled: dict[str, float] = {}
    last = prices[keys[0]]
    cursor = start
    while cursor <= end:
        key = cursor.strftime("%Y-%m-%dT%H:%M:%SZ")
        if key in prices:
            last = prices[key]
        filled[key] = last
        cursor += datetime.timedelta(minutes=SLOT_MINUTES)
    return filled


def _get_text(element: ElementTree.Element, path: str) -> str | None:
    el = element.find(path)
    return el.text if el is not None else None


def _resolution_to_minutes(resolution: str) -> int | None:
    mapping = {"PT15M": 15, "PT30M": 30, "PT60M": 60}
    return mapping.get(resolution)
