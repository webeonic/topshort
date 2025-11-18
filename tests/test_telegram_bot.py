"""Comprehensive tests for TelegramBot class."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest
from telegram import Update
from telegram.ext import Application

from src.bot.telegram_bot import TelegramBot
from src.config import TelegramConfig


@pytest.fixture
def mock_config():
    """Create mock Telegram configuration."""
    config = Mock(spec=TelegramConfig)
    config.bot_token = "test_token_123456"
    config.chat_id = "123456789"
    return config


@pytest.fixture
def mock_session():
    """Create mock database session."""
    session = MagicMock()
    return session


@pytest.fixture
def mock_engine():
    """Create mock trading engine."""
    engine = MagicMock()
    engine.get_status.return_value = {
        "risk_summary": {
            "current_positions": 5,
            "max_positions": 10,
            "current_margin": 500.0,
            "max_margin": 1000.0,
            "positions_utilization_pct": 50.0,
            "margin_utilization_pct": 50.0,
        }
    }
    return engine


@pytest.fixture
def telegram_bot(mock_config, mock_session, mock_engine):
    """Create TelegramBot instance for testing."""
    with patch("src.bot.telegram_bot.init_keyboard_templates"):
        bot = TelegramBot(mock_config, mock_session, mock_engine)
    return bot


class TestTelegramBotInitialization:
    """Test TelegramBot initialization."""

    def test_init_creates_bot_with_config(self, mock_config, mock_session, mock_engine):
        """Test bot initialization with config."""
        with patch("src.bot.telegram_bot.init_keyboard_templates") as mock_init:
            bot = TelegramBot(mock_config, mock_session, mock_engine)

            assert bot.config == mock_config
            assert bot.session == mock_session
            assert bot.engine == mock_engine
            assert bot.chat_id == mock_config.chat_id
            assert bot.application is None
            mock_init.assert_called_once_with(mock_session)

    def test_init_creates_components(self, telegram_bot):
        """Test that all bot components are created."""
        assert telegram_bot.commands is not None
        assert telegram_bot.callback_handler is not None
        assert telegram_bot.keyboard_builder is not None

    def test_init_creates_stop_event(self, telegram_bot):
        """Test that stop event is created."""
        assert isinstance(telegram_bot._stop_event, asyncio.Event)
        assert not telegram_bot._stop_event.is_set()


class TestTelegramBotSetup:
    """Test bot setup and handler registration."""

    @patch("src.bot.telegram_bot.Application")
    def test_setup_creates_application(self, mock_application_class, telegram_bot):
        """Test that setup creates Application."""
        mock_app = MagicMock()
        mock_builder = MagicMock()
        mock_builder.token.return_value = mock_builder
        mock_builder.build.return_value = mock_app
        mock_application_class.builder.return_value = mock_builder

        telegram_bot.setup()

        mock_application_class.builder.assert_called_once()
        mock_builder.token.assert_called_once_with(telegram_bot.config.bot_token)
        mock_builder.build.assert_called_once()
        assert telegram_bot.application == mock_app

    @patch("src.bot.telegram_bot.Application")
    def test_setup_registers_command_handlers(self, mock_application_class, telegram_bot):
        """Test that all command handlers are registered."""
        mock_app = MagicMock()
        mock_builder = MagicMock()
        mock_builder.token.return_value = mock_builder
        mock_builder.build.return_value = mock_app
        mock_application_class.builder.return_value = mock_builder

        telegram_bot.setup()

        # Check that add_handler was called multiple times
        assert mock_app.add_handler.call_count >= 14  # At least 14 handlers

    @patch("src.bot.telegram_bot.Application")
    def test_setup_registers_callback_handler(self, mock_application_class, telegram_bot):
        """Test that callback query handler is registered."""
        mock_app = MagicMock()
        mock_builder = MagicMock()
        mock_builder.token.return_value = mock_builder
        mock_builder.build.return_value = mock_app
        mock_application_class.builder.return_value = mock_builder

        telegram_bot.setup()

        # Verify CallbackQueryHandler was added
        handler_calls = [call[0][0] for call in mock_app.add_handler.call_args_list]
        callback_handlers = [h for h in handler_calls if "CallbackQueryHandler" in str(type(h))]
        assert len(callback_handlers) >= 1


class TestTelegramBotInitialize:
    """Test bot initialization and startup."""

    @pytest.mark.asyncio
    async def test_initialize_starts_application(self, telegram_bot):
        """Test that initialize starts the application."""
        mock_app = AsyncMock()
        telegram_bot.application = mock_app

        await telegram_bot.initialize()

        mock_app.initialize.assert_called_once()
        mock_app.start.assert_called_once()


class TestTelegramBotSendMessage:
    """Test message sending functionality."""

    @pytest.mark.asyncio
    async def test_send_message_success(self, telegram_bot):
        """Test successful message sending."""
        mock_app = AsyncMock()
        mock_bot = AsyncMock()
        mock_app.bot = mock_bot
        telegram_bot.application = mock_app

        await telegram_bot.send_message("Test message")

        mock_bot.send_message.assert_called_once_with(chat_id=telegram_bot.chat_id, text="Test message", parse_mode="Markdown")

    @pytest.mark.asyncio
    async def test_send_message_custom_parse_mode(self, telegram_bot):
        """Test message with custom parse mode."""
        mock_app = AsyncMock()
        mock_bot = AsyncMock()
        mock_app.bot = mock_bot
        telegram_bot.application = mock_app

        await telegram_bot.send_message("Test message", parse_mode="HTML")

        mock_bot.send_message.assert_called_once_with(chat_id=telegram_bot.chat_id, text="Test message", parse_mode="HTML")

    @pytest.mark.asyncio
    async def test_send_message_no_application(self, telegram_bot):
        """Test that no error occurs when application is None."""
        telegram_bot.application = None

        # Should not raise exception
        await telegram_bot.send_message("Test message")

    @pytest.mark.asyncio
    async def test_send_message_handles_error(self, telegram_bot):
        """Test that errors are handled gracefully."""
        mock_app = AsyncMock()
        mock_bot = AsyncMock()
        mock_bot.send_message.side_effect = Exception("Network error")
        mock_app.bot = mock_bot
        telegram_bot.application = mock_app

        # Should not raise exception
        await telegram_bot.send_message("Test message")


class TestTelegramBotNotifications:
    """Test notification methods."""

    @pytest.mark.asyncio
    async def test_notify_position_opened(self, telegram_bot):
        """Test position opened notification."""
        position_info = {
            "symbol": "BTCUSDT",
            "entry_price": 50000.0,
            "take_profit_price": 48000.0,
            "leverage": 10,
            "margin": 100.0,
            "order_id": "12345",
        }

        with patch.object(telegram_bot, "send_message", new_callable=AsyncMock) as mock_send:
            await telegram_bot.notify_position_opened(position_info)

            mock_send.assert_called_once()
            message = mock_send.call_args[0][0]
            assert "New Position Opened" in message
            assert "BTCUSDT" in message
            assert "50000" in message
            assert "48000" in message

    @pytest.mark.asyncio
    async def test_notify_position_closed_profit(self, telegram_bot):
        """Test position closed notification with profit."""
        close_info = {
            "symbol": "BTCUSDT",
            "entry_price": 50000.0,
            "exit_price": 48000.0,
            "pnl": 100.0,
            "pnl_pct": 10.0,
            "reason": "take_profit",
            "position_id": "pos_123",
        }

        with patch.object(telegram_bot, "send_message", new_callable=AsyncMock) as mock_send:
            await telegram_bot.notify_position_closed(close_info)

            mock_send.assert_called_once()
            message = mock_send.call_args[0][0]
            assert "Position Closed" in message
            assert "BTCUSDT" in message
            assert "100.0" in message
            assert "🟢" in message  # Profit emoji

    @pytest.mark.asyncio
    async def test_notify_position_closed_loss(self, telegram_bot):
        """Test position closed notification with loss."""
        close_info = {
            "symbol": "BTCUSDT",
            "entry_price": 50000.0,
            "exit_price": 51000.0,
            "pnl": -50.0,
            "pnl_pct": -5.0,
            "reason": "stop_loss",
            "position_id": "pos_123",
        }

        with patch.object(telegram_bot, "send_message", new_callable=AsyncMock) as mock_send:
            await telegram_bot.notify_position_closed(close_info)

            mock_send.assert_called_once()
            message = mock_send.call_args[0][0]
            assert "🔴" in message  # Loss emoji

    @pytest.mark.asyncio
    async def test_notify_scan_complete_no_positions(self, telegram_bot):
        """Test scan complete notification with no new positions."""
        scan_result = {"signals_found": 5, "positions_opened": 0}

        with patch.object(telegram_bot, "send_message", new_callable=AsyncMock) as mock_send:
            await telegram_bot.notify_scan_complete(scan_result)

            mock_send.assert_called_once()
            message = mock_send.call_args[0][0]
            assert "Scan Completed" in message
            assert "5" in message
            assert "New positions" not in message

    @pytest.mark.asyncio
    async def test_notify_scan_complete_with_positions(self, telegram_bot):
        """Test scan complete notification with new positions."""
        scan_result = {
            "signals_found": 3,
            "positions_opened": 2,
            "opened_positions": [
                {"symbol": "BTCUSDT", "entry_price": 50000.0},
                {"symbol": "ETHUSDT", "entry_price": 3000.0},
            ],
        }

        with patch.object(telegram_bot, "send_message", new_callable=AsyncMock) as mock_send:
            await telegram_bot.notify_scan_complete(scan_result)

            mock_send.assert_called_once()
            message = mock_send.call_args[0][0]
            assert "Scan Completed" in message
            assert "BTCUSDT" in message
            assert "ETHUSDT" in message

    @pytest.mark.asyncio
    async def test_notify_error(self, telegram_bot):
        """Test error notification."""
        error_message = "Failed to connect to exchange"

        with patch.object(telegram_bot, "send_message", new_callable=AsyncMock) as mock_send:
            await telegram_bot.notify_error(error_message)

            mock_send.assert_called_once()
            message = mock_send.call_args[0][0]
            assert "Error" in message
            assert error_message in message


class TestTelegramBotPolling:
    """Test polling functionality."""

    @pytest.mark.asyncio
    async def test_start_polling(self, telegram_bot):
        """Test bot starts polling."""
        mock_app = AsyncMock()
        mock_updater = AsyncMock()
        mock_app.updater = mock_updater
        telegram_bot.application = mock_app

        # Set stop event after short delay to prevent infinite wait
        async def set_stop_event():
            await asyncio.sleep(0.1)
            telegram_bot._stop_event.set()

        asyncio.create_task(set_stop_event())

        await telegram_bot.start_polling()

        mock_updater.start_polling.assert_called_once()


class TestTelegramBotStop:
    """Test bot stopping functionality."""

    @pytest.mark.asyncio
    async def test_stop_stops_application(self, telegram_bot):
        """Test that stop stops the application."""
        mock_app = AsyncMock()
        mock_updater = AsyncMock()
        mock_updater.running = True
        mock_app.updater = mock_updater
        telegram_bot.application = mock_app

        await telegram_bot.stop()

        mock_updater.stop.assert_called_once()
        mock_app.stop.assert_called_once()
        mock_app.shutdown.assert_called_once()

    @pytest.mark.asyncio
    async def test_stop_sets_event(self, telegram_bot):
        """Test that stop sets the stop event."""
        mock_app = AsyncMock()
        mock_updater = AsyncMock()
        mock_updater.running = False
        mock_app.updater = mock_updater
        telegram_bot.application = mock_app

        await telegram_bot.stop()

        assert telegram_bot._stop_event.is_set()

    @pytest.mark.asyncio
    async def test_stop_handles_error(self, telegram_bot):
        """Test that stop handles errors gracefully."""
        mock_app = AsyncMock()
        mock_updater = AsyncMock()
        mock_updater.running = True
        mock_updater.stop.side_effect = Exception("Stop error")
        mock_app.updater = mock_updater
        telegram_bot.application = mock_app

        # Should not raise exception
        await telegram_bot.stop()

    @pytest.mark.asyncio
    async def test_stop_with_no_application(self, telegram_bot):
        """Test that stop works when application is None."""
        telegram_bot.application = None

        # Should not raise exception
        await telegram_bot.stop()
