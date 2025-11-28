"""Limit order monitoring service.

This service monitors pending take-profit limit orders and updates their status
when they get filled or cancelled on the exchange.
"""

import logging
from typing import Dict, List, Optional

from sqlalchemy.orm import Session

from ..database.repository import BotStatusRepository, LimitOrderRepository, PositionRepository
from ..exchange.binance_client import BinanceClient

logger = logging.getLogger(__name__)


class LimitOrderMonitor:
    """Monitors limit orders and syncs their status with the exchange."""

    def __init__(self, session: Session, client: BinanceClient):
        self.session = session
        self.client = client
        self.position_repo = PositionRepository(session)
        self.limit_order_repo = LimitOrderRepository(session)
        self.bot_status_repo = BotStatusRepository(session)

    def monitor_take_profit_orders(self) -> List[Dict]:
        """Monitor all pending take-profit limit orders.

        Checks the status of pending TP orders on the exchange and updates
        the database accordingly. If an order is filled, closes the position.

        Returns: List of positions that were closed due to filled TP orders
        """
        # Get all positions with pending TP orders
        positions_with_pending_tp = self.position_repo.get_positions_with_pending_tp()

        if not positions_with_pending_tp:
            logger.debug("No pending take-profit orders to monitor")
            return []

        logger.debug(f"Monitoring {len(positions_with_pending_tp)} pending take-profit orders")
        closed_positions = []

        for position in positions_with_pending_tp:
            try:
                if not position.take_profit_order_id:
                    logger.warning(f"Position {position.id} has pending TP status but no order ID")
                    continue

                # Fetch order status from exchange
                order_status = self._get_order_status(position.symbol, position.take_profit_order_id)

                if not order_status:
                    logger.warning(f"Could not fetch status for TP order {position.take_profit_order_id}")
                    continue

                status = order_status.get("status", "").lower()
                filled = order_status.get("filled", 0)
                avg_price = order_status.get("average")

                logger.debug(
                    f"TP order {position.take_profit_order_id} for {position.symbol}: " f"status={status}, filled={filled}"
                )

                # Handle filled orders
                if status == "closed" or status == "filled":
                    logger.info(
                        f"Take-profit order filled for {position.symbol}: "
                        f"{position.take_profit_order_id} @ {avg_price:.4f}"
                    )

                    # Update TP order status
                    self.position_repo.update_take_profit_status(position.id, "filled", fill_price=avg_price)

                    # Close position in database
                    closed_position = self.position_repo.close(
                        position.id,
                        exit_price=avg_price or position.take_profit_price,
                        close_reason="take_profit",
                        exit_order_id=position.take_profit_order_id,
                    )

                    # Update bot statistics
                    self.bot_status_repo.increment_closed(closed_position.pnl)

                    logger.info(
                        f"Position closed via TP limit order: {position.symbol}, "
                        f"P&L={closed_position.pnl:.2f} USDT ({closed_position.pnl_pct:.2f}%)"
                    )

                    closed_positions.append(
                        {
                            "position_id": position.id,
                            "symbol": position.symbol,
                            "entry_price": position.entry_price,
                            "exit_price": avg_price or position.take_profit_price,
                            "pnl": closed_position.pnl,
                            "pnl_pct": closed_position.pnl_pct,
                            "reason": "take_profit",
                            "order_id": position.take_profit_order_id,
                        }
                    )

                # Handle cancelled orders
                elif status == "canceled" or status == "cancelled":
                    logger.warning(f"Take-profit order cancelled for {position.symbol}: {position.take_profit_order_id}")

                    self.position_repo.update_take_profit_status(position.id, "cancelled")

                    # Optionally: Re-create the limit order or alert the user
                    logger.warning(f"Position {position.id} ({position.symbol}) no longer has TP protection!")

                # Handle expired orders
                elif status == "expired":
                    logger.warning(f"Take-profit order expired for {position.symbol}: {position.take_profit_order_id}")

                    self.position_repo.update_take_profit_status(position.id, "cancelled")  # Treat expired as cancelled

            except Exception as e:
                logger.error(f"Error monitoring TP order for position {position.id} ({position.symbol}): {e}")
                continue

        if closed_positions:
            logger.info(f"Closed {len(closed_positions)} positions via filled TP orders")

        return closed_positions

    def _get_order_status(self, symbol: str, order_id: str) -> Optional[Dict]:
        """Get order status from exchange.

        Args:
            symbol: Trading symbol
            order_id: Exchange order ID

        Returns: Order info dict or None if not found
        """
        try:
            order = self.client.exchange.fetch_order(order_id, symbol)
            return order
        except Exception as e:
            logger.error(f"Error fetching order {order_id} for {symbol}: {e}")
            return None

    def retry_failed_take_profit_orders(self) -> int:
        """Retry placing take-profit orders that failed.

        Returns: Number of orders successfully retried
        """
        failed_positions = self.position_repo.get_positions_with_failed_tp()

        if not failed_positions:
            return 0

        logger.info(f"Retrying {len(failed_positions)} failed take-profit orders")
        success_count = 0

        for position in failed_positions:
            try:
                # Place take-profit limit order
                tp_order = self.client.create_limit_order(
                    symbol=position.symbol,
                    side="buy",  # Buy to close short position
                    quantity=position.quantity,
                    price=position.take_profit_price,
                    position_side="SHORT",
                )

                if tp_order:
                    # Update database with new order ID
                    self.position_repo.place_take_profit_order(position.id, tp_order.get("id"))
                    logger.info(
                        f"Successfully retried TP order for {position.symbol}: "
                        f"{tp_order.get('id')} @ {position.take_profit_price:.4f}"
                    )
                    success_count += 1
                else:
                    logger.warning(f"Failed to retry TP order for {position.symbol}")

            except Exception as e:
                logger.error(f"Error retrying TP order for position {position.id} ({position.symbol}): {e}")
                continue

        if success_count > 0:
            logger.info(f"Successfully retried {success_count}/{len(failed_positions)} failed TP orders")

        return success_count

    def cancel_take_profit_order(self, position_id: int) -> bool:
        """Cancel a take-profit order for a position.

        Args:
            position_id: Position ID

        Returns: True if successfully cancelled
        """
        try:
            position = self.position_repo.get(position_id)
            if not position or not position.take_profit_order_id:
                logger.warning(f"No TP order to cancel for position {position_id}")
                return False

            # Cancel order on exchange
            try:
                self.client.exchange.cancel_order(position.take_profit_order_id, position.symbol)
                logger.info(f"Cancelled TP order {position.take_profit_order_id} for {position.symbol}")
            except Exception as e:
                logger.warning(f"Error cancelling TP order on exchange: {e}")
                # Continue to update database even if exchange call fails

            # Update database
            self.position_repo.update_take_profit_status(position_id, "cancelled")

            return True

        except Exception as e:
            logger.error(f"Error cancelling TP order for position {position_id}: {e}")
            return False
