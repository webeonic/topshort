"""Database models for TopShort trading bot."""

from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, Float, ForeignKey, Index, Integer, String, Text, create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import DeclarativeMeta, relationship, sessionmaker, validates

Base: DeclarativeMeta = declarative_base()


class Settings(Base):
    """Trading settings table."""

    __tablename__ = "settings"

    id = Column(Integer, primary_key=True)
    key = Column(String(100), unique=True, nullable=False, index=True)
    value = Column(String(500), nullable=False)
    description = Column(Text, nullable=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def __repr__(self):
        return f"<Settings(key='{self.key}', value='{self.value}')>"


class Position(Base):
    """Active positions table with multi-source tracking and limit order management."""

    __tablename__ = "positions"

    id = Column(Integer, primary_key=True)
    symbol = Column(String(50), nullable=False, index=True)
    entry_price = Column(Float, nullable=False)
    current_price = Column(Float, nullable=True)
    quantity = Column(Float, nullable=False)
    margin = Column(Float, nullable=False)
    leverage = Column(Integer, nullable=False)
    side = Column(String(10), nullable=False, default="short")  # 'short' or 'long'

    # Multi-source tracking
    source = Column(String(30), nullable=False, default="bot_auto", index=True)  # 'bot_auto', 'manual', 'external_system'
    source_metadata = Column(Text, nullable=True)  # JSON for additional source-specific data

    # Enhanced take-profit management
    take_profit_price = Column(Float, nullable=False)
    take_profit_order_id = Column(String(100), nullable=True)
    take_profit_order_status = Column(String(20), default="pending")  # 'pending', 'filled', 'cancelled', 'failed'
    take_profit_placed_at = Column(DateTime, nullable=True)

    # Stop-loss management
    stop_loss_price = Column(Float, nullable=True)
    stop_loss_order_id = Column(String(100), nullable=True)
    stop_loss_order_status = Column(String(20), nullable=True)

    order_id = Column(String(100), nullable=True)  # Entry order ID
    status = Column(String(20), nullable=False, default="open", index=True)  # 'open', 'closing', 'closed'
    opened_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    closed_at = Column(DateTime, nullable=True)
    pnl = Column(Float, nullable=True)
    pnl_pct = Column(Float, nullable=True)

    # Relationships
    limit_orders = relationship("LimitOrder", back_populates="position", cascade="all, delete-orphan")

    # Composite indexes
    __table_args__ = (Index("idx_source_status", "source", "status"),)

    @validates("source")
    def validate_source(self, key, value):
        """Validate source field."""
        valid_sources = ["bot_auto", "manual", "external_system"]
        if value not in valid_sources:
            raise ValueError(f"Invalid source: {value}. Must be one of {valid_sources}")
        return value

    @validates("take_profit_order_status")
    def validate_tp_order_status(self, key, value):
        """Validate take-profit order status."""
        valid_statuses = ["pending", "filled", "cancelled", "failed", None]
        if value not in valid_statuses:
            raise ValueError(f"Invalid TP order status: {value}")
        return value

    def __repr__(self):
        return f"<Position(symbol='{self.symbol}', side='{self.side}', margin={self.margin}, source='{self.source}', status='{self.status}')>"


class LimitOrder(Base):
    """Limit orders tracking table for comprehensive order management."""

    __tablename__ = "limit_orders"

    id = Column(Integer, primary_key=True)
    position_id = Column(Integer, ForeignKey("positions.id"), nullable=False, index=True)
    order_id = Column(String(100), unique=True, nullable=False, index=True)
    symbol = Column(String(50), nullable=False)
    order_type = Column(String(20), nullable=False, index=True)  # 'take_profit', 'stop_loss', 'entry', 'exit'
    side = Column(String(10), nullable=False)  # 'buy', 'sell'
    price = Column(Float, nullable=False)
    quantity = Column(Float, nullable=False)
    status = Column(
        String(20), nullable=False, default="pending", index=True
    )  # 'pending', 'filled', 'partially_filled', 'cancelled', 'failed', 'expired'
    filled_quantity = Column(Float, default=0)
    avg_fill_price = Column(Float, nullable=True)
    exchange_status = Column(String(50), nullable=True)  # Raw status from exchange
    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    filled_at = Column(DateTime, nullable=True)
    cancelled_at = Column(DateTime, nullable=True)

    # Relationships
    position = relationship("Position", back_populates="limit_orders")

    def __repr__(self):
        return f"<LimitOrder(order_id='{self.order_id}', symbol='{self.symbol}', type='{self.order_type}', status='{self.status}')>"


class TradeHistory(Base):
    """Trade history table with source tracking."""

    __tablename__ = "trade_history"

    id = Column(Integer, primary_key=True)
    symbol = Column(String(50), nullable=False, index=True)
    entry_price = Column(Float, nullable=False)
    exit_price = Column(Float, nullable=False)
    quantity = Column(Float, nullable=False)
    margin = Column(Float, nullable=False)
    leverage = Column(Integer, nullable=False)
    side = Column(String(10), nullable=False)

    # Source tracking
    source = Column(String(30), default="bot_auto")  # 'bot_auto', 'manual', 'external_system'

    take_profit_price = Column(Float, nullable=True)
    stop_loss_price = Column(Float, nullable=True)
    entry_order_id = Column(String(100), nullable=True)
    exit_order_id = Column(String(100), nullable=True)

    # Limit order tracking
    take_profit_order_id = Column(String(100), nullable=True)
    stop_loss_order_id = Column(String(100), nullable=True)

    opened_at = Column(DateTime, nullable=False)
    closed_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    pnl = Column(Float, nullable=False)
    pnl_pct = Column(Float, nullable=False)
    close_reason = Column(String(50), nullable=True)  # 'take_profit', 'stop_loss', 'manual'
    notes = Column(Text, nullable=True)

    def __repr__(self):
        return f"<TradeHistory(symbol='{self.symbol}', source='{self.source}', pnl={self.pnl}, pnl_pct={self.pnl_pct}%)>"


class MarketSignal(Base):
    """Market signals table (for analysis and debugging)."""

    __tablename__ = "market_signals"

    id = Column(Integer, primary_key=True)
    symbol = Column(String(50), nullable=False, index=True)
    signal_type = Column(String(20), nullable=False)  # 'pump_detected', 'cooldown_detected'
    price = Column(Float, nullable=False)
    volume_24h = Column(Float, nullable=True)
    price_change_pct = Column(Float, nullable=True)
    volume_change_pct = Column(Float, nullable=True)
    score = Column(Float, nullable=True)
    signal_metadata = Column(Text, nullable=True)  # JSON string with additional data
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)
    action_taken = Column(Boolean, default=False)

    def __repr__(self):
        return f"<MarketSignal(symbol='{self.symbol}', type='{self.signal_type}', score={self.score})>"


class BotStatus(Base):
    """Bot status and control table."""

    __tablename__ = "bot_status"

    id = Column(Integer, primary_key=True)
    is_active = Column(Boolean, default=True, nullable=False)
    is_paused = Column(Boolean, default=False, nullable=False)
    last_scan_at = Column(DateTime, nullable=True)
    last_monitor_at = Column(DateTime, nullable=True)
    total_positions_opened = Column(Integer, default=0)
    total_positions_closed = Column(Integer, default=0)
    total_pnl = Column(Float, default=0.0)
    started_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def __repr__(self):
        return f"<BotStatus(active={self.is_active}, paused={self.is_paused})>"


class KeyboardTemplate(Base):
    """Dynamic keyboard templates for different bot states."""

    __tablename__ = "keyboard_templates"

    id = Column(Integer, primary_key=True)
    name = Column(String(100), unique=True, nullable=False, index=True)
    description = Column(Text, nullable=True)
    keyboard_type = Column(String(20), nullable=False, default="inline")  # 'inline' or 'reply'
    keyboard_data = Column(Text, nullable=False)  # JSON string with keyboard structure
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    buttons = relationship("KeyboardButton", back_populates="template", cascade="all, delete-orphan")

    @validates("keyboard_type")
    def validate_keyboard_type(self, key, value):
        """Validate keyboard type."""
        valid_types = ["inline", "reply"]
        if value not in valid_types:
            raise ValueError(f"Invalid keyboard type: {value}. Must be one of {valid_types}")
        return value

    def __repr__(self):
        return f"<KeyboardTemplate(name='{self.name}', type='{self.keyboard_type}')>"


class KeyboardButton(Base):
    """Individual keyboard buttons with dynamic configuration."""

    __tablename__ = "keyboard_buttons"

    id = Column(Integer, primary_key=True)
    template_id = Column(Integer, ForeignKey("keyboard_templates.id"), nullable=False, index=True)
    label = Column(String(100), nullable=False)
    callback_data = Column(String(200), nullable=True)  # For inline keyboards
    url = Column(String(500), nullable=True)  # For URL buttons
    row_position = Column(Integer, default=0, nullable=False)
    column_position = Column(Integer, default=0, nullable=False)
    button_type = Column(String(30), nullable=False, default="callback")  # 'callback', 'url', 'text'
    action = Column(String(100), nullable=True)  # Action to perform on click
    action_params = Column(Text, nullable=True)  # JSON string with action parameters
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    template = relationship("KeyboardTemplate", back_populates="buttons")

    # Composite index for ordering
    __table_args__ = (Index("idx_template_position", "template_id", "row_position", "column_position"),)

    @validates("button_type")
    def validate_button_type(self, key, value):
        """Validate button type."""
        valid_types = ["callback", "url", "text", "contact", "location"]
        if value not in valid_types:
            raise ValueError(f"Invalid button type: {value}. Must be one of {valid_types}")
        return value

    def __repr__(self):
        return f"<KeyboardButton(label='{self.label}', type='{self.button_type}', action='{self.action}')>"


class KeyboardState(Base):
    """Track keyboard states per user for dynamic behavior."""

    __tablename__ = "keyboard_states"

    id = Column(Integer, primary_key=True)
    user_id = Column(String(50), nullable=False, index=True)
    chat_id = Column(String(50), nullable=False, index=True)
    current_keyboard = Column(String(100), nullable=True)  # Current keyboard template name
    state_data = Column(Text, nullable=True)  # JSON string with state-specific data
    last_interaction_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Composite unique index
    __table_args__ = (Index("idx_user_chat", "user_id", "chat_id", unique=True),)

    def __repr__(self):
        return f"<KeyboardState(user_id='{self.user_id}', keyboard='{self.current_keyboard}')>"


class CallbackLog(Base):
    """Log all callback interactions for analytics and debugging."""

    __tablename__ = "callback_logs"

    id = Column(Integer, primary_key=True)
    user_id = Column(String(50), nullable=False, index=True)
    username = Column(String(100), nullable=True)
    chat_id = Column(String(50), nullable=False)
    callback_data = Column(String(200), nullable=False, index=True)
    action = Column(String(100), nullable=True)
    success = Column(Boolean, default=True, nullable=False)
    error_message = Column(Text, nullable=True)
    response_time_ms = Column(Integer, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)

    def __repr__(self):
        return f"<CallbackLog(user='{self.user_id}', action='{self.action}', success={self.success})>"


class ScanProgress(Base):
    """Track real-time progress of market scans."""

    __tablename__ = "scan_progress"

    id = Column(Integer, primary_key=True)
    scan_id = Column(String(100), unique=True, nullable=False, index=True)
    scan_type = Column(String(20), nullable=False, default="manual", index=True)  # 'manual', 'scheduled', 'on_demand'
    status = Column(String(20), nullable=False, default="running", index=True)  # 'running', 'completed', 'failed', 'cancelled'

    # Progress tracking
    total_symbols = Column(Integer, nullable=False, default=0)
    processed_symbols = Column(Integer, nullable=False, default=0)
    progress_pct = Column(Float, nullable=False, default=0.0)

    # Results
    signals_found = Column(Integer, nullable=False, default=0)
    positions_opened = Column(Integer, nullable=False, default=0)

    # Timing
    started_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    completed_at = Column(DateTime, nullable=True)
    duration_seconds = Column(Float, nullable=True)

    # Error tracking
    error_message = Column(Text, nullable=True)

    # Metadata
    triggered_by = Column(String(50), nullable=True, index=True)  # user_id or 'scheduler'
    scan_params = Column(Text, nullable=True)  # JSON with scan parameters

    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Composite index
    __table_args__ = (Index("idx_scan_type_status", "scan_type", "status"),)

    @validates("scan_type")
    def validate_scan_type(self, key, value):
        """Validate scan type."""
        valid_types = ["manual", "scheduled", "on_demand"]
        if value not in valid_types:
            raise ValueError(f"Invalid scan type: {value}. Must be one of {valid_types}")
        return value

    @validates("status")
    def validate_status(self, key, value):
        """Validate status."""
        valid_statuses = ["running", "completed", "failed", "cancelled"]
        if value not in valid_statuses:
            raise ValueError(f"Invalid status: {value}. Must be one of {valid_statuses}")
        return value

    def __repr__(self):
        return f"<ScanProgress(scan_id='{self.scan_id}', status='{self.status}', progress={self.progress_pct:.1f}%)>"


def create_database(database_url: str, auto_migrate: bool = True):
    """Create database and all tables with automatic migrations.

    Args:
        database_url: Database URL (e.g., 'sqlite:///data/topshort.db')
        auto_migrate: If True, automatically run pending migrations

    Returns:
        SQLAlchemy engine
    """
    import logging

    logger = logging.getLogger(__name__)

    # Create engine
    engine = create_engine(database_url, echo=False)

    # Create base tables (if database is new)
    Base.metadata.create_all(engine)

    # Run automatic migrations if enabled
    if auto_migrate:
        try:
            # Extract file path from URL
            if database_url.startswith("sqlite:///"):
                db_path = database_url.replace("sqlite:///", "")

                # Import and run migrations
                from .migrations.migration_manager import run_auto_migrations

                logger.info("Running automatic database migrations...")

                success = run_auto_migrations(db_path, create_backup=True)

                if success:
                    logger.info("✓ Database migrations completed successfully")
                else:
                    logger.warning("⚠ Some migrations may have failed - check logs")

            else:
                logger.warning(f"Auto-migration only supported for SQLite databases")

        except Exception as e:
            logger.error(f"Error running auto-migrations: {e}")
            logger.warning("Continuing without migrations - you may need to run them manually")

    return engine


def get_session(engine):
    """Get database session."""
    Session = sessionmaker(bind=engine)
    return Session()


def init_default_settings(session):
    """Initialize default settings if they don't exist."""
    default_settings = [
        ("margin_per_trade", "100.0", "Margin per trade in USDT"),
        ("max_positions", "10", "Maximum number of simultaneous positions"),
        ("max_total_margin", "1000.0", "Maximum total margin in USDT"),
        ("default_leverage", "20", "Default leverage for positions"),
        ("take_profit_pct", "5.0", "Take profit percentage"),
        ("pump_threshold_pct", "30.0", "Minimum pump percentage to trigger signal"),
        ("pump_period_hours_min", "48", "Minimum hours for pump period"),
        ("pump_period_hours_max", "72", "Maximum hours for pump period"),
        ("cooldown_period_hours_min", "4", "Minimum hours for cooldown period"),
        ("cooldown_period_hours_max", "8", "Maximum hours for cooldown period"),
        ("volume_decrease_threshold_pct", "20.0", "Volume decrease threshold percentage"),
    ]

    for key, value, description in default_settings:
        existing = session.query(Settings).filter_by(key=key).first()
        if not existing:
            setting = Settings(key=key, value=value, description=description)
            session.add(setting)

    # Initialize bot status
    bot_status = session.query(BotStatus).first()
    if not bot_status:
        bot_status = BotStatus()
        session.add(bot_status)

    session.commit()
