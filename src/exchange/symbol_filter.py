"""Fast symbol pre-filtering to reduce OHLCV API requests.

This module provides quick rejection filtering using already-fetched ticker data
to eliminate symbols that clearly won't meet trading criteria. This dramatically
reduces the number of expensive OHLCV API calls needed during market scans.

Example:
    Pre-filtering 533 symbols to ~100 candidates before OHLCV fetch
    reduces scan time from 10-15 minutes to 2-3 minutes.
"""

import logging
from typing import Dict, List

logger = logging.getLogger(__name__)


class SymbolPreFilter:
    """Quick rejection filter using ticker data before OHLCV fetch.

    Uses 24h price change and volume from ticker data to quickly identify
    symbols that are unlikely to meet pump/cooldown criteria, avoiding
    expensive OHLCV API calls for those symbols.
    """

    def __init__(
        self,
        min_24h_change_pct: float = 10.0,
        min_volume_usdt: float = 100000.0,
    ):
        """Initialize the pre-filter with thresholds.

        Args:
            min_24h_change_pct: Minimum 24h price change to consider.
                               Default 10% as quick filter before detailed analysis.
            min_volume_usdt: Minimum 24h volume in USDT to consider.
                            Low-volume symbols are risky and often have poor liquidity.
        """
        self.min_24h_change_pct = min_24h_change_pct
        self.min_volume_usdt = min_volume_usdt

    def filter_for_pump_scan(
        self,
        symbols: List[str],
        tickers: Dict[str, Dict],
        pump_threshold_pct: float,
    ) -> List[str]:
        """Filter symbols likely to meet pump criteria.

        Logic: If 24h price change is small, unlikely to have 30%+ pump over 72h.
        Uses pump_threshold/3 as minimum (e.g., 10% for 30% threshold).

        Note: Symbol exclusions (e.g., existing positions) should be applied
        before calling this method, as they are semantic constraints independent
        of the performance optimization this filter provides.

        Args:
            symbols: Symbols to filter (already excluding any blacklisted symbols)
            tickers: Pre-fetched ticker data from fetch_tickers()
            pump_threshold_pct: Required pump percentage (e.g., 30.0)

        Returns:
            Filtered list of candidate symbols
        """
        if not symbols:
            return []

        # Use the more restrictive of: configured minimum OR pump_threshold/3
        quick_threshold = max(self.min_24h_change_pct, pump_threshold_pct / 3)

        candidates = []
        stats = {
            "no_ticker": 0,
            "low_change": 0,
            "low_volume": 0,
        }

        for symbol in symbols:
            ticker = tickers.get(symbol)
            if not ticker:
                stats["no_ticker"] += 1
                continue

            # Check 24h price change (use absolute - both pumps and dumps can lead to reversals)
            change_24h = abs(ticker.get("percentage") or 0)
            if change_24h < quick_threshold:
                stats["low_change"] += 1
                continue

            # Check 24h volume in quote currency (USDT)
            quote_volume = ticker.get("quoteVolume") or 0
            if quote_volume < self.min_volume_usdt:
                stats["low_volume"] += 1
                continue

            candidates.append(symbol)

        logger.info(
            f"Pre-filter: {len(symbols)} -> {len(candidates)} symbols "
            f"(no_ticker={stats['no_ticker']}, low_change={stats['low_change']}, "
            f"low_volume={stats['low_volume']})"
        )

        return candidates

    def filter_active_symbols(
        self,
        symbols: List[str],
        tickers: Dict[str, Dict],
    ) -> List[str]:
        """Filter to only actively traded symbols.

        Simple filter that just checks for minimum volume.
        Useful for Order Block and other strategies that don't need pump detection.

        Args:
            symbols: All available symbols
            tickers: Pre-fetched ticker data

        Returns:
            List of symbols with sufficient trading volume
        """
        if not symbols:
            return []

        candidates = []
        for symbol in symbols:
            ticker = tickers.get(symbol)
            if not ticker:
                continue

            quote_volume = ticker.get("quoteVolume") or 0
            if quote_volume >= self.min_volume_usdt:
                candidates.append(symbol)

        logger.debug(f"Volume filter: {len(symbols)} -> {len(candidates)} symbols")
        return candidates
