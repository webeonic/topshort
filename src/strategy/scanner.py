"""Market scanner for finding trading opportunities."""

import logging
from typing import Any, Callable, Dict, List, Optional

from ..config import ScannerConfig
from ..data.top_pairs_service import TopPairsService
from ..exchange.market_data import MarketData
from .detector import PumpDetector
from .order_block_breakout import OrderBlockBreakoutStrategy

logger = logging.getLogger(__name__)


class MarketScanner:
    """Scans market for trading opportunities."""

    def __init__(
        self,
        market_data: MarketData,
        config: ScannerConfig,
        top_pairs_service: Optional[TopPairsService] = None,
        order_block_strategy: Optional[OrderBlockBreakoutStrategy] = None,
    ):
        self.market_data = market_data
        self.config = config
        self.detector = PumpDetector(market_data, config)
        self.top_pairs_service = top_pairs_service
        self.order_block_strategy = order_block_strategy

    def get_symbol_universe(self, top_only: bool = False) -> List[str]:
        """Return list of tradable symbols (optionally limited to top pairs)."""
        if top_only and self.top_pairs_service:
            try:
                symbols = self.top_pairs_service.get_pairs()
                if symbols:
                    return symbols
            except Exception as exc:  # pragma: no cover - defensive logging
                logger.error(f"Failed to load top pairs: {exc}")

        return self.market_data.client.get_usdt_perpetual_symbols()

    def get_order_block_universe(self, limit: Optional[int] = None) -> List[str]:
        """Return curated subset for Order Block scanning."""
        symbols = self.get_symbol_universe(top_only=True)
        if limit and len(symbols) > limit:
            return symbols[:limit]
        return symbols

    def scan(
        self,
        top_n: int = 30,
        *,
        symbols: Optional[List[str]] = None,
        strategy_mode: str = "pump_cooldown",
        progress_callback: Optional[Callable[[int, int, int], None]] = None,
    ) -> List[Dict[str, Any]]:
        """Scan market and return top N opportunities.

        Args:
            top_n: Number of top opportunities to return.
            symbols: Optional explicit universe of symbols to scan.
            strategy_mode: Strategy identifier ('pump_cooldown' or 'order_block').
            progress_callback: Optional callback(processed, total, signals_found) for progress updates.

        Returns: List of dicts with symbol analysis, sorted by score
        """
        if strategy_mode == "order_block":
            return self._scan_order_block(top_n, symbols=symbols, progress_callback=progress_callback)

        logger.info(f"Starting market scan to find top {top_n} opportunities")
        return self._scan_pump(
            top_n,
            symbols=symbols,
            progress_callback=progress_callback,
        )

    def _scan_pump(
        self,
        top_n: int,
        symbols: Optional[List[str]] = None,
        progress_callback: Optional[Callable[[int, int, int], None]] = None,
    ) -> List[Dict[str, Any]]:
        results = self.market_data.scan_market(
            pump_threshold=self.config.pump_threshold_pct,
            pump_hours_min=self.config.pump_period_hours_min,
            pump_hours_max=self.config.pump_period_hours_max,
            cooldown_hours_min=self.config.cooldown_period_hours_min,
            cooldown_hours_max=self.config.cooldown_period_hours_max,
            volume_decrease_threshold=self.config.volume_decrease_threshold_pct,
            top_n=top_n,
            symbols=symbols,
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

    def _scan_order_block(
        self,
        top_n: int,
        symbols: Optional[List[str]] = None,
        progress_callback: Optional[Callable[[int, int, int], None]] = None,
    ) -> List[Dict[str, Any]]:
        if not self.order_block_strategy:
            raise ValueError("Order block strategy not configured")

        if not symbols:
            symbols = self.get_order_block_universe()

        signals = self.order_block_strategy.scan(
            symbols=symbols,
            top_n=top_n,
            progress_callback=progress_callback,
        )

        for i, signal in enumerate(signals[:5], 1):
            logger.info(
                f"[OrderBlock] #{i} {signal['symbol']} "
                f"dir={signal['direction']} "
                f"score={signal.get('score', 0):.1f} "
                f"entry={signal.get('entry_price')} "
                f"rr={signal.get('rr_ratio')} "
                f"session={'yes' if signal.get('session_match') else 'no'}"
            )

        return [dict(signal) for signal in signals]

    def quick_check(self, symbol: str) -> Dict:
        """Quick check if a single symbol meets criteria."""
        return self.detector.detect(symbol)
