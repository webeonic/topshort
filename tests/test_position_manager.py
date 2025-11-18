"""Unit tests for PositionManager."""

from decimal import Decimal
from unittest.mock import MagicMock, Mock, call, patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.config import TradingConfig
from src.database.models import Base, Position
from src.database.repository import BotStatusRepository, PositionRepository, SettingsRepository
from src.trading.position_manager import PositionManager


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
    client.open_short_position = Mock()
    client.close_short_position = Mock()
    client.create_limit_order = Mock()
    client.get_ticker = Mock()
    client.fetch_tickers = Mock()
    return client


@pytest.fixture
def config():
    """Create test trading config."""
    return TradingConfig(
        margin_per_trade=100.0, max_positions=10, max_total_margin=1000.0, take_profit_pct=5.0, default_leverage=20
    )


@pytest.fixture
def position_manager(db_session, mock_client, config):
    """Create PositionManager instance."""
    return PositionManager(db_session, mock_client, config)


class TestPositionManagerInit:
    """Test PositionManager initialization."""

    def test_initialization(self, position_manager, db_session, mock_client, config):
        """Test that PositionManager initializes correctly."""
        assert position_manager.session == db_session
        assert position_manager.client == mock_client
        assert position_manager.config == config
        assert isinstance(position_manager.position_repo, PositionRepository)
        assert isinstance(position_manager.settings_repo, SettingsRepository)
        assert isinstance(position_manager.bot_status_repo, BotStatusRepository)


class TestTakeProfitCalculation:
    """Test take profit price calculation."""

    def test_get_take_profit_pct_from_config(self, position_manager):
        """Test getting TP percentage from config."""
        tp_pct = position_manager.get_take_profit_pct()
        assert tp_pct == 5.0

    def test_calculate_take_profit_price(self, position_manager):
        """Test calculating TP price for short position."""
        entry_price = 50000.0
        tp_price = position_manager.calculate_take_profit_price(entry_price)

        # For short: TP = entry * (1 - 0.05) = 50000 * 0.95 = 47500
        assert tp_price == 47500.0

    def test_calculate_take_profit_precision(self, position_manager):
        """Test TP calculation precision."""
        entry_price = 33333.33
        tp_price = position_manager.calculate_take_profit_price(entry_price)

        # Should use Decimal for precision
        expected = 33333.33 * 0.95
        assert abs(tp_price - expected) < 0.01

    def test_calculate_take_profit_various_prices(self, position_manager):
        """Test TP calculation with various prices."""
        test_cases = [
            (100.0, 95.0),
            (1000.0, 950.0),
            (0.001, 0.00095),
        ]

        for entry, expected_tp in test_cases:
            tp_price = position_manager.calculate_take_profit_price(entry)
            assert abs(tp_price - expected_tp) < 0.0001


class TestOpenPosition:
    """Test opening positions."""

    def test_open_position_success(self, position_manager, mock_client, db_session):
        """Test successfully opening a position."""
        # Mock exchange responses
        mock_client.open_short_position.return_value = {"id": "ORDER123", "average": 50000.0, "filled": 0.1}
        mock_client.create_limit_order.return_value = {"id": "TP_ORDER123"}

        result = position_manager.open_position("BTCUSDT", 100.0, 20)

        assert result is not None
        assert result["symbol"] == "BTCUSDT"
        assert result["entry_price"] == 50000.0
        assert result["quantity"] == 0.1
        assert result["take_profit_price"] == 47500.0
        assert result["take_profit_order_id"] == "TP_ORDER123"

        # Verify exchange was called
        mock_client.open_short_position.assert_called_once_with("BTCUSDT", 100.0, 20)
        mock_client.create_limit_order.assert_called_once()

        # Verify position was saved to database
        position = db_session.query(Position).filter_by(symbol="BTCUSDT").first()
        assert position is not None
        assert position.status == "open"
        assert position.take_profit_order_id == "TP_ORDER123"

    def test_open_position_exchange_failure(self, position_manager, mock_client):
        """Test handling exchange failure when opening position."""
        mock_client.open_short_position.return_value = None

        result = position_manager.open_position("BTCUSDT", 100.0, 20)

        assert result is None

    def test_open_position_no_entry_price(self, position_manager, mock_client):
        """Test handling missing entry price."""
        mock_client.open_short_position.return_value = {"id": "ORDER123", "filled": 0.1}
        mock_client.get_ticker.return_value = {"last": 50000.0}
        mock_client.create_limit_order.return_value = {"id": "TP_ORDER123"}

        result = position_manager.open_position("BTCUSDT", 100.0, 20)

        # Should fallback to ticker price
        assert result is not None
        assert result["entry_price"] == 50000.0

    def test_open_position_tp_order_fails(self, position_manager, mock_client, db_session):
        """Test handling TP order placement failure."""
        mock_client.open_short_position.return_value = {"id": "ORDER123", "average": 50000.0, "filled": 0.1}
        mock_client.create_limit_order.return_value = None  # TP order fails

        result = position_manager.open_position("BTCUSDT", 100.0, 20)

        assert result is not None
        assert result["take_profit_order_id"] is None

        # Verify position was still saved with failed TP status
        position = db_session.query(Position).filter_by(symbol="BTCUSDT").first()
        assert position is not None
        assert position.take_profit_order_status == "failed"

    def test_open_position_db_error_cleanup(self, position_manager, mock_client, db_session):
        """Test cleanup of orphaned exchange position on DB error."""
        mock_client.open_short_position.return_value = {"id": "ORDER123", "average": 50000.0, "filled": 0.1}
        mock_client.create_limit_order.side_effect = Exception("DB Error")
        mock_client.close_short_position.return_value = {"success": True}

        result = position_manager.open_position("BTCUSDT", 100.0, 20)

        assert result is None
        # Verify cleanup was attempted
        mock_client.close_short_position.assert_called()

    def test_open_position_creates_correct_limit_order(self, position_manager, mock_client):
        """Test that limit order is created with correct parameters."""
        mock_client.open_short_position.return_value = {"id": "ORDER123", "average": 50000.0, "filled": 0.1}
        mock_client.create_limit_order.return_value = {"id": "TP_ORDER123"}

        position_manager.open_position("BTCUSDT", 100.0, 20)

        # Verify limit order call
        call_args = mock_client.create_limit_order.call_args
        assert call_args[1]["symbol"] == "BTCUSDT"
        assert call_args[1]["side"] == "buy"  # Buy to close short
        assert call_args[1]["quantity"] == 0.1
        assert call_args[1]["price"] == 47500.0  # TP price
        assert call_args[1]["position_side"] == "SHORT"


class TestClosePosition:
    """Test closing positions."""

    def test_close_position_success(self, position_manager, mock_client, db_session):
        """Test successfully closing a position."""
        # Create open position
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

        # Mock exchange response
        mock_client.close_short_position.return_value = {"average": 47500.0}

        result = position_manager.close_position(position.id, "take_profit")

        assert result is not None
        assert result["symbol"] == "BTCUSDT"
        assert result["exit_price"] == 47500.0
        assert result["pnl"] == 250.0  # (50000 - 47500) * 0.1
        assert result["pnl_pct"] == 5.0
        assert result["reason"] == "take_profit"

        # Verify position is closed in database
        updated = db_session.query(Position).filter_by(id=position.id).first()
        assert updated.status == "closed"

    def test_close_nonexistent_position(self, position_manager, mock_client):
        """Test closing position that doesn't exist."""
        result = position_manager.close_position(99999, "manual")
        assert result is None

    def test_close_already_closed_position(self, position_manager, mock_client, db_session):
        """Test closing position that's already closed."""
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

        result = position_manager.close_position(position.id, "manual")
        assert result is None

    def test_close_position_exchange_failure(self, position_manager, mock_client, db_session):
        """Test handling exchange failure when closing."""
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

        mock_client.close_short_position.return_value = None

        result = position_manager.close_position(position.id, "manual")
        assert result is None

    def test_close_position_fallback_price(self, position_manager, mock_client, db_session):
        """Test using fallback price when order doesn't have average."""
        position = Position(
            symbol="BTCUSDT",
            entry_price=50000.0,
            current_price=48000.0,
            quantity=0.1,
            margin=100.0,
            leverage=20,
            take_profit_price=47500.0,
            status="open",
        )
        db_session.add(position)
        db_session.commit()

        mock_client.close_short_position.return_value = {"id": "CLOSE123"}
        mock_client.get_ticker.return_value = {"last": 48500.0}

        result = position_manager.close_position(position.id, "manual")

        # Should use ticker price as fallback
        assert result is not None
        assert result["exit_price"] == 48500.0


class TestMonitorPositions:
    """Test position monitoring."""

    def test_monitor_positions_empty(self, position_manager):
        """Test monitoring with no open positions."""
        closed = position_manager.monitor_positions()
        assert closed == []

    def test_monitor_positions_tp_reached(self, position_manager, mock_client, db_session):
        """Test closing position when TP is reached."""
        # Create open position
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

        # Mock current price at TP
        mock_client.fetch_tickers.return_value = {"BTCUSDT": {"last": 47500.0}}
        mock_client.close_short_position.return_value = {"average": 47500.0}

        closed = position_manager.monitor_positions()

        assert len(closed) == 1
        assert closed[0]["symbol"] == "BTCUSDT"

        # Verify position was closed
        updated = db_session.query(Position).filter_by(id=position.id).first()
        assert updated.status == "closed"

    def test_monitor_positions_tp_not_reached(self, position_manager, mock_client, db_session):
        """Test position stays open when TP not reached."""
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

        # Mock current price above TP
        mock_client.fetch_tickers.return_value = {"BTCUSDT": {"last": 49000.0}}

        closed = position_manager.monitor_positions()

        assert len(closed) == 0

        # Verify position still open but price updated
        updated = db_session.query(Position).filter_by(id=position.id).first()
        assert updated.status == "open"
        assert updated.current_price == 49000.0

    def test_monitor_multiple_positions(self, position_manager, mock_client, db_session):
        """Test monitoring multiple positions."""
        # Create two positions
        pos1 = Position(
            symbol="BTCUSDT",
            entry_price=50000.0,
            current_price=50000.0,
            quantity=0.1,
            margin=100.0,
            leverage=20,
            take_profit_price=47500.0,
            status="open",
        )
        pos2 = Position(
            symbol="ETHUSDT",
            entry_price=3000.0,
            current_price=3000.0,
            quantity=1.0,
            margin=150.0,
            leverage=20,
            take_profit_price=2850.0,
            status="open",
        )
        db_session.add(pos1)
        db_session.add(pos2)
        db_session.commit()

        # Mock BTC at TP, ETH above TP
        mock_client.fetch_tickers.return_value = {"BTCUSDT": {"last": 47500.0}, "ETHUSDT": {"last": 2900.0}}
        mock_client.close_short_position.return_value = {"average": 47500.0}

        closed = position_manager.monitor_positions()

        # Only BTC should be closed
        assert len(closed) == 1
        assert closed[0]["symbol"] == "BTCUSDT"

    def test_monitor_positions_batch_ticker_fetch(self, position_manager, mock_client, db_session):
        """Test that tickers are fetched in batch."""
        # Create multiple positions
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

        mock_client.fetch_tickers.return_value = {
            "BTC0": {"last": 49000.0},
            "BTC1": {"last": 49000.0},
            "BTC2": {"last": 49000.0},
        }

        position_manager.monitor_positions()

        # Verify single batch call was made
        mock_client.fetch_tickers.assert_called_once()
        call_args = mock_client.fetch_tickers.call_args[0][0]
        assert len(call_args) == 3


class TestGetAllOpenPositions:
    """Test getting all open positions."""

    def test_get_all_open_empty(self, position_manager):
        """Test with no open positions."""
        positions = position_manager.get_all_open_positions()
        assert positions == []

    def test_get_all_open_with_unrealized_pnl(self, position_manager, db_session):
        """Test calculating unrealized P&L."""
        position = Position(
            symbol="BTCUSDT",
            entry_price=50000.0,
            current_price=49000.0,
            quantity=0.1,
            margin=100.0,
            leverage=20,
            take_profit_price=47500.0,
            status="open",
        )
        db_session.add(position)
        db_session.commit()

        positions = position_manager.get_all_open_positions()

        assert len(positions) == 1
        assert positions[0]["symbol"] == "BTCUSDT"
        # Unrealized P&L = (50000 - 49000) * 0.1 = 100
        assert positions[0]["unrealized_pnl"] == 100.0
        assert positions[0]["unrealized_pnl_pct"] == 2.0

    def test_get_all_open_negative_pnl(self, position_manager, db_session):
        """Test with negative unrealized P&L."""
        position = Position(
            symbol="BTCUSDT",
            entry_price=50000.0,
            current_price=51000.0,  # Price went up (bad for short)
            quantity=0.1,
            margin=100.0,
            leverage=20,
            take_profit_price=47500.0,
            status="open",
        )
        db_session.add(position)
        db_session.commit()

        positions = position_manager.get_all_open_positions()

        assert len(positions) == 1
        # Unrealized P&L = (50000 - 51000) * 0.1 = -100
        assert positions[0]["unrealized_pnl"] == -100.0
        assert positions[0]["unrealized_pnl_pct"] == -2.0


class TestClosePositionBySymbol:
    """Test closing position by symbol."""

    def test_close_by_symbol_success(self, position_manager, mock_client, db_session):
        """Test closing position by symbol."""
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

        mock_client.close_short_position.return_value = {"average": 47500.0}

        result = position_manager.close_position_by_symbol("BTCUSDT", "manual")

        assert result is not None
        assert result["symbol"] == "BTCUSDT"

    def test_close_by_symbol_not_found(self, position_manager, mock_client):
        """Test closing non-existent symbol."""
        result = position_manager.close_position_by_symbol("NONEXISTENT", "manual")
        assert result is None
