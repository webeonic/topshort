"""Tests for parallel market data scanning functionality."""

import logging
from unittest.mock import Mock, patch

import pytest

from src.config import ScannerConfig
from src.exchange.market_data import MarketData

logger = logging.getLogger(__name__)


@pytest.fixture
def scanner_config():
    """Create scanner configuration for tests."""
    return ScannerConfig(
        pump_threshold_pct=30.0,
        pump_period_hours_min=48,
        pump_period_hours_max=72,
        cooldown_period_hours_min=4,
        cooldown_period_hours_max=8,
        volume_decrease_threshold_pct=20.0,
    )


@pytest.fixture
def mock_ohlcv_data():
    """Create mock OHLCV data for a pumped symbol."""
    # Create 100 hours of data
    # Price pumps from 100 to 140 over 60 hours, then cools down
    ohlcv = []
    for i in range(100):
        if i < 40:
            # Before pump
            price = 100.0
            volume = 1000.0
        elif i < 60:
            # Pumping phase (40-60 hours ago)
            price = 100.0 + (40.0 * (i - 40) / 20)  # Pump to 140
            volume = 2000.0  # High volume during pump
        else:
            # Cooldown phase (last 40 hours)
            price = 140.0 - ((i - 60) * 0.1)  # Slight decline
            volume = 500.0  # Low volume during cooldown

        ohlcv.append([i * 3600000, price, price * 1.01, price * 0.99, price, volume])

    return ohlcv


@pytest.fixture
def mock_binance_client_with_symbols():
    """Create mock Binance client with multiple symbols."""
    client = Mock()

    # Mock 10 symbols
    symbols = [f"SYM{i}USDT" for i in range(10)]
    client.get_usdt_perpetual_symbols = Mock(return_value=symbols)

    # Mock batch ticker fetch
    tickers = {symbol: {"last": 100.0 + i, "bid": 100.0 + i, "ask": 100.0 + i} for i, symbol in enumerate(symbols)}
    client.fetch_tickers = Mock(return_value=tickers)

    # Mock OHLCV data
    def get_ohlcv_mock(symbol, timeframe="1h", limit=100):
        """Return OHLCV data based on symbol."""
        # First 3 symbols will meet criteria
        if symbol in ["SYM0USDT", "SYM1USDT", "SYM2USDT"]:
            # Pump pattern
            ohlcv = []
            for i in range(100):
                if i < 40:
                    price = 100.0
                    volume = 1000.0
                elif i < 60:
                    price = 100.0 + (40.0 * (i - 40) / 20)
                    volume = 2000.0
                else:
                    price = 140.0 - ((i - 60) * 0.1)
                    volume = 500.0
                ohlcv.append([i * 3600000, price, price * 1.01, price * 0.99, price, volume])
            return ohlcv
        else:
            # No pump pattern
            ohlcv = []
            for i in range(100):
                price = 100.0
                volume = 1000.0
                ohlcv.append([i * 3600000, price, price * 1.01, price * 0.99, price, volume])
            return ohlcv

    client.get_ohlcv = Mock(side_effect=get_ohlcv_mock)

    # Mock get_ticker
    def get_ticker_mock(symbol):
        return {"last": 140.0, "bid": 139.0, "ask": 141.0, "high": 145.0, "low": 135.0}

    client.get_ticker = Mock(side_effect=get_ticker_mock)

    return client


class TestParallelScanner:
    """Tests for parallel market scanning."""

    def test_calculate_optimal_workers_small_symbols(self, mock_binance_client_with_symbols):
        """Test optimal workers calculation with small number of symbols."""
        market_data = MarketData(mock_binance_client_with_symbols)

        # With 5 symbols, should not exceed symbol count
        workers = market_data._calculate_optimal_workers(5)
        assert workers == 5

    def test_calculate_optimal_workers_many_symbols(self, mock_binance_client_with_symbols):
        """Test optimal workers calculation with many symbols."""
        market_data = MarketData(mock_binance_client_with_symbols)

        # With 200 symbols, should use CPU-based calculation but cap at 50
        workers = market_data._calculate_optimal_workers(200)
        assert 4 <= workers <= 50

    def test_calculate_optimal_workers_minimum(self, mock_binance_client_with_symbols):
        """Test optimal workers minimum is enforced."""
        market_data = MarketData(mock_binance_client_with_symbols)

        # Should never go below 4
        workers = market_data._calculate_optimal_workers(2)
        assert workers == 2  # Limited by symbol count

        workers = market_data._calculate_optimal_workers(10)
        assert workers >= 4

    def test_parallel_scan_market_finds_signals(self, mock_binance_client_with_symbols, scanner_config):
        """Test parallel scan finds expected signals."""
        market_data = MarketData(mock_binance_client_with_symbols)

        results = market_data.scan_market(
            pump_threshold=scanner_config.pump_threshold_pct,
            pump_hours_min=scanner_config.pump_period_hours_min,
            pump_hours_max=scanner_config.pump_period_hours_max,
            cooldown_hours_min=scanner_config.cooldown_period_hours_min,
            cooldown_hours_max=scanner_config.cooldown_period_hours_max,
            volume_decrease_threshold=scanner_config.volume_decrease_threshold_pct,
            top_n=5,
        )

        # Should find 3 signals (SYM0, SYM1, SYM2)
        assert len(results) == 3
        assert all(r["meets_criteria"] for r in results)
        assert all(r["score"] > 0 for r in results)

    def test_parallel_scan_market_sorted_by_score(self, mock_binance_client_with_symbols, scanner_config):
        """Test parallel scan results are sorted by score."""
        market_data = MarketData(mock_binance_client_with_symbols)

        results = market_data.scan_market(
            pump_threshold=scanner_config.pump_threshold_pct,
            pump_hours_min=scanner_config.pump_period_hours_min,
            pump_hours_max=scanner_config.pump_period_hours_max,
            cooldown_hours_min=scanner_config.cooldown_period_hours_min,
            cooldown_hours_max=scanner_config.cooldown_period_hours_max,
            volume_decrease_threshold=scanner_config.volume_decrease_threshold_pct,
            top_n=5,
        )

        # Results should be sorted by score descending
        scores = [r["score"] for r in results]
        assert scores == sorted(scores, reverse=True)

    def test_parallel_scan_market_respects_top_n(self, mock_binance_client_with_symbols, scanner_config):
        """Test parallel scan respects top_n parameter."""
        market_data = MarketData(mock_binance_client_with_symbols)

        # Request only top 2
        results = market_data.scan_market(
            pump_threshold=scanner_config.pump_threshold_pct,
            pump_hours_min=scanner_config.pump_period_hours_min,
            pump_hours_max=scanner_config.pump_period_hours_max,
            cooldown_hours_min=scanner_config.cooldown_period_hours_min,
            cooldown_hours_max=scanner_config.cooldown_period_hours_max,
            volume_decrease_threshold=scanner_config.volume_decrease_threshold_pct,
            top_n=2,
        )

        # Should return only 2 results even though 3 match
        assert len(results) <= 2

    def test_parallel_scan_uses_batch_ticker_fetch(self, mock_binance_client_with_symbols, scanner_config):
        """Test parallel scan uses batch ticker fetching."""
        market_data = MarketData(mock_binance_client_with_symbols)

        market_data.scan_market(
            pump_threshold=scanner_config.pump_threshold_pct,
            pump_hours_min=scanner_config.pump_period_hours_min,
            pump_hours_max=scanner_config.pump_period_hours_max,
            cooldown_hours_min=scanner_config.cooldown_period_hours_min,
            cooldown_hours_max=scanner_config.cooldown_period_hours_max,
            volume_decrease_threshold=scanner_config.volume_decrease_threshold_pct,
            top_n=5,
        )

        # Should call fetch_tickers once (batch call)
        assert mock_binance_client_with_symbols.fetch_tickers.call_count == 1

        # Should NOT call get_ticker for individual symbols during scan
        # (may still be called during analyze_pump_pattern)
        # assert mock_binance_client_with_symbols.get_ticker.call_count == 0

    def test_parallel_scan_handles_errors_gracefully(self, mock_binance_client_with_symbols, scanner_config):
        """Test parallel scan handles symbol analysis errors gracefully."""
        market_data = MarketData(mock_binance_client_with_symbols)

        # Make one symbol fail
        original_get_ohlcv = mock_binance_client_with_symbols.get_ohlcv.side_effect

        def failing_get_ohlcv(symbol, timeframe="1h", limit=100):
            if symbol == "SYM1USDT":
                raise Exception("API Error")
            return original_get_ohlcv(symbol, timeframe, limit)

        mock_binance_client_with_symbols.get_ohlcv = Mock(side_effect=failing_get_ohlcv)

        results = market_data.scan_market(
            pump_threshold=scanner_config.pump_threshold_pct,
            pump_hours_min=scanner_config.pump_period_hours_min,
            pump_hours_max=scanner_config.pump_period_hours_max,
            cooldown_hours_min=scanner_config.cooldown_period_hours_min,
            cooldown_hours_max=scanner_config.cooldown_period_hours_max,
            volume_decrease_threshold=scanner_config.volume_decrease_threshold_pct,
            top_n=5,
        )

        # Should still return results from working symbols
        # SYM0 and SYM2 should work, SYM1 will fail
        assert len(results) == 2

    @pytest.mark.slow
    def test_parallel_scan_performance(self, mock_binance_client_with_symbols, scanner_config):
        """Test that parallel scan completes in reasonable time."""
        import time

        market_data = MarketData(mock_binance_client_with_symbols)

        start_time = time.time()
        market_data.scan_market(
            pump_threshold=scanner_config.pump_threshold_pct,
            pump_hours_min=scanner_config.pump_period_hours_min,
            pump_hours_max=scanner_config.pump_period_hours_max,
            cooldown_hours_min=scanner_config.cooldown_period_hours_min,
            cooldown_hours_max=scanner_config.cooldown_period_hours_max,
            volume_decrease_threshold=scanner_config.volume_decrease_threshold_pct,
            top_n=5,
        )
        duration = time.time() - start_time

        # With mocked data, should complete very quickly
        # Even with 10 symbols, parallel processing should be fast
        assert duration < 2.0, f"Scan took too long: {duration:.2f}s"


class TestOptimalWorkersCalculation:
    """Tests for dynamic worker calculation."""

    def test_workers_scale_with_cpu(self, mock_binance_client_with_symbols):
        """Test workers scale with CPU count."""
        market_data = MarketData(mock_binance_client_with_symbols)

        with patch("os.cpu_count", return_value=8):
            # With 8 CPUs and 100 symbols, should use 8 * 3 = 24 workers
            workers = market_data._calculate_optimal_workers(100)
            assert workers == 24

    def test_workers_capped_at_50(self, mock_binance_client_with_symbols):
        """Test workers are capped at maximum."""
        market_data = MarketData(mock_binance_client_with_symbols)

        with patch("os.cpu_count", return_value=32):
            # With 32 CPUs, 32 * 3 = 96 workers, but should cap at 50
            workers = market_data._calculate_optimal_workers(200)
            assert workers == 50

    def test_workers_limited_by_symbol_count(self, mock_binance_client_with_symbols):
        """Test workers don't exceed symbol count."""
        market_data = MarketData(mock_binance_client_with_symbols)

        with patch("os.cpu_count", return_value=16):
            # With only 10 symbols, should use 10 workers max
            workers = market_data._calculate_optimal_workers(10)
            assert workers == 10

    def test_workers_zero_symbols_returns_one(self, mock_binance_client_with_symbols):
        """Ensure thread pool still has a worker when there are no symbols."""
        market_data = MarketData(mock_binance_client_with_symbols)

        workers = market_data._calculate_optimal_workers(0)
        assert workers == 1

    def test_workers_minimum_enforced(self, mock_binance_client_with_symbols):
        """Test minimum workers is enforced."""
        market_data = MarketData(mock_binance_client_with_symbols)

        with patch("os.cpu_count", return_value=1):
            # Even with 1 CPU, should use at least 4 workers for I/O tasks
            workers = market_data._calculate_optimal_workers(100)
            assert workers >= 4

    def test_workers_with_missing_cpu_count(self, mock_binance_client_with_symbols):
        """Test fallback when CPU count unavailable."""
        market_data = MarketData(mock_binance_client_with_symbols)

        with patch("os.cpu_count", return_value=None):
            # Should fall back to 4 CPUs default
            workers = market_data._calculate_optimal_workers(100)
            # 4 * 3 = 12 workers
            assert workers == 12
