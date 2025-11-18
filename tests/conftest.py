"""Pytest configuration and shared fixtures."""

import logging
from typing import Generator
from unittest.mock import MagicMock, Mock

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from src.config import TradingConfig
from src.database.models import Base

# Configure logging for tests
logging.basicConfig(level=logging.DEBUG, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")


# Database Fixtures
@pytest.fixture(scope="function")
def test_db_engine():
    """Create a clean in-memory SQLite database for each test."""
    engine = create_engine("sqlite:///:memory:", echo=False)
    Base.metadata.create_all(engine)
    yield engine
    Base.metadata.drop_all(engine)
    engine.dispose()


@pytest.fixture(scope="function")
def test_db_session(test_db_engine) -> Generator[Session, None, None]:
    """Create a new database session for each test."""
    Session = sessionmaker(bind=test_db_engine)
    session = Session()

    try:
        yield session
    finally:
        session.rollback()
        session.close()


# Configuration Fixtures
@pytest.fixture
def test_config():
    """Create test trading configuration."""
    return TradingConfig(
        margin_per_trade=100.0,
        max_positions=10,
        max_total_margin=1000.0,
        take_profit_pct=5.0,
        default_leverage=20,
        pump_threshold_pct=30.0,
        pump_period_hours_min=48,
        pump_period_hours_max=72,
        cooldown_period_hours_min=4,
        cooldown_period_hours_max=8,
        volume_decrease_threshold_pct=20.0,
    )


# Mock Exchange Client Fixtures
@pytest.fixture
def mock_binance_client():
    """Create a mock Binance client for testing."""
    client = Mock()

    # Mock common methods
    client.open_short_position = Mock(
        return_value={"id": "TEST_ORDER_123", "average": 50000.0, "filled": 0.1, "status": "closed"}
    )

    client.close_short_position = Mock(
        return_value={"id": "TEST_CLOSE_123", "average": 47500.0, "filled": 0.1, "status": "closed"}
    )

    client.create_limit_order = Mock(
        return_value={"id": "TEST_LIMIT_123", "status": "open", "price": 47500.0, "quantity": 0.1}
    )

    client.get_ticker = Mock(
        return_value={
            "symbol": "BTCUSDT",
            "last": 50000.0,
            "bid": 49999.0,
            "ask": 50001.0,
            "high": 51000.0,
            "low": 49000.0,
            "volume": 1000.0,
        }
    )

    client.fetch_tickers = Mock(return_value={"BTCUSDT": {"last": 50000.0}, "ETHUSDT": {"last": 3000.0}})

    client.get_positions = Mock(return_value=[])

    # Mock exchange attribute for direct API calls
    client.exchange = Mock()
    client.exchange.fetch_order = Mock(return_value={"id": "TEST_ORDER_123", "status": "open", "filled": 0, "remaining": 0.1})
    client.exchange.cancel_order = Mock(return_value={"success": True})

    return client


# Helper Fixtures
@pytest.fixture
def sample_position_data():
    """Sample position data for testing."""
    return {
        "symbol": "BTCUSDT",
        "entry_price": 50000.0,
        "quantity": 0.1,
        "margin": 100.0,
        "leverage": 20,
        "take_profit_price": 47500.0,
        "side": "short",
        "status": "open",
    }


@pytest.fixture
def sample_order_data():
    """Sample order data for testing."""
    return {
        "id": "ORDER123",
        "symbol": "BTCUSDT",
        "type": "limit",
        "side": "buy",
        "price": 47500.0,
        "amount": 0.1,
        "filled": 0,
        "remaining": 0.1,
        "status": "open",
        "timestamp": 1609459200000,
    }


# Pytest Hooks
def pytest_configure(config):
    """Configure pytest with custom markers and settings."""
    config.addinivalue_line("markers", "unit: mark test as a unit test")
    config.addinivalue_line("markers", "integration: mark test as an integration test")
    config.addinivalue_line("markers", "slow: mark test as slow running")
    config.addinivalue_line("markers", "database: mark test as requiring database")
    config.addinivalue_line("markers", "exchange: mark test as requiring exchange API")


def pytest_collection_modifyitems(config, items):
    """Automatically mark tests based on their names/paths."""
    for item in items:
        # Auto-mark database tests
        if "database" in item.nodeid.lower():
            item.add_marker(pytest.mark.database)

        # Auto-mark integration tests
        if "integration" in item.nodeid.lower():
            item.add_marker(pytest.mark.integration)

        # Auto-mark unit tests (default)
        if not any(mark.name in ["integration", "slow"] for mark in item.iter_markers()):
            item.add_marker(pytest.mark.unit)


# Mock Factory Functions
def create_mock_position(**kwargs):
    """Factory function to create mock position with default values."""
    from datetime import datetime

    from src.database.models import Position

    defaults = {
        "symbol": "BTCUSDT",
        "entry_price": 50000.0,
        "current_price": 50000.0,
        "quantity": 0.1,
        "margin": 100.0,
        "leverage": 20,
        "side": "short",
        "take_profit_price": 47500.0,
        "status": "open",
        "source": "bot_auto",
        "opened_at": datetime.utcnow(),
    }
    defaults.update(kwargs)
    return Position(**defaults)


def create_mock_limit_order(**kwargs):
    """Factory function to create mock limit order with default values."""
    from src.database.models import LimitOrder

    defaults = {
        "order_id": "TEST_ORDER_123",
        "symbol": "BTCUSDT",
        "order_type": "take_profit",
        "side": "buy",
        "price": 47500.0,
        "quantity": 0.1,
        "status": "pending",
        "filled_quantity": 0.0,
    }
    defaults.update(kwargs)
    return LimitOrder(**defaults)


# Register factory functions as fixtures
@pytest.fixture
def position_factory():
    """Fixture that returns the position factory function."""
    return create_mock_position


@pytest.fixture
def limit_order_factory():
    """Fixture that returns the limit order factory function."""
    return create_mock_limit_order


# Assertions Helpers
class AssertionHelpers:
    """Collection of custom assertion helpers."""

    @staticmethod
    def assert_position_equal(pos1, pos2, ignore_fields=None):
        """Assert two positions are equal, ignoring specified fields."""
        ignore_fields = ignore_fields or ["id", "opened_at", "updated_at"]

        for attr in ["symbol", "entry_price", "quantity", "margin", "leverage", "status"]:
            if attr not in ignore_fields:
                assert getattr(pos1, attr) == getattr(
                    pos2, attr
                ), f"Position {attr} mismatch: {getattr(pos1, attr)} != {getattr(pos2, attr)}"

    @staticmethod
    def assert_price_close(price1, price2, tolerance=0.01):
        """Assert two prices are close within tolerance."""
        assert abs(price1 - price2) < tolerance, f"Prices not close: {price1} vs {price2} (tolerance: {tolerance})"

    @staticmethod
    def assert_pnl_calculation(entry_price, exit_price, quantity, expected_pnl, expected_pnl_pct):
        """Assert P&L calculation is correct for short position."""
        actual_pnl = (entry_price - exit_price) * quantity
        actual_pnl_pct = ((entry_price - exit_price) / entry_price) * 100

        assert abs(actual_pnl - expected_pnl) < 0.01, f"P&L mismatch: {actual_pnl} != {expected_pnl}"
        assert abs(actual_pnl_pct - expected_pnl_pct) < 0.01, f"P&L % mismatch: {actual_pnl_pct} != {expected_pnl_pct}"


@pytest.fixture
def assert_helpers():
    """Fixture providing assertion helper methods."""
    return AssertionHelpers()


# Cleanup Hooks
@pytest.fixture(autouse=True)
def cleanup_logging():
    """Cleanup logging handlers after each test."""
    yield
    # Remove any handlers added during tests
    for logger_name in logging.Logger.manager.loggerDict:
        logger = logging.getLogger(logger_name)
        logger.handlers.clear()
        logger.setLevel(logging.NOTSET)


# Performance Monitoring (optional)
@pytest.fixture(autouse=True)
def log_test_duration(request):
    """Log test execution duration."""
    import time

    start = time.time()
    yield
    duration = time.time() - start
    if duration > 1.0:  # Log slow tests
        logging.warning(f"Slow test: {request.node.nodeid} took {duration:.2f}s")
