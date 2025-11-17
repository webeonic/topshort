"""Database repository for CRUD operations."""
from datetime import datetime
from typing import Optional, List
from sqlalchemy.orm import Session
from sqlalchemy import desc, and_

from .models import Settings, Position, TradeHistory, MarketSignal, BotStatus


class SettingsRepository:
    """Repository for settings operations."""

    def __init__(self, session: Session):
        self.session = session

    def get(self, key: str) -> Optional[Settings]:
        """Get setting by key."""
        return self.session.query(Settings).filter_by(key=key).first()

    def get_value(self, key: str, default: str = None) -> Optional[str]:
        """Get setting value by key."""
        setting = self.get(key)
        return setting.value if setting else default

    def get_float(self, key: str, default: float = 0.0) -> float:
        """Get setting as float."""
        value = self.get_value(key)
        return float(value) if value else default

    def get_int(self, key: str, default: int = 0) -> int:
        """Get setting as int."""
        value = self.get_value(key)
        return int(value) if value else default

    def set(self, key: str, value: str, description: str = None) -> Settings:
        """Set or update setting."""
        setting = self.get(key)
        if setting:
            setting.value = value
            if description:
                setting.description = description
            setting.updated_at = datetime.utcnow()
        else:
            setting = Settings(key=key, value=value, description=description)
            self.session.add(setting)
        self.session.commit()
        return setting

    def get_all(self) -> List[Settings]:
        """Get all settings."""
        return self.session.query(Settings).all()


class PositionRepository:
    """Repository for position operations."""

    def __init__(self, session: Session):
        self.session = session

    def create(self, symbol: str, entry_price: float, quantity: float,
               margin: float, leverage: int, take_profit_price: float,
               stop_loss_price: Optional[float] = None, order_id: Optional[str] = None) -> Position:
        """Create new position."""
        position = Position(
            symbol=symbol,
            entry_price=entry_price,
            current_price=entry_price,
            quantity=quantity,
            margin=margin,
            leverage=leverage,
            side='short',
            take_profit_price=take_profit_price,
            stop_loss_price=stop_loss_price,
            order_id=order_id,
            status='open',
            opened_at=datetime.utcnow()
        )
        self.session.add(position)
        self.session.commit()
        return position

    def get(self, position_id: int) -> Optional[Position]:
        """Get position by ID."""
        return self.session.query(Position).filter_by(id=position_id).first()

    def get_by_symbol(self, symbol: str) -> Optional[Position]:
        """Get open position by symbol."""
        return self.session.query(Position).filter(
            and_(Position.symbol == symbol, Position.status == 'open')
        ).first()

    def get_all_open(self) -> List[Position]:
        """Get all open positions."""
        return self.session.query(Position).filter_by(status='open').all()

    def update_current_price(self, position_id: int, current_price: float):
        """Update current price of position."""
        position = self.get(position_id)
        if position:
            position.current_price = current_price
            self.session.commit()

    def close(self, position_id: int, exit_price: float, close_reason: str = 'take_profit') -> Position:
        """Close position and move to history."""
        position = self.get(position_id)
        if not position:
            raise ValueError(f"Position {position_id} not found")

        # Calculate P&L for short position
        # P&L = (entry_price - exit_price) * quantity
        pnl = (position.entry_price - exit_price) * position.quantity
        pnl_pct = ((position.entry_price - exit_price) / position.entry_price) * 100

        # Update position
        position.status = 'closed'
        position.closed_at = datetime.utcnow()
        position.current_price = exit_price
        position.pnl = pnl
        position.pnl_pct = pnl_pct

        # Create history record
        history = TradeHistory(
            symbol=position.symbol,
            entry_price=position.entry_price,
            exit_price=exit_price,
            quantity=position.quantity,
            margin=position.margin,
            leverage=position.leverage,
            side=position.side,
            take_profit_price=position.take_profit_price,
            stop_loss_price=position.stop_loss_price,
            entry_order_id=position.order_id,
            opened_at=position.opened_at,
            closed_at=datetime.utcnow(),
            pnl=pnl,
            pnl_pct=pnl_pct,
            close_reason=close_reason
        )
        self.session.add(history)
        self.session.commit()
        return position

    def count_open(self) -> int:
        """Count open positions."""
        return self.session.query(Position).filter_by(status='open').count()

    def get_total_margin(self) -> float:
        """Get total margin used in open positions."""
        result = self.session.query(Position).filter_by(status='open').all()
        return sum(p.margin for p in result)


class TradeHistoryRepository:
    """Repository for trade history operations."""

    def __init__(self, session: Session):
        self.session = session

    def get_recent(self, limit: int = 10) -> List[TradeHistory]:
        """Get recent trade history."""
        return self.session.query(TradeHistory).order_by(
            desc(TradeHistory.closed_at)
        ).limit(limit).all()

    def get_by_symbol(self, symbol: str, limit: int = 10) -> List[TradeHistory]:
        """Get trade history for symbol."""
        return self.session.query(TradeHistory).filter_by(
            symbol=symbol
        ).order_by(desc(TradeHistory.closed_at)).limit(limit).all()

    def get_statistics(self) -> dict:
        """Get trading statistics."""
        all_trades = self.session.query(TradeHistory).all()
        if not all_trades:
            return {
                'total_trades': 0,
                'winning_trades': 0,
                'losing_trades': 0,
                'total_pnl': 0.0,
                'win_rate': 0.0,
                'avg_pnl': 0.0,
                'avg_pnl_pct': 0.0
            }

        winning_trades = [t for t in all_trades if t.pnl > 0]
        losing_trades = [t for t in all_trades if t.pnl < 0]
        total_pnl = sum(t.pnl for t in all_trades)

        return {
            'total_trades': len(all_trades),
            'winning_trades': len(winning_trades),
            'losing_trades': len(losing_trades),
            'total_pnl': round(total_pnl, 2),
            'win_rate': round((len(winning_trades) / len(all_trades)) * 100, 2),
            'avg_pnl': round(total_pnl / len(all_trades), 2),
            'avg_pnl_pct': round(sum(t.pnl_pct for t in all_trades) / len(all_trades), 2)
        }


class MarketSignalRepository:
    """Repository for market signals operations."""

    def __init__(self, session: Session):
        self.session = session

    def create(self, symbol: str, signal_type: str, price: float,
               volume_24h: Optional[float] = None, price_change_pct: Optional[float] = None,
               volume_change_pct: Optional[float] = None, score: Optional[float] = None,
               signal_metadata: Optional[str] = None) -> MarketSignal:
        """Create new market signal."""
        signal = MarketSignal(
            symbol=symbol,
            signal_type=signal_type,
            price=price,
            volume_24h=volume_24h,
            price_change_pct=price_change_pct,
            volume_change_pct=volume_change_pct,
            score=score,
            signal_metadata=signal_metadata,
            created_at=datetime.utcnow(),
            action_taken=False
        )
        self.session.add(signal)
        self.session.commit()
        return signal

    def mark_action_taken(self, signal_id: int):
        """Mark signal as action taken."""
        signal = self.session.query(MarketSignal).filter_by(id=signal_id).first()
        if signal:
            signal.action_taken = True
            self.session.commit()

    def get_recent(self, limit: int = 50) -> List[MarketSignal]:
        """Get recent signals."""
        return self.session.query(MarketSignal).order_by(
            desc(MarketSignal.created_at)
        ).limit(limit).all()


class BotStatusRepository:
    """Repository for bot status operations."""

    def __init__(self, session: Session):
        self.session = session

    def get(self) -> BotStatus:
        """Get bot status (create if doesn't exist)."""
        status = self.session.query(BotStatus).first()
        if not status:
            status = BotStatus()
            self.session.add(status)
            self.session.commit()
        return status

    def update_scan_time(self):
        """Update last scan time."""
        status = self.get()
        status.last_scan_at = datetime.utcnow()
        status.updated_at = datetime.utcnow()
        self.session.commit()

    def update_monitor_time(self):
        """Update last monitor time."""
        status = self.get()
        status.last_monitor_at = datetime.utcnow()
        status.updated_at = datetime.utcnow()
        self.session.commit()

    def set_active(self, is_active: bool):
        """Set bot active status."""
        status = self.get()
        status.is_active = is_active
        status.updated_at = datetime.utcnow()
        self.session.commit()

    def set_paused(self, is_paused: bool):
        """Set bot paused status."""
        status = self.get()
        status.is_paused = is_paused
        status.updated_at = datetime.utcnow()
        self.session.commit()

    def increment_opened(self):
        """Increment total positions opened."""
        status = self.get()
        status.total_positions_opened += 1
        status.updated_at = datetime.utcnow()
        self.session.commit()

    def increment_closed(self, pnl: float):
        """Increment total positions closed and update total P&L."""
        status = self.get()
        status.total_positions_closed += 1
        status.total_pnl += pnl
        status.updated_at = datetime.utcnow()
        self.session.commit()
