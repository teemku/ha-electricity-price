"""Install Home Assistant stubs into sys.modules before any component code is imported.

All HA imports in the custom component are satisfied by lightweight fakes so
the test suite runs without a full Home Assistant installation.
"""

import sys
from datetime import datetime, timezone
from enum import Enum
from types import ModuleType
from unittest.mock import MagicMock

import voluptuous as vol

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_FIXED_UTC = datetime(2026, 3, 29, 12, 0, 0, tzinfo=timezone.utc)


def _mod(name: str, **attrs) -> ModuleType:
    m = ModuleType(name)
    for k, v in attrs.items():
        setattr(m, k, v)
    return m


# ---------------------------------------------------------------------------
# homeassistant.util.dt
# ---------------------------------------------------------------------------

ha_dt = _mod(
    "homeassistant.util.dt",
    utcnow=lambda: _FIXED_UTC,
    now=lambda: _FIXED_UTC,
    # In tests we treat UTC as the local timezone so expected local times are
    # straightforward to reason about.
    as_local=lambda dt: dt,
)

ha_util = _mod("homeassistant.util", dt=ha_dt)

# ---------------------------------------------------------------------------
# homeassistant.core
# ---------------------------------------------------------------------------

ha_core = _mod(
    "homeassistant.core",
    HomeAssistant=MagicMock,
    CALLBACK_TYPE=type,
    callback=lambda f: f,  # passthrough — callbacks behave like plain functions
)

# ---------------------------------------------------------------------------
# homeassistant.const
# ---------------------------------------------------------------------------

class _EntityCategory(str, Enum):
    CONFIG = "config"
    DIAGNOSTIC = "diagnostic"

ha_const = _mod(
    "homeassistant.const",
    CONF_DEVICE_ID="device_id",
    CONF_DOMAIN="domain",
    CONF_TYPE="type",
    EntityCategory=_EntityCategory,
)

# ---------------------------------------------------------------------------
# homeassistant.components.sensor
# ---------------------------------------------------------------------------


class _SensorDeviceClass(str, Enum):
    TIMESTAMP = "timestamp"
    ENUM = "enum"


class _SensorStateClass(str, Enum):
    MEASUREMENT = "measurement"


ha_sensor_mod = _mod(
    "homeassistant.components.sensor",
    SensorDeviceClass=_SensorDeviceClass,
    SensorStateClass=_SensorStateClass,
    SensorEntity=object,
)

# ---------------------------------------------------------------------------
# homeassistant.components.device_automation
# ---------------------------------------------------------------------------

ha_da = _mod(
    "homeassistant.components.device_automation",
    DEVICE_TRIGGER_BASE_SCHEMA=vol.Schema(
        {
            vol.Required("device_id"): str,
            vol.Required("domain"): str,
            vol.Required("type"): str,
        },
        extra=vol.ALLOW_EXTRA,
    ),
)

# ---------------------------------------------------------------------------
# homeassistant.helpers.update_coordinator
# ---------------------------------------------------------------------------


class _MockCoordinatorEntity:
    """Minimal stand-in for CoordinatorEntity."""

    def __init__(self, coordinator):
        self.coordinator = coordinator

    def __class_getitem__(cls, item):
        return cls


class _MockDataUpdateCoordinator:
    """Minimal stand-in for DataUpdateCoordinator."""

    def __init__(self, *args, **kwargs):
        pass

    def __class_getitem__(cls, item):
        return cls


ha_upd_coord = _mod(
    "homeassistant.helpers.update_coordinator",
    CoordinatorEntity=_MockCoordinatorEntity,
    DataUpdateCoordinator=_MockDataUpdateCoordinator,
    UpdateFailed=Exception,
)

# ---------------------------------------------------------------------------
# homeassistant.helpers.selector
# ---------------------------------------------------------------------------

ha_selector = _mod(
    "homeassistant.helpers.selector",
    NumberSelector=MagicMock,
    NumberSelectorConfig=MagicMock,
    NumberSelectorMode=MagicMock(BOX="box"),
    TimeSelector=MagicMock,
    SelectSelector=MagicMock,
    SelectSelectorConfig=MagicMock,
    SelectSelectorMode=MagicMock(DROPDOWN="dropdown"),
    TextSelector=MagicMock,
    TextSelectorConfig=MagicMock,
    TextSelectorType=MagicMock(PASSWORD="password", COLOR="color"),
)

# ---------------------------------------------------------------------------
# homeassistant.components.frontend / http
# ---------------------------------------------------------------------------

ha_frontend = _mod(
    "homeassistant.components.frontend",
    add_extra_js_url=MagicMock(),
)

ha_http = _mod(
    "homeassistant.components.http",
    StaticPathConfig=MagicMock,
)

ha_components = _mod("homeassistant.components")

# ---------------------------------------------------------------------------
# homeassistant.helpers.storage
# ---------------------------------------------------------------------------


class _MockStore:
    """Minimal Store stub — enough for _Store to subclass without becoming a Mock."""

    def __init__(self, hass, version, key, **kwargs):
        pass

    async def async_load(self):
        return None

    async def async_save(self, data):
        pass


ha_storage = _mod("homeassistant.helpers.storage", Store=_MockStore)

# ---------------------------------------------------------------------------
# homeassistant.helpers.event
# ---------------------------------------------------------------------------

ha_event = _mod(
    "homeassistant.helpers.event",
    async_track_utc_time_change=MagicMock(return_value=lambda: None),
    async_track_point_in_time=MagicMock(return_value=lambda: None),
)

# ---------------------------------------------------------------------------
# Register all mocks before any component code is imported
# ---------------------------------------------------------------------------

_MOCKS = {
    "homeassistant": MagicMock(),
    "homeassistant.util": ha_util,
    "homeassistant.util.dt": ha_dt,
    "homeassistant.core": ha_core,
    "homeassistant.const": ha_const,
    "homeassistant.components": ha_components,
    "homeassistant.components.sensor": ha_sensor_mod,
    "homeassistant.components.device_automation": ha_da,
    "homeassistant.components.frontend": ha_frontend,
    "homeassistant.components.http": ha_http,
    "homeassistant.components.diagnostics": MagicMock(),
    "homeassistant.config_entries": MagicMock(),
    "homeassistant.helpers": MagicMock(),
    "homeassistant.helpers.update_coordinator": ha_upd_coord,
    "homeassistant.helpers.selector": ha_selector,
    "homeassistant.helpers.event": ha_event,
    "homeassistant.helpers.aiohttp_client": MagicMock(),
    "homeassistant.helpers.storage": ha_storage,
    "homeassistant.helpers.device_registry": MagicMock(),
    "homeassistant.helpers.entity_platform": MagicMock(),
    "homeassistant.helpers.entity_registry": MagicMock(),
}

for name, mock in _MOCKS.items():
    sys.modules[name] = mock
