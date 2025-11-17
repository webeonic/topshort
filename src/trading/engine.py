"""Trading engine - main trading logic coordinator."""
import logging
from typing import List, Dict, Optional
from sqlalchemy.orm import Session

from ..config import Config
from ..exchange.binance_client import BinanceClient
from ..exchange.market_data import MarketData
from ..strategy.scanner import MarketScanner
from ..database.repository import SettingsRepository, MarketSignalRepository
from .risk_manager import RiskManager
from .position_manager import PositionManager

logger = logging.getLogger(__name__)


class TradingEngine:
    """Main trading engine coordinating all components."""

    def __init__(self, session: Session, client: BinanceClient, config: Config):
        self.session = session
        self.client = client
        self.config = config

        # Initialize components
        self.market_data = MarketData(client)
        self.scanner = MarketScanner(self.market_data, config.scanner)
        self.risk_manager = RiskManager(session, config.trading)
        self.position_manager = PositionManager(session, client, config.trading)

        # Repositories
        self.settings_repo = SettingsRepository(session)
        self.signal_repo = MarketSignalRepository(session)

    def get_default_leverage(self) -> int:
        """Get default leverage from settings."""
        return self.settings_repo.get_int('default_leverage', self.config.trading.default_leverage)

    def get_margin_per_trade(self) -> float:
        """Get margin per trade from settings."""
        return self.settings_repo.get_float('margin_per_trade', self.config.trading.margin_per_trade)

    def execute_scan_and_trade(self, max_signals: int = 30) -> Dict:
        """Execute market scan and open positions.

        Returns: Dict with execution results
        """
        logger.info("=" * 80)
        logger.info("Starting scan and trade cycle")
        logger.info("=" * 80)

        # Get risk summary
        risk_summary = self.risk_manager.get_risk_summary()
        logger.info(
            f"Current state: {risk_summary['current_positions']}/{risk_summary['max_positions']} positions, "
            f"{risk_summary['current_margin']:.2f}/{risk_summary['max_margin']:.2f} USDT margin"
        )

        # Check if we can open any positions
        if risk_summary['available_slots'] == 0:
            logger.info("No available position slots")
            return {
                'success': True,
                'signals_found': 0,
                'positions_opened': 0,
                'reason': 'No available position slots'
            }

        # Scan market for opportunities
        signals = self.scanner.scan(top_n=max_signals)

        if not signals:
            logger.info("No trading signals found")
            return {
                'success': True,
                'signals_found': 0,
                'positions_opened': 0,
                'reason': 'No signals found'
            }

        logger.info(f"Found {len(signals)} trading signals")

        # Save signals to database
        for signal in signals:
            try:
                self.signal_repo.create(
                    symbol=signal['symbol'],
                    signal_type='pump_cooldown',
                    price=signal['current_price'],
                    volume_24h=signal.get('volume_24h'),
                    price_change_pct=signal.get('price_change_pct'),
                    volume_change_pct=signal.get('volume_change_pct'),
                    score=signal.get('score'),
                    metadata=signal.get('reason')
                )
            except Exception as e:
                logger.error(f"Error saving signal for {signal['symbol']}: {e}")

        # Try to open positions
        positions_opened = []
        margin_per_trade = self.get_margin_per_trade()
        leverage = self.get_default_leverage()

        for signal in signals:
            symbol = signal['symbol']

            # Check if we've reached limits
            if len(positions_opened) >= risk_summary['available_slots']:
                logger.info("Reached maximum position limit")
                break

            # Risk check
            risk_check = self.risk_manager.check_before_trade(symbol, margin_per_trade, leverage)

            if not risk_check['approved']:
                logger.info(f"Trade not approved for {symbol}: {risk_check['reason']}")
                continue

            # Open position
            logger.info(f"Opening position for {symbol} (Score: {signal['score']:.2f})")
            position_info = self.position_manager.open_position(symbol, margin_per_trade, leverage)

            if position_info:
                positions_opened.append(position_info)
                logger.info(f" Position opened for {symbol}")
            else:
                logger.error(f" Failed to open position for {symbol}")

        logger.info(
            f"Scan and trade cycle completed: "
            f"{len(signals)} signals found, "
            f"{len(positions_opened)} positions opened"
        )
        logger.info("=" * 80)

        return {
            'success': True,
            'signals_found': len(signals),
            'positions_opened': len(positions_opened),
            'signals': signals[:5],  # Return top 5 signals
            'opened_positions': positions_opened
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

        return {
            'success': True,
            'positions_closed': len(closed_positions),
            'closed_positions': closed_positions
        }

    def get_status(self) -> Dict:
        """Get current trading status."""
        risk_summary = self.risk_manager.get_risk_summary()
        open_positions = self.position_manager.get_all_open_positions()

        return {
            'risk_summary': risk_summary,
            'open_positions': open_positions,
            'position_count': len(open_positions)
        }

    def close_all_positions(self, reason: str = 'manual') -> Dict:
        """Close all open positions.

        Returns: Dict with results
        """
        logger.info("Closing all open positions")
        open_positions = self.position_manager.get_all_open_positions()

        if not open_positions:
            logger.info("No open positions to close")
            return {
                'success': True,
                'positions_closed': 0,
                'reason': 'No open positions'
            }

        closed = []
        for pos in open_positions:
            logger.info(f"Closing position {pos['id']}: {pos['symbol']}")
            result = self.position_manager.close_position(pos['id'], reason)
            if result:
                closed.append(result)

        logger.info(f"Closed {len(closed)}/{len(open_positions)} positions")

        return {
            'success': True,
            'positions_closed': len(closed),
            'total_positions': len(open_positions),
            'closed_positions': closed
        }
