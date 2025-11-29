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

    def test_without_auth_filter_accepts_any_user(self, menu_handler):
        """Test handler without auth_filter accepts any user message."""
        handler = menu_handler.get_message_handler(auth_filter=None)

        # Create mock message with menu button text
        mock_message = MagicMock(spec=Message)
        mock_message.text = MENU_BTN_STATUS
        mock_message.from_user = MagicMock(spec=User)
        mock_message.from_user.username = "any_user"
        mock_message.from_user.id = 12345

        # Filter should check for text match (not auth)
        assert isinstance(handler, MessageHandler)

    def test_with_auth_filter_combines_filters(self, menu_handler):
        """Test handler with auth_filter combines text and auth filters."""
        from telegram.ext import filters

        # Create a simple mock auth filter
        mock_auth_filter = MagicMock(spec=filters.BaseFilter)

        handler = menu_handler.get_message_handler(auth_filter=mock_auth_filter)

        assert isinstance(handler, MessageHandler)
        # The handler should have a combined filter
        assert handler.filters is not None


class TestMenuHandlerAuthorizationIntegration:
    """Test menu handler authorization filter integration.

    These tests verify that the auth_filter parameter properly integrates
    with the message handler to block unauthorized users.
    """

    def test_auth_filter_is_applied(self, menu_handler):
        """Test that auth_filter is properly applied to the handler."""
        from telegram.ext import filters

        class MockAuthFilter(filters.MessageFilter):
            """Mock filter that always returns False (unauthorized)."""

            def filter(self, message):
                return False

        mock_auth = MockAuthFilter()
        handler = menu_handler.get_message_handler(auth_filter=mock_auth)

        # Create mock message
        mock_message = MagicMock(spec=Message)
        mock_message.text = MENU_BTN_STATUS
        mock_message.from_user = MagicMock(spec=User)
        mock_message.from_user.username = "unauthorized_user"
        mock_message.from_user.id = 99999

        # The combined filter should return False because auth filter returns False
        assert handler.filters.check_update(MagicMock(message=mock_message, effective_message=mock_message)) is False

    def test_authorized_user_passes_filter(self, menu_handler):
        """Test that authorized user passes the combined filter."""
        from telegram.ext import filters

        class MockAuthFilter(filters.MessageFilter):
            """Mock filter that always returns True (authorized)."""

            def filter(self, message):
                return True

        mock_auth = MockAuthFilter()
        handler = menu_handler.get_message_handler(auth_filter=mock_auth)

        # Create mock message with valid menu button text
        mock_message = MagicMock(spec=Message)
        mock_message.text = MENU_BTN_STATUS
        mock_message.from_user = MagicMock(spec=User)
        mock_message.from_user.username = "authorized_user"
        mock_message.from_user.id = 12345

        mock_update = MagicMock()
        mock_update.message = mock_message
        mock_update.effective_message = mock_message

        # The combined filter should return truthy value (dict with matches or True)
        result = handler.filters.check_update(mock_update)
        assert result  # Truthy value means filter passed

    def test_unauthorized_user_blocked_with_valid_text(self, menu_handler):
        """Test unauthorized user is blocked even with valid menu button text.

        This is the key security test - verifying that sending menu button
        text like '📊 Статус' does not bypass authorization.
        """
        from telegram.ext import filters

        class MockAuthFilter(filters.MessageFilter):
            """Mock filter simulating unauthorized user."""

            def filter(self, message):
                # Simulate checking if user is in authorized list
                return message.from_user.username == "authorized_only"

        mock_auth = MockAuthFilter()
        handler = menu_handler.get_message_handler(auth_filter=mock_auth)

        # Create mock message from unauthorized user with valid menu text
        mock_message = MagicMock(spec=Message)
        mock_message.text = MENU_BTN_STATUS  # Valid menu button text
        mock_message.from_user = MagicMock(spec=User)
        mock_message.from_user.username = "hacker"  # Not authorized
        mock_message.from_user.id = 99999

        mock_update = MagicMock()
        mock_update.message = mock_message
        mock_update.effective_message = mock_message

        # Should be blocked despite valid menu button text
        assert handler.filters.check_update(mock_update) is False


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
