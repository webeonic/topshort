"""Unit tests for database repository."""

from datetime import datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.database.models import Base, BotStatus, LimitOrder, MarketSignal, Position, Settings, TradeHistory
from src.database.repository import (
    BotStatusRepository,
    LimitOrderRepository,
    MarketSignalRepository,
    PositionRepository,
    SettingsRepository,
    TradeHistoryRepository,
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
    session.rollback()
    session.close()


class TestSettingsRepository:
    """Test SettingsRepository."""

    def test_get_setting(self, db_session):
        """Test getting a setting."""
        # Create setting directly
        setting = Settings(key="test_key", value="test_value")
        db_session.add(setting)
        db_session.commit()

        repo = SettingsRepository(db_session)
        result = repo.get("test_key")

        assert result is not None
        assert result.key == "test_key"
        assert result.value == "test_value"

    def test_get_nonexistent_setting(self, db_session):
        """Test getting a setting that doesn't exist."""
        repo = SettingsRepository(db_session)
        result = repo.get("nonexistent")

        assert result is None

    def test_get_value(self, db_session):
        """Test getting setting value."""
        setting = Settings(key="margin", value="100.0")
        db_session.add(setting)
        db_session.commit()

        repo = SettingsRepository(db_session)
        value = repo.get_value("margin")

        assert value == "100.0"

    def test_get_value_with_default(self, db_session):
        """Test getting value with default fallback."""
        repo = SettingsRepository(db_session)
        value = repo.get_value("nonexistent", default="50.0")

        assert value == "50.0"

    def test_get_float(self, db_session):
        """Test getting setting as float."""
        setting = Settings(key="margin", value="123.45")
        db_session.add(setting)
        db_session.commit()

        repo = SettingsRepository(db_session)
        value = repo.get_float("margin")

        assert value == 123.45
        assert isinstance(value, float)

    def test_get_float_with_default(self, db_session):
        """Test getting float with default."""
        repo = SettingsRepository(db_session)
        value = repo.get_float("nonexistent", default=99.9)

        assert value == 99.9

    def test_get_int(self, db_session):
        """Test getting setting as int."""
        setting = Settings(key="max_positions", value="10")
        db_session.add(setting)
        db_session.commit()

        repo = SettingsRepository(db_session)
        value = repo.get_int("max_positions")

        assert value == 10
        assert isinstance(value, int)

    def test_get_int_with_default(self, db_session):
        """Test getting int with default."""
        repo = SettingsRepository(db_session)
        value = repo.get_int("nonexistent", default=5)

        assert value == 5

    def test_set_new_setting(self, db_session):
        """Test setting a new value."""
        repo = SettingsRepository(db_session)
        result = repo.set("new_key", "new_value", "Test description")

        assert result.key == "new_key"
        assert result.value == "new_value"
        assert result.description == "Test description"

        # Verify in database
        setting = db_session.query(Settings).filter_by(key="new_key").first()
        assert setting is not None
        assert setting.value == "new_value"

    def test_set_update_existing(self, db_session):
        """Test updating existing setting."""
        setting = Settings(key="update_key", value="old_value")
        db_session.add(setting)
        db_session.commit()

        repo = SettingsRepository(db_session)
        repo.set("update_key", "new_value")

        # Verify updated
        updated = db_session.query(Settings).filter_by(key="update_key").first()
        assert updated.value == "new_value"

    def test_get_all(self, db_session):
        """Test getting all settings."""
        db_session.add(Settings(key="key1", value="value1"))
        db_session.add(Settings(key="key2", value="value2"))
        db_session.commit()

        repo = SettingsRepository(db_session)
        settings = repo.get_all()

        assert len(settings) == 2
        assert any(s.key == "key1" for s in settings)
        assert any(s.key == "key2" for s in settings)


class TestPositionRepository:
    """Test PositionRepository."""

    def test_create_position(self, db_session):
        """Test creating a position."""
        repo = PositionRepository(db_session)
        position = repo.create(
            symbol="BTCUSDT",
            entry_price=50000.0,
            quantity=0.1,
            margin=100.0,
            leverage=20,
            take_profit_price=47500.0,
            source="bot_auto",
        )

        assert position.id is not None
        assert position.symbol == "BTCUSDT"
        assert position.status == "open"
        assert position.source == "bot_auto"

    def test_create_position_with_metadata(self, db_session):
        """Test creating position with source metadata."""
        repo = PositionRepository(db_session)
        metadata = {"signal_id": 123, "strategy": "pump_detector"}

        position = repo.create(
            symbol="ETHUSDT",
            entry_price=3000.0,
            quantity=1.0,
            margin=150.0,
            leverage=20,
            take_profit_price=2850.0,
            source="bot_auto",
            source_metadata=metadata,
        )

        assert position.source_metadata is not None
        assert "signal_id" in position.source_metadata

    def test_get_position(self, db_session):
        """Test getting position by ID."""
        position = Position(
            symbol="BTCUSDT",
            entry_price=50000.0,
            current_price=50000.0,
            quantity=0.1,
            margin=100.0,
            leverage=20,
            take_profit_price=47500.0,
        )
        db_session.add(position)
        db_session.commit()

        repo = PositionRepository(db_session)
        result = repo.get(position.id)

        assert result is not None
        assert result.id == position.id
        assert result.symbol == "BTCUSDT"

    def test_get_nonexistent_position(self, db_session):
        """Test getting position that doesn't exist."""
        repo = PositionRepository(db_session)
        result = repo.get(99999)

        assert result is None

    def test_delete_position(self, db_session):
        """Test deleting a position."""
        position = Position(
            symbol="BTCUSDT",
            entry_price=50000.0,
            current_price=50000.0,
            quantity=0.1,
            margin=100.0,
            leverage=20,
            take_profit_price=47500.0,
            status="open",
        )
        db_session.add(position)
        db_session.commit()
        position_id = position.id

        repo = PositionRepository(db_session)
        result = repo.delete(position_id)

        assert result is True
        assert repo.get(position_id) is None

    def test_delete_nonexistent_position(self, db_session):
        """Test deleting position that doesn't exist."""
        repo = PositionRepository(db_session)
        result = repo.delete(99999)

        assert result is False

    def test_delete_position_with_limit_orders(self, db_session):
        """Test deleting position also deletes associated limit orders (cascade)."""
        # Create position
        position = Position(
            symbol="BTCUSDT",
            entry_price=50000.0,
            current_price=50000.0,
            quantity=0.1,
            margin=100.0,
            leverage=20,
            take_profit_price=47500.0,
            status="open",
        )
        db_session.add(position)
        db_session.commit()
        position_id = position.id

        # Create associated limit orders
        order1 = LimitOrder(
            position_id=position_id,
            order_id="TP_ORDER_123",
            symbol="BTCUSDT",
            order_type="take_profit",
            side="buy",
            price=47500.0,
            quantity=0.1,
        )
        order2 = LimitOrder(
            position_id=position_id,
            order_id="SL_ORDER_456",
            symbol="BTCUSDT",
            order_type="stop_loss",
            side="buy",
            price=52500.0,
            quantity=0.1,
        )
        db_session.add(order1)
        db_session.add(order2)
        db_session.commit()

        # Verify orders exist before deletion
        orders_before = db_session.query(LimitOrder).filter_by(position_id=position_id).all()
        assert len(orders_before) == 2

        # Delete position
        repo = PositionRepository(db_session)
        result = repo.delete(position_id)

        # Assert position deleted
        assert result is True
        assert repo.get(position_id) is None

        # Assert associated limit orders were cascade-deleted
        orders_after = db_session.query(LimitOrder).filter_by(position_id=position_id).all()
        assert len(orders_after) == 0

        # Also verify by order_id that orders don't exist anymore
        assert db_session.query(LimitOrder).filter_by(order_id="TP_ORDER_123").first() is None
        assert db_session.query(LimitOrder).filter_by(order_id="SL_ORDER_456").first() is None

    def test_get_by_symbol(self, db_session):
        """Test getting position by symbol."""
        position = Position(
            symbol="BTCUSDT",
            entry_price=50000.0,
            current_price=50000.0,
            quantity=0.1,
            margin=100.0,
            leverage=20,
            take_profit_price=47500.0,
            status="open",
        )
        db_session.add(position)
        db_session.commit()

        repo = PositionRepository(db_session)
        result = repo.get_by_symbol("BTCUSDT")

        assert result is not None
        assert result.symbol == "BTCUSDT"

    def test_get_by_symbol_closed_position(self, db_session):
        """Test that closed positions are not returned by get_by_symbol."""
        position = Position(
            symbol="BTCUSDT",
            entry_price=50000.0,
            current_price=47500.0,
            quantity=0.1,
            margin=100.0,
            leverage=20,
            take_profit_price=47500.0,
            status="closed",
        )
        db_session.add(position)
        db_session.commit()

        repo = PositionRepository(db_session)
        result = repo.get_by_symbol("BTCUSDT")

        assert result is None

    def test_get_all_open(self, db_session):
        """Test getting all open positions."""
        db_session.add(
            Position(
                symbol="BTC1",
                entry_price=50000.0,
                current_price=50000.0,
                quantity=0.1,
                margin=100.0,
                leverage=20,
                take_profit_price=47500.0,
                status="open",
            )
        )
        db_session.add(
            Position(
                symbol="BTC2",
                entry_price=50000.0,
                current_price=50000.0,
                quantity=0.1,
                margin=100.0,
                leverage=20,
                take_profit_price=47500.0,
                status="open",
            )
        )
        db_session.add(
            Position(
                symbol="BTC3",
                entry_price=50000.0,
                current_price=47500.0,
                quantity=0.1,
                margin=100.0,
                leverage=20,
                take_profit_price=47500.0,
                status="closed",
            )
        )
        db_session.commit()

        repo = PositionRepository(db_session)
        positions = repo.get_all_open()

        assert len(positions) == 2
        assert all(p.status == "open" for p in positions)

    def test_update_current_price(self, db_session):
        """Test updating current price."""
        position = Position(
            symbol="BTCUSDT",
            entry_price=50000.0,
            current_price=50000.0,
            quantity=0.1,
            margin=100.0,
            leverage=20,
            take_profit_price=47500.0,
        )
        db_session.add(position)
        db_session.commit()

        repo = PositionRepository(db_session)
        repo.update_current_price(position.id, 49000.0)

        updated = db_session.query(Position).filter_by(id=position.id).first()
        assert updated.current_price == 49000.0

    def test_close_position(self, db_session):
        """Test closing a position."""
        position = Position(
            symbol="BTCUSDT",
            entry_price=50000.0,
            current_price=50000.0,
            quantity=0.1,
            margin=100.0,
            leverage=20,
            take_profit_price=47500.0,
            status="open",
            opened_at=datetime.utcnow(),
        )
        db_session.add(position)
        db_session.commit()

        repo = PositionRepository(db_session)
        closed = repo.close(position.id, exit_price=47500.0, close_reason="take_profit")

        assert closed.status == "closed"
        assert closed.closed_at is not None
        assert closed.pnl is not None
        assert closed.pnl_pct is not None

        # Verify history was created
        history = db_session.query(TradeHistory).filter_by(symbol="BTCUSDT").first()
        assert history is not None
        assert history.close_reason == "take_profit"

    def test_close_position_saves_strategy_to_history(self, db_session):
        """Test that strategy from source_metadata is saved to trade history."""
        import json

        position = Position(
            symbol="ETHUSDT",
            entry_price=3000.0,
            current_price=3000.0,
            quantity=1.0,
            margin=150.0,
            leverage=20,
            take_profit_price=2850.0,
            status="open",
            opened_at=datetime.utcnow(),
            source_metadata=json.dumps({"strategy": "order_block", "rr_ratio": 2.5}),
        )
        db_session.add(position)
        db_session.commit()

        repo = PositionRepository(db_session)
        repo.close(position.id, exit_price=2850.0, close_reason="take_profit")

        # Verify strategy was saved to history
        history = db_session.query(TradeHistory).filter_by(symbol="ETHUSDT").first()
        assert history is not None
        assert history.strategy == "order_block"

    def test_close_position_handles_missing_strategy(self, db_session):
        """Test that closing position without strategy works correctly."""
        position = Position(
            symbol="BTCUSDT",
            entry_price=50000.0,
            current_price=50000.0,
            quantity=0.1,
            margin=100.0,
            leverage=20,
            take_profit_price=47500.0,
            status="open",
            opened_at=datetime.utcnow(),
            source_metadata=None,
        )
        db_session.add(position)
        db_session.commit()

        repo = PositionRepository(db_session)
        repo.close(position.id, exit_price=47500.0, close_reason="take_profit")

        # Verify history was created with None strategy
        history = db_session.query(TradeHistory).filter_by(symbol="BTCUSDT").first()
        assert history is not None
        assert history.strategy is None

    def test_close_position_pnl_calculation(self, db_session):
        """Test P&L calculation for short position."""
        position = Position(
            symbol="BTCUSDT",
            entry_price=50000.0,
            current_price=50000.0,
            quantity=0.1,  # 0.1 BTC
            margin=100.0,
            leverage=20,
            take_profit_price=47500.0,
            status="open",
            opened_at=datetime.utcnow(),
        )
        db_session.add(position)
        db_session.commit()

        repo = PositionRepository(db_session)
        # Close at lower price (profitable for short)
        closed = repo.close(position.id, exit_price=47500.0)

        # P&L = (entry - exit) * quantity = (50000 - 47500) * 0.1 = 250
        assert closed.pnl == 250.0
        # P&L % = ((entry - exit) / entry) * 100 = 5%
        assert closed.pnl_pct == 5.0

    def test_count_open(self, db_session):
        """Test counting open positions."""
        db_session.add(
            Position(
                symbol="BTC1",
                entry_price=50000.0,
                current_price=50000.0,
                quantity=0.1,
                margin=100.0,
                leverage=20,
                take_profit_price=47500.0,
                status="open",
            )
        )
        db_session.add(
            Position(
                symbol="BTC2",
                entry_price=50000.0,
                current_price=50000.0,
                quantity=0.1,
                margin=100.0,
                leverage=20,
                take_profit_price=47500.0,
                status="open",
            )
        )
        db_session.commit()

        repo = PositionRepository(db_session)
        count = repo.count_open()

        assert count == 2

    def test_get_total_margin(self, db_session):
        """Test calculating total margin."""
        db_session.add(
            Position(
                symbol="BTC1",
                entry_price=50000.0,
                current_price=50000.0,
                quantity=0.1,
                margin=100.0,
                leverage=20,
                take_profit_price=47500.0,
                status="open",
            )
        )
        db_session.add(
            Position(
                symbol="BTC2",
                entry_price=50000.0,
                current_price=50000.0,
                quantity=0.1,
                margin=150.0,
                leverage=20,
                take_profit_price=47500.0,
                status="open",
            )
        )
        db_session.commit()

        repo = PositionRepository(db_session)
        total = repo.get_total_margin()

        assert total == 250.0

    def test_get_by_source(self, db_session):
        """Test getting positions by source."""
        db_session.add(
            Position(
                symbol="BTC1",
                entry_price=50000.0,
                current_price=50000.0,
                quantity=0.1,
                margin=100.0,
                leverage=20,
                take_profit_price=47500.0,
                source="bot_auto",
                status="open",
            )
        )
        db_session.add(
            Position(
                symbol="BTC2",
                entry_price=50000.0,
                current_price=50000.0,
                quantity=0.1,
                margin=100.0,
                leverage=20,
                take_profit_price=47500.0,
                source="manual",
                status="open",
            )
        )
        db_session.commit()

        repo = PositionRepository(db_session)
        bot_positions = repo.get_by_source("bot_auto")
        manual_positions = repo.get_by_source("manual")

        assert len(bot_positions) == 1
        assert len(manual_positions) == 1
        assert bot_positions[0].source == "bot_auto"
        assert manual_positions[0].source == "manual"

    def test_count_by_source(self, db_session):
        """Test counting positions by source."""
        db_session.add(
            Position(
                symbol="BTC1",
                entry_price=50000.0,
                current_price=50000.0,
                quantity=0.1,
                margin=100.0,
                leverage=20,
                take_profit_price=47500.0,
                source="bot_auto",
                status="open",
            )
        )
        db_session.add(
            Position(
                symbol="BTC2",
                entry_price=50000.0,
                current_price=50000.0,
                quantity=0.1,
                margin=100.0,
                leverage=20,
                take_profit_price=47500.0,
                source="bot_auto",
                status="open",
            )
        )
        db_session.add(
            Position(
                symbol="BTC3",
                entry_price=50000.0,
                current_price=50000.0,
                quantity=0.1,
                margin=100.0,
                leverage=20,
                take_profit_price=47500.0,
                source="manual",
                status="open",
            )
        )
        db_session.commit()

        repo = PositionRepository(db_session)
        counts = repo.count_by_source()

        assert counts["bot_auto"] == 2
        assert counts["manual"] == 1

    def test_place_take_profit_order(self, db_session):
        """Test placing take-profit order."""
        position = Position(
            symbol="BTCUSDT",
            entry_price=50000.0,
            current_price=50000.0,
            quantity=0.1,
            margin=100.0,
            leverage=20,
            take_profit_price=47500.0,
            status="open",
        )
        db_session.add(position)
        db_session.commit()

        repo = PositionRepository(db_session)
        result = repo.place_take_profit_order(position.id, "ORDER123")

        assert result.take_profit_order_id == "ORDER123"
        assert result.take_profit_order_status == "pending"
        assert result.take_profit_placed_at is not None

        # Verify limit order was created
        limit_order = db_session.query(LimitOrder).filter_by(order_id="ORDER123").first()
        assert limit_order is not None
        assert limit_order.order_type == "take_profit"

    def test_update_take_profit_status(self, db_session):
        """Test updating take-profit status."""
        position = Position(
            symbol="BTCUSDT",
            entry_price=50000.0,
            current_price=50000.0,
            quantity=0.1,
            margin=100.0,
            leverage=20,
            take_profit_price=47500.0,
            take_profit_order_id="ORDER123",
            take_profit_order_status="pending",
        )
        db_session.add(position)
        db_session.commit()

        # Create limit order
        limit_order = LimitOrder(
            position_id=position.id,
            order_id="ORDER123",
            symbol="BTCUSDT",
            order_type="take_profit",
            side="buy",
            price=47500.0,
            quantity=0.1,
            status="pending",
        )
        db_session.add(limit_order)
        db_session.commit()

        repo = PositionRepository(db_session)
        result = repo.update_take_profit_status(position.id, "filled", fill_price=47500.0)

        assert result.take_profit_order_status == "filled"

        # Verify limit order was updated
        updated_order = db_session.query(LimitOrder).filter_by(order_id="ORDER123").first()
        assert updated_order.status == "filled"
        assert updated_order.filled_at is not None
        assert updated_order.avg_fill_price == 47500.0

    def test_get_positions_with_pending_tp(self, db_session):
        """Test getting positions with pending TP orders."""
        db_session.add(
            Position(
                symbol="BTC1",
                entry_price=50000.0,
                current_price=50000.0,
                quantity=0.1,
                margin=100.0,
                leverage=20,
                take_profit_price=47500.0,
                status="open",
                take_profit_order_status="pending",
            )
        )
        db_session.add(
            Position(
                symbol="BTC2",
                entry_price=50000.0,
                current_price=50000.0,
                quantity=0.1,
                margin=100.0,
                leverage=20,
                take_profit_price=47500.0,
                status="open",
                take_profit_order_status="filled",
            )
        )
        db_session.commit()

        repo = PositionRepository(db_session)
        positions = repo.get_positions_with_pending_tp()

        assert len(positions) == 1
        assert positions[0].symbol == "BTC1"

    def test_get_positions_with_failed_tp(self, db_session):
        """Test getting positions with failed TP orders."""
        db_session.add(
            Position(
                symbol="BTC1",
                entry_price=50000.0,
                current_price=50000.0,
                quantity=0.1,
                margin=100.0,
                leverage=20,
                take_profit_price=47500.0,
                status="open",
                take_profit_order_status="failed",
            )
        )
        db_session.add(
            Position(
                symbol="BTC2",
                entry_price=50000.0,
                current_price=50000.0,
                quantity=0.1,
                margin=100.0,
                leverage=20,
                take_profit_price=47500.0,
                status="open",
                take_profit_order_status="pending",
            )
        )
        db_session.commit()

        repo = PositionRepository(db_session)
        positions = repo.get_positions_with_failed_tp()

        assert len(positions) == 1
        assert positions[0].symbol == "BTC1"


class TestTradeHistoryRepository:
    """Test TradeHistoryRepository."""

    def test_get_recent(self, db_session):
        """Test getting recent trades."""
        # Create trades at different times
        for i in range(5):
            trade = TradeHistory(
                symbol=f"BTC{i}",
                entry_price=50000.0,
                exit_price=47500.0,
                quantity=0.1,
                margin=100.0,
                leverage=20,
                side="short",
                opened_at=datetime.utcnow() - timedelta(days=i),
                closed_at=datetime.utcnow() - timedelta(days=i),
                pnl=250.0,
                pnl_pct=5.0,
            )
            db_session.add(trade)
        db_session.commit()

        repo = TradeHistoryRepository(db_session)
        recent = repo.get_recent(limit=3)

        assert len(recent) == 3
        # Should be in descending order (most recent first)
        assert recent[0].symbol == "BTC0"

    def test_get_by_symbol(self, db_session):
        """Test getting trade history by symbol."""
        db_session.add(
            TradeHistory(
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
        )
        db_session.add(
            TradeHistory(
                symbol="ETHUSDT",
                entry_price=3000.0,
                exit_price=2850.0,
                quantity=1.0,
                margin=150.0,
                leverage=20,
                side="short",
                opened_at=datetime.utcnow(),
                pnl=150.0,
                pnl_pct=5.0,
            )
        )
        db_session.commit()

        repo = TradeHistoryRepository(db_session)
        btc_trades = repo.get_by_symbol("BTCUSDT")

        assert len(btc_trades) == 1
        assert btc_trades[0].symbol == "BTCUSDT"

    def test_get_statistics_empty(self, db_session):
        """Test statistics with no trades."""
        repo = TradeHistoryRepository(db_session)
        stats = repo.get_statistics()

        assert stats["total_trades"] == 0
        assert stats["winning_trades"] == 0
        assert stats["losing_trades"] == 0
        assert stats["total_pnl"] == 0.0
        assert stats["win_rate"] == 0.0

    def test_get_statistics(self, db_session):
        """Test calculating trading statistics."""
        # Add winning trades
        db_session.add(
            TradeHistory(
                symbol="WIN1",
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
        )
        db_session.add(
            TradeHistory(
                symbol="WIN2",
                entry_price=3000.0,
                exit_price=2850.0,
                quantity=1.0,
                margin=150.0,
                leverage=20,
                side="short",
                opened_at=datetime.utcnow(),
                pnl=150.0,
                pnl_pct=5.0,
            )
        )

        # Add losing trade
        db_session.add(
            TradeHistory(
                symbol="LOSS1",
                entry_price=50000.0,
                exit_price=52000.0,
                quantity=0.1,
                margin=100.0,
                leverage=20,
                side="short",
                opened_at=datetime.utcnow(),
                pnl=-200.0,
                pnl_pct=-4.0,
            )
        )
        db_session.commit()

        repo = TradeHistoryRepository(db_session)
        stats = repo.get_statistics()

        assert stats["total_trades"] == 3
        assert stats["winning_trades"] == 2
        assert stats["losing_trades"] == 1
        assert stats["total_pnl"] == 200.0
        assert stats["win_rate"] == 66.67


class TestLimitOrderRepository:
    """Test LimitOrderRepository."""

    def test_get_by_order_id(self, db_session):
        """Test getting order by ID."""
        position = Position(
            symbol="BTCUSDT",
            entry_price=50000.0,
            current_price=50000.0,
            quantity=0.1,
            margin=100.0,
            leverage=20,
            take_profit_price=47500.0,
        )
        db_session.add(position)
        db_session.commit()

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

        repo = LimitOrderRepository(db_session)
        result = repo.get_by_order_id("ORDER123")

        assert result is not None
        assert result.order_id == "ORDER123"

    def test_get_by_position(self, db_session):
        """Test getting all orders for a position."""
        position = Position(
            symbol="BTCUSDT",
            entry_price=50000.0,
            current_price=50000.0,
            quantity=0.1,
            margin=100.0,
            leverage=20,
            take_profit_price=47500.0,
        )
        db_session.add(position)
        db_session.commit()

        db_session.add(
            LimitOrder(
                position_id=position.id,
                order_id="ORDER1",
                symbol="BTCUSDT",
                order_type="take_profit",
                side="buy",
                price=47500.0,
                quantity=0.1,
            )
        )
        db_session.add(
            LimitOrder(
                position_id=position.id,
                order_id="ORDER2",
                symbol="BTCUSDT",
                order_type="stop_loss",
                side="buy",
                price=52500.0,
                quantity=0.1,
            )
        )
        db_session.commit()

        repo = LimitOrderRepository(db_session)
        orders = repo.get_by_position(position.id)

        assert len(orders) == 2

    def test_get_pending_orders(self, db_session):
        """Test getting pending orders."""
        position = Position(
            symbol="BTCUSDT",
            entry_price=50000.0,
            current_price=50000.0,
            quantity=0.1,
            margin=100.0,
            leverage=20,
            take_profit_price=47500.0,
        )
        db_session.add(position)
        db_session.commit()

        db_session.add(
            LimitOrder(
                position_id=position.id,
                order_id="PENDING1",
                symbol="BTCUSDT",
                order_type="take_profit",
                side="buy",
                price=47500.0,
                quantity=0.1,
                status="pending",
            )
        )
        db_session.add(
            LimitOrder(
                position_id=position.id,
                order_id="FILLED1",
                symbol="BTCUSDT",
                order_type="take_profit",
                side="buy",
                price=47500.0,
                quantity=0.1,
                status="filled",
            )
        )
        db_session.commit()

        repo = LimitOrderRepository(db_session)
        pending = repo.get_pending_orders()

        assert len(pending) == 1
        assert pending[0].order_id == "PENDING1"

    def test_update_status(self, db_session):
        """Test updating order status."""
        position = Position(
            symbol="BTCUSDT",
            entry_price=50000.0,
            current_price=50000.0,
            quantity=0.1,
            margin=100.0,
            leverage=20,
            take_profit_price=47500.0,
        )
        db_session.add(position)
        db_session.commit()

        order = LimitOrder(
            position_id=position.id,
            order_id="ORDER123",
            symbol="BTCUSDT",
            order_type="take_profit",
            side="buy",
            price=47500.0,
            quantity=0.1,
            status="pending",
        )
        db_session.add(order)
        db_session.commit()

        repo = LimitOrderRepository(db_session)
        repo.update_status("ORDER123", "filled", fill_price=47500.0, filled_quantity=0.1)

        updated = db_session.query(LimitOrder).filter_by(order_id="ORDER123").first()
        assert updated.status == "filled"
        assert updated.avg_fill_price == 47500.0
        assert updated.filled_quantity == 0.1
        assert updated.filled_at is not None


class TestMarketSignalRepository:
    """Test MarketSignalRepository."""

    def test_create_signal(self, db_session):
        """Test creating market signal."""
        repo = MarketSignalRepository(db_session)
        signal = repo.create(
            symbol="BTCUSDT",
            signal_type="pump_detected",
            price=50000.0,
            volume_24h=1000000.0,
            price_change_pct=35.0,
            score=0.85,
        )

        assert signal.id is not None
        assert signal.symbol == "BTCUSDT"
        assert signal.action_taken is False

    def test_mark_action_taken(self, db_session):
        """Test marking signal action as taken."""
        signal = MarketSignal(symbol="BTCUSDT", signal_type="pump_detected", price=50000.0, action_taken=False)
        db_session.add(signal)
        db_session.commit()

        repo = MarketSignalRepository(db_session)
        repo.mark_action_taken(signal.id)

        updated = db_session.query(MarketSignal).filter_by(id=signal.id).first()
        assert updated.action_taken is True

    def test_cleanup_old_signals(self, db_session):
        """Test cleaning up old signals."""
        # Add old signal
        old_signal = MarketSignal(
            symbol="OLD", signal_type="pump_detected", price=50000.0, created_at=datetime.utcnow() - timedelta(days=40)
        )
        db_session.add(old_signal)

        # Add recent signal
        new_signal = MarketSignal(symbol="NEW", signal_type="pump_detected", price=50000.0, created_at=datetime.utcnow())
        db_session.add(new_signal)
        db_session.commit()

        repo = MarketSignalRepository(db_session)
        deleted = repo.cleanup_old_signals(retention_days=30)

        assert deleted == 1
        # Verify old signal was deleted
        remaining = db_session.query(MarketSignal).all()
        assert len(remaining) == 1
        assert remaining[0].symbol == "NEW"


class TestBotStatusRepository:
    """Test BotStatusRepository."""

    def test_get_creates_if_not_exists(self, db_session):
        """Test that get() creates status if it doesn't exist."""
        repo = BotStatusRepository(db_session)
        status = repo.get()

        assert status is not None
        assert status.is_active is True
        assert status.is_paused is False

    def test_update_scan_time(self, db_session):
        """Test updating scan time."""
        repo = BotStatusRepository(db_session)
        status = repo.get()
        old_time = status.last_scan_at

        repo.update_scan_time()

        updated = repo.get()
        assert updated.last_scan_at is not None
        assert updated.last_scan_at != old_time

    def test_update_monitor_time(self, db_session):
        """Test updating monitor time."""
        repo = BotStatusRepository(db_session)
        repo.update_monitor_time()

        status = repo.get()
        assert status.last_monitor_at is not None

    def test_set_active(self, db_session):
        """Test setting active status."""
        repo = BotStatusRepository(db_session)
        repo.set_active(False)

        status = repo.get()
        assert status.is_active is False

    def test_set_paused(self, db_session):
        """Test setting paused status."""
        repo = BotStatusRepository(db_session)
        repo.set_paused(True)

        status = repo.get()
        assert status.is_paused is True

    def test_increment_opened(self, db_session):
        """Test incrementing opened positions."""
        repo = BotStatusRepository(db_session)
        status = repo.get()
        initial = status.total_positions_opened

        repo.increment_opened()

        updated = repo.get()
        assert updated.total_positions_opened == initial + 1

    def test_increment_closed(self, db_session):
        """Test incrementing closed positions."""
        repo = BotStatusRepository(db_session)
        status = repo.get()
        initial_closed = status.total_positions_closed
        initial_pnl = status.total_pnl

        repo.increment_closed(pnl=250.0)

        updated = repo.get()
        assert updated.total_positions_closed == initial_closed + 1
        assert updated.total_pnl == initial_pnl + 250.0
