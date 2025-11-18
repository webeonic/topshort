"""Unit tests for database models."""

from datetime import datetime

import pytest
from sqlalchemy import create_engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

from src.database.models import (
    Base,
    BotStatus,
    LimitOrder,
    MarketSignal,
    Position,
    Settings,
    TradeHistory,
    create_database,
    init_default_settings,
)


@pytest.fixture
def db_engine():
    """Create in-memory SQLite database for testing."""
    engine = create_engine("sqlite:///:memory:", echo=False)
    Base.metadata.create_all(engine)
    return engine


@pytest.fixture
def db_session(db_engine):
    """Create database session."""
    Session = sessionmaker(bind=db_engine)
    session = Session()
    yield session
    session.close()


class TestSettings:
    """Test Settings model."""

    def test_create_setting(self, db_session):
        """Test creating a new setting."""
        setting = Settings(key="test_key", value="test_value", description="Test description")
        db_session.add(setting)
        db_session.commit()

        assert setting.id is not None
        assert setting.key == "test_key"
        assert setting.value == "test_value"
        assert setting.description == "Test description"
        assert setting.updated_at is not None

    def test_unique_key_constraint(self, db_session):
        """Test that setting keys must be unique."""
        setting1 = Settings(key="duplicate_key", value="value1")
        db_session.add(setting1)
        db_session.commit()

        setting2 = Settings(key="duplicate_key", value="value2")
        db_session.add(setting2)

        with pytest.raises(IntegrityError):
            db_session.commit()

    def test_setting_repr(self, db_session):
        """Test string representation."""
        setting = Settings(key="test", value="123")
        assert "test" in repr(setting)
        assert "123" in repr(setting)


class TestPosition:
    """Test Position model."""

    def test_create_position(self, db_session):
        """Test creating a new position."""
        position = Position(
            symbol="BTCUSDT",
            entry_price=50000.0,
            current_price=50000.0,
            quantity=0.1,
            margin=100.0,
            leverage=20,
            side="short",
            take_profit_price=47500.0,
            source="bot_auto",
        )
        db_session.add(position)
        db_session.commit()

        assert position.id is not None
        assert position.symbol == "BTCUSDT"
        assert position.entry_price == 50000.0
        assert position.quantity == 0.1
        assert position.status == "open"
        assert position.source == "bot_auto"
        assert position.opened_at is not None

    def test_position_source_validation(self, db_session):
        """Test that position source is validated."""
        with pytest.raises(ValueError, match="Invalid source"):
            position = Position(
                symbol="ETHUSDT",
                entry_price=3000.0,
                current_price=3000.0,
                quantity=1.0,
                margin=100.0,
                leverage=20,
                side="short",
                take_profit_price=2850.0,
                source="invalid_source",
            )

    def test_valid_sources(self, db_session):
        """Test all valid position sources."""
        valid_sources = ["bot_auto", "manual", "external_system"]

        for source in valid_sources:
            position = Position(
                symbol=f"BTC{source}",
                entry_price=50000.0,
                current_price=50000.0,
                quantity=0.1,
                margin=100.0,
                leverage=20,
                side="short",
                take_profit_price=47500.0,
                source=source,
            )
            db_session.add(position)
            db_session.commit()
            assert position.source == source

    def test_take_profit_status_validation(self, db_session):
        """Test take-profit order status validation."""
        with pytest.raises(ValueError, match="Invalid TP order status"):
            position = Position(
                symbol="BTCUSDT",
                entry_price=50000.0,
                current_price=50000.0,
                quantity=0.1,
                margin=100.0,
                leverage=20,
                side="short",
                take_profit_price=47500.0,
                take_profit_order_status="invalid_status",
            )

    def test_valid_tp_statuses(self, db_session):
        """Test all valid TP order statuses."""
        # Test explicit statuses
        valid_statuses = ["pending", "filled", "cancelled", "failed"]

        for i, status in enumerate(valid_statuses):
            position = Position(
                symbol=f"BTC{i}",
                entry_price=50000.0,
                current_price=50000.0,
                quantity=0.1,
                margin=100.0,
                leverage=20,
                side="short",
                take_profit_price=47500.0,
                take_profit_order_status=status,
            )
            db_session.add(position)
            db_session.commit()
            assert position.take_profit_order_status == status

        # Test that None is converted to default 'pending'
        position_with_none = Position(
            symbol="BTC4",
            entry_price=50000.0,
            current_price=50000.0,
            quantity=0.1,
            margin=100.0,
            leverage=20,
            side="short",
            take_profit_price=47500.0,
            take_profit_order_status=None,
        )
        db_session.add(position_with_none)
        db_session.commit()
        assert position_with_none.take_profit_order_status == "pending"

    def test_position_with_limit_orders(self, db_session):
        """Test position relationship with limit orders."""
        position = Position(
            symbol="BTCUSDT",
            entry_price=50000.0,
            current_price=50000.0,
            quantity=0.1,
            margin=100.0,
            leverage=20,
            side="short",
            take_profit_price=47500.0,
        )
        db_session.add(position)
        db_session.commit()

        # Create limit order
        limit_order = LimitOrder(
            position_id=position.id,
            order_id="TEST123",
            symbol="BTCUSDT",
            order_type="take_profit",
            side="buy",
            price=47500.0,
            quantity=0.1,
        )
        db_session.add(limit_order)
        db_session.commit()

        assert len(position.limit_orders) == 1
        assert position.limit_orders[0].order_id == "TEST123"

    def test_position_repr(self, db_session):
        """Test string representation."""
        position = Position(
            symbol="BTCUSDT",
            entry_price=50000.0,
            current_price=50000.0,
            quantity=0.1,
            margin=100.0,
            leverage=20,
            side="short",
            take_profit_price=47500.0,
            source="bot_auto",
        )
        repr_str = repr(position)
        assert "BTCUSDT" in repr_str
        assert "short" in repr_str
        assert "bot_auto" in repr_str


class TestLimitOrder:
    """Test LimitOrder model."""

    def test_create_limit_order(self, db_session):
        """Test creating a limit order."""
        # First create a position
        position = Position(
            symbol="BTCUSDT",
            entry_price=50000.0,
            current_price=50000.0,
            quantity=0.1,
            margin=100.0,
            leverage=20,
            side="short",
            take_profit_price=47500.0,
        )
        db_session.add(position)
        db_session.commit()

        # Create limit order
        order = LimitOrder(
            position_id=position.id,
            order_id="ORDER123",
            symbol="BTCUSDT",
            order_type="take_profit",
            side="buy",
            price=47500.0,
            quantity=0.1,
        )
        db_session.add(order)
        db_session.commit()

        assert order.id is not None
        assert order.order_id == "ORDER123"
        assert order.status == "pending"
        assert order.filled_quantity == 0
        assert order.created_at is not None

    def test_unique_order_id(self, db_session):
        """Test that order IDs must be unique."""
        position = Position(
            symbol="BTCUSDT",
            entry_price=50000.0,
            current_price=50000.0,
            quantity=0.1,
            margin=100.0,
            leverage=20,
            side="short",
            take_profit_price=47500.0,
        )
        db_session.add(position)
        db_session.commit()

        order1 = LimitOrder(
            position_id=position.id,
            order_id="DUPLICATE",
            symbol="BTCUSDT",
            order_type="take_profit",
            side="buy",
            price=47500.0,
            quantity=0.1,
        )
        db_session.add(order1)
        db_session.commit()

        order2 = LimitOrder(
            position_id=position.id,
            order_id="DUPLICATE",
            symbol="ETHUSDT",
            order_type="take_profit",
            side="buy",
            price=2850.0,
            quantity=1.0,
        )
        db_session.add(order2)

        with pytest.raises(IntegrityError):
            db_session.commit()

    def test_limit_order_repr(self, db_session):
        """Test string representation."""
        position = Position(
            symbol="BTCUSDT",
            entry_price=50000.0,
            current_price=50000.0,
            quantity=0.1,
            margin=100.0,
            leverage=20,
            side="short",
            take_profit_price=47500.0,
        )
        db_session.add(position)
        db_session.commit()

        order = LimitOrder(
            position_id=position.id,
            order_id="TEST123",
            symbol="BTCUSDT",
            order_type="take_profit",
            side="buy",
            price=47500.0,
            quantity=0.1,
        )
        repr_str = repr(order)
        assert "TEST123" in repr_str
        assert "BTCUSDT" in repr_str
        assert "take_profit" in repr_str


class TestTradeHistory:
    """Test TradeHistory model."""

    def test_create_trade_history(self, db_session):
        """Test creating trade history record."""
        history = TradeHistory(
            symbol="BTCUSDT",
            entry_price=50000.0,
            exit_price=47500.0,
            quantity=0.1,
            margin=100.0,
            leverage=20,
            side="short",
            source="bot_auto",
            opened_at=datetime.utcnow(),
            pnl=250.0,
            pnl_pct=5.0,
            close_reason="take_profit",
        )
        db_session.add(history)
        db_session.commit()

        assert history.id is not None
        assert history.symbol == "BTCUSDT"
        assert history.pnl == 250.0
        assert history.pnl_pct == 5.0
        assert history.source == "bot_auto"
        assert history.closed_at is not None

    def test_trade_history_repr(self, db_session):
        """Test string representation."""
        history = TradeHistory(
            symbol="BTCUSDT",
            entry_price=50000.0,
            exit_price=47500.0,
            quantity=0.1,
            margin=100.0,
            leverage=20,
            side="short",
            opened_at=datetime.utcnow(),
            pnl=250.0,
            pnl_pct=5.0,
        )
        repr_str = repr(history)
        assert "BTCUSDT" in repr_str
        assert "250.0" in repr_str


class TestMarketSignal:
    """Test MarketSignal model."""

    def test_create_market_signal(self, db_session):
        """Test creating market signal."""
        signal = MarketSignal(
            symbol="BTCUSDT",
            signal_type="pump_detected",
            price=50000.0,
            volume_24h=1000000.0,
            price_change_pct=35.0,
            volume_change_pct=150.0,
            score=0.85,
        )
        db_session.add(signal)
        db_session.commit()

        assert signal.id is not None
        assert signal.symbol == "BTCUSDT"
        assert signal.signal_type == "pump_detected"
        assert signal.action_taken is False
        assert signal.created_at is not None

    def test_signal_repr(self, db_session):
        """Test string representation."""
        signal = MarketSignal(symbol="BTCUSDT", signal_type="pump_detected", price=50000.0, score=0.85)
        repr_str = repr(signal)
        assert "BTCUSDT" in repr_str
        assert "pump_detected" in repr_str


class TestBotStatus:
    """Test BotStatus model."""

    def test_create_bot_status(self, db_session):
        """Test creating bot status."""
        status = BotStatus()
        db_session.add(status)
        db_session.commit()

        assert status.id is not None
        assert status.is_active is True
        assert status.is_paused is False
        assert status.total_positions_opened == 0
        assert status.total_positions_closed == 0
        assert status.total_pnl == 0.0
        assert status.started_at is not None

    def test_bot_status_repr(self, db_session):
        """Test string representation."""
        status = BotStatus(is_active=True, is_paused=False)
        repr_str = repr(status)
        assert "active=True" in repr_str
        assert "paused=False" in repr_str


class TestDatabaseCreation:
    """Test database creation functions."""

    def test_create_database_basic(self, tmp_path):
        """Test basic database creation."""
        db_file = tmp_path / "test.db"
        db_url = f"sqlite:///{db_file}"

        # Create without auto-migration
        engine = create_database(db_url, auto_migrate=False)

        assert engine is not None
        assert db_file.exists()

    def test_init_default_settings(self, db_session):
        """Test initializing default settings."""
        init_default_settings(db_session)

        # Check that default settings exist
        margin_setting = db_session.query(Settings).filter_by(key="margin_per_trade").first()
        assert margin_setting is not None
        assert margin_setting.value == "100.0"

        max_positions = db_session.query(Settings).filter_by(key="max_positions").first()
        assert max_positions is not None
        assert max_positions.value == "10"

        # Check bot status was created
        bot_status = db_session.query(BotStatus).first()
        assert bot_status is not None
        assert bot_status.is_active is True

    def test_init_default_settings_idempotent(self, db_session):
        """Test that initializing settings twice doesn't create duplicates."""
        init_default_settings(db_session)
        init_default_settings(db_session)

        # Should still only have one of each setting
        setting_count = db_session.query(Settings).filter_by(key="margin_per_trade").count()
        assert setting_count == 1

        status_count = db_session.query(BotStatus).count()
        assert status_count == 1
