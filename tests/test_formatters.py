"""Tests for bot formatters module."""

from src.bot.formatters import format_strategy_label


class TestFormatStrategyLabel:
    """Tests for format_strategy_label function."""

    def test_pump_cooldown_strategy(self):
        """Test pump_cooldown strategy formatting."""
        result = format_strategy_label("pump_cooldown")
        assert result == "Pump & Cooldown"

    def test_order_block_strategy(self):
        """Test order_block strategy formatting."""
        result = format_strategy_label("order_block")
        assert result == "Order Block"

    def test_none_strategy_returns_na(self):
        """Test that None strategy returns N/A."""
        result = format_strategy_label(None)
        assert result == "N/A"

    def test_empty_string_returns_na(self):
        """Test that empty string returns N/A."""
        result = format_strategy_label("")
        assert result == "N/A"

    def test_unknown_strategy_returns_original(self):
        """Test that unknown strategy returns original value."""
        result = format_strategy_label("custom_strategy")
        assert result == "custom_strategy"

    def test_unknown_strategy_preserves_case(self):
        """Test that unknown strategy preserves original case."""
        result = format_strategy_label("MyCustomStrategy")
        assert result == "MyCustomStrategy"
