"""Market data fetching and analysis."""

import logging
import statistics
from datetime import datetime, timedelta
from typing import Dict, List, Optional

from .binance_client import BinanceClient

logger = logging.getLogger(__name__)


class MarketData:
    """Market data analyzer."""

    def __init__(self, client: BinanceClient):
        self.client = client

    def calculate_price_change(self, ohlcv: List[List], hours: int) -> Optional[float]:
        """Calculate price change percentage over specified hours.

        Args:
            ohlcv: OHLCV data [timestamp, open, high, low, close, volume]
            hours: Number of hours to look back

        Returns: Price change percentage or None
        """
        if not ohlcv or len(ohlcv) < hours:
            return None

        # Use close prices
        start_price = ohlcv[-hours][4]  # Close price from 'hours' ago
        current_price = ohlcv[-1][4]  # Current close price

        if start_price == 0:
            return None

        price_change_pct = ((current_price - start_price) / start_price) * 100
        return price_change_pct

    def calculate_volume_change(self, ohlcv: List[List], recent_hours: int, older_hours: int) -> Optional[float]:
        """Calculate volume change between two periods.

        Args:
            ohlcv: OHLCV data
            recent_hours: Recent period (e.g., last 4-8 hours)
            older_hours: Older period to compare against

        Returns: Volume change percentage (negative means decrease)
        """
        if not ohlcv or len(ohlcv) < (recent_hours + older_hours):
            return None

        # Calculate average volume for recent period
        recent_volumes = [candle[5] for candle in ohlcv[-recent_hours:]]
        avg_recent_volume = statistics.mean(recent_volumes) if recent_volumes else 0

        # Calculate average volume for older period (before recent period)
        older_start = -(recent_hours + older_hours)
        older_end = -recent_hours
        older_volumes = [candle[5] for candle in ohlcv[older_start:older_end]]
        avg_older_volume = statistics.mean(older_volumes) if older_volumes else 0

        if avg_older_volume == 0:
            return None

        volume_change_pct = ((avg_recent_volume - avg_older_volume) / avg_older_volume) * 100
        return volume_change_pct

    def get_symbol_metrics(self, symbol: str, pump_hours: int = 72, cooldown_hours: int = 8) -> Optional[Dict]:
        """Get comprehensive metrics for a symbol.

        Args:
            symbol: Trading symbol
            pump_hours: Hours to check for pump (48-72)
            cooldown_hours: Hours to check for cooldown (4-8)

        Returns: Dict with metrics or None
        """
        try:
            # Fetch OHLCV data (need enough data for analysis)
            # Add extra hours for volume comparison
            total_hours = pump_hours + cooldown_hours + 24
            ohlcv = self.client.get_ohlcv(symbol, timeframe="1h", limit=total_hours)

            if not ohlcv or len(ohlcv) < total_hours:
                logger.debug(f"Insufficient data for {symbol}")
                return None

            # Calculate metrics
            price_change_pct = self.calculate_price_change(ohlcv, pump_hours)
            volume_change_pct = self.calculate_volume_change(ohlcv, cooldown_hours, pump_hours)

            # Get current price and volume
            current_candle = ohlcv[-1]
            current_price = current_candle[4]
            current_volume = current_candle[5]

            # Calculate 24h volume
            volume_24h = sum(candle[5] for candle in ohlcv[-24:])

            # Get ticker for additional data
            ticker = self.client.get_ticker(symbol)

            return {
                "symbol": symbol,
                "current_price": current_price,
                "price_change_pct": price_change_pct,
                "volume_change_pct": volume_change_pct,
                "current_volume": current_volume,
                "volume_24h": volume_24h,
                "bid": ticker.get("bid") if ticker else None,
                "ask": ticker.get("ask") if ticker else None,
                "high_24h": ticker.get("high") if ticker else None,
                "low_24h": ticker.get("low") if ticker else None,
            }

        except Exception as e:
            logger.error(f"Error getting metrics for {symbol}: {e}")
            return None

    def analyze_pump_pattern(
        self,
        symbol: str,
        pump_threshold: float,
        pump_hours_min: int,
        pump_hours_max: int,
        cooldown_hours_min: int,
        cooldown_hours_max: int,
        volume_decrease_threshold: float,
    ) -> Dict:
        """Analyze if symbol shows pump and cooldown pattern.

        Args:
            symbol: Trading symbol
            pump_threshold: Minimum price increase percentage (e.g., 30%)
            pump_hours_min: Minimum hours for pump period (e.g., 48)
            pump_hours_max: Maximum hours for pump period (e.g., 72)
            cooldown_hours_min: Minimum hours for cooldown (e.g., 4)
            cooldown_hours_max: Maximum hours for cooldown (e.g., 8)
            volume_decrease_threshold: Volume decrease threshold (e.g., 20%)

        Returns: Dict with analysis results
        """
        # Use midpoint for analysis
        pump_hours = (pump_hours_min + pump_hours_max) // 2
        cooldown_hours = (cooldown_hours_min + cooldown_hours_max) // 2

        metrics = self.get_symbol_metrics(symbol, pump_hours, cooldown_hours)

        if not metrics:
            return {"symbol": symbol, "is_pump": False, "is_cooldown": False, "score": 0.0, "reason": "Insufficient data"}

        price_change = metrics.get("price_change_pct", 0)
        volume_change = metrics.get("volume_change_pct", 0)

        # Check if there was a pump
        is_pump = price_change >= pump_threshold

        # Check if volume is decreasing (cooldown)
        is_cooldown = volume_change < -volume_decrease_threshold

        # Calculate score (0-100)
        score = 0.0
        if is_pump and is_cooldown:
            # Weight price change and volume decrease
            price_score = min(price_change / pump_threshold * 50, 50)
            volume_score = min(abs(volume_change) / volume_decrease_threshold * 50, 50)
            score = price_score + volume_score

        reason = ""
        if not is_pump:
            reason = f"Price change {price_change:.2f}% < {pump_threshold}%"
        elif not is_cooldown:
            reason = f"Volume change {volume_change:.2f}% > -{volume_decrease_threshold}%"
        else:
            reason = f"Pump detected: +{price_change:.2f}%, Volume cooling: {volume_change:.2f}%"

        return {
            "symbol": symbol,
            "is_pump": is_pump,
            "is_cooldown": is_cooldown,
            "meets_criteria": is_pump and is_cooldown,
            "score": round(score, 2),
            "price_change_pct": round(price_change, 2),
            "volume_change_pct": round(volume_change, 2),
            "current_price": metrics["current_price"],
            "volume_24h": metrics["volume_24h"],
            "reason": reason,
        }

    def scan_market(
        self,
        pump_threshold: float,
        pump_hours_min: int,
        pump_hours_max: int,
        cooldown_hours_min: int,
        cooldown_hours_max: int,
        volume_decrease_threshold: float,
        top_n: int = 30,
    ) -> List[Dict]:
        """Scan market for symbols matching criteria.

        Returns: List of top N symbols sorted by score
        """
        logger.info("Starting market scan...")

        symbols = self.client.get_usdt_perpetual_symbols()
        logger.info(f"Scanning {len(symbols)} USDT perpetual symbols")

        results = []
        for i, symbol in enumerate(symbols):
            if i % 50 == 0:
                logger.info(f"Scanned {i}/{len(symbols)} symbols...")

            analysis = self.analyze_pump_pattern(
                symbol=symbol,
                pump_threshold=pump_threshold,
                pump_hours_min=pump_hours_min,
                pump_hours_max=pump_hours_max,
                cooldown_hours_min=cooldown_hours_min,
                cooldown_hours_max=cooldown_hours_max,
                volume_decrease_threshold=volume_decrease_threshold,
            )

            if analysis.get("meets_criteria"):
                results.append(analysis)

        # Sort by score descending
        results.sort(key=lambda x: x["score"], reverse=True)

        # Take top N
        top_results = results[:top_n]

        logger.info(f"Market scan completed: Found {len(results)} matching symbols, returning top {len(top_results)}")

        return top_results
