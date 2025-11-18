"""Unit tests for LimitOrderMonitor."""

from unittest.mock import Mock

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.database.models import Base, LimitOrder, Position
from src.trading.limit_order_monitor import LimitOrderMonitor


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


@pytest.fixture
def mock_client():
    """Create mock Binance client."""
    client = Mock()
    client.exchange = Mock()
    client.create_limit_order = Mock()
    return client


@pytest.fixture
def monitor(db_session, mock_client):
    """Create LimitOrderMonitor instance."""
    return LimitOrderMonitor(db_session, mock_client)


class TestMonitorTakeProfitOrders:
    """Test monitoring TP orders."""

    def test_monitor_no_pending_orders(self, monitor):
        """Test with no pending TP orders."""
        closed = monitor.monitor_take_profit_orders()
        assert closed == []

    def test_monitor_order_filled(self, monitor, mock_client, db_session):
        """Test closing position when TP order is filled."""
        # Create position with pending TP
        position = Position(
            symbol="BTCUSDT",
            entry_price=50000.0,
            current_price=50000.0,
            quantity=0.1,
            margin=100.0,
            leverage=20,
            take_profit_price=47500.0,
            take_profit_order_id="TP123",
            take_profit_order_status="pending",
            status="open",
        )
        db_session.add(position)
        db_session.commit()

        # Create limit order
        limit_order = LimitOrder(
            position_id=position.id,
            order_id="TP123",
            symbol="BTCUSDT",
            order_type="take_profit",
            side="buy",
            price=47500.0,
            quantity=0.1,
            status="pending",
        )
        db_session.add(limit_order)
        db_session.commit()

        # Mock filled order status
        mock_client.exchange.fetch_order.return_value = {"status": "filled", "filled": 0.1, "average": 47500.0}

        closed = monitor.monitor_take_profit_orders()

        assert len(closed) == 1
        assert closed[0]["symbol"] == "BTCUSDT"
        assert closed[0]["reason"] == "take_profit"

        # Verify position is closed
        updated = db_session.query(Position).filter_by(id=position.id).first()
        assert updated.status == "closed"

    def test_monitor_order_cancelled(self, monitor, mock_client, db_session):
        """Test handling cancelled TP order."""
        position = Position(
            symbol="BTCUSDT",
            entry_price=50000.0,
            current_price=50000.0,
            quantity=0.1,
            margin=100.0,
            leverage=20,
            take_profit_price=47500.0,
            take_profit_order_id="TP123",
            take_profit_order_status="pending",
            status="open",
        )
        db_session.add(position)
        db_session.commit()

        mock_client.exchange.fetch_order.return_value = {"status": "canceled", "filled": 0}

        closed = monitor.monitor_take_profit_orders()

        assert len(closed) == 0

        # Verify TP status updated
        updated = db_session.query(Position).filter_by(id=position.id).first()
        assert updated.take_profit_order_status == "cancelled"
        assert updated.status == "open"  # Position still open

    def test_monitor_order_pending(self, monitor, mock_client, db_session):
        """Test order still pending."""
        position = Position(
            symbol="BTCUSDT",
            entry_price=50000.0,
            current_price=50000.0,
            quantity=0.1,
            margin=100.0,
            leverage=20,
            take_profit_price=47500.0,
            take_profit_order_id="TP123",
            take_profit_order_status="pending",
            status="open",
        )
        db_session.add(position)
        db_session.commit()

        mock_client.exchange.fetch_order.return_value = {"status": "open", "filled": 0}  # Still pending

        closed = monitor.monitor_take_profit_orders()

        assert len(closed) == 0

        # Position should still be open
        updated = db_session.query(Position).filter_by(id=position.id).first()
        assert updated.status == "open"
        assert updated.take_profit_order_status == "pending"


class TestRetryFailedOrders:
    """Test retrying failed TP orders."""

    def test_retry_no_failed_orders(self, monitor):
        """Test with no failed orders."""
        count = monitor.retry_failed_take_profit_orders()
        assert count == 0

    def test_retry_failed_order_success(self, monitor, mock_client, db_session):
        """Test successfully retrying failed order."""
        position = Position(
            symbol="BTCUSDT",
            entry_price=50000.0,
            current_price=50000.0,
            quantity=0.1,
            margin=100.0,
            leverage=20,
            take_profit_price=47500.0,
            take_profit_order_status="failed",
            status="open",
        )
        db_session.add(position)
        db_session.commit()

        mock_client.create_limit_order.return_value = {"id": "TP_NEW123"}

        count = monitor.retry_failed_take_profit_orders()

        assert count == 1

        # Verify new order placed
        updated = db_session.query(Position).filter_by(id=position.id).first()
        assert updated.take_profit_order_id == "TP_NEW123"
        assert updated.take_profit_order_status == "pending"

    def test_retry_failed_order_fails_again(self, monitor, mock_client, db_session):
        """Test retry that fails again."""
        position = Position(
            symbol="BTCUSDT",
            entry_price=50000.0,
            current_price=50000.0,
            quantity=0.1,
            margin=100.0,
            leverage=20,
            take_profit_price=47500.0,
            take_profit_order_status="failed",
            status="open",
        )
        db_session.add(position)
        db_session.commit()

        mock_client.create_limit_order.return_value = None

        count = monitor.retry_failed_take_profit_orders()

        assert count == 0


class TestCancelTakeProfitOrder:
    """Test cancelling TP orders."""

    def test_cancel_order_success(self, monitor, mock_client, db_session):
        """Test successfully cancelling order."""
        position = Position(
            symbol="BTCUSDT",
            entry_price=50000.0,
            current_price=50000.0,
            quantity=0.1,
            margin=100.0,
            leverage=20,
            take_profit_price=47500.0,
            take_profit_order_id="TP123",
            take_profit_order_status="pending",
            status="open",
        )
        db_session.add(position)
        db_session.commit()

        mock_client.exchange.cancel_order.return_value = {"success": True}

        result = monitor.cancel_take_profit_order(position.id)

        assert result is True

        # Verify status updated
        updated = db_session.query(Position).filter_by(id=position.id).first()
        assert updated.take_profit_order_status == "cancelled"

    def test_cancel_nonexistent_position(self, monitor):
        """Test cancelling for non-existent position."""
        result = monitor.cancel_take_profit_order(99999)
        assert result is False

    def test_cancel_position_without_order(self, monitor, db_session):
        """Test cancelling for position without TP order."""
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

        result = monitor.cancel_take_profit_order(position.id)
        assert result is False


class TestGetOrderStatus:
    """Test getting order status from exchange."""

    def test_get_order_status_success(self, monitor, mock_client):
        """Test successfully getting order status."""
        mock_client.exchange.fetch_order.return_value = {"id": "ORDER123", "status": "filled"}

        status = monitor._get_order_status("BTCUSDT", "ORDER123")

        assert status is not None
        assert status["status"] == "filled"

    def test_get_order_status_error(self, monitor, mock_client):
        """Test handling error when fetching order."""
        mock_client.exchange.fetch_order.side_effect = Exception("Network error")

        status = monitor._get_order_status("BTCUSDT", "ORDER123")

        assert status is None
