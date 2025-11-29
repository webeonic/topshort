"""Tests for BinanceClient."""

import logging
from unittest.mock import Mock, patch

import pytest

from src.exchange.binance_client import BinanceClient


@pytest.fixture
def binance_client(monkeypatch):
    """Create BinanceClient instance for testing."""
    # Prevent real CCXT initialization/network calls during tests
    mock_exchange = Mock()
    mock_exchange.set_sandbox_mode = Mock()
    mock_exchange.fapiPrivatePostPositionSideDual = Mock(return_value={"dualSidePosition": True})

    def mock_binance_constructor(*args, **kwargs):
        return mock_exchange

    monkeypatch.setattr("src.exchange.binance_client.ccxt.binance", mock_binance_constructor)

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


class TestExchangeInitialization:
    """Tests for exchange initialization and configuration."""

    def test_create_exchange_instance_sets_hedge_mode(self, binance_client, monkeypatch):
        """Ensure each exchange instance configures hedge mode."""
        captured = {}

        def mock_set_hedge_mode(exchange=None):
            captured["exchange"] = exchange
            return True

        monkeypatch.setattr(binance_client, "_set_hedge_mode", mock_set_hedge_mode)

        exchange = binance_client._create_exchange_instance()

        assert captured["exchange"] is exchange


class TestFetchTickers:
    """Tests for fetch_tickers method - critical for scan performance."""

    def test_fetch_tickers_batch_success(self, binance_client):
        """Verify batch fetch returns dict mapping symbol to ticker."""
        # Setup mock to return all tickers
        mock_all_tickers = {
            "BTC/USDT:USDT": {"symbol": "BTC/USDT:USDT", "last": 50000.0, "percentage": 5.0},
            "ETH/USDT:USDT": {"symbol": "ETH/USDT:USDT", "last": 3000.0, "percentage": 3.0},
            "SOL/USDT:USDT": {"symbol": "SOL/USDT:USDT", "last": 100.0, "percentage": 10.0},
        }
        binance_client.exchange.fetch_tickers = Mock(return_value=mock_all_tickers)

        result = binance_client.fetch_tickers(["BTC/USDT:USDT", "ETH/USDT:USDT"])

        # Should return only requested symbols
        assert len(result) == 2
        assert "BTC/USDT:USDT" in result
        assert "ETH/USDT:USDT" in result
        assert "SOL/USDT:USDT" not in result
        # Verify single batch call was made
        assert binance_client.exchange.fetch_tickers.call_count == 1

    def test_fetch_tickers_no_fallback_on_error(self, binance_client):
        """Verify NO fallback to individual requests on error - this is critical for performance."""
        # Setup mock to raise exception
        binance_client.exchange.fetch_tickers = Mock(side_effect=Exception("API Error"))
        binance_client.exchange.fetch_ticker = Mock(return_value={"last": 50000.0})

        result = binance_client.fetch_tickers(["BTC/USDT:USDT", "ETH/USDT:USDT"])

        # Should return empty dict, NOT fall back to individual requests
        assert result == {}
        # Verify NO individual ticker calls were made
        assert binance_client.exchange.fetch_ticker.call_count == 0

    def test_fetch_tickers_filters_to_requested_symbols(self, binance_client):
        """Verify only requested symbols are returned from batch fetch."""
        # Mock returns more symbols than requested
        mock_all_tickers = {
            "BTC/USDT:USDT": {"last": 50000.0},
            "ETH/USDT:USDT": {"last": 3000.0},
            "XRP/USDT:USDT": {"last": 0.5},
            "DOGE/USDT:USDT": {"last": 0.1},
        }
        binance_client.exchange.fetch_tickers = Mock(return_value=mock_all_tickers)

        # Request only 2 symbols
        result = binance_client.fetch_tickers(["BTC/USDT:USDT", "XRP/USDT:USDT"])

        assert len(result) == 2
        assert "BTC/USDT:USDT" in result
        assert "XRP/USDT:USDT" in result
        assert "ETH/USDT:USDT" not in result
        assert "DOGE/USDT:USDT" not in result

    def test_fetch_tickers_handles_missing_symbols(self, binance_client):
        """Verify graceful handling when requested symbols not in exchange response."""
        mock_all_tickers = {
            "BTC/USDT:USDT": {"last": 50000.0},
        }
        binance_client.exchange.fetch_tickers = Mock(return_value=mock_all_tickers)

        # Request symbols that don't exist in response
        result = binance_client.fetch_tickers(["BTC/USDT:USDT", "NONEXISTENT/USDT:USDT"])

        assert len(result) == 1
        assert "BTC/USDT:USDT" in result
        assert "NONEXISTENT/USDT:USDT" not in result

    def test_fetch_tickers_empty_symbols_list(self, binance_client):
        """Verify empty list request returns empty result without API call."""
        mock_all_tickers = {"BTC/USDT:USDT": {"last": 50000.0}}
        binance_client.exchange.fetch_tickers = Mock(return_value=mock_all_tickers)

        result = binance_client.fetch_tickers([])

        assert result == {}
        # API should still be called (we fetch all tickers)
        assert binance_client.exchange.fetch_tickers.call_count == 1


class TestGetOHLCV:
    """Tests for get_ohlcv method."""

    def test_get_ohlcv_success(self, binance_client):
        """Verify OHLCV data is returned correctly."""
        mock_ohlcv = [
            [1700000000000, 50000.0, 51000.0, 49000.0, 50500.0, 1000.0],
            [1700003600000, 50500.0, 52000.0, 50000.0, 51500.0, 1200.0],
        ]
        binance_client.exchange.fetch_ohlcv = Mock(return_value=mock_ohlcv)

        result = binance_client.get_ohlcv("BTC/USDT:USDT", "1h", 2)

        assert result == mock_ohlcv
        assert len(result) == 2
        binance_client.exchange.fetch_ohlcv.assert_called_once_with("BTC/USDT:USDT", "1h", limit=2)

    def test_get_ohlcv_returns_empty_on_error(self, binance_client):
        """Verify empty list returned on error instead of exception."""
        binance_client.exchange.fetch_ohlcv = Mock(side_effect=Exception("Network error"))

        result = binance_client.get_ohlcv("BTC/USDT:USDT", "1h", 100)

        assert result == []

    def test_get_ohlcv_respects_timeframe(self, binance_client):
        """Verify timeframe parameter is passed correctly."""
        binance_client.exchange.fetch_ohlcv = Mock(return_value=[])

        binance_client.get_ohlcv("BTC/USDT:USDT", "4h", 50)

        binance_client.exchange.fetch_ohlcv.assert_called_once_with("BTC/USDT:USDT", "4h", limit=50)
