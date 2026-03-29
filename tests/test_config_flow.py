"""Tests for config_flow helper functions."""

import json

import pytest

from custom_components.electricity_price.config_flow import (
    _build_thresholds,
    _load_tiers,
    _thresholds_to_str,
)
from custom_components.electricity_price.const import CONF_THRESHOLDS, DEFAULT_THRESHOLDS


# ---------------------------------------------------------------------------
# _thresholds_to_str
# ---------------------------------------------------------------------------


class TestThresholdsToStr:
    def test_serializes_to_json(self):
        result = _thresholds_to_str([{"name": "Cheap", "below": 5.0}])
        assert json.loads(result) == [{"name": "Cheap", "below": 5.0}]

    def test_roundtrip_preserves_structure(self):
        tiers = [
            {"name": "Low", "color": "#0f0", "below": 5.0},
            {"name": "High", "color": "#f00", "below": None},
        ]
        assert json.loads(_thresholds_to_str(tiers)) == tiers

    def test_empty_list(self):
        assert json.loads(_thresholds_to_str([])) == []


# ---------------------------------------------------------------------------
# _load_tiers
# ---------------------------------------------------------------------------


class TestLoadTiers:
    def test_loads_from_json_string(self):
        tiers = [
            {"name": "A", "below": 5.0, "color": "#fff"},
            {"name": "B", "below": None, "color": "#000"},
        ]
        opts = {CONF_THRESHOLDS: json.dumps(tiers)}
        assert _load_tiers(opts) == tiers

    def test_loads_from_list_directly(self):
        tiers = [{"name": "A", "below": 5.0}]
        opts = {CONF_THRESHOLDS: tiers}
        assert _load_tiers(opts) == tiers

    def test_falls_back_to_defaults_when_key_missing(self):
        assert _load_tiers({}) == list(DEFAULT_THRESHOLDS)

    def test_falls_back_when_value_is_empty_list_string(self):
        assert _load_tiers({CONF_THRESHOLDS: "[]"}) == list(DEFAULT_THRESHOLDS)

    def test_falls_back_when_value_is_empty_list(self):
        assert _load_tiers({CONF_THRESHOLDS: []}) == list(DEFAULT_THRESHOLDS)

    def test_falls_back_on_invalid_json(self):
        assert _load_tiers({CONF_THRESHOLDS: "not valid json {"}) == list(DEFAULT_THRESHOLDS)

    def test_falls_back_when_value_is_none(self):
        assert _load_tiers({CONF_THRESHOLDS: None}) == list(DEFAULT_THRESHOLDS)


# ---------------------------------------------------------------------------
# _build_thresholds
# ---------------------------------------------------------------------------


class TestBuildThresholds:
    def test_builds_two_tier_thresholds(self):
        user_input = {
            "tier_1_name": "Cheap",
            "tier_1_color": "#00ff00",
            "tier_1_below": 8.0,
            "tier_2_name": "Expensive",
            "tier_2_color": "#ff0000",
        }
        result = _build_thresholds(user_input, 2)
        assert result == [
            {"name": "Cheap", "color": "#00ff00", "below": 8.0},
            {"name": "Expensive", "color": "#ff0000", "below": None},
        ]

    def test_builds_three_tier_thresholds(self):
        user_input = {
            "tier_1_name": "Low",
            "tier_1_color": "#0f0",
            "tier_1_below": 5.0,
            "tier_2_name": "Mid",
            "tier_2_color": "#ff0",
            "tier_2_below": 12.0,
            "tier_3_name": "High",
            "tier_3_color": "#f00",
        }
        result = _build_thresholds(user_input, 3)
        assert len(result) == 3
        assert result[0]["below"] == 5.0
        assert result[1]["below"] == 12.0
        assert result[2]["below"] is None

    def test_single_tier_no_below(self):
        result = _build_thresholds({"tier_1_name": "Any", "tier_1_color": "#fff"}, 1)
        assert result == [{"name": "Any", "color": "#fff", "below": None}]

    def test_raises_on_empty_tier_name(self):
        user_input = {
            "tier_1_name": "",
            "tier_1_color": "#fff",
            "tier_1_below": 5.0,
            "tier_2_name": "High",
            "tier_2_color": "#f00",
        }
        with pytest.raises(ValueError, match="name is required"):
            _build_thresholds(user_input, 2)

    def test_raises_on_whitespace_only_name(self):
        user_input = {
            "tier_1_name": "   ",
            "tier_1_color": "#fff",
            "tier_1_below": 5.0,
            "tier_2_name": "High",
            "tier_2_color": "#f00",
        }
        with pytest.raises(ValueError, match="name is required"):
            _build_thresholds(user_input, 2)

    def test_raises_when_intermediate_below_is_none(self):
        # tier_1_below missing → treated as None → must raise
        user_input = {
            "tier_1_name": "Low",
            "tier_1_color": "#fff",
            "tier_2_name": "High",
            "tier_2_color": "#000",
        }
        with pytest.raises(ValueError, match="missing an upper limit"):
            _build_thresholds(user_input, 2)

    def test_raises_when_below_values_not_strictly_increasing(self):
        user_input = {
            "tier_1_name": "Low",
            "tier_1_color": "#fff",
            "tier_1_below": 10.0,
            "tier_2_name": "Mid",
            "tier_2_color": "#ff0",
            "tier_2_below": 5.0,  # lower than tier_1_below
            "tier_3_name": "High",
            "tier_3_color": "#f00",
        }
        with pytest.raises(ValueError, match="must be greater than"):
            _build_thresholds(user_input, 3)

    def test_raises_when_below_values_equal(self):
        user_input = {
            "tier_1_name": "Low",
            "tier_1_color": "#fff",
            "tier_1_below": 8.0,
            "tier_2_name": "Mid",
            "tier_2_color": "#ff0",
            "tier_2_below": 8.0,  # equal to previous
            "tier_3_name": "High",
            "tier_3_color": "#f00",
        }
        with pytest.raises(ValueError, match="must be greater than"):
            _build_thresholds(user_input, 3)

    def test_default_color_used_when_missing(self):
        user_input = {
            "tier_1_name": "Low",
            "tier_1_below": 5.0,
            "tier_2_name": "High",
        }
        result = _build_thresholds(user_input, 2)
        assert result[0]["color"] == "#94a3b8"
