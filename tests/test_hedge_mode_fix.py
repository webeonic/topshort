"""Test that hedge mode is set only once in multi-threaded environment."""

import logging
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import MagicMock, patch

import pytest

from src.exchange.binance_client import BinanceClient

# Capture logs
logging.basicConfig(level=logging.DEBUG)


@pytest.fixture
def mock_binance():
    """Mock CCXT Binance client."""
    with patch("src.exchange.binance_client.ccxt.binance") as mock_ccxt:
        mock_exchange = MagicMock()
        mock_exchange.fapiPrivatePostPositionSideDual.return_value = {"code": 200, "msg": "success"}
        mock_exchange.set_sandbox_mode = MagicMock()
        mock_exchange.load_markets = MagicMock(return_value={})
        mock_ccxt.return_value = mock_exchange
        yield mock_exchange


def test_hedge_mode_set_once_in_multithread(mock_binance, caplog):
    """Test that hedge mode is only set once even with multiple threads."""
    caplog.set_level(logging.INFO)

    # Create client
    client = BinanceClient(api_key="test", api_secret="test", testnet=True)

    # Simulate multiple threads accessing exchange (like in parallel scan)
    def access_exchange():
        """Access exchange from thread."""
        _ = client.exchange  # This creates thread-local exchange
        return True

    # Run 10 threads in parallel
    with ThreadPoolExecutor(max_workers=10) as executor:
        futures = [executor.submit(access_exchange) for _ in range(10)]
        results = [f.result() for f in futures]

    # All should succeed
    assert all(results)

    # Count how many times hedge mode was actually set (not just attempted)
    info_logs = [record for record in caplog.records if record.levelname == "INFO"]
    hedge_mode_logs = [log for log in info_logs if "Position mode set to HEDGE mode" in log.message]

    # Should only be set once due to our flag
    assert len(hedge_mode_logs) == 1, f"Hedge mode was set {len(hedge_mode_logs)} times, expected 1"


def test_hedge_mode_handles_already_set_error(caplog):
    """Test that -4059 error is handled gracefully."""
    caplog.set_level(logging.DEBUG)

    with patch("src.exchange.binance_client.ccxt.binance") as mock_ccxt:
        mock_exchange = MagicMock()
        # Simulate error that hedge mode is already set
        mock_exchange.fapiPrivatePostPositionSideDual.side_effect = Exception(
            'binance {"code":-4059,"msg":"No need to change position side."}'
        )
        mock_exchange.set_sandbox_mode = MagicMock()
        mock_exchange.load_markets = MagicMock(return_value={})
        mock_ccxt.return_value = mock_exchange

        # Create client - should not raise exception
        client = BinanceClient(api_key="test", api_secret="test", testnet=True)

        # Check debug log instead of warning
        debug_logs = [record for record in caplog.records if record.levelname == "DEBUG"]
        hedge_logs = [log for log in debug_logs if "Hedge mode already enabled" in log.message]

        # Should log as debug, not warning
        assert len(hedge_logs) == 1

        # Verify hedge mode flag was set to True
        assert client._hedge_mode_set is True
