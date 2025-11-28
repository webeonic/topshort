"""Unit tests for metadata_utils module."""

import json

import pytest

from src.utils.metadata_utils import extract_strategy_from_metadata


class TestExtractStrategyFromMetadata:
    """Tests for extract_strategy_from_metadata function."""

    def test_valid_json_string(self):
        """Test extracting strategy from valid JSON string."""
        metadata = json.dumps({"strategy": "pump_cooldown", "score": 0.85})
        result = extract_strategy_from_metadata(metadata)

        assert result == "pump_cooldown"

    def test_valid_dict(self):
        """Test extracting strategy from dict."""
        metadata = {"strategy": "order_block", "rr_ratio": 2.5}
        result = extract_strategy_from_metadata(metadata)

        assert result == "order_block"

    def test_none_input(self):
        """Test None input returns None."""
        result = extract_strategy_from_metadata(None)

        assert result is None

    def test_empty_string(self):
        """Test empty string returns None."""
        result = extract_strategy_from_metadata("")

        assert result is None

    def test_invalid_json(self):
        """Test invalid JSON returns None."""
        result = extract_strategy_from_metadata("not valid json")

        assert result is None

    def test_malformed_json(self):
        """Test malformed JSON with syntax errors."""
        result = extract_strategy_from_metadata('{"strategy": invalid}')

        assert result is None

    def test_missing_strategy_key(self):
        """Test metadata without strategy key returns None."""
        metadata = json.dumps({"score": 0.75, "volume": 1000})
        result = extract_strategy_from_metadata(metadata)

        assert result is None

    def test_whitespace_only_input(self):
        """Test whitespace-only string returns None."""
        result = extract_strategy_from_metadata("   ")

        assert result is None

    def test_json_with_null_strategy(self):
        """Test JSON with null strategy value returns None."""
        metadata = json.dumps({"strategy": None, "score": 0.9})
        result = extract_strategy_from_metadata(metadata)

        assert result is None

    def test_nested_metadata_only_top_level(self):
        """Test that only top-level strategy key is extracted."""
        metadata = json.dumps({"strategy": "pump_cooldown", "details": {"strategy": "nested_should_be_ignored"}})
        result = extract_strategy_from_metadata(metadata)

        assert result == "pump_cooldown"

    def test_unicode_strategy_name(self):
        """Test Unicode characters in strategy name."""
        metadata = json.dumps({"strategy": "стратегия_тест"})
        result = extract_strategy_from_metadata(metadata)

        assert result == "стратегия_тест"

    def test_numeric_strategy_value(self):
        """Test non-string strategy value."""
        metadata = json.dumps({"strategy": 123})
        result = extract_strategy_from_metadata(metadata)

        # Should return the numeric value (JSON allows it)
        assert result == 123

    def test_boolean_strategy_value(self):
        """Test boolean strategy value."""
        metadata = json.dumps({"strategy": True})
        result = extract_strategy_from_metadata(metadata)

        assert result is True

    def test_empty_dict(self):
        """Test empty dict returns None."""
        result = extract_strategy_from_metadata({})

        assert result is None

    def test_empty_json_object(self):
        """Test empty JSON object string returns None."""
        result = extract_strategy_from_metadata("{}")

        assert result is None

    def test_large_metadata_object(self):
        """Test large metadata object with many keys."""
        metadata = {"strategy": "pump_cooldown", **{f"key_{i}": f"value_{i}" for i in range(100)}}
        result = extract_strategy_from_metadata(json.dumps(metadata))

        assert result == "pump_cooldown"

    def test_json_with_special_characters(self):
        """Test strategy name with special characters."""
        metadata = json.dumps({"strategy": "pump&cooldown_v2.0"})
        result = extract_strategy_from_metadata(metadata)

        assert result == "pump&cooldown_v2.0"

    def test_dict_with_extra_keys(self):
        """Test dict with many extra keys still extracts strategy."""
        metadata = {"strategy": "order_block", "score": 0.95, "volume": 10000, "timestamp": "2024-01-01", "rr_ratio": 3.0}
        result = extract_strategy_from_metadata(metadata)

        assert result == "order_block"

    def test_type_error_handling(self):
        """Test non-dict, non-string input returns None."""
        result = extract_strategy_from_metadata(12345)

        assert result is None

    def test_list_input(self):
        """Test list input returns None."""
        result = extract_strategy_from_metadata(["strategy", "pump_cooldown"])

        assert result is None
