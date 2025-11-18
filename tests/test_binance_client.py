"""Tests for BinanceClient."""

import logging
from unittest.mock import Mock, patch

import pytest

from src.exchange.binance_client import BinanceClient


@pytest.fixture
def binance_client():
    """Create BinanceClient instance for testing."""
    # Use testnet mode with dummy credentials
    return BinanceClient(api_key="test_key", api_secret="test_secret", testnet=True)


class TestCloseShortPosition:
    """Test close_short_position method."""

    def test_close_short_position_success_logs(self, binance_client, caplog):
        """Test that successful close logs correctly."""
        with caplog.at_level(logging.INFO):
            # Mock successful order creation
            with patch.object(binance_client, "create_market_order") as mock_create:
                mock_create.return_value = {"id": "ORDER123", "average": 47500.0, "status": "closed"}

                result = binance_client.close_short_position("BTCUSDT", 0.1)

                assert result is not None
                assert result["id"] == "ORDER123"
                # Should log success message
                assert "Closed short position: BTCUSDT" in caplog.text

    def test_close_short_position_error_2022_no_log(self, binance_client, caplog):
        """Test that error -2022 (position already closed) doesn't log success."""
        with caplog.at_level(logging.INFO):
            # Mock error -2022 response
            with patch.object(binance_client, "create_market_order") as mock_create:
                mock_create.return_value = {"error_code": -2022, "message": "Position already closed"}

                result = binance_client.close_short_position("BTCUSDT", 0.1)

                assert result is not None
                assert result["error_code"] == -2022
                # Should NOT log success message
                assert "Closed short position: BTCUSDT" not in caplog.text

    def test_close_short_position_none_no_log(self, binance_client, caplog):
        """Test that None response doesn't log success."""
        with caplog.at_level(logging.INFO):
            # Mock None response
            with patch.object(binance_client, "create_market_order") as mock_create:
                mock_create.return_value = None

                result = binance_client.close_short_position("BTCUSDT", 0.1)

                assert result is None
                # Should NOT log success message
                assert "Closed short position: BTCUSDT" not in caplog.text

    def test_close_short_position_returns_error_dict(self, binance_client):
        """Test that error dict is returned correctly."""
        with patch.object(binance_client, "create_market_order") as mock_create:
            error_dict = {"error_code": -2022, "message": "Position already closed"}
            mock_create.return_value = error_dict

            result = binance_client.close_short_position("BTCUSDT", 0.1)

            assert result == error_dict
            assert result["error_code"] == -2022
