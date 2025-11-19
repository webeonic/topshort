"""Market scanner for finding trading opportunities."""

import logging
from typing import Callable, Dict, List, Optional

from ..config import ScannerConfig
from ..exchange.market_data import MarketData
from .detector import PumpDetector

logger = logging.getLogger(__name__)


class MarketScanner:
    """Scans market for trading opportunities."""

    def __init__(self, market_data: MarketData, config: ScannerConfig):
        self.market_data = market_data
        self.config = config
        self.detector = PumpDetector(market_data, config)

    def scan(self, top_n: int = 30, progress_callback: Optional[Callable[[int, int, int], None]] = None) -> List[Dict]:
        """Scan market and return top N opportunities.

        Args:
            top_n: Number of top opportunities to return
            progress_callback: Optional callback(processed, total, signals_found) for progress updates

        Returns: List of dicts with symbol analysis, sorted by score
        """
        logger.info(f"Starting market scan to find top {top_n} opportunities")

        results = self.market_data.scan_market(
            pump_threshold=self.config.pump_threshold_pct,
            pump_hours_min=self.config.pump_period_hours_min,
            pump_hours_max=self.config.pump_period_hours_max,
            cooldown_hours_min=self.config.cooldown_period_hours_min,
            cooldown_hours_max=self.config.cooldown_period_hours_max,
            volume_decrease_threshold=self.config.volume_decrease_threshold_pct,
            top_n=top_n,
            progress_callback=progress_callback,
        )

        logger.info(f"Market scan completed: Found {len(results)} opportunities")

        # Log top 5 for visibility
        for i, result in enumerate(results[:5], 1):
            logger.info(
                f"#{i} {result['symbol']}: "
                f"Score={result['score']:.2f}, "
                f"Price change={result['price_change_pct']:.2f}%, "
                f"Volume change={result['volume_change_pct']:.2f}%"
            )

        return results

    def quick_check(self, symbol: str) -> Dict:
        """Quick check if a single symbol meets criteria."""
        return self.detector.detect(symbol)
