"""Tests for Order Block scan latency optimization features.

Tests cover:
1. Adaptive lookback - different candle counts per timeframe
2. Batch prefetch - parallel OHLCV data loading
"""

from types import SimpleNamespace
from unittest.mock import MagicMock

import pandas as pd
import pytest

from src.config import SessionWindow
from src.strategy.order_block_breakout import (
    MAX_CANDLES_PER_REQUEST,
    TIMEFRAME_LOOKBACK_MONTHS,
    TIMEFRAME_TO_MINUTES,
    OrderBlockBreakoutStrategy,
)


def _make_strategy(**overrides) -> OrderBlockBreakoutStrategy:
    """Create test strategy with sensible defaults."""
    defaults = {
        "lookback_months": 6,
        "swing_length": 10,
        "timeframes": ["1d", "4h", "1h", "15m", "5m"],
        "entry_timeframe": "15m",
        "confirmation_timeframe": "5m",
        "max_workers": 4,
        "atr_stop_multiplier": 1.5,
        "atr_target_multiplier": 2.0,
        "volume_spike_threshold": 2.0,
        "atr_period": 14,
        "min_fvg_size_pct": 0.3,
        "min_ob_score": 0.5,
        "volume_ma_period": 20,
        "high_volume_threshold": 1.5,
        "risk_per_trade_pct": 1.0,
        "max_signals": 10,
        "chunk_size": 10,
        "chunk_pause_ms": 0,
        "sessions_utc": [SessionWindow(name="London", start_utc="08:00", end_utc="10:00")],
    }
    defaults.update(overrides)
    config = SimpleNamespace(**defaults)
    market_data = MagicMock()
    return OrderBlockBreakoutStrategy(market_data, config)


def _generate_ohlcv(num_candles: int = 200) -> list:
    """Generate mock OHLCV data."""
    return [[i * 3600000, 100.0, 101.0, 99.0, 100.0, 1000.0] for i in range(num_candles)]


# ============================================================================
# Adaptive Lookback Tests
# ============================================================================


class TestAdaptiveLookback:
    """Tests for adaptive lookback per timeframe."""

    def test_htf_gets_fewer_candles_than_ltf(self):
        """1d should fetch fewer candles than 5m (same period, different granularity)."""
        strategy = _make_strategy()

        candles_1d = strategy._candles_for_timeframe("1d")
        candles_5m = strategy._candles_for_timeframe("5m")

        # 1d with 6 months = ~180 candles, 5m with 1 week = ~2016 (capped at 1500)
        assert candles_1d < candles_5m
        assert candles_1d < 300  # 6 months of daily candles should be ~180

    def test_respects_max_candles_limit(self):
        """All timeframes should respect MAX_CANDLES_PER_REQUEST cap."""
        strategy = _make_strategy()

        for tf in TIMEFRAME_TO_MINUTES:
            candles = strategy._candles_for_timeframe(tf)
            assert candles <= MAX_CANDLES_PER_REQUEST, f"{tf} exceeds max candles"

    def test_respects_minimum_candles(self):
        """Candle count should always be >= swing_length * 5."""
        strategy = _make_strategy(swing_length=20)

        for tf in TIMEFRAME_TO_MINUTES:
            candles = strategy._candles_for_timeframe(tf)
            assert candles >= 100, f"{tf} below minimum candles (swing_length * 5)"

    def test_unknown_timeframe_returns_minimum(self):
        """Unknown timeframe should fallback to swing_length * 5."""
        strategy = _make_strategy(swing_length=10)

        candles = strategy._candles_for_timeframe("unknown_tf")

        assert candles == 50  # swing_length * 5

    def test_uses_adaptive_lookback_from_mapping(self):
        """Should use TIMEFRAME_LOOKBACK_MONTHS for known timeframes."""
        strategy = _make_strategy(lookback_months=6)

        # 4h has 3 months lookback = 3*30*24/4 = 540 candles
        candles_4h = strategy._candles_for_timeframe("4h")
        assert candles_4h == 540

        # 1h has 1.5 months lookback = 1.5*30*24 = 1080 candles
        candles_1h = strategy._candles_for_timeframe("1h")
        assert candles_1h == 1080

    def test_falls_back_to_config_for_unmapped_timeframes(self):
        """Timeframes not in TIMEFRAME_LOOKBACK_MONTHS use config.lookback_months."""
        strategy = _make_strategy(lookback_months=3)

        # 30m is in TIMEFRAME_TO_MINUTES but not in TIMEFRAME_LOOKBACK_MONTHS
        # So it should use config.lookback_months (3 months) = 3*30*24*2 = 4320, capped at 1500
        candles_30m = strategy._candles_for_timeframe("30m")
        assert candles_30m == MAX_CANDLES_PER_REQUEST  # Capped


# ============================================================================
# Batch Prefetch Tests
# ============================================================================


class TestBatchPrefetch:
    """Tests for batch OHLCV prefetching."""

    def test_prefetch_creates_correct_task_count(self):
        """Should create symbol × timeframe tasks."""
        strategy = _make_strategy(timeframes=["1h", "15m"])
        strategy.market_data.client.get_ohlcv.return_value = _generate_ohlcv(200)

        result = strategy._prefetch_ohlcv_batch(["SYM1", "SYM2"])

        # 2 symbols × 2 timeframes = 4 calls
        assert strategy.market_data.client.get_ohlcv.call_count == 4
        assert "SYM1" in result
        assert "SYM2" in result

    def test_prefetch_returns_correct_structure(self):
        """Result should be Dict[symbol, Dict[timeframe, DataFrame]]."""
        strategy = _make_strategy(timeframes=["1h"])
        strategy.market_data.client.get_ohlcv.return_value = _generate_ohlcv(200)

        result = strategy._prefetch_ohlcv_batch(["SYM1"])

        assert "SYM1" in result
        assert "1h" in result["SYM1"]
        assert isinstance(result["SYM1"]["1h"], pd.DataFrame)

    def test_partial_failure_continues_other_symbols(self):
        """Failed fetches should not stop other symbols from being fetched."""
        strategy = _make_strategy(timeframes=["1h"])

        def selective_fail(symbol, **kwargs):
            if "FAIL" in symbol:
                raise Exception("API error")
            return _generate_ohlcv(200)

        strategy.market_data.client.get_ohlcv.side_effect = selective_fail

        result = strategy._prefetch_ohlcv_batch(["GOOD1", "FAIL1", "GOOD2"])

        assert "GOOD1" in result and result["GOOD1"]
        assert "FAIL1" not in result or not result["FAIL1"]
        assert "GOOD2" in result and result["GOOD2"]

    def test_empty_symbols_returns_empty(self):
        """Empty symbols list should return empty dict immediately."""
        strategy = _make_strategy()

        result = strategy._prefetch_ohlcv_batch([])

        assert result == {}
        assert strategy.market_data.client.get_ohlcv.call_count == 0

    def test_insufficient_data_excluded_from_results(self):
        """Symbols with insufficient candles should be excluded."""
        strategy = _make_strategy(timeframes=["1h"], swing_length=100)
        # Return only 10 candles, which is less than swing_length * 4 = 400
        strategy.market_data.client.get_ohlcv.return_value = _generate_ohlcv(10)

        result = strategy._prefetch_ohlcv_batch(["SYM1"])

        # SYM1 should be in results but with empty timeframe dict
        assert not result.get("SYM1", {}).get("1h")


# ============================================================================
# Scan with Prefetch Tests
# ============================================================================


class TestScanWithPrefetch:
    """Tests for scan method with batch prefetch integration."""

    def test_scan_uses_prefetched_data_by_default(self):
        """Scan should use analyze_from_datasets with prefetched data."""
        strategy = _make_strategy(timeframes=["1h"])
        strategy.market_data.client.get_ohlcv.return_value = _generate_ohlcv(200)

        # Track which method is called
        calls = []
        original_analyze_from_datasets = strategy.analyze_from_datasets

        def spy(sym, data):
            calls.append((sym, list(data.keys())))
            return {"symbol": sym, "meets_criteria": False, "score": 0}

        strategy.analyze_from_datasets = spy

        strategy.scan(["SYM1", "SYM2"], use_batch_prefetch=True)

        assert len(calls) == 2
        symbols_analyzed = {c[0] for c in calls}
        assert symbols_analyzed == {"SYM1", "SYM2"}

    def test_scan_fallback_when_prefetch_disabled(self):
        """With prefetch=False, should call analyze() directly."""
        strategy = _make_strategy(timeframes=["1h"])

        analyze_calls = []

        def mock_analyze(sym):
            analyze_calls.append(sym)
            return {"symbol": sym, "meets_criteria": False, "score": 0}

        strategy.analyze = mock_analyze

        strategy.scan(["SYM1"], use_batch_prefetch=False)

        assert "SYM1" in analyze_calls

    def test_scan_fallback_for_failed_prefetch(self):
        """If prefetch fails for a symbol, should fallback to analyze()."""
        strategy = _make_strategy(timeframes=["1h"])

        # Prefetch will fail
        strategy.market_data.client.get_ohlcv.side_effect = Exception("API error")

        analyze_calls = []

        def mock_analyze(sym):
            analyze_calls.append(sym)
            return {"symbol": sym, "meets_criteria": False, "score": 0}

        strategy.analyze = mock_analyze

        strategy.scan(["SYM1"], use_batch_prefetch=True)

        # Should have fallen back to analyze()
        assert "SYM1" in analyze_calls

    def test_scan_empty_symbols_returns_empty(self):
        """Empty symbols should return empty list without API calls."""
        strategy = _make_strategy()

        result = strategy.scan([])

        assert result == []
        assert strategy.market_data.client.get_ohlcv.call_count == 0

    def test_scan_returns_sorted_by_score(self):
        """Results should be sorted by score descending."""
        strategy = _make_strategy(timeframes=["1h"])
        strategy.market_data.client.get_ohlcv.return_value = _generate_ohlcv(200)

        # Return signals with different scores
        scores = {"SYM1": 30, "SYM2": 80, "SYM3": 50}

        def mock_analyze(sym, data):
            return {"symbol": sym, "meets_criteria": True, "score": scores[sym]}

        strategy.analyze_from_datasets = mock_analyze

        result = strategy.scan(["SYM1", "SYM2", "SYM3"])

        assert [s["symbol"] for s in result] == ["SYM2", "SYM3", "SYM1"]

    def test_scan_respects_top_n_limit(self):
        """Should return at most top_n signals."""
        strategy = _make_strategy(timeframes=["1h"])
        strategy.market_data.client.get_ohlcv.return_value = _generate_ohlcv(200)

        def mock_analyze(sym, data):
            return {"symbol": sym, "meets_criteria": True, "score": 50}

        strategy.analyze_from_datasets = mock_analyze

        result = strategy.scan(["S1", "S2", "S3", "S4", "S5"], top_n=2)

        assert len(result) == 2


# ============================================================================
# Integration Tests
# ============================================================================


class TestIntegration:
    """Integration tests combining adaptive lookback and batch prefetch."""

    def test_prefetch_uses_adaptive_candle_counts(self):
        """Prefetch should request different candle counts per timeframe."""
        strategy = _make_strategy(timeframes=["1d", "5m"])
        strategy.market_data.client.get_ohlcv.return_value = _generate_ohlcv(200)

        strategy._prefetch_ohlcv_batch(["SYM1"])

        # Check the limit parameter in each call
        calls = strategy.market_data.client.get_ohlcv.call_args_list
        limits = {call.kwargs.get("timeframe"): call.kwargs.get("limit") for call in calls}

        # 1d should have fewer candles than 5m
        assert limits["1d"] < limits["5m"]
