"""Position management."""

import logging
from decimal import ROUND_HALF_UP, Decimal
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from ..config import TradingConfig
from ..database.repository import BotStatusRepository, PositionRepository, SettingsRepository
from ..exchange.binance_client import BinanceClient

logger = logging.getLogger(__name__)


class PositionManager:
    """Manages trading positions."""

    def __init__(self, session: Session, client: BinanceClient, config: TradingConfig):
        self.session = session
        self.client = client
        self.config = config
        self.position_repo = PositionRepository(session)
        self.settings_repo = SettingsRepository(session)
        self.bot_status_repo = BotStatusRepository(session)

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
    ) -> Optional[Dict]:
        """Open a new position.

        Args:
            symbol: Trading symbol
            margin: Margin in USDT
            leverage: Leverage to use
            direction: 'long' or 'short'
            take_profit_price: Optional custom take profit level
            stop_loss_price: Optional stop loss reference
            metadata: Additional metadata stored in DB

        Returns: Dict with position info or None if failed
        """
        order = None
        try:
            direction = direction.lower()
            logger.info(f"Opening {direction} position: {symbol}, Margin={margin}, Leverage={leverage}x")

            # Open position on exchange
            if direction == "long":
                order = self.client.open_long_position(symbol, margin, leverage)
            else:
                order = self.client.open_short_position(symbol, margin, leverage)

            if not order:
                logger.error(f"Failed to open position for {symbol}")
                return None

            # Get entry price from order
            entry_price = float(order.get("average", 0) or order.get("price", 0))
            if entry_price == 0:
                # Fallback to current price if order doesn't have price
                ticker = self.client.get_ticker(symbol)
                entry_price = ticker["last"] if ticker else 0

            if entry_price == 0:
                logger.error(f"Could not determine entry price for {symbol}")
                # Try to close orphaned exchange position
                if order:
                    quantity = float(order.get("filled", 0) or order.get("amount", 0))
                    if quantity > 0:
                        try:
                            self.client.close_short_position(symbol, quantity)
                            logger.info(f"Closed orphaned position for {symbol}")
                        except:
                            logger.error(f"Failed to close orphaned position for {symbol}")
                return None

            # Calculate quantity from order
            quantity = float(order.get("filled", 0) or order.get("amount", 0))

            # Calculate take profit price
            tp_price = (
                float(take_profit_price)
                if take_profit_price is not None
                else self.calculate_take_profit_price(entry_price, direction)
            )

            # Begin nested transaction for database operations
            self.session.begin_nested()

            try:
                # Save position to database
                position = self.position_repo.create(
                    symbol=symbol,
                    entry_price=entry_price,
                    quantity=quantity,
                    margin=margin,
                    leverage=leverage,
                    take_profit_price=tp_price,
                    side=direction,
                    stop_loss_price=stop_loss_price,
                    order_id=order.get("id"),
                    source="bot_auto",
                    source_metadata=metadata,
                )

                # Place take-profit limit order immediately
                tp_order = self.client.create_limit_order(
                    symbol=symbol,
                    side="sell" if direction == "long" else "buy",
                    quantity=quantity,
                    price=tp_price,
                    position_side="LONG" if direction == "long" else "SHORT",
                )

                if tp_order:
                    # Record TP limit order in database
                    self.position_repo.place_take_profit_order(position.id, tp_order.get("id"))
                    logger.info(f"Take-profit limit order placed: {tp_order.get('id')} @ {tp_price:.4f}")
                else:
                    logger.warning(f"Failed to place take-profit limit order for {symbol}")
                    # Mark TP order as failed
                    self.position_repo.update_take_profit_status(
                        position.id, "failed", error_message="Failed to place limit order"
                    )

                # Update bot statistics
                self.bot_status_repo.increment_opened()

                # Commit transaction
                self.session.commit()

                logger.info(
                    f"Position opened: {symbol}, "
                    f"Entry={entry_price:.4f}, "
                    f"Quantity={quantity:.8f}, "
                    f"TP={tp_price:.4f} ({self.get_take_profit_pct()}%), "
                    f"TP Order={tp_order.get('id') if tp_order else 'FAILED'}, "
                    f"Side={direction.upper()}"
                )

                return {
                    "position_id": position.id,
                    "symbol": symbol,
                    "entry_price": entry_price,
                    "quantity": quantity,
                    "margin": margin,
                    "leverage": leverage,
                    "take_profit_price": tp_price,
                    "stop_loss_price": stop_loss_price,
                    "direction": direction,
                    "order_id": order.get("id"),
                    "take_profit_order_id": tp_order.get("id") if tp_order else None,
                }

            except Exception as db_error:
                # Rollback database transaction
                self.session.rollback()
                logger.error(f"Database error, rolling back: {db_error}")

                # Try to close orphaned exchange position
                try:
                    if direction == "long":
                        self.client.close_long_position(symbol, quantity)
                    else:
                        self.client.close_short_position(symbol, quantity)
                    logger.info(f"Closed orphaned position after DB error for {symbol}")
                except:
                    logger.error(f"CRITICAL: Failed to close orphaned position for {symbol}!")

                return None

        except Exception as e:
            logger.error(f"Error opening position for {symbol}: {e}")

            # Try to close orphaned exchange position
            if order:
                try:
                    quantity = float(order.get("filled", 0) or order.get("amount", 0))
                    if quantity > 0:
                        if direction == "long":
                            self.client.close_long_position(symbol, quantity)
                        else:
                            self.client.close_short_position(symbol, quantity)
                        logger.info(f"Closed orphaned position after error for {symbol}")
                except:
                    logger.error(f"CRITICAL: Failed to close orphaned position for {symbol}!")

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

            logger.info(f"Closing position {position_id}: {position.symbol}, Reason={reason}")

            # Check if position exists on exchange before attempting to close
            exchange_position = self.client.get_position_by_symbol(position.symbol)

            # If no position exists on exchange (already closed manually or by TP order)
            if not exchange_position or float(exchange_position.get("positionAmt", 0)) == 0:
                logger.warning(
                    f"Position {position_id} ({position.symbol}) not found on exchange - "
                    f"likely already closed manually or by limit order. Syncing database..."
                )
                # Get current price for P&L calculation
                ticker = self.client.get_ticker(position.symbol)
                exit_price = ticker["last"] if ticker else position.current_price

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
                # Get current price for P&L calculation
                ticker = self.client.get_ticker(position.symbol)
                exit_price = ticker["last"] if ticker else position.current_price

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
                sl_reached = False
                stop_loss_price = position.stop_loss_price
                if position.side == "short":
                    tp_reached = current_price <= position.take_profit_price
                    if stop_loss_price is not None and stop_loss_price > 0:
                        sl_reached = current_price >= stop_loss_price
                else:
                    tp_reached = current_price >= position.take_profit_price
                    if stop_loss_price is not None and stop_loss_price > 0:
                        sl_reached = current_price <= stop_loss_price

                if tp_reached:
                    logger.info(
                        f"Take profit reached for {position.symbol}: "
                        f"Current={current_price:.4f}, TP={position.take_profit_price:.4f}"
                    )
                    close_info = self.close_position(position.id, "take_profit")
                    if close_info:
                        closed.append(close_info)
                        continue

                if sl_reached:
                    logger.info(
                        f"Stop loss triggered for {position.symbol}: "
                        f"Current={current_price:.4f}, SL={position.stop_loss_price:.4f}"
                    )
                    close_info = self.close_position(position.id, "stop_loss")
                    if close_info:
                        closed.append(close_info)

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
        }
