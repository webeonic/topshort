"""Thread-safe OHLCV data cache with smart TTL.

This module provides caching for OHLCV (candlestick) data with intelligent TTL
based on timeframe boundaries. For example, 1-hour data expires at the start
of the next hour, ensuring cached data is always fresh.

The cache uses LRU eviction to prevent unbounded memory growth.
"""

import logging
import threading
import time
from collections import OrderedDict
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# Mapping of timeframe strings to minutes
TIMEFRAME_MINUTES = {
    "1m": 1,
    "3m": 3,
    "5m": 5,
    "15m": 15,
    "30m": 30,
    "1h": 60,
    "2h": 120,
    "4h": 240,
    "6h": 360,
    "8h": 480,
    "12h": 720,
    "1d": 1440,
}


@dataclass
class CacheEntry:
    """Single cache entry with metadata."""

    data: List[List]
    fetched_at: float
    expires_at: float
    timeframe: str


class OHLCVCache:
    """Thread-safe OHLCV cache with smart TTL based on timeframe.

    Features:
    - Smart TTL: Cache expires at timeframe boundary (e.g., 1h data expires at next hour)
    - Memory-Bounded: LRU eviction when max_entries is reached
    - Thread-Safe: Uses RLock for all operations
    - Statistics: Tracks hits/misses for monitoring
    """

    def __init__(self, max_entries: int = 5000):
        """Initialize the OHLCV cache.

        Args:
            max_entries: Maximum number of cache entries before LRU eviction.
                        Default 5000 is sufficient for most use cases.
        """
        self._cache: OrderedDict[Tuple[str, str, int], CacheEntry] = OrderedDict()
        self._lock = threading.RLock()
        self._max_entries = max_entries
        self._hits = 0
        self._misses = 0

    def get(self, symbol: str, timeframe: str, limit: int) -> Optional[List[List]]:
        """Get cached OHLCV data if valid.

        Args:
            symbol: Trading symbol (e.g., "BTC/USDT:USDT")
            timeframe: Timeframe string (e.g., "1h", "4h")
            limit: Number of candles

        Returns:
            Cached OHLCV data if valid and not expired, None otherwise.
        """
        key = (symbol, timeframe, limit)
        with self._lock:
            entry = self._cache.get(key)
            if entry and time.time() < entry.expires_at:
                # Move to end for LRU tracking
                self._cache.move_to_end(key)
                self._hits += 1
                return entry.data
            elif entry:
                # Expired - remove it
                del self._cache[key]
            self._misses += 1
            return None

    def set(self, symbol: str, timeframe: str, limit: int, data: List[List]) -> None:
        """Store OHLCV data with smart TTL.

        Args:
            symbol: Trading symbol
            timeframe: Timeframe string
            limit: Number of candles
            data: OHLCV data to cache
        """
        if not data:
            return

        key = (symbol, timeframe, limit)
        expires_at = self._calculate_expiry(timeframe)

        with self._lock:
            # Evict oldest entries if at capacity
            while len(self._cache) >= self._max_entries:
                self._cache.popitem(last=False)

            self._cache[key] = CacheEntry(
                data=data,
                fetched_at=time.time(),
                expires_at=expires_at,
                timeframe=timeframe,
            )

    def _calculate_expiry(self, timeframe: str) -> float:
        """Calculate expiry timestamp aligned to timeframe boundary.

        For example:
        - "1h" data fetched at 14:30 expires at 15:00
        - "4h" data fetched at 14:30 expires at 16:00 (next 4h mark)
        - "1d" data fetched at any time expires at midnight UTC

        Args:
            timeframe: Timeframe string

        Returns:
            Unix timestamp when the cached data should expire.
        """
        minutes = TIMEFRAME_MINUTES.get(timeframe, 60)
        now = datetime.now(timezone.utc)

        # Calculate seconds since midnight UTC
        total_seconds = now.hour * 3600 + now.minute * 60 + now.second
        period_seconds = minutes * 60

        # Find current period and calculate next period start
        current_period = total_seconds // period_seconds
        next_period_seconds = (current_period + 1) * period_seconds

        # Handle day rollover for daily timeframe
        if next_period_seconds >= 86400:
            next_period_seconds = next_period_seconds % 86400

        seconds_until_expiry = next_period_seconds - total_seconds
        if seconds_until_expiry <= 0:
            seconds_until_expiry += period_seconds

        # Add small buffer (5 seconds) to ensure we don't serve stale data
        return time.time() + seconds_until_expiry + 5

    def invalidate(self, symbol: str, timeframe: Optional[str] = None) -> int:
        """Invalidate cache entries for a symbol.

        Args:
            symbol: Symbol to invalidate
            timeframe: Optional specific timeframe to invalidate.
                      If None, invalidates all timeframes for the symbol.

        Returns:
            Number of entries removed.
        """
        removed = 0
        with self._lock:
            keys_to_remove = [k for k in self._cache.keys() if k[0] == symbol and (timeframe is None or k[1] == timeframe)]
            for key in keys_to_remove:
                del self._cache[key]
                removed += 1
        if removed > 0:
            logger.debug(f"Invalidated {removed} cache entries for {symbol}")
        return removed

    def clear(self) -> None:
        """Clear all cached data and reset statistics."""
        with self._lock:
            self._cache.clear()
            self._hits = 0
            self._misses = 0
        logger.debug("OHLCV cache cleared")

    def get_stats(self) -> Dict:
        """Get cache statistics.

        Returns:
            Dict with entries count, hits, misses, and hit rate percentage.
        """
        with self._lock:
            total = self._hits + self._misses
            return {
                "entries": len(self._cache),
                "max_entries": self._max_entries,
                "hits": self._hits,
                "misses": self._misses,
                "hit_rate_pct": round(self._hits / total * 100, 2) if total > 0 else 0,
            }

    def cleanup_expired(self) -> int:
        """Remove expired entries from cache.

        This is normally not needed as expired entries are removed on access,
        but can be called periodically to free memory.

        Returns:
            Number of expired entries removed.
        """
        now = time.time()
        removed = 0
        with self._lock:
            keys_to_remove = [k for k, v in self._cache.items() if v.expires_at <= now]
            for key in keys_to_remove:
                del self._cache[key]
                removed += 1
        if removed > 0:
            logger.debug(f"Cleaned up {removed} expired cache entries")
        return removed

    def __len__(self) -> int:
        """Return number of cached entries."""
        with self._lock:
            return len(self._cache)
