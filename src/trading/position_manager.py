"""Position management."""

import json
import logging
import math
import time
from datetime import datetime
from decimal import ROUND_HALF_UP, Decimal
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from ..config import TradingConfig
from ..database.repository import BotStatusRepository, PositionRepository, SettingsRepository
from ..exchange.binance_client import BinanceClient

logger = logging.getLogger(__name__)

_POSITION_CONFIRMATION_TIMEOUT = 3.0
_POSITION_CONFIRMATION_INTERVAL = 0.25


class PositionManager:
    """Manages trading positions."""

    def __init__(self, session: Session, client: BinanceClient, config: TradingConfig):
        self.session = session
        self.client = client
        self.config = config
        self.position_repo = PositionRepository(session)
        self.settings_repo = SettingsRepository(session)
        self.bot_status_repo = BotStatusRepository(session)
        # Track critical errors for notification by upper layers
        self._last_critical_error: Optional[Dict[str, Any]] = None

    def get_and_clear_critical_error(self) -> Optional[Dict[str, Any]]:
        """Get and clear the last critical error for notification."""
        error = self._last_critical_error
        self._last_critical_error = None
        return error

    def get_take_profit_pct(self) -> float:
        """Get take profit percentage from settings."""
        return self.settings_repo.get_float("take_profit_pct", self.config.take_profit_pct)

    def calculate_take_profit_price(self, entry_price: float, direction: str) -> float:
        """Calculate take profit price for a given direction."""
        tp_pct = self.get_take_profit_pct()
        direction = direction.lower()

        # Use Decimal for precise calculation
        entry = Decimal(str(entry_price))
        tp_percent = Decimal(str(tp_pct))

        if direction == "long":
            tp_price = (entry * (1 + tp_percent / 100)).quantize(Decimal("0.00000001"), rounding=ROUND_HALF_UP)
        else:
            tp_price = (entry * (1 - tp_percent / 100)).quantize(Decimal("0.00000001"), rounding=ROUND_HALF_UP)

        return float(tp_price)

    def open_position(
        self,
        symbol: str,
        margin: float,
        leverage: int,
        *,
        direction: str = "short",
        take_profit_price: Optional[float] = None,
        stop_loss_price: Optional[float] = None,
        metadata: Optional[Dict] = None,
        reference_entry_price: Optional[float] = None,
    ) -> Optional[Dict]:
        """Open a new position.

        Args:
            symbol: Trading symbol
            margin: Margin in USDT
            leverage: Leverage to use
            direction: 'long' or 'short'
            take_profit_price: Strategy-provided take profit level (pre-trade)
            stop_loss_price: Strategy-provided stop loss reference
            metadata: Additional metadata stored in DB
            reference_entry_price: Strategy entry assumption for TP/SL recalculation

        Returns: Dict with position info or None if failed
        """
        order = None
        try:
            direction = direction.lower()
            reference_entry = float(reference_entry_price) if reference_entry_price else None
            logger.info(f"Opening {direction} position: {symbol}, Margin={margin}, Leverage={leverage}x")

            if direction == "long":
                order = self.client.open_long_position(symbol, margin, leverage)
            else:
                order = self.client.open_short_position(symbol, margin, leverage)

            if not order:
                logger.error(f"Failed to open position for {symbol}")
                return None

            entry_price = float(order.get("average", 0) or order.get("price", 0))
            if entry_price == 0:
                ticker = self.client.get_ticker(symbol)
                entry_price = ticker["last"] if ticker else 0

            if entry_price == 0:
                logger.error(f"Could not determine entry price for {symbol}")
                quantity = float(order.get("filled", 0) or order.get("amount", 0))
                if quantity > 0:
                    try:
                        self._close_orphaned_position(symbol, direction, quantity)
                    except Exception:
                        logger.error(f"Failed to close orphaned position for {symbol}")
                return None

            quantity = float(order.get("filled", 0) or order.get("amount", 0))

            snapshot = self._wait_for_position_confirmation(symbol, direction)
            if snapshot:
                entry_from_exchange = float(snapshot.get("entryPrice") or 0)
                if entry_from_exchange > 0:
                    entry_price = entry_from_exchange
                snapshot_qty = abs(float(snapshot.get("positionAmt", 0) or 0))
                if snapshot_qty > 0:
                    quantity = snapshot_qty

            final_tp_price = self._determine_take_profit_price(
                direction=direction,
                actual_entry=entry_price,
                strategy_target=take_profit_price,
                reference_entry=reference_entry,
            )
            # Stop-loss disabled - we rely only on take-profit
            # final_sl_price = self._determine_stop_loss_price(
            #     direction=direction,
            #     actual_entry=entry_price,
            #     strategy_stop=stop_loss_price,
            #     reference_entry=reference_entry,
            # )
            final_sl_price = None

            self.session.begin_nested()

            try:
                metadata_to_store = dict(metadata) if metadata else {}
                if reference_entry is not None:
                    metadata_to_store.setdefault("strategy_reference_entry_price", reference_entry)

                position = self.position_repo.create(
                    symbol=symbol,
                    entry_price=entry_price,
                    quantity=quantity,
                    margin=margin,
                    leverage=leverage,
                    take_profit_price=final_tp_price,
                    side=direction,
                    stop_loss_price=final_sl_price,
                    order_id=order.get("id"),
                    source="bot_auto",
                    source_metadata=metadata_to_store or None,
                )

                tp_order = self.client.create_limit_order(
                    symbol=symbol,
                    side="sell" if direction == "long" else "buy",
                    quantity=quantity,
                    price=final_tp_price,
                    position_side="LONG" if direction == "long" else "SHORT",
                )

                if tp_order:
                    self.position_repo.place_take_profit_order(position.id, tp_order.get("id"))
                    logger.info(f"Take-profit limit order placed: {tp_order.get('id')} @ {final_tp_price:.4f}")
                else:
                    logger.warning(f"Failed to place take-profit limit order for {symbol}")
                    self.position_repo.update_take_profit_status(
                        position.id, "failed", error_message="Failed to place limit order"
                    )

                self.bot_status_repo.increment_opened()
                self.session.commit()

                logger.info(
                    f"Position opened: {symbol}, "
                    f"Entry={entry_price:.4f}, "
                    f"Quantity={quantity:.8f}, "
                    f"TP={final_tp_price:.4f}, "
                    f"Side={direction.upper()}"
                )

                # Extract strategy from metadata
                strategy = metadata_to_store.get("strategy") if metadata_to_store else None

                return {
                    "position_id": position.id,
                    "symbol": symbol,
                    "entry_price": entry_price,
                    "quantity": quantity,
                    "margin": margin,
                    "leverage": leverage,
                    "take_profit_price": final_tp_price,
                    "stop_loss_price": final_sl_price,
                    "direction": direction,
                    "order_id": order.get("id"),
                    "take_profit_order_id": tp_order.get("id") if tp_order else None,
                    "strategy": strategy,
                }

            except Exception as db_error:
                self.session.rollback()
                logger.error(f"Database error, rolling back: {db_error}")
                try:
                    self._close_orphaned_position(symbol, direction, quantity)
                except Exception as orphan_error:
                    logger.critical(f"CRITICAL: Failed to close orphaned position for {symbol}!")
                    self._last_critical_error = {
                        "type": "orphaned_position_cleanup_failed",
                        "symbol": symbol,
                        "direction": direction,
                        "quantity": quantity,
                        "original_error": str(db_error),
                        "cleanup_error": str(orphan_error),
                        "timestamp": datetime.utcnow().isoformat(),
                    }
                return None

        except Exception as e:
            logger.error(f"Error opening position for {symbol}: {e}")
            if order:
                try:
                    quantity = float(order.get("filled", 0) or order.get("amount", 0))
                    if quantity > 0:
                        self._close_orphaned_position(symbol, direction, quantity)
                except Exception as orphan_error:
                    logger.critical(f"CRITICAL: Failed to close orphaned position for {symbol}!")
                    self._last_critical_error = {
                        "type": "orphaned_position_cleanup_failed",
                        "symbol": symbol,
                        "direction": direction,
                        "quantity": quantity,
                        "original_error": str(e),
                        "cleanup_error": str(orphan_error),
                        "timestamp": datetime.utcnow().isoformat(),
                    }
            return None

    def _close_orphaned_position(self, symbol: str, direction: str, quantity: float) -> None:
        """Attempt to close a partially opened position when bookkeeping fails."""
        if quantity <= 0:
            return
        if direction == "long":
            self.client.close_long_position(symbol, quantity)
        else:
            self.client.close_short_position(symbol, quantity)
        logger.info(f"Closed orphaned position for {symbol}")

    def _wait_for_position_confirmation(self, symbol: str, direction: str) -> Optional[Dict]:
        """Poll exchange for a short period to obtain the confirmed entry price."""
        deadline = time.monotonic() + _POSITION_CONFIRMATION_TIMEOUT
        direction = direction.lower()
        while time.monotonic() < deadline:
            snapshot = self.client.get_position_by_symbol(symbol)
            if not snapshot:
                time.sleep(_POSITION_CONFIRMATION_INTERVAL)
                continue
            position_amt = float(snapshot.get("positionAmt", 0) or 0)
            if (direction == "long" and position_amt > 0) or (direction == "short" and position_amt < 0):
                return snapshot
            time.sleep(_POSITION_CONFIRMATION_INTERVAL)

        logger.warning(
            "Timed out waiting for %s position confirmation on %s after %.1fs",
            direction,
            symbol,
            _POSITION_CONFIRMATION_TIMEOUT,
        )
        return None

    def _determine_take_profit_price(
        self,
        *,
        direction: str,
        actual_entry: float,
        strategy_target: Optional[float],
        reference_entry: Optional[float],
    ) -> float:
        adjusted = self._recalculate_price(
            actual_entry=actual_entry,
            reference_entry=reference_entry,
            strategy_price=strategy_target,
            direction=direction,
            mode="tp",
        )
        if adjusted is not None:
            return adjusted

        if strategy_target is not None and self._is_price_valid(direction, actual_entry, float(strategy_target), "tp"):
            return float(strategy_target)

        return self.calculate_take_profit_price(actual_entry, direction)

    def _determine_stop_loss_price(
        self,
        *,
        direction: str,
        actual_entry: float,
        strategy_stop: Optional[float],
        reference_entry: Optional[float],
    ) -> Optional[float]:
        adjusted = self._recalculate_price(
            actual_entry=actual_entry,
            reference_entry=reference_entry,
            strategy_price=strategy_stop,
            direction=direction,
            mode="sl",
        )
        if adjusted is not None:
            return adjusted

        if strategy_stop is not None and self._is_price_valid(direction, actual_entry, float(strategy_stop), "sl"):
            return float(strategy_stop)

        return None

    def _recalculate_price(
        self,
        *,
        actual_entry: float,
        reference_entry: Optional[float],
        strategy_price: Optional[float],
        direction: str,
        mode: str,
    ) -> Optional[float]:
        if strategy_price is None or reference_entry is None or reference_entry <= 0:
            return None
        try:
            relative_move = (float(strategy_price) - reference_entry) / reference_entry
            recalculated = actual_entry * (1 + relative_move)
        except Exception:
            return None

        if not math.isfinite(recalculated):
            return None

        if not self._is_price_valid(direction, actual_entry, recalculated, mode):
            return None

        return round(recalculated, 6)

    def _is_price_valid(self, direction: str, entry_price: float, candidate: float, mode: str) -> bool:
        """Validate that candidate TP/SL sits on the correct side of entry."""
        if candidate <= 0:
            return False
        direction = direction.lower()
        if mode == "tp":
            return candidate > entry_price if direction == "long" else candidate < entry_price
        # mode == "sl"
        return candidate < entry_price if direction == "long" else candidate > entry_price

    def _extract_strategy_from_metadata(self, source_metadata) -> Optional[str]:
        """Extract strategy name from position source_metadata."""
        if not source_metadata:
            return None
        try:
            if isinstance(source_metadata, str):
                metadata = json.loads(source_metadata)
            else:
                metadata = source_metadata
            return metadata.get("strategy")
        except (json.JSONDecodeError, TypeError):
            return None

    def close_position(self, position_id: int, reason: str = "take_profit") -> Optional[Dict]:
        """Close an open position.

        Args:
            position_id: Position ID in database
            reason: Reason for closing ('take_profit', 'stop_loss', 'manual')

        Returns: Dict with close info or None if failed
        """
        try:
            position = self.position_repo.get(position_id)
            if not position:
                logger.error(f"Position {position_id} not found")
                return None

            if position.status != "open":
                logger.warning(f"Position {position_id} is not open: {position.status}")
                return None

            # Extract strategy before position might be closed
            strategy = self._extract_strategy_from_metadata(position.source_metadata)

            logger.info(f"Closing position {position_id}: {position.symbol}, Reason={reason}")

            # Check if position exists on exchange before attempting to close
            exchange_position = self.client.get_position_by_symbol(position.symbol)

            # If no position exists on exchange (already closed manually or by TP order)
            if not exchange_position or float(exchange_position.get("positionAmt", 0)) == 0:
                logger.warning(
                    f"Position {position_id} ({position.symbol}) not found on exchange - "
                    f"likely already closed manually or by limit order. Syncing database..."
                )

                # Try to get exit price from TP order if it was filled
                exit_price = None
                if position.take_profit_order_id:
                    tp_order = self.client.fetch_order(position.take_profit_order_id, position.symbol)
                    if tp_order:
                        order_status = tp_order.get("status", "").lower()
                        if order_status in ("closed", "filled"):
                            exit_price = tp_order.get("average")
                            if exit_price:
                                logger.info(f"Got TP order fill price for {position.symbol}: {exit_price:.4f}")

                # Fallback to current price if TP order price not available
                if not exit_price:
                    ticker = self.client.get_ticker(position.symbol)
                    exit_price = ticker["last"] if ticker else position.current_price
                    logger.debug(f"Using current market price for {position.symbol}: {exit_price}")

                # Close position in database with reason indicating it was already closed
                closed_position = self.position_repo.close(position_id, exit_price, f"{reason}_sync")

                # Update bot statistics
                self.bot_status_repo.increment_closed(closed_position.pnl)

                logger.info(
                    f"Position synced: {position.symbol}, "
                    f"Entry={position.entry_price:.4f}, "
                    f"Exit={exit_price:.4f}, "
                    f"P&L={closed_position.pnl:.2f} USDT ({closed_position.pnl_pct:.2f}%)"
                )

                return {
                    "position_id": position_id,
                    "symbol": position.symbol,
                    "entry_price": position.entry_price,
                    "exit_price": exit_price,
                    "pnl": closed_position.pnl,
                    "pnl_pct": closed_position.pnl_pct,
                    "reason": f"{reason}_sync",
                    "synced": True,
                    "strategy": strategy,
                }

            # Close position on exchange
            if position.side == "long":
                order = self.client.close_long_position(position.symbol, position.quantity)
            else:
                order = self.client.close_short_position(position.symbol, position.quantity)

            if not order:
                logger.error(f"Failed to close position {position_id}")
                return None

            # Check if order indicates position was already closed (error code -2022)
            if isinstance(order, dict) and order.get("error_code") == -2022:
                logger.warning(f"Position {position_id} ({position.symbol}) already closed on exchange. Syncing database...")

                # Try to get exit price from TP order if it was filled
                exit_price = None
                if position.take_profit_order_id:
                    tp_order = self.client.fetch_order(position.take_profit_order_id, position.symbol)
                    if tp_order:
                        order_status = tp_order.get("status", "").lower()
                        if order_status in ("closed", "filled"):
                            exit_price = tp_order.get("average")
                            if exit_price:
                                logger.info(f"Got TP order fill price for {position.symbol}: {exit_price:.4f}")

                # Fallback to current price if TP order price not available
                if not exit_price:
                    ticker = self.client.get_ticker(position.symbol)
                    exit_price = ticker["last"] if ticker else position.current_price
                    logger.debug(f"Using current market price for {position.symbol}: {exit_price}")

                # Close position in database
                closed_position = self.position_repo.close(position_id, exit_price, f"{reason}_sync")

                # Update bot statistics
                self.bot_status_repo.increment_closed(closed_position.pnl)

                logger.info(
                    f"Position synced: {position.symbol}, "
                    f"Entry={position.entry_price:.4f}, "
                    f"Exit={exit_price:.4f}, "
                    f"P&L={closed_position.pnl:.2f} USDT ({closed_position.pnl_pct:.2f}%)"
                )

                return {
                    "position_id": position_id,
                    "symbol": position.symbol,
                    "entry_price": position.entry_price,
                    "exit_price": exit_price,
                    "pnl": closed_position.pnl,
                    "pnl_pct": closed_position.pnl_pct,
                    "reason": f"{reason}_sync",
                    "synced": True,
                    "strategy": strategy,
                }

            # Get exit price from order
            exit_price = float(order.get("average", 0) or order.get("price", 0))
            if exit_price == 0:
                # Fallback to current price
                ticker = self.client.get_ticker(position.symbol)
                exit_price = ticker["last"] if ticker else position.current_price

            # Close position in database
            closed_position = self.position_repo.close(position_id, exit_price, reason)

            # Update bot statistics
            self.bot_status_repo.increment_closed(closed_position.pnl)

            logger.info(
                f"Position closed: {position.symbol}, "
                f"Entry={position.entry_price:.4f}, "
                f"Exit={exit_price:.4f}, "
                f"P&L={closed_position.pnl:.2f} USDT ({closed_position.pnl_pct:.2f}%)"
            )

            return {
                "position_id": position_id,
                "symbol": position.symbol,
                "entry_price": position.entry_price,
                "exit_price": exit_price,
                "pnl": closed_position.pnl,
                "pnl_pct": closed_position.pnl_pct,
                "reason": reason,
                "strategy": strategy,
            }

        except Exception as e:
            logger.error(f"Error closing position {position_id}: {e}")
            return None

    def monitor_positions(self) -> List[Dict]:
        """Monitor all open positions and close if TP is reached.

        Returns: List of closed positions
        """
        open_positions = self.position_repo.get_all_open()

        if not open_positions:
            return []

        logger.debug(f"Monitoring {len(open_positions)} open positions")
        closed = []

        # Get all symbols for batch ticker fetch
        symbols = [pos.symbol for pos in open_positions]

        # Batch fetch all tickers (single API call instead of N calls)
        tickers = self.client.fetch_tickers(symbols)

        for position in open_positions:
            try:
                # Get ticker from batch results
                ticker = tickers.get(position.symbol)
                if not ticker:
                    logger.warning(f"Could not get ticker for {position.symbol}")
                    continue

                current_price = ticker["last"]

                # Update current price in database
                self.position_repo.update_current_price(position.id, current_price)

                tp_reached = False
                if position.side == "short":
                    tp_reached = current_price <= position.take_profit_price
                else:
                    tp_reached = current_price >= position.take_profit_price

                if tp_reached:
                    logger.info(
                        f"Take profit reached for {position.symbol}: "
                        f"Current={current_price:.4f}, TP={position.take_profit_price:.4f}"
                    )
                    close_info = self.close_position(position.id, "take_profit")
                    if close_info:
                        closed.append(close_info)
                        continue

                # Stop-loss monitoring disabled - positions close only on TP or manually
                # stop_loss_price = position.stop_loss_price
                # if position.side == "short":
                #     if stop_loss_price is not None and stop_loss_price > 0:
                #         sl_reached = current_price >= stop_loss_price
                # else:
                #     if stop_loss_price is not None and stop_loss_price > 0:
                #         sl_reached = current_price <= stop_loss_price
                # if sl_reached:
                #     logger.info(...)
                #     close_info = self.close_position(position.id, "stop_loss")

            except Exception as e:
                logger.error(f"Error monitoring position {position.id} ({position.symbol}): {e}")

        if closed:
            logger.info(f"Closed {len(closed)} positions in this monitoring cycle")

        return closed

    def get_all_open_positions(self) -> List[Dict]:
        """Get all open positions with current prices."""
        positions = self.position_repo.get_all_open()
        return [self._build_position_snapshot(pos) for pos in positions]

    def close_position_by_symbol(self, symbol: str, reason: str = "manual") -> Optional[Dict]:
        """Close position by symbol."""
        position = self.position_repo.get_by_symbol(symbol)
        if not position:
            logger.warning(f"No open position found for {symbol}")
            return None

        return self.close_position(position.id, reason)

    def get_position_by_symbol(self, symbol: str) -> Optional[Dict[str, Any]]:
        """Return a single position snapshot by symbol."""
        position = self.position_repo.get_by_symbol(symbol)
        if not position:
            return None
        return self._build_position_snapshot(position)

    def update_positions(self) -> List[Dict]:
        """Refresh open positions and return latest snapshots."""
        self.monitor_positions()
        return self.get_all_open_positions()

    def _build_position_snapshot(self, position) -> Dict[str, Any]:
        """Build a dictionary with position metrics for UI/API consumers."""
        if position.current_price and position.entry_price:
            entry = Decimal(str(position.entry_price))
            current = Decimal(str(position.current_price))
            qty = Decimal(str(position.quantity))

            if position.side == "long":
                unrealized_pnl = float(((current - entry) * qty).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))
                unrealized_pnl_pct = float(
                    (((current - entry) / entry) * 100).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
                )
            else:
                unrealized_pnl = float(((entry - current) * qty).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))
                unrealized_pnl_pct = float(
                    (((entry - current) / entry) * 100).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
                )
        else:
            unrealized_pnl = 0.0
            unrealized_pnl_pct = 0.0

        # Extract strategy from source_metadata
        strategy = self._extract_strategy_from_metadata(position.source_metadata)

        return {
            "id": position.id,
            "symbol": position.symbol,
            "entry_price": position.entry_price,
            "current_price": position.current_price,
            "quantity": position.quantity,
            "margin": position.margin,
            "leverage": position.leverage,
            "take_profit_price": position.take_profit_price,
            "stop_loss_price": position.stop_loss_price,
            "side": position.side,
            "unrealized_pnl": round(unrealized_pnl, 2),
            "unrealized_pnl_pct": round(unrealized_pnl_pct, 2),
            "opened_at": position.opened_at.isoformat() if position.opened_at else None,
            "strategy": strategy,
        }
