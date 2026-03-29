"""Tests for __init__.py service helpers."""

from unittest.mock import MagicMock

from custom_components.electricity_price import _target_entry_ids
from custom_components.electricity_price.const import DOMAIN


def _make_hass(*entry_ids):
    hass = MagicMock()
    entries = []
    for eid in entry_ids:
        e = MagicMock()
        e.entry_id = eid
        e.runtime_data = MagicMock()
        entries.append(e)
    hass.config_entries.async_entries.return_value = entries
    return hass


def _make_call(device_id):
    call = MagicMock()
    call.data = {"device_id": device_id}
    return call


def _setup_entity_registry(entity_entries):
    import homeassistant.helpers.entity_registry as er_mod
    mock_reg = MagicMock()
    mock_reg.entities.values.return_value = entity_entries
    er_mod.async_get = MagicMock(return_value=mock_reg)
    return mock_reg


def _entity(entity_id, config_entry_id, platform=DOMAIN, device_id=None):
    e = MagicMock()
    e.entity_id = entity_id
    e.config_entry_id = config_entry_id
    e.platform = platform
    e.device_id = device_id
    return e


class TestTargetEntryIdsDeviceId:
    def test_device_id_resolves_via_entity_registry(self):
        hass = _make_hass("entry1")
        _setup_entity_registry([_entity("sensor.price", "entry1", device_id="dev_abc")])
        result = _target_entry_ids(hass, _make_call("dev_abc"))
        assert result == ["entry1"]

    def test_device_from_different_platform_is_excluded(self):
        hass = _make_hass("entry1")
        _setup_entity_registry([
            _entity("sensor.other", "entry1", platform="other_domain", device_id="dev_abc")
        ])
        result = _target_entry_ids(hass, _make_call("dev_abc"))
        assert result == []

    def test_unknown_device_id_returns_empty(self):
        hass = _make_hass("entry1")
        _setup_entity_registry([_entity("sensor.price", "entry1", device_id="dev_xyz")])
        result = _target_entry_ids(hass, _make_call("dev_unknown"))
        assert result == []

    def test_multiple_entities_same_device_deduplicated(self):
        hass = _make_hass("entry1")
        _setup_entity_registry([
            _entity("sensor.price", "entry1", device_id="dev_abc"),
            _entity("sensor.level", "entry1", device_id="dev_abc"),
        ])
        result = _target_entry_ids(hass, _make_call("dev_abc"))
        assert len(result) == 1
        assert result[0] == "entry1"

    def test_device_targets_correct_entry_among_multiple(self):
        hass = _make_hass("entry1", "entry2")
        _setup_entity_registry([
            _entity("sensor.fi_price", "entry1", device_id="dev_fi"),
            _entity("sensor.se_price", "entry2", device_id="dev_se"),
        ])
        result = _target_entry_ids(hass, _make_call("dev_fi"))
        assert result == ["entry1"]
