"""Trading engine - main trading logic coordinator."""

import json
import logging
import threading
import uuid
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from ..config import Config
from ..data.top_pairs_service import TopPairsService
from ..database.repository import MarketSignalRepository, ScanProgressRepository, SettingsRepository
from ..exchange.binance_client import BinanceClient
from ..exchange.market_data import MarketData
from ..strategy.order_block_breakout import OrderBlockBreakoutStrategy
from ..strategy.scanner import MarketScanner
from .position_manager import PositionManager
from .risk_manager import RiskManager

logger = logging.getLogger(__name__)


class TradingEngine:
    """Main trading engine coordinating all components."""

    def __init__(self, session: Session, client: BinanceClient, config: Config):
        self.session = session
        self.client = client
        self.config = config

        # Initialize components
        self.market_data = MarketData(client)
        self.top_pairs_service = TopPairsService(client, config.pairs)
        self.order_block_strategy = OrderBlockBreakoutStrategy(self.market_data, config.order_block_strategy)
        self.scanner = MarketScanner(
            self.market_data,
            config.scanner,
            top_pairs_service=self.top_pairs_service,
            order_block_strategy=self.order_block_strategy if config.order_block_strategy.enabled else None,
        )
        self.risk_manager = RiskManager(session, config.trading)
        self.position_manager = PositionManager(session, client, config.trading)

        # Repositories
        self.settings_repo = SettingsRepository(session)
        self.signal_repo = MarketSignalRepository(session)
        self.scan_progress_repo = ScanProgressRepository(session)

        # Thread safety - locks for preventing race conditions
        self._position_locks: Dict[str, threading.Lock] = {}
        self._global_lock = threading.Lock()
        self._lock_timeout = 5.0  # seconds

    def get_default_leverage(self) -> int:
        """Get default leverage from settings."""
        return self.settings_repo.get_int("default_leverage", self.config.trading.default_leverage)

    def get_margin_per_trade(self) -> float:
        """Get margin per trade from settings."""
        return self.settings_repo.get_float("margin_per_trade", self.config.trading.margin_per_trade)

    def _get_symbol_lock(self, symbol: str) -> threading.Lock:
        """Get or create a lock for the given symbol."""
        with self._global_lock:
            if symbol not in self._position_locks:
                self._position_locks[symbol] = threading.Lock()
            return self._position_locks[symbol]

    def execute_scan_and_trade(
        self,
        max_signals: int = 30,
        scan_id: Optional[str] = None,
        triggered_by: Optional[str] = None,
        strategy_mode: Optional[str] = None,
    ) -> Dict:
        """Execute market scan and open positions.

        Args:
            max_signals: Maximum number of signals to process
            scan_id: Optional scan ID for progress tracking
            triggered_by: Optional user_id or 'scheduler' for audit tracking
            strategy_mode: Strategy identifier ('pump_cooldown' or 'order_block')

        Returns: Dict with execution results
        """
        logger.info("=" * 80)
        logger.info("Starting scan and trade cycle")
        logger.info("=" * 80)

        # Generate scan_id if not provided
        if not scan_id:
            scan_id = f"scan_{uuid.uuid4().hex[:12]}"

        # Determine scan and strategy type
        scan_type = "manual" if triggered_by and triggered_by != "scheduler" else "scheduled"
        strategy_mode = (
            strategy_mode
            if strategy_mode
            else ("order_block" if self.config.order_block_strategy.enabled else "pump_cooldown")
        )

        # Get total symbols count for progress tracking
        try:
            if strategy_mode == "order_block":
                symbols = self.scanner.get_symbol_universe(top_only=True)
            else:
                symbols = self.client.get_usdt_perpetual_symbols()
            total_symbols = len(symbols)
        except Exception as e:
            logger.error(f"Error getting symbol universe: {e}")
            symbols = self.client.get_usdt_perpetual_symbols()
            total_symbols = len(symbols)

        # Update or create progress tracking record
        try:
            existing_progress = self.scan_progress_repo.get(scan_id)
            if existing_progress:
                # Update total symbols if already created by command handler
                existing_progress.total_symbols = total_symbols
                self.session.commit()
            else:
                # Create new progress record
                self.scan_progress_repo.create(
                    scan_id=scan_id, scan_type=scan_type, total_symbols=total_symbols, triggered_by=triggered_by
                )
        except Exception as e:
            logger.error(f"Error creating scan progress: {e}")

        # Get risk summary
        risk_summary = self.risk_manager.get_risk_summary()
        logger.info(
            f"Current state: {risk_summary['current_positions']}/{risk_summary['max_positions']} positions, "
            f"{risk_summary['current_margin']:.2f}/{risk_summary['max_margin']:.2f} USDT margin"
        )

        # Check if we can open any positions
        if risk_summary["available_slots"] == 0:
            logger.info("No available position slots")
            return {
                "success": True,
                "scan_id": scan_id,
                "signals_found": 0,
                "positions_opened": 0,
                "reason": "No available position slots",
                "strategy_mode": strategy_mode,
            }

        # Define progress callback
        def progress_callback(processed: int, total: int, signals_found: int):
            """Update scan progress in database."""
            try:
                self.scan_progress_repo.update_progress(scan_id, processed, signals_found)
            except Exception as e:
                logger.error(f"Error updating scan progress: {e}")

        # Scan market for opportunities with progress tracking
        scan_symbols = symbols if strategy_mode == "order_block" else None
        signals = self.scanner.scan(
            top_n=max_signals,
            symbols=scan_symbols,
            strategy_mode=strategy_mode,
            progress_callback=progress_callback,
        )

        if not signals:
            logger.info("No trading signals found")
            # Complete scan progress
            try:
                self.scan_progress_repo.complete(scan_id, signals_found=0, positions_opened=0)
            except Exception as e:
                logger.error(f"Error completing scan progress: {e}")

            return {
                "success": True,
                "scan_id": scan_id,
                "signals_found": 0,
                "positions_opened": 0,
                "reason": "No signals found",
                "strategy_mode": strategy_mode,
            }

        logger.info(f"Found {len(signals)} trading signals")

        # Save signals to database
        for signal in signals:
            try:
                if strategy_mode == "order_block":
                    signal_metadata = json.dumps(
                        {
                            "reason": signal.get("reason"),
                            "direction": signal.get("direction"),
                            "targets": signal.get("targets"),
                            "rr": signal.get("rr_ratio"),
                            "session_match": signal.get("session_match"),
                        }
                    )
                    self.signal_repo.create(
                        symbol=signal["symbol"],
                        signal_type="order_block_breakout",
                        price=signal.get("entry_price", 0),
                        volume_24h=None,
                        price_change_pct=None,
                        volume_change_pct=None,
                        score=signal.get("score"),
                        signal_metadata=signal_metadata,
                    )
                else:
                    self.signal_repo.create(
                        symbol=signal["symbol"],
                        signal_type="pump_cooldown",
                        price=signal["current_price"],
                        volume_24h=signal.get("volume_24h"),
                        price_change_pct=signal.get("price_change_pct"),
                        volume_change_pct=signal.get("volume_change_pct"),
                        score=signal.get("score"),
                        signal_metadata=signal.get("reason"),
                    )
            except Exception as e:
                logger.error(f"Error saving signal for {signal['symbol']}: {e}")

        # Try to open positions
        positions_opened: List[Dict] = []
        margin_per_trade = self.get_margin_per_trade()
        leverage = self.get_default_leverage()

        for signal in signals:
            symbol = signal["symbol"]

            # Check if we've reached limits
            if len(positions_opened) >= risk_summary["available_slots"]:
                logger.info("Reached maximum position limit")
                break

            # Get symbol-specific lock
            symbol_lock = self._get_symbol_lock(symbol)

            # Try to acquire lock (non-blocking)
            if not symbol_lock.acquire(blocking=False):
                logger.info(f"Skipping {symbol} - already being processed by another thread")
                continue

            try:
                # Risk check (within lock)
                risk_check = self.risk_manager.check_before_trade(symbol, margin_per_trade, leverage)

                if not risk_check["approved"]:
                    logger.info(f"Trade not approved for {symbol}: {risk_check['reason']}")
                    continue

                # Open position (within lock)
                logger.info(f"Opening position for {symbol} (Score: {signal['score']:.2f})")
                direction = signal.get("direction", "short") if strategy_mode == "order_block" else "short"
                metadata: Optional[Dict[str, Any]] = None
                tp_price = None
                sl_price = None
                if strategy_mode == "order_block":
                    tp_targets = signal.get("targets") or []
                    tp_price = tp_targets[0] if tp_targets else None
                    sl_price = signal.get("stop_loss")
                    metadata = {
                        "strategy": "order_block_breakout",
                        "score": signal.get("score"),
                        "rr_ratio": signal.get("rr_ratio"),
                    }

                position_info = self.position_manager.open_position(
                    symbol,
                    margin_per_trade,
                    leverage,
                    direction=direction,
                    take_profit_price=tp_price,
                    stop_loss_price=sl_price,
                    metadata=metadata,
                )

                if position_info:
                    positions_opened.append(position_info)
                    logger.info(f"✓ Position opened for {symbol}")
                else:
                    logger.error(f"✗ Failed to open position for {symbol}")

            finally:
                # Always release the lock
                symbol_lock.release()

        logger.info(
            f"Scan and trade cycle completed: " f"{len(signals)} signals found, " f"{len(positions_opened)} positions opened"
        )
        logger.info("=" * 80)

        # Complete scan progress
        try:
            self.scan_progress_repo.complete(scan_id, signals_found=len(signals), positions_opened=len(positions_opened))
        except Exception as e:
            logger.error(f"Error completing scan progress: {e}")

        return {
            "success": True,
            "scan_id": scan_id,
            "signals_found": len(signals),
            "positions_opened": len(positions_opened),
            "signals": signals[:5],  # Return top 5 signals
            "opened_positions": positions_opened,
            "strategy_mode": strategy_mode,
        }

    def monitor_and_close(self) -> Dict:
        """Monitor open positions and close if targets are reached.

        Returns: Dict with monitoring results
        """
        closed_positions = self.position_manager.monitor_positions()

        if closed_positions:
            logger.info(f"Monitoring cycle: {len(closed_positions)} positions closed")
        else:
            logger.debug("Monitoring cycle: No positions closed")

        return {"success": True, "positions_closed": len(closed_positions), "closed_positions": closed_positions}

    def get_status(self) -> Dict:
        """Get current trading status."""
        risk_summary = self.risk_manager.get_risk_summary()
        open_positions = self.position_manager.get_all_open_positions()

        return {"risk_summary": risk_summary, "open_positions": open_positions, "position_count": len(open_positions)}

    def close_all_positions(self, reason: str = "manual") -> Dict:
        """Close all open positions.

        Returns: Dict with results
        """
        logger.info("Closing all open positions")
        open_positions = self.position_manager.get_all_open_positions()

        if not open_positions:
            logger.info("No open positions to close")
            return {"success": True, "positions_closed": 0, "reason": "No open positions"}

        closed = []
        for pos in open_positions:
            logger.info(f"Closing position {pos['id']}: {pos['symbol']}")
            result = self.position_manager.close_position(pos["id"], reason)
            if result:
                closed.append(result)

        logger.info(f"Closed {len(closed)}/{len(open_positions)} positions")

        return {
            "success": True,
            "positions_closed": len(closed),
            "total_positions": len(open_positions),
            "closed_positions": closed,
        }
