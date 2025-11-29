"""Tests for OHLCVCache - thread-safe OHLCV data caching."""

import threading
import time
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch

import pytest

from src.exchange.ohlcv_cache import TIMEFRAME_MINUTES, OHLCVCache


class TestOHLCVCacheBasics:
    """Basic functionality tests for OHLCVCache."""

    def test_cache_set_and_get(self):
        """Should store and retrieve OHLCV data."""
        cache = OHLCVCache()
        data = [[1700000000000, 100, 105, 95, 102, 1000]]

        cache.set("BTC/USDT:USDT", "1h", 100, data)
        result = cache.get("BTC/USDT:USDT", "1h", 100)

        assert result == data

    def test_cache_miss_returns_none(self):
        """Should return None for cache miss."""
        cache = OHLCVCache()

        result = cache.get("BTC/USDT:USDT", "1h", 100)

        assert result is None

    def test_cache_different_keys(self):
        """Different keys should be stored separately."""
        cache = OHLCVCache()
        data1 = [[1700000000000, 100, 105, 95, 102, 1000]]
        data2 = [[1700000000000, 200, 210, 190, 205, 2000]]
        data3 = [[1700000000000, 300, 315, 285, 310, 3000]]

        cache.set("BTC/USDT:USDT", "1h", 100, data1)
        cache.set("ETH/USDT:USDT", "1h", 100, data2)
        cache.set("BTC/USDT:USDT", "4h", 100, data3)

        assert cache.get("BTC/USDT:USDT", "1h", 100) == data1
        assert cache.get("ETH/USDT:USDT", "1h", 100) == data2
        assert cache.get("BTC/USDT:USDT", "4h", 100) == data3

    def test_cache_empty_data_not_stored(self):
        """Empty data should not be cached."""
        cache = OHLCVCache()

        cache.set("BTC/USDT:USDT", "1h", 100, [])

        assert cache.get("BTC/USDT:USDT", "1h", 100) is None
        assert len(cache) == 0

    def test_cache_len(self):
        """Should return correct number of cached entries."""
        cache = OHLCVCache()
        data = [[1700000000000, 100, 105, 95, 102, 1000]]

        assert len(cache) == 0

        cache.set("SYM1", "1h", 100, data)
        assert len(cache) == 1

        cache.set("SYM2", "1h", 100, data)
        assert len(cache) == 2


class TestOHLCVCacheExpiration:
    """Tests for cache expiration and TTL."""

    def test_expired_entry_returns_none(self):
        """Expired entries should return None and be removed."""
        cache = OHLCVCache()
        data = [[1700000000000, 100, 105, 95, 102, 1000]]

        cache.set("BTC/USDT:USDT", "1h", 100, data)

        # Manually expire the entry
        key = ("BTC/USDT:USDT", "1h", 100)
        cache._cache[key].expires_at = time.time() - 1

        result = cache.get("BTC/USDT:USDT", "1h", 100)

        assert result is None
        assert len(cache) == 0

    def test_cleanup_expired_removes_old_entries(self):
        """cleanup_expired should remove all expired entries."""
        cache = OHLCVCache()
        data = [[1700000000000, 100, 105, 95, 102, 1000]]

        # Add entries
        cache.set("SYM1", "1h", 100, data)
        cache.set("SYM2", "1h", 100, data)
        cache.set("SYM3", "1h", 100, data)

        # Expire some entries
        cache._cache[("SYM1", "1h", 100)].expires_at = time.time() - 1
        cache._cache[("SYM2", "1h", 100)].expires_at = time.time() - 1

        removed = cache.cleanup_expired()

        assert removed == 2
        assert len(cache) == 1
        assert cache.get("SYM3", "1h", 100) == data

    def test_cleanup_expired_returns_zero_when_nothing_expired(self):
        """cleanup_expired should return 0 when no entries are expired."""
        cache = OHLCVCache()
        data = [[1700000000000, 100, 105, 95, 102, 1000]]

        cache.set("SYM1", "1h", 100, data)

        removed = cache.cleanup_expired()

        assert removed == 0
        assert len(cache) == 1


class TestOHLCVCacheExpiryCalculation:
    """Tests for timeframe-aligned expiry calculation."""

    def test_calculate_expiry_aligns_to_hour(self):
        """1h timeframe should expire at next hour boundary."""
        cache = OHLCVCache()

        # Mock datetime to a known time
        with patch("src.exchange.ohlcv_cache.datetime") as mock_dt:
            from datetime import datetime, timezone

            # Set time to 14:30:00 UTC
            mock_now = datetime(2024, 1, 15, 14, 30, 0, tzinfo=timezone.utc)
            mock_dt.now.return_value = mock_now
            mock_dt.side_effect = lambda *args, **kw: datetime(*args, **kw)

            with patch("src.exchange.ohlcv_cache.time") as mock_time:
                mock_time.time.return_value = 1705329000.0  # epoch for 14:30

                expiry = cache._calculate_expiry("1h")

                # Should expire at 15:00:00 + 5s buffer = 30min + 5s from now
                expected_seconds = 30 * 60 + 5
                assert abs(expiry - (mock_time.time.return_value + expected_seconds)) < 1

    def test_calculate_expiry_aligns_to_4h(self):
        """4h timeframe should expire at next 4h boundary."""
        cache = OHLCVCache()

        with patch("src.exchange.ohlcv_cache.datetime") as mock_dt:
            from datetime import datetime, timezone

            # Set time to 14:30:00 UTC (within 12:00-16:00 4h period)
            mock_now = datetime(2024, 1, 15, 14, 30, 0, tzinfo=timezone.utc)
            mock_dt.now.return_value = mock_now
            mock_dt.side_effect = lambda *args, **kw: datetime(*args, **kw)

            with patch("src.exchange.ohlcv_cache.time") as mock_time:
                mock_time.time.return_value = 1705329000.0

                expiry = cache._calculate_expiry("4h")

                # Should expire at 16:00:00 + 5s buffer = 1h30m + 5s from now
                expected_seconds = 90 * 60 + 5
                assert abs(expiry - (mock_time.time.return_value + expected_seconds)) < 1

    def test_calculate_expiry_unknown_timeframe_defaults_to_1h(self):
        """Unknown timeframe should default to 1h (60 min)."""
        cache = OHLCVCache()

        expiry = cache._calculate_expiry("unknown")

        # Should be sometime within the next hour
        assert expiry > time.time()
        assert expiry < time.time() + 3700  # Within ~1 hour

    def test_calculate_expiry_handles_midnight_rollover(self):
        """Expiry calculation should handle day rollover correctly.

        Bug fix: At 23:30 with 2h timeframe, next period is midnight (00:00).
        Previously, modulo arithmetic caused negative seconds_until_expiry.
        """
        cache = OHLCVCache()

        with patch("src.exchange.ohlcv_cache.datetime") as mock_dt:
            from datetime import datetime, timezone

            # Set time to 23:30:00 UTC - next 2h boundary is midnight
            mock_now = datetime(2024, 1, 15, 23, 30, 0, tzinfo=timezone.utc)
            mock_dt.now.return_value = mock_now
            mock_dt.side_effect = lambda *args, **kw: datetime(*args, **kw)

            with patch("src.exchange.ohlcv_cache.time") as mock_time:
                mock_time.time.return_value = 1705361400.0  # epoch for 23:30 UTC

                expiry = cache._calculate_expiry("2h")

                # Should expire at midnight (00:00) + 5s buffer = 30min + 5s
                expected_seconds = 30 * 60 + 5
                actual_diff = expiry - mock_time.time.return_value

                # Verify expiry is in the future (not negative/past)
                assert actual_diff > 0, f"Expiry should be in future, got {actual_diff}s"
                assert abs(actual_diff - expected_seconds) < 1

    def test_calculate_expiry_4h_near_midnight(self):
        """4h timeframe at 23:00 should expire at midnight."""
        cache = OHLCVCache()

        with patch("src.exchange.ohlcv_cache.datetime") as mock_dt:
            from datetime import datetime, timezone

            # Set time to 23:00:00 UTC - in 20:00-00:00 period
            mock_now = datetime(2024, 1, 15, 23, 0, 0, tzinfo=timezone.utc)
            mock_dt.now.return_value = mock_now
            mock_dt.side_effect = lambda *args, **kw: datetime(*args, **kw)

            with patch("src.exchange.ohlcv_cache.time") as mock_time:
                mock_time.time.return_value = 1705359600.0  # epoch for 23:00 UTC

                expiry = cache._calculate_expiry("4h")

                # Should expire at midnight (00:00) + 5s buffer = 1h + 5s
                expected_seconds = 60 * 60 + 5
                actual_diff = expiry - mock_time.time.return_value

                assert actual_diff > 0, f"Expiry should be in future, got {actual_diff}s"
                assert abs(actual_diff - expected_seconds) < 1


class TestOHLCVCacheLRU:
    """Tests for LRU eviction behavior."""

    def test_lru_eviction_removes_oldest(self):
        """When at capacity, oldest entries should be evicted."""
        cache = OHLCVCache(max_entries=3)
        data = [[1700000000000, 100, 105, 95, 102, 1000]]

        # Fill cache
        cache.set("SYM1", "1h", 100, data)
        cache.set("SYM2", "1h", 100, data)
        cache.set("SYM3", "1h", 100, data)

        # Add one more, should evict SYM1
        cache.set("SYM4", "1h", 100, data)

        assert len(cache) == 3
        assert cache.get("SYM1", "1h", 100) is None  # Evicted
        assert cache.get("SYM2", "1h", 100) == data
        assert cache.get("SYM3", "1h", 100) == data
        assert cache.get("SYM4", "1h", 100) == data

    def test_lru_access_updates_order(self):
        """Accessing an entry should move it to end (most recently used)."""
        cache = OHLCVCache(max_entries=3)
        data = [[1700000000000, 100, 105, 95, 102, 1000]]

        # Fill cache
        cache.set("SYM1", "1h", 100, data)
        cache.set("SYM2", "1h", 100, data)
        cache.set("SYM3", "1h", 100, data)

        # Access SYM1 (moves it to end)
        cache.get("SYM1", "1h", 100)

        # Add new entry, should evict SYM2 (now oldest)
        cache.set("SYM4", "1h", 100, data)

        assert cache.get("SYM1", "1h", 100) == data  # Still exists (was accessed)
        assert cache.get("SYM2", "1h", 100) is None  # Evicted
        assert cache.get("SYM3", "1h", 100) == data
        assert cache.get("SYM4", "1h", 100) == data


class TestOHLCVCacheInvalidation:
    """Tests for cache invalidation."""

    def test_invalidate_symbol_all_timeframes(self):
        """invalidate(symbol) should remove all timeframes for that symbol."""
        cache = OHLCVCache()
        data = [[1700000000000, 100, 105, 95, 102, 1000]]

        cache.set("BTC/USDT:USDT", "1h", 100, data)
        cache.set("BTC/USDT:USDT", "4h", 100, data)
        cache.set("ETH/USDT:USDT", "1h", 100, data)

        removed = cache.invalidate("BTC/USDT:USDT")

        assert removed == 2
        assert cache.get("BTC/USDT:USDT", "1h", 100) is None
        assert cache.get("BTC/USDT:USDT", "4h", 100) is None
        assert cache.get("ETH/USDT:USDT", "1h", 100) == data

    def test_invalidate_symbol_specific_timeframe(self):
        """invalidate(symbol, timeframe) should remove only that timeframe."""
        cache = OHLCVCache()
        data = [[1700000000000, 100, 105, 95, 102, 1000]]

        cache.set("BTC/USDT:USDT", "1h", 100, data)
        cache.set("BTC/USDT:USDT", "4h", 100, data)

        removed = cache.invalidate("BTC/USDT:USDT", "1h")

        assert removed == 1
        assert cache.get("BTC/USDT:USDT", "1h", 100) is None
        assert cache.get("BTC/USDT:USDT", "4h", 100) == data

    def test_invalidate_nonexistent_symbol(self):
        """Invalidating nonexistent symbol should return 0."""
        cache = OHLCVCache()

        removed = cache.invalidate("NONEXISTENT")

        assert removed == 0

    def test_clear_removes_all_and_resets_stats(self):
        """clear() should remove all entries and reset statistics."""
        cache = OHLCVCache()
        data = [[1700000000000, 100, 105, 95, 102, 1000]]

        cache.set("SYM1", "1h", 100, data)
        cache.set("SYM2", "1h", 100, data)
        cache.get("SYM1", "1h", 100)  # Hit
        cache.get("NONEXISTENT", "1h", 100)  # Miss

        cache.clear()

        assert len(cache) == 0
        stats = cache.get_stats()
        assert stats["entries"] == 0
        assert stats["hits"] == 0
        assert stats["misses"] == 0


class TestOHLCVCacheStatistics:
    """Tests for cache statistics tracking."""

    def test_stats_initial_values(self):
        """New cache should have zero stats."""
        cache = OHLCVCache(max_entries=100)
        stats = cache.get_stats()

        assert stats["entries"] == 0
        assert stats["max_entries"] == 100
        assert stats["hits"] == 0
        assert stats["misses"] == 0
        assert stats["hit_rate_pct"] == 0

    def test_stats_tracks_hits(self):
        """Successful cache gets should increment hits."""
        cache = OHLCVCache()
        data = [[1700000000000, 100, 105, 95, 102, 1000]]

        cache.set("SYM1", "1h", 100, data)
        cache.get("SYM1", "1h", 100)
        cache.get("SYM1", "1h", 100)

        stats = cache.get_stats()
        assert stats["hits"] == 2
        assert stats["misses"] == 0

    def test_stats_tracks_misses(self):
        """Cache misses should increment misses."""
        cache = OHLCVCache()

        cache.get("SYM1", "1h", 100)
        cache.get("SYM2", "1h", 100)

        stats = cache.get_stats()
        assert stats["hits"] == 0
        assert stats["misses"] == 2

    def test_stats_calculates_hit_rate(self):
        """Hit rate should be calculated correctly."""
        cache = OHLCVCache()
        data = [[1700000000000, 100, 105, 95, 102, 1000]]

        cache.set("SYM1", "1h", 100, data)

        # 3 hits
        cache.get("SYM1", "1h", 100)
        cache.get("SYM1", "1h", 100)
        cache.get("SYM1", "1h", 100)

        # 1 miss
        cache.get("SYM2", "1h", 100)

        stats = cache.get_stats()
        assert stats["hits"] == 3
        assert stats["misses"] == 1
        assert stats["hit_rate_pct"] == 75.0  # 3/4 = 75%


class TestOHLCVCacheThreadSafety:
    """Tests for thread safety."""

    def test_concurrent_reads_and_writes(self):
        """Cache should handle concurrent reads and writes safely."""
        cache = OHLCVCache(max_entries=1000)
        data = [[1700000000000, 100, 105, 95, 102, 1000]]
        errors = []

        def writer(symbol_id):
            try:
                for _ in range(100):
                    cache.set(f"SYM{symbol_id}", "1h", 100, data)
            except Exception as e:
                errors.append(e)

        def reader(symbol_id):
            try:
                for _ in range(100):
                    cache.get(f"SYM{symbol_id}", "1h", 100)
            except Exception as e:
                errors.append(e)

        with ThreadPoolExecutor(max_workers=20) as executor:
            futures = []
            for i in range(10):
                futures.append(executor.submit(writer, i))
                futures.append(executor.submit(reader, i))

            for future in futures:
                future.result()

        assert len(errors) == 0

    def test_concurrent_invalidation(self):
        """Cache should handle concurrent invalidation safely."""
        cache = OHLCVCache(max_entries=1000)
        data = [[1700000000000, 100, 105, 95, 102, 1000]]
        errors = []

        # Pre-populate cache
        for i in range(100):
            cache.set(f"SYM{i}", "1h", 100, data)

        def invalidator():
            try:
                for i in range(100):
                    cache.invalidate(f"SYM{i}")
            except Exception as e:
                errors.append(e)

        def writer():
            try:
                for i in range(100):
                    cache.set(f"SYM{i}", "1h", 100, data)
            except Exception as e:
                errors.append(e)

        threads = [
            threading.Thread(target=invalidator),
            threading.Thread(target=writer),
            threading.Thread(target=invalidator),
            threading.Thread(target=writer),
        ]

        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0


class TestTimeframeMinutes:
    """Tests for TIMEFRAME_MINUTES constant."""

    def test_all_common_timeframes_defined(self):
        """All common timeframes should be defined."""
        expected_timeframes = ["1m", "3m", "5m", "15m", "30m", "1h", "2h", "4h", "6h", "8h", "12h", "1d"]

        for tf in expected_timeframes:
            assert tf in TIMEFRAME_MINUTES

    def test_timeframe_values_are_correct(self):
        """Timeframe minute values should be correct."""
        assert TIMEFRAME_MINUTES["1m"] == 1
        assert TIMEFRAME_MINUTES["5m"] == 5
        assert TIMEFRAME_MINUTES["15m"] == 15
        assert TIMEFRAME_MINUTES["1h"] == 60
        assert TIMEFRAME_MINUTES["4h"] == 240
        assert TIMEFRAME_MINUTES["1d"] == 1440
