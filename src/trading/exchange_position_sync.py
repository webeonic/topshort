"""Exchange position synchronization service.

This service syncs positions from the exchange to track positions opened
manually or by other systems, ensuring the bot knows about all active positions
when making trading decisions.
"""

import logging
from decimal import ROUND_HALF_UP, Decimal
from typing import Dict, List, Optional

from sqlalchemy.orm import Session

from ..config import TradingConfig
from ..database.repository import PositionRepository, SettingsRepository
from ..exchange.binance_client import BinanceClient

logger = logging.getLogger(__name__)


class ExchangePositionSync:
    """Syncs positions from exchange to local database."""

    def __init__(self, session: Session, client: BinanceClient, config: TradingConfig):
        self.session = session
        self.client = client
        self.config = config
        self.position_repo = PositionRepository(session)
        self.settings_repo = SettingsRepository(session)

    def sync_positions_from_exchange(self) -> Dict[str, int]:
        """Sync all positions from exchange to database.

        Fetches all open positions from the exchange and creates database
        records for any positions not already tracked.

        Returns: Dict with sync statistics
        """
        try:
            # Fetch all positions from exchange
            exchange_positions = self.client.get_positions()

            if not exchange_positions:
                logger.debug("No positions found on exchange")
                return {"total": 0, "new": 0, "existing": 0, "updated": 0}

            # Filter for SHORT positions with non-zero amount
            short_positions = [
                pos for pos in exchange_positions if pos.get("side") == "short" and float(pos.get("contracts", 0)) > 0
            ]

            logger.info(f"Found {len(short_positions)} short positions on exchange")

            stats = {"total": len(short_positions), "new": 0, "existing": 0, "updated": 0}

            for exchange_pos in short_positions:
                symbol = exchange_pos.get("symbol")
                entry_price = float(exchange_pos.get("entryPrice", 0))
                quantity = float(exchange_pos.get("contracts", 0))
                leverage = int(exchange_pos.get("leverage", self.config.default_leverage))

                # Calculate margin (notional / leverage)
                notional = entry_price * quantity
                margin = notional / leverage

                # Check if position already exists in database
                existing_position = self.position_repo.get_by_symbol(symbol)

                if existing_position:
                    # Position already tracked
                    stats["existing"] += 1

                    # Update current price if needed
                    if existing_position.current_price != entry_price:
                        self.position_repo.update_current_price(existing_position.id, entry_price)
                        stats["updated"] += 1
                        logger.debug(f"Updated current price for {symbol}: {entry_price:.4f}")
                else:
                    # New position not tracked in database - import it
                    logger.info(
                        f"Importing external position: {symbol}, "
                        f"Entry={entry_price:.4f}, Quantity={quantity:.8f}, "
                        f"Leverage={leverage}x, Margin={margin:.2f} USDT"
                    )

                    # Calculate take-profit price
                    tp_pct = self.settings_repo.get_float("take_profit_pct", self.config.take_profit_pct)
                    entry_decimal = Decimal(str(entry_price))
                    tp_decimal = (entry_decimal * (1 - Decimal(str(tp_pct)) / 100)).quantize(
                        Decimal("0.00000001"), rounding=ROUND_HALF_UP
                    )
                    tp_price = float(tp_decimal)

                    # Create position record with 'external_system' or 'manual' source
                    # We'll mark it as 'external_system' since we can't distinguish
                    new_position = self.position_repo.create(
                        symbol=symbol,
                        entry_price=entry_price,
                        quantity=quantity,
                        margin=margin,
                        leverage=leverage,
                        take_profit_price=tp_price,
                        source="external_system",
                        source_metadata={"imported_from_exchange": True, "exchange": "binance", "original_notional": notional},
                    )

                    stats["new"] += 1
                    logger.info(f"Imported external position {symbol} as position ID {new_position.id}")

            logger.info(
                f"Position sync completed: {stats['total']} total, "
                f"{stats['new']} new, {stats['existing']} existing, "
                f"{stats['updated']} updated"
            )

            return stats

        except Exception as e:
            logger.error(f"Error syncing positions from exchange: {e}")
            return {"total": 0, "new": 0, "existing": 0, "updated": 0, "error": str(e)}

    def get_total_active_pairs(self) -> int:
        """Get total number of active trading pairs across all sources.

        Returns: Total count of open positions
        """
        return self.position_repo.count_open()

    def get_active_pairs_by_source(self) -> Dict[str, int]:
        """Get count of active trading pairs grouped by source.

        Returns: Dict mapping source to count
        """
        return self.position_repo.count_by_source()

    def check_position_limits(self, max_positions: Optional[int] = None) -> Dict:
        """Check if opening a new position would exceed limits.

        Args:
            max_positions: Maximum allowed positions (uses config default if not provided)

        Returns: Dict with limit check results
        """
        if max_positions is None:
            max_positions = self.settings_repo.get_int("max_positions", self.config.max_positions)

        current_count = self.get_total_active_pairs()
        by_source = self.get_active_pairs_by_source()

        can_open = current_count < max_positions

        return {
            "can_open_position": can_open,
            "current_positions": current_count,
            "max_positions": max_positions,
            "available_slots": max(0, max_positions - current_count),
            "positions_by_source": by_source,
        }

    def reconcile_closed_positions(self) -> int:
        """Reconcile database with exchange - close positions that no longer exist.

        Checks if any positions marked as 'open' in database no longer exist
        on the exchange (were closed manually or by another system).

        Returns: Number of positions reconciled
        """
        try:
            # Get all open positions from database
            db_positions = self.position_repo.get_all_open()

            if not db_positions:
                return 0

            # Get all positions from exchange
            exchange_positions = self.client.get_positions()
            exchange_symbols = {
                pos.get("symbol"): pos
                for pos in exchange_positions
                if pos.get("side") == "short" and float(pos.get("contracts", 0)) > 0
            }

            reconciled_count = 0

            for db_pos in db_positions:
                # Check if position still exists on exchange
                if db_pos.symbol not in exchange_symbols:
                    logger.warning(f"Position {db_pos.id} ({db_pos.symbol}) closed externally " f"- reconciling in database")

                    # Position was closed externally, close it in database
                    # Use current price as exit price
                    ticker = self.client.get_ticker(db_pos.symbol)
                    exit_price = ticker["last"] if ticker else db_pos.current_price

                    self.position_repo.close(db_pos.id, exit_price=exit_price, close_reason="manual", exit_order_id=None)

                    reconciled_count += 1
                    logger.info(f"Reconciled position {db_pos.id} ({db_pos.symbol})")

            if reconciled_count > 0:
                logger.info(f"Reconciled {reconciled_count} positions that were closed externally")

            return reconciled_count

        except Exception as e:
            logger.error(f"Error reconciling positions: {e}")
            return 0

    def get_risk_summary(self) -> Dict:
        """Get comprehensive risk summary including all sources.

        Returns: Dict with risk metrics
        """
        try:
            total_positions = self.position_repo.count_open()
            total_margin = self.position_repo.get_total_margin()
            by_source = self.get_active_pairs_by_source()

            max_positions = self.settings_repo.get_int("max_positions", self.config.max_positions)
            max_margin = self.settings_repo.get_float("max_total_margin", self.config.max_total_margin)

            return {
                "total_positions": total_positions,
                "max_positions": max_positions,
                "position_utilization_pct": round((total_positions / max_positions) * 100, 2) if max_positions > 0 else 0,
                "total_margin_used": round(total_margin, 2),
                "max_margin": round(max_margin, 2),
                "margin_utilization_pct": round((total_margin / max_margin) * 100, 2) if max_margin > 0 else 0,
                "available_margin": round(max(0, max_margin - total_margin), 2),
                "positions_by_source": by_source,
            }

        except Exception as e:
            logger.error(f"Error getting risk summary: {e}")
            return {"error": str(e), "total_positions": 0, "total_margin_used": 0}
