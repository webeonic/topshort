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
    client.open_long_position = Mock()
    client.close_short_position = Mock()
    client.close_long_position = Mock()
    client.create_limit_order = Mock()
    client.get_ticker = Mock()
    client.fetch_tickers = Mock()
    client.get_position_by_symbol = Mock()
    client.get_positions = Mock(return_value=[])  # Batch fetch for monitor_positions
    client.fetch_order = Mock()
    # Mock exchange.market() for symbol conversion (CCXT unified -> exchange native)
    # In tests, symbols are already in native format (e.g., "BTCUSDT"), so return same symbol
    client.exchange = Mock()
    client.exchange.market = Mock(side_effect=lambda symbol: {"id": symbol})
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
    manager = PositionManager(db_session, mock_client, config)
    manager._wait_for_position_confirmation = MagicMock(return_value=None)
    return manager


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

    def test_calculate_take_profit_price_short(self, position_manager):
        """Test calculating TP price for short position."""
        entry_price = 50000.0
        tp_price = position_manager.calculate_take_profit_price(entry_price, "short")

        # For short: TP = entry * (1 - 0.05) = 50000 * 0.95 = 47500
        assert tp_price == 47500.0

    def test_calculate_take_profit_price_long(self, position_manager):
        """Test calculating TP price for long position."""
        entry_price = 2000.0
        tp_price = position_manager.calculate_take_profit_price(entry_price, "long")
        assert tp_price == 2100.0  # 5% gain

    def test_calculate_take_profit_precision(self, position_manager):
        """Test TP calculation precision."""
        entry_price = 33333.33
        tp_price = position_manager.calculate_take_profit_price(entry_price, "short")

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
            tp_price = position_manager.calculate_take_profit_price(entry, "short")
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
        position_manager._wait_for_position_confirmation.return_value = None

        position_manager.open_position("BTCUSDT", 100.0, 20)

        # Verify limit order call
        call_args = mock_client.create_limit_order.call_args
        assert call_args[1]["symbol"] == "BTCUSDT"
        assert call_args[1]["side"] == "buy"  # Buy to close short
        assert call_args[1]["quantity"] == 0.1
        assert call_args[1]["price"] == 47500.0  # TP price
        assert call_args[1]["position_side"] == "SHORT"

    def test_open_long_position(self, position_manager, mock_client, db_session):
        """Test opening a long position."""
        mock_client.open_long_position.return_value = {"id": "ORDER999", "average": 2000.0, "filled": 1.0}
        mock_client.create_limit_order.return_value = {"id": "TP_LONG"}

        result = position_manager.open_position(
            "ETHUSDT", 50.0, 5, direction="long", take_profit_price=2100.0, stop_loss_price=1950.0
        )

        assert result is not None
        assert result["direction"] == "long"
        assert result["take_profit_price"] == 2100.0
        # Stop-loss is disabled - always returns None regardless of input
        assert result["stop_loss_price"] is None

        mock_client.open_long_position.assert_called_once_with("ETHUSDT", 50.0, 5)
        mock_client.create_limit_order.assert_called_with(
            symbol="ETHUSDT", side="sell", quantity=1.0, price=2100.0, position_side="LONG"
        )

        position = db_session.query(Position).filter_by(symbol="ETHUSDT").first()
        assert position is not None
        assert position.side == "long"
        # Stop-loss is disabled
        assert position.stop_loss_price is None

    def test_open_position_recalculates_tp_from_strategy_reference(self, position_manager, mock_client):
        """TP should be recalculated from strategy reference entry when actual fill differs."""
        mock_client.open_short_position.return_value = {"id": "ORDER123", "average": 1.5111, "filled": 661.7}
        mock_client.create_limit_order.return_value = {"id": "TP_ORDER123"}
        position_manager._wait_for_position_confirmation.return_value = {
            "entryPrice": 1.5111,
            "positionAmt": "-661.7",
        }

        result = position_manager.open_position(
            "TONUSDT",
            50.0,
            20,
            take_profit_price=1.6135,
            reference_entry_price=1.62075,
        )

        assert result is not None
        expected_tp = pytest.approx(1.5111 * (1 + (1.6135 - 1.62075) / 1.62075), rel=1e-6)
        assert result["take_profit_price"] == expected_tp
        mock_client.create_limit_order.assert_called_with(
            symbol="TONUSDT",
            side="buy",
            quantity=661.7,
            price=expected_tp,
            position_side="SHORT",
        )


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

        # Mock exchange response - position exists
        mock_client.get_position_by_symbol.return_value = {"positionAmt": "-0.1"}
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

        mock_client.get_position_by_symbol.return_value = {"positionAmt": "-0.1"}
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

        mock_client.get_position_by_symbol.return_value = {"positionAmt": "-0.1"}
        mock_client.close_short_position.return_value = {"id": "CLOSE123"}
        mock_client.get_ticker.return_value = {"last": 48500.0}

        result = position_manager.close_position(position.id, "manual")

        # Should use ticker price as fallback
        assert result is not None
        assert result["exit_price"] == 48500.0

    def test_close_position_already_closed_on_exchange(self, position_manager, mock_client, db_session):
        """Test syncing position when it's already closed on exchange."""
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

        # Position doesn't exist on exchange
        mock_client.get_position_by_symbol.return_value = None
        mock_client.get_ticker.return_value = {"last": 47500.0}

        result = position_manager.close_position(position.id, "take_profit")

        # Should sync and close in database
        assert result is not None
        assert result["symbol"] == "BTCUSDT"
        assert result["exit_price"] == 47500.0
        assert result["reason"] == "take_profit_sync"
        assert result.get("synced") is True

        # Verify position was closed in database
        updated = db_session.query(Position).filter_by(id=position.id).first()
        assert updated.status == "closed"

    def test_close_position_zero_amount_on_exchange(self, position_manager, mock_client, db_session):
        """Test syncing position when exchange shows zero amount."""
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

        # Position has zero amount on exchange
        mock_client.get_position_by_symbol.return_value = {"positionAmt": "0"}
        mock_client.get_ticker.return_value = {"last": 47500.0}

        result = position_manager.close_position(position.id, "take_profit")

        # Should sync and close in database
        assert result is not None
        assert result.get("synced") is True
        assert result["reason"] == "take_profit_sync"

    def test_close_position_reduce_only_error(self, position_manager, mock_client, db_session):
        """Test handling ReduceOnly error (position already closed)."""
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

        # Position exists on exchange check, but close order fails with error -2022
        mock_client.get_position_by_symbol.return_value = {"positionAmt": "-0.1"}
        mock_client.close_short_position.return_value = {"error_code": -2022, "message": "Position already closed"}
        mock_client.get_ticker.return_value = {"last": 47500.0}

        result = position_manager.close_position(position.id, "take_profit")

        # Should detect error and sync
        assert result is not None
        assert result.get("synced") is True
        assert result["reason"] == "take_profit_sync"

        # Verify position was closed in database
        updated = db_session.query(Position).filter_by(id=position.id).first()
        assert updated.status == "closed"

    def test_close_position_uses_tp_order_fill_price_when_position_closed(self, position_manager, mock_client, db_session):
        """Test that when position is already closed on exchange, TP order fill price is used."""
        position = Position(
            symbol="BTCUSDT",
            entry_price=50000.0,
            current_price=48000.0,
            quantity=0.1,
            margin=100.0,
            leverage=20,
            take_profit_price=47500.0,
            take_profit_order_id="TP_ORDER_123",
            status="open",
        )
        db_session.add(position)
        db_session.commit()

        # Position no longer exists on exchange (already closed by TP order)
        mock_client.get_position_by_symbol.return_value = None
        # TP order was filled at the TP price
        mock_client.fetch_order.return_value = {
            "status": "closed",
            "average": 47500.0,  # Filled at TP price
            "filled": 0.1,
        }
        # Current market price is much lower (this should NOT be used)
        mock_client.get_ticker.return_value = {"last": 45000.0}

        result = position_manager.close_position(position.id, "take_profit")

        assert result is not None
        # Should use TP order fill price, not current market price
        assert result["exit_price"] == 47500.0
        assert result["pnl"] == 250.0  # (50000 - 47500) * 0.1 = 5%
        assert result["pnl_pct"] == 5.0
        assert result["reason"] == "take_profit_sync"

        # Verify fetch_order was called with correct arguments
        mock_client.fetch_order.assert_called_once_with("TP_ORDER_123", "BTCUSDT")
        # get_ticker should NOT be called since we got TP order fill price
        mock_client.get_ticker.assert_not_called()

    def test_close_position_falls_back_to_ticker_when_no_tp_order(self, position_manager, mock_client, db_session):
        """Test fallback to ticker price when no TP order ID is available."""
        position = Position(
            symbol="BTCUSDT",
            entry_price=50000.0,
            current_price=48000.0,
            quantity=0.1,
            margin=100.0,
            leverage=20,
            take_profit_price=47500.0,
            take_profit_order_id=None,  # No TP order
            status="open",
        )
        db_session.add(position)
        db_session.commit()

        mock_client.get_position_by_symbol.return_value = None
        mock_client.get_ticker.return_value = {"last": 45000.0}

        result = position_manager.close_position(position.id, "take_profit")

        assert result is not None
        # Should use ticker price as fallback
        assert result["exit_price"] == 45000.0
        mock_client.fetch_order.assert_not_called()

    def test_close_position_falls_back_to_ticker_when_tp_order_not_filled(self, position_manager, mock_client, db_session):
        """Test fallback to ticker when TP order exists but is not filled."""
        position = Position(
            symbol="BTCUSDT",
            entry_price=50000.0,
            current_price=48000.0,
            quantity=0.1,
            margin=100.0,
            leverage=20,
            take_profit_price=47500.0,
            take_profit_order_id="TP_ORDER_123",
            status="open",
        )
        db_session.add(position)
        db_session.commit()

        mock_client.get_position_by_symbol.return_value = None
        # TP order was cancelled, not filled
        mock_client.fetch_order.return_value = {
            "status": "canceled",
            "average": None,
            "filled": 0,
        }
        mock_client.get_ticker.return_value = {"last": 45000.0}

        result = position_manager.close_position(position.id, "manual")

        assert result is not None
        # Should fall back to ticker price
        assert result["exit_price"] == 45000.0
        assert result["reason"] == "manual_sync"

    def test_close_position_uses_tp_order_price_on_reduce_only_error(self, position_manager, mock_client, db_session):
        """Test TP order fill price is used when ReduceOnly error occurs."""
        position = Position(
            symbol="BTCUSDT",
            entry_price=50000.0,
            current_price=48000.0,
            quantity=0.1,
            margin=100.0,
            leverage=20,
            take_profit_price=47500.0,
            take_profit_order_id="TP_ORDER_456",
            status="open",
        )
        db_session.add(position)
        db_session.commit()

        # Position appears to exist on exchange, but close order fails
        mock_client.get_position_by_symbol.return_value = {"positionAmt": "-0.1"}
        mock_client.close_short_position.return_value = {"error_code": -2022, "message": "Position already closed"}
        # TP order was filled
        mock_client.fetch_order.return_value = {
            "status": "filled",
            "average": 47500.0,
        }
        # Current price is different
        mock_client.get_ticker.return_value = {"last": 46000.0}

        result = position_manager.close_position(position.id, "take_profit")

        assert result is not None
        # Should use TP order fill price
        assert result["exit_price"] == 47500.0
        assert result["reason"] == "take_profit_sync"
        mock_client.fetch_order.assert_called_once_with("TP_ORDER_456", "BTCUSDT")


class TestMonitorPositions:
    """Test position monitoring."""

    def test_monitor_positions_empty(self, position_manager):
        """Test monitoring with no open positions."""
        closed = position_manager.monitor_positions()
        assert closed == []

    def test_monitor_positions_removes_closed_position(self, position_manager, mock_client, db_session):
        """Test removing position that no longer exists on exchange."""
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
        position_id = position.id

        # Mock: position no longer exists on exchange (closed by TP)
        # get_positions returns empty list - no active positions
        mock_client.get_positions.return_value = []

        removed = position_manager.monitor_positions()

        assert len(removed) == 1
        assert removed[0]["symbol"] == "BTCUSDT"
        assert removed[0]["reason"] == "closed_on_exchange"

        # Verify position was deleted from DB
        deleted = db_session.query(Position).filter_by(id=position_id).first()
        assert deleted is None

    def test_monitor_positions_keeps_open_position(self, position_manager, mock_client, db_session):
        """Test that position stays when it still exists on exchange."""
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

        # Mock: position still exists on exchange (batch fetch)
        mock_client.get_positions.return_value = [{"symbol": "BTCUSDT", "positionAmt": "-0.1"}]

        removed = position_manager.monitor_positions()

        # No positions should be removed
        assert len(removed) == 0

        # Verify position still exists
        existing = db_session.query(Position).filter_by(id=position.id).first()
        assert existing is not None
        assert existing.status == "open"

    def test_monitor_multiple_positions(self, position_manager, mock_client, db_session):
        """Test monitoring multiple positions - only removes those closed on exchange."""
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
        pos1_id = pos1.id
        pos2_id = pos2.id

        # Mock: BTC closed on exchange (not in list), ETH still open
        # Batch fetch returns only ETH position
        mock_client.get_positions.return_value = [{"symbol": "ETHUSDT", "positionAmt": "-1.0"}]

        removed = position_manager.monitor_positions()

        # Only BTC should be removed
        assert len(removed) == 1
        assert removed[0]["symbol"] == "BTCUSDT"
        assert removed[0]["reason"] == "closed_on_exchange"

        # Verify BTC deleted, ETH still exists
        assert db_session.query(Position).filter_by(id=pos1_id).first() is None
        assert db_session.query(Position).filter_by(id=pos2_id).first() is not None

    def test_monitor_positions_delete_fails(self, position_manager, mock_client, db_session):
        """Test that position is not reported as removed if delete fails."""
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

        # Mock: position no longer exists on exchange (batch fetch returns empty)
        mock_client.get_positions.return_value = []

        # Mock: delete returns False (e.g., race condition - already deleted)
        position_manager.position_repo.delete = lambda x: False

        removed = position_manager.monitor_positions()

        # Should NOT report position as removed since delete failed
        assert len(removed) == 0

    def test_monitor_positions_api_error_does_not_delete(self, position_manager, mock_client, db_session):
        """Test that API errors don't cause position deletion.

        This is a critical test: if get_positions() raises an exception
        (network error, rate limit, etc.), we should NOT delete any positions.
        The method returns early, leaving all positions intact.
        """
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

        # Mock: batch API call raises an exception (network error, rate limit, etc.)
        mock_client.get_positions.side_effect = Exception("Network timeout")

        removed = position_manager.monitor_positions()

        # Should NOT remove any positions when API fails
        assert len(removed) == 0

        # Position should still exist in database
        existing = db_session.query(Position).filter_by(id=position_id).first()
        assert existing is not None
        assert existing.status == "open"

    def test_monitor_positions_batch_fetch(self, position_manager, mock_client, db_session):
        """Test that positions are fetched in a single batch API call.

        This verifies efficiency: instead of N API calls for N positions,
        we make one get_positions() call and use the result for all positions.
        """
        # Create multiple positions
        for i in range(3):
            db_session.add(
                Position(
                    symbol=f"COIN{i}USDT",
                    entry_price=1000.0,
                    current_price=1000.0,
                    quantity=0.1,
                    margin=100.0,
                    leverage=20,
                    take_profit_price=950.0,
                    status="open",
                )
            )
        db_session.commit()

        # Mock: all positions still open on exchange
        mock_client.get_positions.return_value = [
            {"symbol": "COIN0USDT", "positionAmt": "-0.1"},
            {"symbol": "COIN1USDT", "positionAmt": "-0.1"},
            {"symbol": "COIN2USDT", "positionAmt": "-0.1"},
        ]

        position_manager.monitor_positions()

        # Verify single batch call was made (not 3 separate calls)
        mock_client.get_positions.assert_called_once()

    def test_monitor_positions_removes_when_side_changed(self, position_manager, mock_client, db_session):
        """Test that position is removed when user manually reversed the position.

        Scenario:
        1. Bot tracks SHORT position for BTCUSDT in database
        2. User manually closes SHORT and opens LONG on exchange
        3. Exchange returns positive positionAmt (indicating LONG)
        4. Bot should recognize SHORT no longer exists and remove from database
        """
        # Create SHORT position in database
        position = Position(
            symbol="BTCUSDT",
            entry_price=50000.0,
            current_price=50000.0,
            quantity=0.1,
            margin=100.0,
            leverage=20,
            take_profit_price=47500.0,
            side="short",  # DB tracks SHORT
            status="open",
        )
        db_session.add(position)
        db_session.commit()
        position_id = position.id

        # Mock: exchange now has LONG position (positive positionAmt)
        # User manually closed SHORT and opened LONG
        mock_client.get_positions.return_value = [{"symbol": "BTCUSDT", "positionAmt": "0.1"}]  # Positive = LONG

        removed = position_manager.monitor_positions()

        # SHORT should be removed because exchange has LONG (side mismatch)
        assert len(removed) == 1
        assert removed[0]["symbol"] == "BTCUSDT"
        assert removed[0]["side"] == "short"
        assert removed[0]["reason"] == "closed_on_exchange"

        # Verify position was deleted from DB
        assert db_session.query(Position).filter_by(id=position_id).first() is None

    def test_monitor_positions_keeps_matching_side(self, position_manager, mock_client, db_session):
        """Test that position is kept when side matches on exchange.

        Verifies that the side-checking logic doesn't accidentally
        remove valid positions.
        """
        # Create SHORT position
        short_pos = Position(
            symbol="BTCUSDT",
            entry_price=50000.0,
            current_price=50000.0,
            quantity=0.1,
            margin=100.0,
            leverage=20,
            take_profit_price=47500.0,
            side="short",
            status="open",
        )
        # Create LONG position
        long_pos = Position(
            symbol="ETHUSDT",
            entry_price=3000.0,
            current_price=3000.0,
            quantity=1.0,
            margin=100.0,
            leverage=20,
            take_profit_price=3150.0,
            side="long",
            status="open",
        )
        db_session.add(short_pos)
        db_session.add(long_pos)
        db_session.commit()

        # Mock: exchange has matching sides (batch fetch)
        mock_client.get_positions.return_value = [
            {"symbol": "BTCUSDT", "positionAmt": "-0.1"},  # Negative = SHORT (matches DB)
            {"symbol": "ETHUSDT", "positionAmt": "1.0"},  # Positive = LONG (matches DB)
        ]

        removed = position_manager.monitor_positions()

        # No positions should be removed - both sides match
        assert len(removed) == 0

        # Both positions should still exist
        assert db_session.query(Position).filter_by(id=short_pos.id).first() is not None
        assert db_session.query(Position).filter_by(id=long_pos.id).first() is not None


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

        mock_client.get_position_by_symbol.return_value = {"positionAmt": "-0.1"}
        mock_client.close_short_position.return_value = {"average": 47500.0}

        result = position_manager.close_position_by_symbol("BTCUSDT", "manual")

        assert result is not None
        assert result["symbol"] == "BTCUSDT"

    def test_close_by_symbol_not_found(self, position_manager, mock_client):
        """Test closing non-existent symbol."""
        result = position_manager.close_position_by_symbol("NONEXISTENT", "manual")
        assert result is None


class TestCriticalErrorTracking:
    """Test critical error tracking for orphaned positions."""

    def test_initial_no_critical_error(self, position_manager):
        """Test that no critical error exists initially."""
        error = position_manager.get_and_clear_critical_error()
        assert error is None

    def test_get_and_clear_removes_error(self, position_manager):
        """Test that get_and_clear returns and removes the error."""
        # Manually set error for testing
        position_manager._last_critical_error = {
            "type": "orphaned_position_cleanup_failed",
            "symbol": "BTCUSDT",
        }

        # First call returns the error
        error = position_manager.get_and_clear_critical_error()
        assert error is not None
        assert error["symbol"] == "BTCUSDT"

        # Second call returns None (error was cleared)
        error2 = position_manager.get_and_clear_critical_error()
        assert error2 is None

    def test_orphaned_position_cleanup_failure_sets_critical_error(self, position_manager, mock_client, db_session):
        """Test that failed orphaned position cleanup sets critical error."""
        # Setup: exchange returns order but DB save will fail
        mock_client.open_short_position.return_value = {
            "id": "ORDER123",
            "average": 50000.0,
            "filled": 0.1,
        }

        # Make create_limit_order raise an exception to trigger DB error path
        mock_client.create_limit_order.side_effect = Exception("DB Error simulation")

        # Make cleanup also fail
        mock_client.close_short_position.side_effect = Exception("Cleanup failed!")

        # Open position should fail and set critical error
        result = position_manager.open_position("BTCUSDT", 100.0, 20)
        assert result is None

        # Critical error should be set
        error = position_manager.get_and_clear_critical_error()
        assert error is not None
        assert error["type"] == "orphaned_position_cleanup_failed"
        assert error["symbol"] == "BTCUSDT"
        assert error["direction"] == "short"
        assert error["quantity"] == 0.1
        assert "Cleanup failed!" in error["cleanup_error"]
        assert "timestamp" in error

    def test_successful_cleanup_no_critical_error(self, position_manager, mock_client, db_session):
        """Test that successful orphan cleanup doesn't set critical error."""
        mock_client.open_short_position.return_value = {
            "id": "ORDER123",
            "average": 50000.0,
            "filled": 0.1,
        }
        mock_client.create_limit_order.side_effect = Exception("DB Error")
        mock_client.close_short_position.return_value = {"success": True}  # Cleanup succeeds

        result = position_manager.open_position("BTCUSDT", 100.0, 20)
        assert result is None

        # No critical error because cleanup succeeded
        error = position_manager.get_and_clear_critical_error()
        assert error is None

    def test_critical_error_contains_all_required_fields(self, position_manager):
        """Test that critical error contains all necessary fields for notification."""
        # Manually set a complete critical error
        position_manager._last_critical_error = {
            "type": "orphaned_position_cleanup_failed",
            "symbol": "ETHUSDT",
            "direction": "long",
            "quantity": 1.5,
            "original_error": "DB connection lost",
            "cleanup_error": "API timeout",
            "timestamp": "2024-01-15T10:30:00",
        }

        error = position_manager.get_and_clear_critical_error()

        # Verify all fields needed for Telegram notification
        assert "symbol" in error
        assert "direction" in error
        assert "quantity" in error
        assert "cleanup_error" in error
        assert error["symbol"] == "ETHUSDT"
        assert error["direction"] == "long"
        assert error["quantity"] == 1.5


class TestStrategyTracking:
    """Test strategy tracking in positions."""

    def test_open_position_returns_strategy(self, position_manager, mock_client, db_session):
        """Test that open_position returns strategy from metadata."""
        mock_client.open_short_position.return_value = {"id": "ORDER123", "average": 50000.0, "filled": 0.1}
        mock_client.create_limit_order.return_value = {"id": "TP_ORDER123"}

        metadata = {"strategy": "pump_cooldown", "score": 0.85}
        result = position_manager.open_position("BTCUSDT", 100.0, 20, metadata=metadata)

        assert result is not None
        assert result.get("strategy") == "pump_cooldown"

    def test_open_position_returns_none_strategy_without_metadata(self, position_manager, mock_client, db_session):
        """Test that open_position returns None strategy when no metadata."""
        mock_client.open_short_position.return_value = {"id": "ORDER123", "average": 50000.0, "filled": 0.1}
        mock_client.create_limit_order.return_value = {"id": "TP_ORDER123"}

        result = position_manager.open_position("BTCUSDT", 100.0, 20)

        assert result is not None
        assert result.get("strategy") is None

    def test_build_position_snapshot_includes_strategy(self, position_manager, db_session):
        """Test that _build_position_snapshot extracts strategy from source_metadata."""
        import json

        position = Position(
            symbol="ETHUSDT",
            entry_price=3000.0,
            current_price=2950.0,
            quantity=1.0,
            margin=150.0,
            leverage=20,
            take_profit_price=2850.0,
            status="open",
            source_metadata=json.dumps({"strategy": "order_block", "rr_ratio": 2.5}),
        )
        db_session.add(position)
        db_session.commit()

        snapshot = position_manager._build_position_snapshot(position)

        assert snapshot["strategy"] == "order_block"

    def test_build_position_snapshot_handles_missing_strategy(self, position_manager, db_session):
        """Test that _build_position_snapshot handles positions without strategy."""
        position = Position(
            symbol="ETHUSDT",
            entry_price=3000.0,
            current_price=2950.0,
            quantity=1.0,
            margin=150.0,
            leverage=20,
            take_profit_price=2850.0,
            status="open",
            source_metadata=None,
        )
        db_session.add(position)
        db_session.commit()

        snapshot = position_manager._build_position_snapshot(position)

        assert snapshot["strategy"] is None

    def test_close_position_returns_strategy(self, position_manager, mock_client, db_session):
        """Test that close_position returns strategy."""
        import json

        position = Position(
            symbol="BTCUSDT",
            entry_price=50000.0,
            current_price=48000.0,
            quantity=0.1,
            margin=100.0,
            leverage=20,
            take_profit_price=47500.0,
            status="open",
            source_metadata=json.dumps({"strategy": "pump_cooldown"}),
        )
        db_session.add(position)
        db_session.commit()

        mock_client.get_position_by_symbol.return_value = {"positionAmt": "-0.1"}
        mock_client.close_short_position.return_value = {"average": 47500.0}

        result = position_manager.close_position(position.id, "take_profit")

        assert result is not None
        assert result.get("strategy") == "pump_cooldown"

    def test_extract_strategy_from_metadata_string(self, position_manager):
        """Test _extract_strategy_from_metadata with JSON string."""
        import json

        metadata = json.dumps({"strategy": "order_block", "score": 0.9})
        strategy = position_manager._extract_strategy_from_metadata(metadata)

        assert strategy == "order_block"

    def test_extract_strategy_from_metadata_dict(self, position_manager):
        """Test _extract_strategy_from_metadata with dict."""
        metadata = {"strategy": "pump_cooldown", "score": 0.75}
        strategy = position_manager._extract_strategy_from_metadata(metadata)

        assert strategy == "pump_cooldown"

    def test_extract_strategy_from_metadata_none(self, position_manager):
        """Test _extract_strategy_from_metadata with None."""
        strategy = position_manager._extract_strategy_from_metadata(None)

        assert strategy is None

    def test_extract_strategy_from_metadata_invalid_json(self, position_manager):
        """Test _extract_strategy_from_metadata with invalid JSON."""
        strategy = position_manager._extract_strategy_from_metadata("not valid json")

        assert strategy is None
