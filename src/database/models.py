"""Database models for TopShort trading bot."""
from datetime import datetime
from sqlalchemy import create_engine, Column, Integer, String, Float, Boolean, DateTime, Text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

Base = declarative_base()


class Settings(Base):
    """Trading settings table."""
    __tablename__ = 'settings'

    id = Column(Integer, primary_key=True)
    key = Column(String(100), unique=True, nullable=False, index=True)
    value = Column(String(500), nullable=False)
    description = Column(Text, nullable=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def __repr__(self):
        return f"<Settings(key='{self.key}', value='{self.value}')>"


class Position(Base):
    """Active positions table."""
    __tablename__ = 'positions'

    id = Column(Integer, primary_key=True)
    symbol = Column(String(50), nullable=False, index=True)
    entry_price = Column(Float, nullable=False)
    current_price = Column(Float, nullable=True)
    quantity = Column(Float, nullable=False)
    margin = Column(Float, nullable=False)
    leverage = Column(Integer, nullable=False)
    side = Column(String(10), nullable=False, default='short')  # 'short' or 'long'
    take_profit_price = Column(Float, nullable=False)
    stop_loss_price = Column(Float, nullable=True)
    order_id = Column(String(100), nullable=True)
    status = Column(String(20), nullable=False, default='open')  # 'open', 'closing', 'closed'
    opened_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    closed_at = Column(DateTime, nullable=True)
    pnl = Column(Float, nullable=True)
    pnl_pct = Column(Float, nullable=True)

    def __repr__(self):
        return f"<Position(symbol='{self.symbol}', side='{self.side}', margin={self.margin}, status='{self.status}')>"


class TradeHistory(Base):
    """Trade history table."""
    __tablename__ = 'trade_history'

    id = Column(Integer, primary_key=True)
    symbol = Column(String(50), nullable=False, index=True)
    entry_price = Column(Float, nullable=False)
    exit_price = Column(Float, nullable=False)
    quantity = Column(Float, nullable=False)
    margin = Column(Float, nullable=False)
    leverage = Column(Integer, nullable=False)
    side = Column(String(10), nullable=False)
    take_profit_price = Column(Float, nullable=True)
    stop_loss_price = Column(Float, nullable=True)
    entry_order_id = Column(String(100), nullable=True)
    exit_order_id = Column(String(100), nullable=True)
    opened_at = Column(DateTime, nullable=False)
    closed_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    pnl = Column(Float, nullable=False)
    pnl_pct = Column(Float, nullable=False)
    close_reason = Column(String(50), nullable=True)  # 'take_profit', 'stop_loss', 'manual'
    notes = Column(Text, nullable=True)

    def __repr__(self):
        return f"<TradeHistory(symbol='{self.symbol}', pnl={self.pnl}, pnl_pct={self.pnl_pct}%)>"


class MarketSignal(Base):
    """Market signals table (for analysis and debugging)."""
    __tablename__ = 'market_signals'

    id = Column(Integer, primary_key=True)
    symbol = Column(String(50), nullable=False, index=True)
    signal_type = Column(String(20), nullable=False)  # 'pump_detected', 'cooldown_detected'
    price = Column(Float, nullable=False)
    volume_24h = Column(Float, nullable=True)
    price_change_pct = Column(Float, nullable=True)
    volume_change_pct = Column(Float, nullable=True)
    score = Column(Float, nullable=True)
    metadata = Column(Text, nullable=True)  # JSON string with additional data
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)
    action_taken = Column(Boolean, default=False)

    def __repr__(self):
        return f"<MarketSignal(symbol='{self.symbol}', type='{self.signal_type}', score={self.score})>"


class BotStatus(Base):
    """Bot status and control table."""
    __tablename__ = 'bot_status'

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


def create_database(database_url: str):
    """Create database and all tables."""
    engine = create_engine(database_url, echo=False)
    Base.metadata.create_all(engine)
    return engine


def get_session(engine):
    """Get database session."""
    Session = sessionmaker(bind=engine)
    return Session()


def init_default_settings(session):
    """Initialize default settings if they don't exist."""
    default_settings = [
        ('margin_per_trade', '100.0', 'Margin per trade in USDT'),
        ('max_positions', '10', 'Maximum number of simultaneous positions'),
        ('max_total_margin', '1000.0', 'Maximum total margin in USDT'),
        ('default_leverage', '20', 'Default leverage for positions'),
        ('take_profit_pct', '5.0', 'Take profit percentage'),
        ('pump_threshold_pct', '30.0', 'Minimum pump percentage to trigger signal'),
        ('pump_period_hours_min', '48', 'Minimum hours for pump period'),
        ('pump_period_hours_max', '72', 'Maximum hours for pump period'),
        ('cooldown_period_hours_min', '4', 'Minimum hours for cooldown period'),
        ('cooldown_period_hours_max', '8', 'Maximum hours for cooldown period'),
        ('volume_decrease_threshold_pct', '20.0', 'Volume decrease threshold percentage'),
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
