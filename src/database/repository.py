"""Database repository for CRUD operations."""

import json
import logging
from datetime import datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal
from functools import wraps
from typing import Callable, Dict, List, Optional, TypeVar

from sqlalchemy import and_, desc, func
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from .models import (
    BotStatus,
    CallbackLog,
    KeyboardButton,
    KeyboardState,
    KeyboardTemplate,
    LimitOrder,
    MarketSignal,
    Position,
    ScanProgress,
    Settings,
    TradeHistory,
)

logger = logging.getLogger(__name__)

T = TypeVar("T")


def db_retry(func: Callable[..., T]) -> Callable[..., T]:
    """Decorator for retrying database operations on transient failures.

    Retries on SQLAlchemy OperationalError (e.g., database locked, connection issues).
    Uses exponential backoff: 0.1s, 0.2s, 0.4s (max 3 attempts).
    """

    @wraps(func)
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=0.1, min=0.1, max=1),
        retry=retry_if_exception_type(OperationalError),
        reraise=True,
    )
    def wrapper(*args, **kwargs) -> T:
        return func(*args, **kwargs)

    return wrapper


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

    @db_retry
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

    @db_retry
    def create(
        self,
        symbol: str,
        entry_price: float,
        quantity: float,
        margin: float,
        leverage: int,
        take_profit_price: float,
        side: str = "short",
        stop_loss_price: Optional[float] = None,
        order_id: Optional[str] = None,
        source: str = "bot_auto",
        source_metadata: Optional[Dict] = None,
    ) -> Position:
        """Create new position with source tracking."""
        side = side.lower() if side else "short"
        position = Position(
            symbol=symbol,
            entry_price=entry_price,
            current_price=entry_price,
            quantity=quantity,
            margin=margin,
            leverage=leverage,
            side=side,
            take_profit_price=take_profit_price,
            stop_loss_price=stop_loss_price,
            order_id=order_id,
            status="open",
            source=source,
            source_metadata=json.dumps(source_metadata) if source_metadata else None,
            opened_at=datetime.utcnow(),
        )
        self.session.add(position)
        self.session.commit()
        return position

    def get(self, position_id: int) -> Optional[Position]:
        """Get position by ID."""
        return self.session.query(Position).filter_by(id=position_id).first()

    def get_by_symbol(self, symbol: str) -> Optional[Position]:
        """Get open position by symbol."""
        return self.session.query(Position).filter(and_(Position.symbol == symbol, Position.status == "open")).first()

    def get_all_open(self) -> List[Position]:
        """Get all open positions."""
        return self.session.query(Position).filter_by(status="open").all()

    @db_retry
    def update_current_price(self, position_id: int, current_price: float):
        """Update current price of position."""
        position = self.get(position_id)
        if position:
            position.current_price = current_price
            self.session.commit()

    @db_retry
    def close(
        self, position_id: int, exit_price: float, close_reason: str = "take_profit", exit_order_id: Optional[str] = None
    ) -> Position:
        """Close position and move to history."""
        position = self.get(position_id)
        if not position:
            raise ValueError(f"Position {position_id} not found")

        entry = Decimal(str(position.entry_price))
        exit_p = Decimal(str(exit_price))
        qty = Decimal(str(position.quantity))

        if position.side == "long":
            pnl = ((exit_p - entry) * qty).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            pnl_pct = (((exit_p - entry) / entry) * 100).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        else:
            pnl = ((entry - exit_p) * qty).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            pnl_pct = (((entry - exit_p) / entry) * 100).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

        # Update position (convert back to float for database storage)
        position.status = "closed"
        position.closed_at = datetime.utcnow()
        position.current_price = exit_price
        position.pnl = float(pnl)
        position.pnl_pct = float(pnl_pct)

        # Extract strategy from source_metadata
        strategy = None
        if position.source_metadata:
            try:
                if isinstance(position.source_metadata, str):
                    metadata = json.loads(position.source_metadata)
                else:
                    metadata = position.source_metadata
                strategy = metadata.get("strategy")
            except (json.JSONDecodeError, TypeError):
                pass

        # Create history record with source tracking
        history = TradeHistory(
            symbol=position.symbol,
            entry_price=position.entry_price,
            exit_price=exit_price,
            quantity=position.quantity,
            margin=position.margin,
            leverage=position.leverage,
            side=position.side,
            source=position.source,
            strategy=strategy,
            take_profit_price=position.take_profit_price,
            stop_loss_price=position.stop_loss_price,
            entry_order_id=position.order_id,
            exit_order_id=exit_order_id,
            take_profit_order_id=position.take_profit_order_id,
            stop_loss_order_id=position.stop_loss_order_id,
            opened_at=position.opened_at,
            closed_at=datetime.utcnow(),
            pnl=pnl,
            pnl_pct=pnl_pct,
            close_reason=close_reason,
        )
        self.session.add(history)
        self.session.commit()
        return position

    @db_retry
    def delete(self, position_id: int) -> bool:
        """Delete position from database.

        Used when position no longer exists on exchange.
        """
        position = self.get(position_id)
        if not position:
            return False

        self.session.delete(position)
        self.session.commit()
        return True

    def count_open(self) -> int:
        """Count open positions."""
        return self.session.query(Position).filter_by(status="open").count()

    def get_total_margin(self) -> float:
        """Get total margin used in open positions."""
        result = self.session.query(Position).filter_by(status="open").all()
        return sum(p.margin for p in result)

    def get_by_source(self, source: str, status: str = "open") -> List[Position]:
        """Get positions by source."""
        return self.session.query(Position).filter(and_(Position.source == source, Position.status == status)).all()

    def count_by_source(self) -> Dict[str, int]:
        """Count positions grouped by source."""
        results = (
            self.session.query(Position.source, func.count(Position.id).label("count"))
            .filter(Position.status == "open")
            .group_by(Position.source)
            .all()
        )

        return {r.source: r.count for r in results}

    def place_take_profit_order(self, position_id: int, order_id: str) -> Position:
        """Record take-profit limit order placement."""
        position = self.get(position_id)
        if position:
            position.take_profit_order_id = order_id
            position.take_profit_order_status = "pending"
            position.take_profit_placed_at = datetime.utcnow()

            # Create limit order record
            limit_order = LimitOrder(
                position_id=position_id,
                order_id=order_id,
                symbol=position.symbol,
                order_type="take_profit",
                side="buy" if position.side == "short" else "sell",
                price=position.take_profit_price,
                quantity=position.quantity,
                status="pending",
            )
            self.session.add(limit_order)
            self.session.commit()
            logger.info(f"Take-profit order placed for position {position_id}: {order_id}")
        return position

    def update_take_profit_status(
        self, position_id: int, status: str, fill_price: Optional[float] = None, error_message: Optional[str] = None
    ) -> Position:
        """Update take-profit order status."""
        position = self.get(position_id)
        if position:
            position.take_profit_order_status = status

            # Update limit order record if it exists
            if position.take_profit_order_id:
                limit_order = self.session.query(LimitOrder).filter_by(order_id=position.take_profit_order_id).first()

                if limit_order:
                    limit_order.status = status
                    limit_order.updated_at = datetime.utcnow()
                    if status == "filled":
                        limit_order.filled_at = datetime.utcnow()
                        limit_order.avg_fill_price = fill_price
                        limit_order.filled_quantity = limit_order.quantity
                    elif status == "cancelled":
                        limit_order.cancelled_at = datetime.utcnow()
                    elif status == "failed":
                        limit_order.error_message = error_message

            self.session.commit()
            logger.info(f"Take-profit order status updated for position {position_id}: {status}")
        return position

    def get_positions_with_pending_tp(self) -> List[Position]:
        """Get all positions with pending take-profit orders."""
        return (
            self.session.query(Position)
            .filter(and_(Position.status == "open", Position.take_profit_order_status == "pending"))
            .all()
        )

    def get_positions_with_failed_tp(self) -> List[Position]:
        """Get positions with failed take-profit orders."""
        return (
            self.session.query(Position)
            .filter(and_(Position.status == "open", Position.take_profit_order_status == "failed"))
            .all()
        )


class TradeHistoryRepository:
    """Repository for trade history operations."""

    def __init__(self, session: Session):
        self.session = session

    def get_recent(self, limit: int = 10) -> List[TradeHistory]:
        """Get recent trade history."""
        return self.session.query(TradeHistory).order_by(desc(TradeHistory.closed_at)).limit(limit).all()

    def get_by_symbol(self, symbol: str, limit: int = 10) -> List[TradeHistory]:
        """Get trade history for symbol."""
        return (
            self.session.query(TradeHistory).filter_by(symbol=symbol).order_by(desc(TradeHistory.closed_at)).limit(limit).all()
        )

    def get_statistics(self) -> dict:
        """Get trading statistics."""
        all_trades = self.session.query(TradeHistory).all()
        if not all_trades:
            return {
                "total_trades": 0,
                "winning_trades": 0,
                "losing_trades": 0,
                "total_pnl": 0.0,
                "win_rate": 0.0,
                "avg_pnl": 0.0,
                "avg_pnl_pct": 0.0,
            }

        winning_trades = [t for t in all_trades if t.pnl > 0]
        losing_trades = [t for t in all_trades if t.pnl < 0]
        total_pnl = sum(t.pnl for t in all_trades)

        return {
            "total_trades": len(all_trades),
            "winning_trades": len(winning_trades),
            "losing_trades": len(losing_trades),
            "total_pnl": round(total_pnl, 2),
            "win_rate": round((len(winning_trades) / len(all_trades)) * 100, 2),
            "avg_pnl": round(total_pnl / len(all_trades), 2),
            "avg_pnl_pct": round(sum(t.pnl_pct for t in all_trades) / len(all_trades), 2),
        }


class LimitOrderRepository:
    """Repository for limit order operations."""

    def __init__(self, session: Session):
        self.session = session

    def get_by_order_id(self, order_id: str) -> Optional[LimitOrder]:
        """Get limit order by order ID."""
        return self.session.query(LimitOrder).filter_by(order_id=order_id).first()

    def get_by_position(self, position_id: int) -> List[LimitOrder]:
        """Get all limit orders for a position."""
        return self.session.query(LimitOrder).filter_by(position_id=position_id).all()

    def get_pending_orders(self) -> List[LimitOrder]:
        """Get all pending limit orders."""
        return self.session.query(LimitOrder).filter_by(status="pending").all()

    def get_by_type_and_status(self, order_type: str, status: str) -> List[LimitOrder]:
        """Get limit orders by type and status."""
        return (
            self.session.query(LimitOrder).filter(and_(LimitOrder.order_type == order_type, LimitOrder.status == status)).all()
        )

    def update_status(
        self,
        order_id: str,
        status: str,
        fill_price: Optional[float] = None,
        filled_quantity: Optional[float] = None,
        error_message: Optional[str] = None,
    ):
        """Update limit order status."""
        order = self.get_by_order_id(order_id)
        if order:
            order.status = status
            order.updated_at = datetime.utcnow()

            if status == "filled":
                order.filled_at = datetime.utcnow()
                order.avg_fill_price = fill_price
                order.filled_quantity = filled_quantity or order.quantity
            elif status == "cancelled":
                order.cancelled_at = datetime.utcnow()
            elif status == "failed":
                order.error_message = error_message

            self.session.commit()
            logger.info(f"Limit order {order_id} status updated to: {status}")
        return order


class MarketSignalRepository:
    """Repository for market signals operations."""

    def __init__(self, session: Session):
        self.session = session

    @db_retry
    def create(
        self,
        symbol: str,
        signal_type: str,
        price: float,
        volume_24h: Optional[float] = None,
        price_change_pct: Optional[float] = None,
        volume_change_pct: Optional[float] = None,
        score: Optional[float] = None,
        signal_metadata: Optional[str] = None,
    ) -> MarketSignal:
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
            action_taken=False,
        )
        self.session.add(signal)
        self.session.commit()
        return signal

    @db_retry
    def mark_action_taken(self, signal_id: int):
        """Mark signal as action taken."""
        signal = self.session.query(MarketSignal).filter_by(id=signal_id).first()
        if signal:
            signal.action_taken = True
            self.session.commit()

    def get_recent(self, limit: int = 50) -> List[MarketSignal]:
        """Get recent signals."""
        return self.session.query(MarketSignal).order_by(desc(MarketSignal.created_at)).limit(limit).all()

    @db_retry
    def cleanup_old_signals(self, retention_days: int = 30) -> int:
        """Delete signals older than retention period."""
        cutoff = datetime.utcnow() - timedelta(days=retention_days)
        deleted = self.session.query(MarketSignal).filter(MarketSignal.created_at < cutoff).delete()
        self.session.commit()
        logger.info(f"Cleaned up {deleted} old market signals (older than {retention_days} days)")
        return deleted


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

    @db_retry
    def update_scan_time(self):
        """Update last scan time."""
        status = self.get()
        status.last_scan_at = datetime.utcnow()
        status.updated_at = datetime.utcnow()
        self.session.commit()

    @db_retry
    def update_monitor_time(self):
        """Update last monitor time."""
        status = self.get()
        status.last_monitor_at = datetime.utcnow()
        status.updated_at = datetime.utcnow()
        self.session.commit()

    @db_retry
    def set_active(self, is_active: bool):
        """Set bot active status."""
        status = self.get()
        status.is_active = is_active
        status.updated_at = datetime.utcnow()
        self.session.commit()

    @db_retry
    def set_paused(self, is_paused: bool):
        """Set bot paused status."""
        status = self.get()
        status.is_paused = is_paused
        status.updated_at = datetime.utcnow()
        self.session.commit()

    @db_retry
    def increment_opened(self):
        """Increment total positions opened."""
        status = self.get()
        status.total_positions_opened += 1
        status.updated_at = datetime.utcnow()
        self.session.commit()

    @db_retry
    def increment_closed(self, pnl: float):
        """Increment total positions closed and update total P&L."""
        status = self.get()
        status.total_positions_closed += 1
        status.total_pnl += pnl
        status.updated_at = datetime.utcnow()
        self.session.commit()


class KeyboardTemplateRepository:
    """Repository for keyboard template operations."""

    def __init__(self, session: Session):
        self.session = session

    def create(
        self, name: str, keyboard_type: str = "inline", keyboard_data: Optional[Dict] = None, description: str = None
    ) -> KeyboardTemplate:
        """Create new keyboard template."""
        template = KeyboardTemplate(
            name=name, keyboard_type=keyboard_type, keyboard_data=json.dumps(keyboard_data or {}), description=description
        )
        self.session.add(template)
        self.session.commit()
        return template

    def get_by_name(self, name: str) -> Optional[KeyboardTemplate]:
        """Get keyboard template by name."""
        return self.session.query(KeyboardTemplate).filter_by(name=name, is_active=True).first()

    def get_all_active(self) -> List[KeyboardTemplate]:
        """Get all active keyboard templates."""
        return self.session.query(KeyboardTemplate).filter_by(is_active=True).all()

    def update_keyboard_data(self, template_id: int, keyboard_data: Dict):
        """Update keyboard data."""
        template = self.session.query(KeyboardTemplate).filter_by(id=template_id).first()
        if template:
            template.keyboard_data = json.dumps(keyboard_data)
            template.updated_at = datetime.utcnow()
            self.session.commit()

    def delete(self, template_id: int):
        """Soft delete keyboard template."""
        template = self.session.query(KeyboardTemplate).filter_by(id=template_id).first()
        if template:
            template.is_active = False
            template.updated_at = datetime.utcnow()
            self.session.commit()


class KeyboardButtonRepository:
    """Repository for keyboard button operations."""

    def __init__(self, session: Session):
        self.session = session

    def create(
        self,
        template_id: int,
        label: str,
        row_position: int = 0,
        column_position: int = 0,
        button_type: str = "callback",
        callback_data: Optional[str] = None,
        url: Optional[str] = None,
        action: Optional[str] = None,
        action_params: Optional[Dict] = None,
    ) -> KeyboardButton:
        """Create new keyboard button."""
        button = KeyboardButton(
            template_id=template_id,
            label=label,
            row_position=row_position,
            column_position=column_position,
            button_type=button_type,
            callback_data=callback_data,
            url=url,
            action=action,
            action_params=json.dumps(action_params) if action_params else None,
        )
        self.session.add(button)
        self.session.commit()
        return button

    def get_by_template(self, template_id: int) -> List[KeyboardButton]:
        """Get all buttons for a template, ordered by position."""
        return (
            self.session.query(KeyboardButton)
            .filter(and_(KeyboardButton.template_id == template_id, KeyboardButton.is_active == True))
            .order_by(KeyboardButton.row_position, KeyboardButton.column_position)
            .all()
        )

    def update_position(self, button_id: int, row_position: int, column_position: int):
        """Update button position."""
        button = self.session.query(KeyboardButton).filter_by(id=button_id).first()
        if button:
            button.row_position = row_position
            button.column_position = column_position
            button.updated_at = datetime.utcnow()
            self.session.commit()

    def delete(self, button_id: int):
        """Soft delete button."""
        button = self.session.query(KeyboardButton).filter_by(id=button_id).first()
        if button:
            button.is_active = False
            button.updated_at = datetime.utcnow()
            self.session.commit()


class KeyboardStateRepository:
    """Repository for keyboard state operations."""

    def __init__(self, session: Session):
        self.session = session

    def get_or_create(self, user_id: str, chat_id: str) -> KeyboardState:
        """Get or create keyboard state for user."""
        state = (
            self.session.query(KeyboardState)
            .filter(and_(KeyboardState.user_id == user_id, KeyboardState.chat_id == chat_id))
            .first()
        )

        if not state:
            state = KeyboardState(user_id=user_id, chat_id=chat_id)
            self.session.add(state)
            self.session.commit()

        return state

    def update_state(self, user_id: str, chat_id: str, current_keyboard: str, state_data: Optional[Dict] = None):
        """Update keyboard state."""
        state = self.get_or_create(user_id, chat_id)
        state.current_keyboard = current_keyboard
        if state_data is not None:
            state.state_data = json.dumps(state_data)
        state.last_interaction_at = datetime.utcnow()
        state.updated_at = datetime.utcnow()
        self.session.commit()

    def get_state_data(self, user_id: str, chat_id: str) -> Optional[Dict]:
        """Get state data for user."""
        state = self.get_or_create(user_id, chat_id)
        if state.state_data:
            return json.loads(state.state_data)
        return None

    def clear_state(self, user_id: str, chat_id: str):
        """Clear keyboard state."""
        state = self.get_or_create(user_id, chat_id)
        state.current_keyboard = None
        state.state_data = None
        state.updated_at = datetime.utcnow()
        self.session.commit()


class CallbackLogRepository:
    """Repository for callback log operations."""

    def __init__(self, session: Session):
        self.session = session

    def log(
        self,
        user_id: str,
        chat_id: str,
        callback_data: str,
        action: Optional[str] = None,
        username: Optional[str] = None,
        success: bool = True,
        error_message: Optional[str] = None,
        response_time_ms: Optional[int] = None,
    ):
        """Log callback interaction."""
        log = CallbackLog(
            user_id=user_id,
            username=username,
            chat_id=chat_id,
            callback_data=callback_data,
            action=action,
            success=success,
            error_message=error_message,
            response_time_ms=response_time_ms,
        )
        self.session.add(log)
        self.session.commit()

    def get_user_interactions(self, user_id: str, limit: int = 50) -> List[CallbackLog]:
        """Get recent user interactions."""
        return (
            self.session.query(CallbackLog)
            .filter_by(user_id=user_id)
            .order_by(desc(CallbackLog.created_at))
            .limit(limit)
            .all()
        )

    def get_action_stats(self, action: str, days: int = 7) -> Dict:
        """Get statistics for a specific action."""
        cutoff = datetime.utcnow() - timedelta(days=days)
        logs = (
            self.session.query(CallbackLog).filter(and_(CallbackLog.action == action, CallbackLog.created_at >= cutoff)).all()
        )

        total = len(logs)
        successful = sum(1 for log in logs if log.success)
        failed = total - successful

        return {
            "total": total,
            "successful": successful,
            "failed": failed,
            "success_rate": (successful / total * 100) if total > 0 else 0,
        }


class ScanProgressRepository:
    """Repository for scan progress operations."""

    def __init__(self, session: Session):
        self.session = session

    def create(
        self,
        scan_id: str,
        scan_type: str = "manual",
        total_symbols: int = 0,
        triggered_by: Optional[str] = None,
        scan_params: Optional[Dict] = None,
    ) -> ScanProgress:
        """Create new scan progress record."""
        progress = ScanProgress(
            scan_id=scan_id,
            scan_type=scan_type,
            status="running",
            total_symbols=total_symbols,
            processed_symbols=0,
            progress_pct=0.0,
            signals_found=0,
            positions_opened=0,
            started_at=datetime.utcnow(),
            triggered_by=triggered_by,
            scan_params=json.dumps(scan_params) if scan_params else None,
        )
        self.session.add(progress)
        self.session.commit()
        return progress

    def get(self, scan_id: str) -> Optional[ScanProgress]:
        """Get scan progress by ID."""
        return self.session.query(ScanProgress).filter_by(scan_id=scan_id).first()

    def update_progress(self, scan_id: str, processed_symbols: int, signals_found: int = None) -> Optional[ScanProgress]:
        """Update scan progress."""
        progress = self.get(scan_id)
        if not progress:
            return None

        progress.processed_symbols = processed_symbols
        if progress.total_symbols > 0:
            progress.progress_pct = (processed_symbols / progress.total_symbols) * 100.0
        else:
            progress.progress_pct = 0.0

        if signals_found is not None:
            progress.signals_found = signals_found

        progress.updated_at = datetime.utcnow()
        self.session.commit()
        return progress

    def complete(
        self, scan_id: str, signals_found: int, positions_opened: int = 0, error_message: Optional[str] = None
    ) -> Optional[ScanProgress]:
        """Mark scan as completed."""
        progress = self.get(scan_id)
        if not progress:
            return None

        progress.status = "failed" if error_message else "completed"
        progress.completed_at = datetime.utcnow()
        progress.signals_found = signals_found
        progress.positions_opened = positions_opened
        progress.error_message = error_message
        progress.progress_pct = 100.0

        # Calculate duration
        if progress.started_at:
            duration = (progress.completed_at - progress.started_at).total_seconds()
            progress.duration_seconds = duration

        progress.updated_at = datetime.utcnow()
        self.session.commit()
        return progress

    def cancel(self, scan_id: str) -> Optional[ScanProgress]:
        """Cancel a running scan."""
        progress = self.get(scan_id)
        if not progress:
            return None

        progress.status = "cancelled"
        progress.completed_at = datetime.utcnow()

        if progress.started_at:
            duration = (progress.completed_at - progress.started_at).total_seconds()
            progress.duration_seconds = duration

        progress.updated_at = datetime.utcnow()
        self.session.commit()
        return progress

    def get_active_scan(self, scan_type: Optional[str] = None) -> Optional[ScanProgress]:
        """Get currently running scan."""
        query = self.session.query(ScanProgress).filter_by(status="running")
        if scan_type:
            query = query.filter_by(scan_type=scan_type)
        return query.order_by(desc(ScanProgress.started_at)).first()

    def get_recent(self, limit: int = 10) -> List[ScanProgress]:
        """Get recent scans."""
        return self.session.query(ScanProgress).order_by(desc(ScanProgress.started_at)).limit(limit).all()

    def get_user_scans(self, user_id: str, limit: int = 10) -> List[ScanProgress]:
        """Get recent scans for a specific user."""
        return (
            self.session.query(ScanProgress)
            .filter_by(triggered_by=user_id)
            .order_by(desc(ScanProgress.started_at))
            .limit(limit)
            .all()
        )

    def get_statistics(self, days: int = 7) -> Dict:
        """Get scan statistics for the last N days."""
        cutoff = datetime.utcnow() - timedelta(days=days)
        scans = self.session.query(ScanProgress).filter(ScanProgress.started_at >= cutoff).all()

        total = len(scans)
        completed = sum(1 for s in scans if s.status == "completed")
        failed = sum(1 for s in scans if s.status == "failed")
        running = sum(1 for s in scans if s.status == "running")

        total_signals = sum(s.signals_found for s in scans if s.status == "completed")
        total_positions = sum(s.positions_opened for s in scans if s.status == "completed")

        avg_duration = None
        completed_scans = [s for s in scans if s.status == "completed" and s.duration_seconds]
        if completed_scans:
            avg_duration = sum(s.duration_seconds for s in completed_scans) / len(completed_scans)

        return {
            "total_scans": total,
            "completed": completed,
            "failed": failed,
            "running": running,
            "total_signals_found": total_signals,
            "total_positions_opened": total_positions,
            "avg_duration_seconds": avg_duration,
        }
