"""Unit tests for ExchangePositionSync."""

from unittest.mock import Mock

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.config import TradingConfig
from src.database.models import Base, Position
from src.trading.exchange_position_sync import ExchangePositionSync


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
    client.get_positions = Mock()
    client.get_ticker = Mock()
    return client


@pytest.fixture
def config():
    """Create test trading config."""
    return TradingConfig(
        margin_per_trade=100.0, max_positions=10, max_total_margin=1000.0, take_profit_pct=5.0, default_leverage=20
    )


@pytest.fixture
def sync_service(db_session, mock_client, config):
    """Create ExchangePositionSync instance."""
    return ExchangePositionSync(db_session, mock_client, config)


class TestSyncPositionsFromExchange:
    """Test syncing positions from exchange."""

    def test_sync_no_positions(self, sync_service, mock_client):
        """Test sync with no exchange positions."""
        mock_client.get_positions.return_value = []

        stats = sync_service.sync_positions_from_exchange()

        assert stats["total"] == 0
        assert stats["new"] == 0

    def test_sync_new_position(self, sync_service, mock_client, db_session):
        """Test importing new position from exchange."""
        mock_client.get_positions.return_value = [
            {"symbol": "BTCUSDT", "side": "short", "entryPrice": 50000.0, "contracts": 0.1, "leverage": 20}
        ]

        stats = sync_service.sync_positions_from_exchange()

        assert stats["new"] == 1
        assert stats["total"] == 1

        # Verify position was created
        position = db_session.query(Position).filter_by(symbol="BTCUSDT").first()
        assert position is not None
        assert position.source == "external_system"
        assert position.entry_price == 50000.0

    def test_sync_existing_position(self, sync_service, mock_client, db_session):
        """Test sync with existing position."""
        # Create existing position
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

        mock_client.get_positions.return_value = [
            {"symbol": "BTCUSDT", "side": "short", "entryPrice": 50000.0, "contracts": 0.1, "leverage": 20}
        ]

        stats = sync_service.sync_positions_from_exchange()

        assert stats["existing"] == 1
        assert stats["new"] == 0

    def test_sync_filters_non_short_positions(self, sync_service, mock_client, db_session):
        """Test that only short positions are synced."""
        mock_client.get_positions.return_value = [
            {"symbol": "BTCUSDT", "side": "long", "entryPrice": 50000.0, "contracts": 0.1, "leverage": 20},  # Not short
            {"symbol": "ETHUSDT", "side": "short", "entryPrice": 3000.0, "contracts": 1.0, "leverage": 20},
        ]

        stats = sync_service.sync_positions_from_exchange()

        # Only short position should be synced
        assert stats["total"] == 1
        assert db_session.query(Position).filter_by(symbol="ETHUSDT").first() is not None
        assert db_session.query(Position).filter_by(symbol="BTCUSDT").first() is None


class TestGetActivePositions:
    """Test getting active position counts."""

    def test_get_total_active_pairs(self, sync_service, db_session):
        """Test getting total active pairs."""
        for i in range(3):
            db_session.add(
                Position(
                    symbol=f"BTC{i}",
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

        total = sync_service.get_total_active_pairs()
        assert total == 3

    def test_get_active_pairs_by_source(self, sync_service, db_session):
        """Test getting pairs by source."""
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

        by_source = sync_service.get_active_pairs_by_source()

        assert by_source["bot_auto"] == 1
        assert by_source["manual"] == 1


class TestCheckPositionLimits:
    """Test position limit checking."""

    def test_check_position_limits_can_open(self, sync_service):
        """Test can open position when under limit."""
        result = sync_service.check_position_limits(max_positions=5)

        assert result["can_open_position"] is True
        assert result["current_positions"] == 0
        assert result["available_slots"] == 5

    def test_check_position_limits_at_max(self, sync_service, db_session):
        """Test at max positions."""
        for i in range(5):
            db_session.add(
                Position(
                    symbol=f"BTC{i}",
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

        result = sync_service.check_position_limits(max_positions=5)

        assert result["can_open_position"] is False
        assert result["current_positions"] == 5
        assert result["available_slots"] == 0


class TestReconcileClosedPositions:
    """Test reconciling closed positions."""

    def test_reconcile_no_positions(self, sync_service, mock_client):
        """Test reconcile with no positions."""
        mock_client.get_positions.return_value = []

        count = sync_service.reconcile_closed_positions()
        assert count == 0

    def test_reconcile_position_closed_externally(self, sync_service, mock_client, db_session):
        """Test reconciling position closed externally."""
        # Create open position in database
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

        # Exchange has no positions (was closed externally)
        mock_client.get_positions.return_value = []
        mock_client.get_ticker.return_value = {"last": 48000.0}

        count = sync_service.reconcile_closed_positions()

        assert count == 1

        # Verify position was closed in database
        updated = db_session.query(Position).filter_by(id=position.id).first()
        assert updated.status == "closed"

    def test_reconcile_position_still_open(self, sync_service, mock_client, db_session):
        """Test position still open on exchange."""
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

        # Position still exists on exchange
        mock_client.get_positions.return_value = [
            {"symbol": "BTCUSDT", "side": "short", "entryPrice": 50000.0, "contracts": 0.1, "leverage": 20}
        ]

        count = sync_service.reconcile_closed_positions()

        assert count == 0

        # Position should still be open
        updated = db_session.query(Position).filter_by(id=position.id).first()
        assert updated.status == "open"


class TestGetRiskSummary:
    """Test getting risk summary."""

    def test_get_risk_summary(self, sync_service, db_session):
        """Test getting comprehensive risk summary."""
        # Add positions
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
                margin=150.0,
                leverage=20,
                take_profit_price=47500.0,
                source="manual",
                status="open",
            )
        )
        db_session.commit()

        summary = sync_service.get_risk_summary()

        assert summary["total_positions"] == 2
        assert summary["total_margin_used"] == 250.0
        assert "positions_by_source" in summary
        assert summary["positions_by_source"]["bot_auto"] == 1
        assert summary["positions_by_source"]["manual"] == 1
