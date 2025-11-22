"""Market scanner for finding trading opportunities."""

import logging
import time
from typing import Any, Callable, Dict, List, Optional

from ..config import ScannerConfig
from ..data.top_pairs_service import TopPairsService
from ..exchange.market_data import MarketData
from .detector import PumpDetector
from .order_block_breakout import OrderBlockBreakoutStrategy, OrderBlockSignal

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
        yield_callback: Optional[Callable[[], None]] = None,
    ) -> List[Dict[str, Any]]:
        """Scan market and return top N opportunities.

        Args:
            top_n: Number of top opportunities to return.
            symbols: Optional explicit universe of symbols to scan.
            strategy_mode: Strategy identifier ('pump_cooldown' or 'order_block').
            progress_callback: Optional callback(processed, total, signals_found) for progress updates.
            yield_callback: Optional callable invoked between chunks to yield control.

        Returns: List of dicts with symbol analysis, sorted by score
        """
        if strategy_mode == "order_block":
            return self._scan_order_block(
                top_n,
                symbols=symbols,
                progress_callback=progress_callback,
                yield_callback=yield_callback,
            )

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
        yield_callback: Optional[Callable[[], None]] = None,
    ) -> List[Dict[str, Any]]:
        if not self.order_block_strategy:
            raise ValueError("Order block strategy not configured")

        if not symbols:
            symbols = self.get_order_block_universe()

        if not symbols:
            return []

        raw_chunk_size = getattr(self.order_block_strategy.config, "chunk_size", len(symbols))
        if isinstance(raw_chunk_size, (int, float)):
            chunk_size = int(raw_chunk_size)
        else:
            chunk_size = len(symbols)
        chunk_size = max(1, chunk_size)

        raw_pause_ms = getattr(self.order_block_strategy.config, "chunk_pause_ms", 0)
        if isinstance(raw_pause_ms, (int, float)):
            pause_seconds = max(0, float(raw_pause_ms)) / 1000.0
        else:
            pause_seconds = 0.0

        total_symbols = len(symbols)
        combined_signals: List[OrderBlockSignal] = []
        processed = 0

        for chunk_start in range(0, total_symbols, chunk_size):
            chunk = symbols[chunk_start : chunk_start + chunk_size]
            chunk_base = processed
            signals_before = len(combined_signals)

            def chunk_progress(chunk_processed: int, chunk_total: int, chunk_signals: int):
                if progress_callback:
                    progress_callback(
                        chunk_base + chunk_processed,
                        total_symbols,
                        signals_before + chunk_signals,
                    )

            chunk_signals = self.order_block_strategy.scan(
                symbols=chunk,
                top_n=min(top_n, len(chunk)),
                progress_callback=chunk_progress if progress_callback else None,
                max_workers=getattr(self.order_block_strategy.config, "max_workers", None),
            )
            combined_signals.extend(chunk_signals)
            processed += len(chunk)

            if progress_callback:
                progress_callback(processed, total_symbols, len(combined_signals))

            if yield_callback:
                yield_callback()
            elif pause_seconds > 0:
                time.sleep(pause_seconds)

        combined_signals.sort(key=lambda item: item.get("score", 0), reverse=True)

        for i, signal in enumerate(combined_signals[:5], 1):
            logger.info(
                f"[OrderBlock] #{i} {signal['symbol']} "
                f"dir={signal['direction']} "
                f"score={signal.get('score', 0):.1f} "
                f"entry={signal.get('entry_price')} "
                f"rr={signal.get('rr_ratio')} "
                f"session={'yes' if signal.get('session_match') else 'no'}"
            )

        return [dict(signal) for signal in combined_signals[:top_n]]

    def quick_check(self, symbol: str) -> Dict:
        """Quick check if a single symbol meets criteria."""
        return self.detector.detect(symbol)
