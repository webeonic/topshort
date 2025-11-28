"""Tests for MenuButtonHandler class."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from telegram import Chat, Message, Update, User
from telegram.ext import ContextTypes, MessageHandler

from src.bot.keyboard_builder import (
    MENU_BTN_HELP,
    MENU_BTN_HISTORY,
    MENU_BTN_POSITIONS,
    MENU_BTN_SCAN,
    MENU_BTN_SETTINGS,
    MENU_BTN_STATUS,
    MENU_BTN_TRADING,
)
from src.bot.menu_handler import MenuButtonHandler


@pytest.fixture
def mock_commands():
    """Create mock BotCommands instance."""
    commands = MagicMock()
    commands.status = AsyncMock()
    commands.positions = AsyncMock()
    commands.show_scan_menu = AsyncMock()
    commands.settings = AsyncMock()
    commands.start = AsyncMock()
    commands.history = AsyncMock()
    commands.show_menu = AsyncMock()
    return commands


@pytest.fixture
def menu_handler(mock_commands):
    """Create MenuButtonHandler instance for testing."""
    return MenuButtonHandler(mock_commands)


@pytest.fixture
def mock_update():
    """Create mock Update with message."""
    update = MagicMock(spec=Update)
    update.message = MagicMock(spec=Message)
    update.message.text = ""
    update.message.chat = MagicMock(spec=Chat)
    update.message.from_user = MagicMock(spec=User)
    return update


@pytest.fixture
def mock_context():
    """Create mock context."""
    return MagicMock(spec=ContextTypes.DEFAULT_TYPE)


class TestMenuButtonHandlerInit:
    """Test MenuButtonHandler initialization."""

    def test_init_stores_commands(self, mock_commands):
        """Test handler stores commands instance."""
        handler = MenuButtonHandler(mock_commands)
        assert handler.commands is mock_commands


class TestHandleMenuButton:
    """Test handle_menu_button method."""

    @pytest.mark.asyncio
    async def test_status_button_calls_status(self, menu_handler, mock_update, mock_context):
        """Test status button calls status command."""
        mock_update.message.text = MENU_BTN_STATUS

        await menu_handler.handle_menu_button(mock_update, mock_context)

        menu_handler.commands.status.assert_called_once_with(mock_update, mock_context)

    @pytest.mark.asyncio
    async def test_positions_button_calls_positions(self, menu_handler, mock_update, mock_context):
        """Test positions button calls positions command."""
        mock_update.message.text = MENU_BTN_POSITIONS

        await menu_handler.handle_menu_button(mock_update, mock_context)

        menu_handler.commands.positions.assert_called_once_with(mock_update, mock_context)

    @pytest.mark.asyncio
    async def test_scan_button_calls_show_scan_menu(self, menu_handler, mock_update, mock_context):
        """Test scan button calls show_scan_menu command."""
        mock_update.message.text = MENU_BTN_SCAN

        await menu_handler.handle_menu_button(mock_update, mock_context)

        menu_handler.commands.show_scan_menu.assert_called_once_with(mock_update, mock_context)

    @pytest.mark.asyncio
    async def test_settings_button_calls_settings(self, menu_handler, mock_update, mock_context):
        """Test settings button calls settings command."""
        mock_update.message.text = MENU_BTN_SETTINGS

        await menu_handler.handle_menu_button(mock_update, mock_context)

        menu_handler.commands.settings.assert_called_once_with(mock_update, mock_context)

    @pytest.mark.asyncio
    async def test_help_button_calls_start(self, menu_handler, mock_update, mock_context):
        """Test help button calls start (help) command."""
        mock_update.message.text = MENU_BTN_HELP

        await menu_handler.handle_menu_button(mock_update, mock_context)

        menu_handler.commands.start.assert_called_once_with(mock_update, mock_context)

    @pytest.mark.asyncio
    async def test_history_button_calls_history(self, menu_handler, mock_update, mock_context):
        """Test history button calls history command."""
        mock_update.message.text = MENU_BTN_HISTORY

        await menu_handler.handle_menu_button(mock_update, mock_context)

        menu_handler.commands.history.assert_called_once_with(mock_update, mock_context)

    @pytest.mark.asyncio
    async def test_trading_button_calls_show_menu(self, menu_handler, mock_update, mock_context):
        """Test trading button calls show_menu command."""
        mock_update.message.text = MENU_BTN_TRADING

        await menu_handler.handle_menu_button(mock_update, mock_context)

        menu_handler.commands.show_menu.assert_called_once_with(mock_update, mock_context)

    @pytest.mark.asyncio
    async def test_unknown_button_logs_warning(self, menu_handler, mock_update, mock_context):
        """Test unknown button text logs warning."""
        mock_update.message.text = "Unknown Button"

        with patch("src.bot.menu_handler.logger") as mock_logger:
            await menu_handler.handle_menu_button(mock_update, mock_context)
            mock_logger.warning.assert_called_once()


class TestGetMessageHandler:
    """Test get_message_handler method."""

    def test_returns_message_handler(self, menu_handler):
        """Test get_message_handler returns MessageHandler."""
        handler = menu_handler.get_message_handler()

        assert isinstance(handler, MessageHandler)

    def test_message_handler_has_callback(self, menu_handler):
        """Test message handler has correct callback function."""
        handler = menu_handler.get_message_handler()

        # Callback should be the handle_menu_button method (bound method check)
        assert handler.callback.__name__ == "handle_menu_button"
        assert handler.callback.__self__ is menu_handler


class TestMenuButtonRouting:
    """Test all menu buttons are properly routed."""

    @pytest.mark.parametrize(
        "button_text,expected_method",
        [
            (MENU_BTN_STATUS, "status"),
            (MENU_BTN_POSITIONS, "positions"),
            (MENU_BTN_SCAN, "show_scan_menu"),
            (MENU_BTN_SETTINGS, "settings"),
            (MENU_BTN_HELP, "start"),
            (MENU_BTN_HISTORY, "history"),
            (MENU_BTN_TRADING, "show_menu"),
        ],
    )
    @pytest.mark.asyncio
    async def test_button_routes_to_correct_method(
        self, menu_handler, mock_update, mock_context, button_text, expected_method
    ):
        """Test each button routes to correct command method."""
        mock_update.message.text = button_text

        await menu_handler.handle_menu_button(mock_update, mock_context)

        method = getattr(menu_handler.commands, expected_method)
        method.assert_called_once_with(mock_update, mock_context)
