"""Device trigger platform: fire at the optimal (cheapest) start time.

Appears in the automation editor under Device → <your Electricity Price device> → Optimal start.
"""

from __future__ import annotations

import logging
import math
from datetime import date as dt_date, datetime, time, timedelta, timezone
from typing import Any, cast

import voluptuous as vol

from homeassistant.components.device_automation import DEVICE_TRIGGER_BASE_SCHEMA
from homeassistant.const import CONF_DEVICE_ID, CONF_DOMAIN, CONF_TYPE
from homeassistant.core import CALLBACK_TYPE, HomeAssistant, callback
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.event import async_track_point_in_time
from homeassistant.helpers.selector import (
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    TimeSelector,
)
from homeassistant.util import dt as dt_util

from .const import DOMAIN, INTEGRATION_NAME
from .coordinator import PriceCoordinator
from .sensor import _find_optimal_start, _get_price_level, _utc_key

_LOGGER = logging.getLogger(__name__)

TRIGGER_TYPE_OPTIMAL_START = "optimal_start"
TRIGGER_TYPE_PRICE_LEVEL_CHANGE = "price_level_change"
TRIGGER_TYPE_PRICE_BELOW = "price_below"
TRIGGER_TYPE_PRICE_ABOVE = "price_above"
TRIGGER_TYPE_TOMORROW_AVAILABLE = "tomorrow_available"

TRIGGER_TYPES = (
    TRIGGER_TYPE_OPTIMAL_START,
    TRIGGER_TYPE_PRICE_LEVEL_CHANGE,
    TRIGGER_TYPE_PRICE_BELOW,
    TRIGGER_TYPE_PRICE_ABOVE,
    TRIGGER_TYPE_TOMORROW_AVAILABLE,
)

TRIGGER_SCHEMA = DEVICE_TRIGGER_BASE_SCHEMA.extend(
    {
        vol.Required(CONF_TYPE): vol.In(TRIGGER_TYPES),
        # optimal_start fields
        vol.Optional("duration"): vol.All(vol.Coerce(float), vol.Range(min=0.25, max=24)),
        vol.Optional("window_start"): str,
        vol.Optional("window_end"): str,
        # price_below / price_above field
        vol.Optional("threshold"): vol.All(vol.Coerce(float), vol.Range(min=-100, max=10000)),
    }
)


def _parse_time(value: str | None) -> time | None:
    """Parse a time string like '07:00:00' or '07:00' into a time object."""
    if not value:
        return None
    try:
        parts = value.split(":")
        return time(int(parts[0]), int(parts[1]))
    except (ValueError, IndexError):
        return None


def _find_optimal_start_windowed(
    prices: dict[str, float],
    duration_hours: float,
    window_start: time | None,
    window_end: time | None,
) -> datetime | None:
    """Cheapest contiguous window, optionally restricted to a local time range.

    When window_start / window_end are given, only windows whose entire run
    fits within [window_start, window_end] (local time) are considered.
    Verifies contiguity of each candidate window so that overnight gaps
    introduced by the time filter do not produce spurious results.
    """
    if window_start is None and window_end is None:
        return _find_optimal_start(prices, duration_hours)

    n = math.ceil(duration_hours * 4)
    now_key = _utc_key(dt_util.utcnow())
    duration_td = timedelta(hours=duration_hours)

    # Keep ALL future slots so that slots in the interior of a valid window
    # are not accidentally removed by the time-window filter.
    items = sorted(
        [(k, v) for k, v in prices.items() if k >= now_key],
        key=lambda x: x[0],
    )

    if len(items) < n:
        return None

    keys = [k for k, _ in items]
    values = [v for _, v in items]

    # Span that a contiguous n-slot window must cover.
    slot_span = timedelta(minutes=15 * (n - 1))

    def _start_qualifies(i: int) -> bool:
        """True when a window starting at index i satisfies the time constraint."""
        t0_utc = datetime.strptime(keys[i], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
        t0_local = dt_util.as_local(t0_utc)
        if window_start is not None and t0_local.time() < window_start:
            return False
        if window_end is not None:
            run_end = t0_local + duration_td
            if run_end.date() > t0_local.date() or run_end.time() > window_end:
                return False
        return True

    def _contiguous(i: int) -> bool:
        t0 = datetime.strptime(keys[i], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
        t1 = datetime.strptime(keys[i + n - 1], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
        return (t1 - t0) == slot_span

    window_sum = sum(values[:n])
    best: float | None = None
    best_i: int | None = None

    if _contiguous(0) and _start_qualifies(0):
        best, best_i = window_sum, 0

    for i in range(1, len(values) - n + 1):
        window_sum += values[i + n - 1] - values[i - 1]
        if _contiguous(i) and _start_qualifies(i) and (best is None or window_sum < best):
            best, best_i = window_sum, i

    if best_i is None:
        return None

    return datetime.strptime(keys[best_i], "%Y-%m-%dT%H:%M:%SZ").replace(
        tzinfo=timezone.utc
    )


def _resolve_coordinator(hass: HomeAssistant, device_id: str) -> PriceCoordinator | None:
    """Return the coordinator for a device, or None if not found."""
    dev_reg = dr.async_get(hass)
    device = dev_reg.async_get(device_id)
    if device is None:
        return None
    for entry_id in device.config_entries:
        entry = hass.config_entries.async_get_entry(entry_id)
        if entry is not None and entry.domain == DOMAIN:
            coordinator = getattr(entry, "runtime_data", None)
            if coordinator is not None:
                return cast(PriceCoordinator, coordinator)
    return None


async def async_get_triggers(
    hass: HomeAssistant, device_id: str
) -> list[dict[str, Any]]:
    """Return the list of triggers available for this device."""
    return [
        {"platform": "device", "domain": DOMAIN, "device_id": device_id, "type": t}
        for t in TRIGGER_TYPES
    ]


async def async_get_trigger_capabilities(
    hass: HomeAssistant, config: dict[str, Any]
) -> dict[str, vol.Schema]:
    """Return extra fields shown in the automation editor for this trigger."""
    trigger_type = config.get(CONF_TYPE)

    if trigger_type == TRIGGER_TYPE_OPTIMAL_START:
        return {
            "extra_fields": vol.Schema(
                {
                    vol.Required("duration", default=1.5): NumberSelector(
                        NumberSelectorConfig(
                            min=0.25, max=24, step=0.25, mode=NumberSelectorMode.BOX
                        )
                    ),
                    vol.Optional("window_start"): TimeSelector(),
                    vol.Optional("window_end"): TimeSelector(),
                }
            )
        }

    if trigger_type in (TRIGGER_TYPE_PRICE_BELOW, TRIGGER_TYPE_PRICE_ABOVE):
        return {
            "extra_fields": vol.Schema(
                {
                    vol.Required("threshold", default=5.0): NumberSelector(
                        NumberSelectorConfig(
                            min=-100,
                            max=10000,
                            step=0.1,
                            mode=NumberSelectorMode.BOX,
                            unit_of_measurement="c/kWh",
                        )
                    ),
                }
            )
        }

    # price_level_change and tomorrow_available need no extra fields.
    return {}


async def async_attach_trigger(
    hass: HomeAssistant,
    config: dict[str, Any],
    action: Any,
    trigger_info: dict[str, Any],
) -> CALLBACK_TYPE:
    """Attach the trigger; returns an unsubscribe callable."""
    trigger_type: str = config[CONF_TYPE]
    device_id: str = config[CONF_DEVICE_ID]

    coordinator = _resolve_coordinator(hass, device_id)
    if coordinator is None:
        _LOGGER.warning("%s: could not find coordinator for device %s", DOMAIN, device_id)
        return lambda: None

    if trigger_type == TRIGGER_TYPE_OPTIMAL_START:
        return _attach_optimal_start(hass, config, action, trigger_info, coordinator, device_id)
    if trigger_type == TRIGGER_TYPE_PRICE_LEVEL_CHANGE:
        return _attach_price_level_change(hass, config, action, trigger_info, coordinator, device_id)
    if trigger_type == TRIGGER_TYPE_PRICE_BELOW:
        return _attach_price_threshold(hass, config, action, trigger_info, coordinator, device_id, below=True)
    if trigger_type == TRIGGER_TYPE_PRICE_ABOVE:
        return _attach_price_threshold(hass, config, action, trigger_info, coordinator, device_id, below=False)
    if trigger_type == TRIGGER_TYPE_TOMORROW_AVAILABLE:
        return _attach_tomorrow_available(hass, config, action, trigger_info, coordinator, device_id)

    return lambda: None


@callback  # type: ignore[untyped-decorator]
def _attach_optimal_start(
    hass: HomeAssistant,
    config: dict[str, Any],
    action: Any,
    trigger_info: dict[str, Any],
    coordinator: PriceCoordinator,
    device_id: str,
) -> CALLBACK_TYPE:
    duration_hours: float = config["duration"]
    window_start: time | None = _parse_time(config.get("window_start"))
    window_end: time | None = _parse_time(config.get("window_end"))

    unsubs: list[CALLBACK_TYPE] = []
    cancel_scheduled: CALLBACK_TYPE | None = None
    fired_on: dt_date | None = None

    @callback  # type: ignore[untyped-decorator]
    def _fire(_now: datetime) -> None:
        nonlocal cancel_scheduled, fired_on
        cancel_scheduled = None
        fired_on = dt_util.now().date()
        hass.async_run_hass_job(
            action,
            {
                "trigger": {
                    **trigger_info,
                    "platform": "device",
                    "domain": DOMAIN,
                    "device_id": device_id,
                    "type": TRIGGER_TYPE_OPTIMAL_START,
                    "duration": duration_hours,
                    "description": f"{INTEGRATION_NAME} optimal start ({duration_hours}h)",
                }
            },
        )

    @callback  # type: ignore[untyped-decorator]
    def _schedule() -> None:
        nonlocal cancel_scheduled

        if cancel_scheduled is not None:
            cancel_scheduled()
            cancel_scheduled = None

        if fired_on == dt_util.now().date():
            return

        if coordinator.data is None:
            return

        data = coordinator.data
        combined = {**data.today_prices, **data.tomorrow_prices}
        optimal_time = _find_optimal_start_windowed(combined, duration_hours, window_start, window_end)

        if optimal_time is None:
            _LOGGER.debug(
                "No optimal window for duration %.2fh (not enough future data)",
                duration_hours,
            )
            return

        _LOGGER.debug(
            "Scheduling %s optimal start at %s (duration=%.2fh)", DOMAIN,
            optimal_time.isoformat(),
            duration_hours,
        )
        cancel_scheduled = async_track_point_in_time(hass, _fire, optimal_time)

    unsubs.append(coordinator.async_add_listener(_schedule))
    _schedule()

    @callback  # type: ignore[untyped-decorator]
    def _unsub() -> None:
        for unsub in unsubs:
            unsub()
        if cancel_scheduled is not None:
            cancel_scheduled()

    return _unsub


@callback  # type: ignore[untyped-decorator]
def _attach_price_level_change(
    hass: HomeAssistant,
    config: dict[str, Any],
    action: Any,
    trigger_info: dict[str, Any],
    coordinator: PriceCoordinator,
    device_id: str,
) -> CALLBACK_TYPE:
    prev_level: str | None = None

    @callback  # type: ignore[untyped-decorator]
    def _on_update() -> None:
        nonlocal prev_level
        if coordinator.data is None:
            return
        data = coordinator.data
        current_price = data.today_prices.get(_utc_key(dt_util.utcnow()))
        if current_price is None:
            return
        current_level = _get_price_level(current_price, data.thresholds)
        if prev_level is not None and current_level != prev_level:
            hass.async_run_hass_job(
                action,
                {
                    "trigger": {
                        **trigger_info,
                        "platform": "device",
                        "domain": DOMAIN,
                        "device_id": device_id,
                        "type": TRIGGER_TYPE_PRICE_LEVEL_CHANGE,
                        "from": prev_level,
                        "to": current_level,
                        "description": f"{INTEGRATION_NAME} price level changed: {prev_level} → {current_level}",
                    }
                },
            )
        prev_level = current_level

    return coordinator.async_add_listener(_on_update)


@callback  # type: ignore[untyped-decorator]
def _attach_price_threshold(
    hass: HomeAssistant,
    config: dict[str, Any],
    action: Any,
    trigger_info: dict[str, Any],
    coordinator: PriceCoordinator,
    device_id: str,
    *,
    below: bool,
) -> CALLBACK_TYPE:
    threshold: float = config["threshold"]
    trigger_type = TRIGGER_TYPE_PRICE_BELOW if below else TRIGGER_TYPE_PRICE_ABOVE
    # None = unknown, True = currently in the triggered state, False = not
    prev_triggered: bool | None = None

    @callback  # type: ignore[untyped-decorator]
    def _on_update() -> None:
        nonlocal prev_triggered
        if coordinator.data is None:
            return
        current_price = coordinator.data.today_prices.get(_utc_key(dt_util.utcnow()))
        if current_price is None:
            return
        triggered = current_price < threshold if below else current_price > threshold
        # Only fire on the rising edge (transition into the triggered state).
        if triggered and prev_triggered is False:
            hass.async_run_hass_job(
                action,
                {
                    "trigger": {
                        **trigger_info,
                        "platform": "device",
                        "domain": DOMAIN,
                        "device_id": device_id,
                        "type": trigger_type,
                        "threshold": threshold,
                        "price": current_price,
                        "description": (
                            f"{INTEGRATION_NAME} price {'below' if below else 'above'} {threshold} c/kWh"
                        ),
                    }
                },
            )
        prev_triggered = triggered

    return coordinator.async_add_listener(_on_update)


@callback  # type: ignore[untyped-decorator]
def _attach_tomorrow_available(
    hass: HomeAssistant,
    config: dict[str, Any],
    action: Any,
    trigger_info: dict[str, Any],
    coordinator: PriceCoordinator,
    device_id: str,
) -> CALLBACK_TYPE:
    prev_available: bool | None = None

    @callback  # type: ignore[untyped-decorator]
    def _on_update() -> None:
        nonlocal prev_available
        if coordinator.data is None:
            return
        available = coordinator.data.tomorrow_available
        if available and prev_available is False:
            hass.async_run_hass_job(
                action,
                {
                    "trigger": {
                        **trigger_info,
                        "platform": "device",
                        "domain": DOMAIN,
                        "device_id": device_id,
                        "type": TRIGGER_TYPE_TOMORROW_AVAILABLE,
                        "description": f"{INTEGRATION_NAME} tomorrow's prices available",
                    }
                },
            )
        prev_available = available

    return coordinator.async_add_listener(_on_update)
