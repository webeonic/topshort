"""Unit tests for RiskManager."""

from unittest.mock import Mock

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.config import TradingConfig
from src.database.models import Base, Position, Settings
from src.database.repository import PositionRepository, SettingsRepository
from src.trading.risk_manager import RiskManager


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
def config():
    """Create test trading config."""
    return TradingConfig(
        margin_per_trade=100.0, max_positions=5, max_total_margin=500.0, default_leverage=20, take_profit_pct=5.0
    )


@pytest.fixture
def risk_manager(db_session, config):
    """Create RiskManager instance."""
    return RiskManager(db_session, config)


class TestRiskManagerInit:
    """Test RiskManager initialization."""

    def test_initialization(self, risk_manager, db_session, config):
        """Test that RiskManager initializes correctly."""
        assert risk_manager.session == db_session
        assert risk_manager.config == config
        assert isinstance(risk_manager.position_repo, PositionRepository)
        assert isinstance(risk_manager.settings_repo, SettingsRepository)


class TestGetRiskParameters:
    """Test getting risk parameters."""

    def test_get_margin_per_trade_from_config(self, risk_manager):
        """Test getting margin per trade from config."""
        margin = risk_manager.get_margin_per_trade()
        assert margin == 100.0

    def test_get_margin_per_trade_from_settings(self, risk_manager, db_session):
        """Test getting margin per trade from database settings."""
        # Add setting to database
        setting = Settings(key="margin_per_trade", value="150.0")
        db_session.add(setting)
        db_session.commit()

        margin = risk_manager.get_margin_per_trade()
        assert margin == 150.0

    def test_get_max_positions_from_config(self, risk_manager):
        """Test getting max positions from config."""
        max_pos = risk_manager.get_max_positions()
        assert max_pos == 5

    def test_get_max_positions_from_settings(self, risk_manager, db_session):
        """Test getting max positions from settings."""
        setting = Settings(key="max_positions", value="10")
        db_session.add(setting)
        db_session.commit()

        max_pos = risk_manager.get_max_positions()
        assert max_pos == 10

    def test_get_max_total_margin_from_config(self, risk_manager):
        """Test getting max total margin from config."""
        max_margin = risk_manager.get_max_total_margin()
        assert max_margin == 500.0

    def test_get_max_total_margin_from_settings(self, risk_manager, db_session):
        """Test getting max total margin from settings."""
        setting = Settings(key="max_total_margin", value="1000.0")
        db_session.add(setting)
        db_session.commit()

        max_margin = risk_manager.get_max_total_margin()
        assert max_margin == 1000.0


class TestCanOpenPosition:
    """Test position opening permission checks."""

    def test_can_open_position_allowed(self, risk_manager, db_session):
        """Test allowing position when all checks pass."""
        result = risk_manager.can_open_position(100.0)

        assert result["allowed"] is True
        assert result["reason"] == "All risk checks passed"
        assert result["current_positions"] == 0
        assert result["max_positions"] == 5

    def test_can_open_position_max_positions_reached(self, risk_manager, db_session):
        """Test blocking when max positions reached."""
        # Add 5 open positions (max is 5)
        for i in range(5):
            position = Position(
                symbol=f"BTC{i}",
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

        result = risk_manager.can_open_position(100.0)

        assert result["allowed"] is False
        assert "Maximum positions limit reached" in result["reason"]
        assert "5/5" in result["reason"]

    def test_can_open_position_margin_limit_exceeded(self, risk_manager, db_session):
        """Test blocking when total margin would exceed limit."""
        # Add position with 400 USDT margin (max is 500)
        position = Position(
            symbol="BTC1",
            entry_price=50000.0,
            current_price=50000.0,
            quantity=0.1,
            margin=400.0,
            leverage=20,
            take_profit_price=47500.0,
            status="open",
        )
        db_session.add(position)
        db_session.commit()

        # Try to add another with 150 USDT (would exceed 500)
        result = risk_manager.can_open_position(150.0)

        assert result["allowed"] is False
        assert "Total margin limit would be exceeded" in result["reason"]
        assert "550.00/500.00" in result["reason"]

    def test_can_open_position_per_trade_margin_exceeded(self, risk_manager):
        """Test blocking when single position margin exceeds limit."""
        # Try to open position with 150 USDT (limit is 100)
        result = risk_manager.can_open_position(150.0)

        assert result["allowed"] is False
        assert "Position margin exceeds limit" in result["reason"]
        assert "150.00/100.00" in result["reason"]

    def test_can_open_position_with_closed_positions(self, risk_manager, db_session):
        """Test that closed positions don't count toward limits."""
        # Add 5 closed positions
        for i in range(5):
            position = Position(
                symbol=f"BTC{i}",
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

        result = risk_manager.can_open_position(100.0)

        # Should be allowed since closed positions don't count
        assert result["allowed"] is True
        assert result["current_positions"] == 0


class TestValidatePositionSize:
    """Test position size validation."""

    def test_validate_position_size_valid(self, risk_manager):
        """Test validating a proper position."""
        result = risk_manager.validate_position_size("BTCUSDT", 100.0, 20)

        assert result["valid"] is True
        assert result["reason"] == "Position size validated"

    def test_validate_position_size_negative_margin(self, risk_manager):
        """Test blocking negative margin."""
        result = risk_manager.validate_position_size("BTCUSDT", -100.0, 20)

        assert result["valid"] is False
        assert "Margin must be positive" in result["reason"]

    def test_validate_position_size_zero_margin(self, risk_manager):
        """Test blocking zero margin."""
        result = risk_manager.validate_position_size("BTCUSDT", 0.0, 20)

        assert result["valid"] is False
        assert "Margin must be positive" in result["reason"]

    def test_validate_position_size_zero_leverage(self, risk_manager):
        """Test blocking zero leverage."""
        result = risk_manager.validate_position_size("BTCUSDT", 100.0, 0)

        assert result["valid"] is False
        assert "Leverage must be at least 1" in result["reason"]

    def test_validate_position_size_negative_leverage(self, risk_manager):
        """Test blocking negative leverage."""
        result = risk_manager.validate_position_size("BTCUSDT", 100.0, -5)

        assert result["valid"] is False
        assert "Leverage must be at least 1" in result["reason"]

    def test_validate_position_size_duplicate_symbol(self, risk_manager, db_session):
        """Test blocking duplicate symbol."""
        # Add existing open position
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

        result = risk_manager.validate_position_size("BTCUSDT", 100.0, 20)

        assert result["valid"] is False
        assert "Position already exists" in result["reason"]

    def test_validate_position_size_allows_different_symbol(self, risk_manager, db_session):
        """Test allowing different symbol even if one exists."""
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

        result = risk_manager.validate_position_size("ETHUSDT", 100.0, 20)

        assert result["valid"] is True

    def test_validate_position_size_high_leverage_warning(self, risk_manager, caplog):
        """Test warning for very high leverage."""
        import logging

        caplog.set_level(logging.WARNING)

        result = risk_manager.validate_position_size("BTCUSDT", 100.0, 125)

        # Should still be valid but log warning
        assert result["valid"] is True
        assert any("Very high leverage" in record.message for record in caplog.records)


class TestCheckBeforeTrade:
    """Test complete pre-trade check."""

    def test_check_before_trade_approved(self, risk_manager):
        """Test approving valid trade."""
        result = risk_manager.check_before_trade("BTCUSDT", 100.0, 20)

        assert result["approved"] is True
        assert result["reason"] == "Trade approved"
        assert "risk_info" in result

    def test_check_before_trade_invalid_size(self, risk_manager):
        """Test rejecting invalid position size."""
        result = risk_manager.check_before_trade("BTCUSDT", -100.0, 20)

        assert result["approved"] is False
        assert result["check"] == "position_size"
        assert "Margin must be positive" in result["reason"]

    def test_check_before_trade_risk_limit(self, risk_manager, db_session):
        """Test rejecting due to risk limits."""
        # Fill up position slots
        for i in range(5):
            position = Position(
                symbol=f"BTC{i}",
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

        result = risk_manager.check_before_trade("ETHUSDT", 100.0, 20)

        assert result["approved"] is False
        assert result["check"] == "risk_limits"
        assert "Maximum positions limit reached" in result["reason"]

    def test_check_before_trade_duplicate_symbol(self, risk_manager, db_session):
        """Test rejecting duplicate symbol."""
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

        result = risk_manager.check_before_trade("BTCUSDT", 100.0, 20)

        assert result["approved"] is False
        assert result["check"] == "position_size"


class TestGetRiskSummary:
    """Test getting risk summary."""

    def test_get_risk_summary_empty(self, risk_manager):
        """Test risk summary with no positions."""
        summary = risk_manager.get_risk_summary()

        assert summary["current_positions"] == 0
        assert summary["max_positions"] == 5
        assert summary["positions_utilization_pct"] == 0.0
        assert summary["current_margin"] == 0.0
        assert summary["max_margin"] == 500.0
        assert summary["margin_utilization_pct"] == 0.0
        assert summary["available_slots"] == 5
        assert summary["available_margin"] == 500.0

    def test_get_risk_summary_with_positions(self, risk_manager, db_session):
        """Test risk summary with active positions."""
        # Add 2 positions with 100 USDT each
        for i in range(2):
            position = Position(
                symbol=f"BTC{i}",
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

        summary = risk_manager.get_risk_summary()

        assert summary["current_positions"] == 2
        assert summary["max_positions"] == 5
        assert summary["positions_utilization_pct"] == 40.0  # 2/5 * 100
        assert summary["current_margin"] == 200.0
        assert summary["max_margin"] == 500.0
        assert summary["margin_utilization_pct"] == 40.0  # 200/500 * 100
        assert summary["available_slots"] == 3
        assert summary["available_margin"] == 300.0

    def test_get_risk_summary_by_source(self, risk_manager, db_session):
        """Test risk summary includes positions by source."""
        # Add positions from different sources
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
        db_session.add(
            Position(
                symbol="BTC3",
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
        db_session.commit()

        summary = risk_manager.get_risk_summary()

        assert summary["positions_by_source"]["bot_auto"] == 2
        assert summary["positions_by_source"]["manual"] == 1

    def test_get_risk_summary_full_capacity(self, risk_manager, db_session):
        """Test risk summary at full capacity."""
        # Fill all 5 slots with 100 USDT each
        for i in range(5):
            position = Position(
                symbol=f"BTC{i}",
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

        summary = risk_manager.get_risk_summary()

        assert summary["current_positions"] == 5
        assert summary["positions_utilization_pct"] == 100.0
        assert summary["current_margin"] == 500.0
        assert summary["margin_utilization_pct"] == 100.0
        assert summary["available_slots"] == 0
        assert summary["available_margin"] == 0.0


class TestRiskManagerEdgeCases:
    """Test edge cases and boundary conditions."""

    def test_zero_max_positions_handling(self, db_session):
        """Test handling zero max positions in config."""
        config = TradingConfig(
            margin_per_trade=100.0, max_positions=0, max_total_margin=500.0, default_leverage=20, take_profit_pct=5.0
        )
        risk_manager = RiskManager(db_session, config)

        summary = risk_manager.get_risk_summary()
        assert summary["positions_utilization_pct"] == 0.0

    def test_zero_max_margin_handling(self, db_session):
        """Test handling zero max margin in config."""
        config = TradingConfig(
            margin_per_trade=100.0, max_positions=5, max_total_margin=0.0, default_leverage=20, take_profit_pct=5.0
        )
        risk_manager = RiskManager(db_session, config)

        summary = risk_manager.get_risk_summary()
        assert summary["margin_utilization_pct"] == 0.0

    def test_fractional_margin(self, risk_manager):
        """Test handling fractional margin values."""
        result = risk_manager.can_open_position(99.99)
        assert result["allowed"] is True

    def test_very_small_margin(self, risk_manager):
        """Test handling very small margin."""
        result = risk_manager.validate_position_size("BTCUSDT", 0.01, 1)
        assert result["valid"] is True

    def test_very_large_leverage(self, risk_manager):
        """Test handling very large leverage."""
        result = risk_manager.validate_position_size("BTCUSDT", 100.0, 1000)
        # Should be valid but may log warning
        assert result["valid"] is True
