"""Comprehensive tests for CallbackHandler class."""

from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest
from telegram import CallbackQuery, Message, Update, User

from src.bot.callback_handler import CallbackHandler, log_callback


@pytest.fixture
def mock_session():
    """Create mock database session."""
    return MagicMock()


@pytest.fixture
def mock_engine():
    """Create mock trading engine."""
    engine = MagicMock()
    engine.position_manager.get_position_by_symbol.return_value = {
        "symbol": "BTCUSDT",
        "entry_price": 50000.0,
        "current_price": 49000.0,
        "take_profit_price": 48000.0,
        "leverage": 10,
        "margin": 100.0,
        "unrealized_pnl": 100.0,
        "unrealized_pnl_pct": 10.0,
        "opened_at": "2024-01-01 10:00:00",
    }
    engine.position_manager.close_position_by_symbol.return_value = {
        "symbol": "BTCUSDT",
        "entry_price": 50000.0,
        "exit_price": 49000.0,
        "pnl": 100.0,
        "pnl_pct": 10.0,
    }
    engine.execute_pump_scan_and_trade.return_value = {
        "signals_found": 5,
        "positions_opened": 2,
        "strategy_mode": "pump_cooldown",
    }
    engine.execute_order_block_cycle.return_value = {
        "signals_found": 1,
        "positions_opened": 1,
        "strategy_mode": "order_block",
    }
    engine.close_all_positions.return_value = {"positions_closed": 3, "total_positions": 3}
    engine.config = MagicMock()
    engine.config.strategy_runtime.default_manual_strategy = "pump_cooldown"
    engine.config.strategy_runtime.order_block_top_pairs = 50
    engine.config.order_block_strategy.enabled = True
    return engine


@pytest.fixture
def callback_handler(mock_session, mock_engine):
    """Create CallbackHandler instance for testing."""
    handler = CallbackHandler(mock_session, mock_engine)
    # Mock the repositories to avoid real database calls
    handler.callback_log_repo = MagicMock()
    handler.state_repo = MagicMock()
    return handler


@pytest.fixture
def mock_update():
    """Create mock Update with callback query."""
    update = Mock(spec=Update)
    update.update_id = 123456
    update.effective_user = Mock(spec=User)
    update.effective_user.id = 987654
    update.effective_user.username = "testuser"

    message = Mock(spec=Message)
    message.chat_id = 123456

    query = Mock(spec=CallbackQuery)
    query.from_user = update.effective_user
    query.message = message
    query.data = "test_callback"
    query.answer = AsyncMock()
    query.edit_message_text = AsyncMock()

    update.callback_query = query
    update.effective_message = message

    return update


@pytest.fixture
def mock_context():
    """Create mock context."""
    context = MagicMock()
    context.args = []
    return context


class TestCallbackHandlerInitialization:
    """Test CallbackHandler initialization."""

    def test_init_creates_handler(self, mock_session, mock_engine):
        """Test handler initialization."""
        handler = CallbackHandler(mock_session, mock_engine)

        assert handler.session == mock_session
        assert handler.engine == mock_engine
        assert handler.callback_log_repo is not None
        assert handler.state_repo is not None
        assert isinstance(handler.handlers, dict)

    def test_init_registers_default_handlers(self, callback_handler):
        """Test that default handlers are registered."""
        # Check command callbacks
        assert "cmd_status" in callback_handler.handlers
        assert "cmd_positions" in callback_handler.handlers
        assert "cmd_history" in callback_handler.handlers
        assert "cmd_stats" in callback_handler.handlers
        assert "cmd_settings" in callback_handler.handlers
        assert "cmd_help" in callback_handler.handlers
        assert "cmd_main" in callback_handler.handlers
        assert "cmd_scan" in callback_handler.handlers

        # Check pattern handlers
        assert "pattern:pos_details_" in callback_handler.handlers
        assert "pattern:pos_refresh_" in callback_handler.handlers
        assert "pattern:confirm_" in callback_handler.handlers
        assert "pattern:scan_strategy_" in callback_handler.handlers


class TestCallbackHandlerRegistration:
    """Test handler registration."""

    def test_register_exact_handler(self, callback_handler):
        """Test registering exact match handler."""
        mock_handler = AsyncMock()
        callback_handler.register("test_action", mock_handler)

        assert "test_action" in callback_handler.handlers
        assert callback_handler.handlers["test_action"] == mock_handler

    def test_register_pattern_handler(self, callback_handler):
        """Test registering pattern match handler."""
        mock_handler = AsyncMock()
        callback_handler.register_pattern("test_pattern_", mock_handler)

        assert "pattern:test_pattern_" in callback_handler.handlers
        assert callback_handler.handlers["pattern:test_pattern_"] == mock_handler


class TestCallbackHandlerRouting:
    """Test callback routing."""

    @pytest.mark.asyncio
    async def test_handle_callback_exact_match(self, callback_handler, mock_update, mock_context):
        """Test routing to exact match handler."""
        mock_handler = AsyncMock()
        callback_handler.register("exact_callback", mock_handler)
        mock_update.callback_query.data = "exact_callback"

        await callback_handler.handle_callback(mock_update, mock_context)

        mock_handler.assert_called_once_with(mock_update, mock_context)
        mock_update.callback_query.answer.assert_called_once()

    @pytest.mark.asyncio
    async def test_handle_callback_pattern_match(self, callback_handler, mock_update, mock_context):
        """Test routing to pattern match handler."""
        mock_handler = AsyncMock()
        callback_handler.register_pattern("pattern_", mock_handler)
        mock_update.callback_query.data = "pattern_test123"

        await callback_handler.handle_callback(mock_update, mock_context)

        mock_handler.assert_called_once_with(mock_update, mock_context)

    @pytest.mark.asyncio
    async def test_handle_callback_no_match(self, callback_handler, mock_update, mock_context):
        """Test handling callback with no matching handler."""
        mock_update.callback_query.data = "unknown_callback"

        await callback_handler.handle_callback(mock_update, mock_context)

        mock_update.callback_query.edit_message_text.assert_called_once()
        call_args = mock_update.callback_query.edit_message_text.call_args[0][0]
        assert "Unknown action" in call_args


class TestCommandCallbacks:
    """Test command callback handlers."""

    @pytest.mark.asyncio
    async def test_handle_status(self, callback_handler, mock_update, mock_context):
        """Test status callback handler."""
        with patch("src.bot.commands.BotCommands") as mock_commands_class:
            mock_commands = AsyncMock()
            mock_commands_class.return_value = mock_commands

            await callback_handler.handle_status(mock_update, mock_context)

            mock_commands_class.assert_called_once_with(callback_handler.session, callback_handler.engine)
            mock_commands.status.assert_called_once_with(mock_update, mock_context)

    @pytest.mark.asyncio
    async def test_handle_positions(self, callback_handler, mock_update, mock_context):
        """Test positions callback handler."""
        with patch("src.bot.commands.BotCommands") as mock_commands_class:
            mock_commands = AsyncMock()
            mock_commands_class.return_value = mock_commands

            await callback_handler.handle_positions(mock_update, mock_context)

            mock_commands.positions.assert_called_once_with(mock_update, mock_context)

    @pytest.mark.asyncio
    async def test_handle_history(self, callback_handler, mock_update, mock_context):
        """Test history callback handler."""
        with patch("src.bot.commands.BotCommands") as mock_commands_class:
            mock_commands = AsyncMock()
            mock_commands_class.return_value = mock_commands

            await callback_handler.handle_history(mock_update, mock_context)

            mock_commands.history.assert_called_once_with(mock_update, mock_context)

    @pytest.mark.asyncio
    async def test_handle_stats(self, callback_handler, mock_update, mock_context):
        """Test stats callback handler."""
        with patch("src.bot.commands.BotCommands") as mock_commands_class:
            mock_commands = AsyncMock()
            mock_commands_class.return_value = mock_commands

            await callback_handler.handle_stats(mock_update, mock_context)

            mock_commands.stats.assert_called_once_with(mock_update, mock_context)

    @pytest.mark.asyncio
    async def test_handle_settings(self, callback_handler, mock_update, mock_context):
        """Test settings callback handler."""
        with patch("src.bot.commands.BotCommands") as mock_commands_class:
            mock_commands = AsyncMock()
            mock_commands_class.return_value = mock_commands

            await callback_handler.handle_settings(mock_update, mock_context)

            mock_commands.settings.assert_called_once_with(mock_update, mock_context)

    @pytest.mark.asyncio
    async def test_handle_help(self, callback_handler, mock_update, mock_context):
        """Test help callback handler."""
        with patch("src.bot.commands.BotCommands") as mock_commands_class:
            mock_commands = AsyncMock()
            mock_commands_class.return_value = mock_commands

            await callback_handler.handle_help(mock_update, mock_context)

            mock_commands.start.assert_called_once_with(mock_update, mock_context)

    @pytest.mark.asyncio
    async def test_handle_main_menu(self, callback_handler, mock_update, mock_context):
        """Test returning to main menu."""
        with patch("src.bot.commands.BotCommands") as mock_commands_class:
            mock_commands = AsyncMock()
            mock_commands_class.return_value = mock_commands

            await callback_handler.handle_main_menu(mock_update, mock_context)

            mock_commands.show_menu.assert_called_once_with(mock_update, mock_context)

    @pytest.mark.asyncio
    async def test_handle_scan_menu(self, callback_handler, mock_update, mock_context):
        """Test showing strategy selection menu."""
        await callback_handler.handle_scan_menu(mock_update, mock_context)

        mock_update.callback_query.edit_message_text.assert_awaited()


class TestPositionCallbacks:
    """Test position-related callback handlers."""

    @pytest.mark.asyncio
    async def test_handle_position_details(self, callback_handler, mock_update, mock_context):
        """Test position details callback."""
        mock_update.callback_query.data = "pos_details_BTCUSDT"

        await callback_handler.handle_position_details(mock_update, mock_context)

        callback_handler.engine.position_manager.get_position_by_symbol.assert_called_once_with("BTCUSDT")
        mock_update.callback_query.edit_message_text.assert_called_once()
        message = mock_update.callback_query.edit_message_text.call_args[0][0]
        assert "Position Details" in message
        assert "BTCUSDT" in message

    @pytest.mark.asyncio
    async def test_handle_position_details_not_found(self, callback_handler, mock_update, mock_context):
        """Test position details when position not found."""
        callback_handler.engine.position_manager.get_position_by_symbol.return_value = None
        mock_update.callback_query.data = "pos_details_UNKNOWN"

        await callback_handler.handle_position_details(mock_update, mock_context)

        mock_update.callback_query.edit_message_text.assert_called_once()
        message = mock_update.callback_query.edit_message_text.call_args[0][0]
        assert "Position not found" in message

    @pytest.mark.asyncio
    async def test_handle_position_refresh(self, callback_handler, mock_update, mock_context):
        """Test position refresh callback."""
        mock_update.callback_query.data = "pos_refresh_BTCUSDT"

        await callback_handler.handle_position_refresh(mock_update, mock_context)

        callback_handler.engine.position_manager.update_positions.assert_called_once()
        mock_update.callback_query.answer.assert_called()

    @pytest.mark.asyncio
    async def test_handle_position_close(self, callback_handler, mock_update, mock_context):
        """Test position close callback."""
        mock_update.callback_query.data = "pos_close_BTCUSDT"

        await callback_handler.handle_position_close(mock_update, mock_context)

        callback_handler.engine.position_manager.close_position_by_symbol.assert_called_once_with("BTCUSDT", "manual")
        mock_update.callback_query.edit_message_text.assert_called_once()
        message = mock_update.callback_query.edit_message_text.call_args[0][0]
        assert "Position Closed" in message

    @pytest.mark.asyncio
    async def test_handle_position_close_failed(self, callback_handler, mock_update, mock_context):
        """Test position close when it fails."""
        callback_handler.engine.position_manager.close_position_by_symbol.return_value = None
        mock_update.callback_query.data = "pos_close_BTCUSDT"

        await callback_handler.handle_position_close(mock_update, mock_context)

        message = mock_update.callback_query.edit_message_text.call_args[0][0]
        assert "Failed to close position" in message


class TestTradingControlCallbacks:
    """Test trading control callback handlers."""

    @pytest.mark.asyncio
    async def test_handle_trading_resume(self, callback_handler, mock_update, mock_context):
        """Test trading resume callback."""
        with patch("src.database.repository.BotStatusRepository") as mock_repo_class:
            mock_repo = MagicMock()
            mock_repo_class.return_value = mock_repo

            await callback_handler.handle_trading_resume(mock_update, mock_context)

            mock_repo.set_paused.assert_called_once_with(False)
            mock_update.callback_query.edit_message_text.assert_called_once()

    @pytest.mark.asyncio
    async def test_handle_trading_pause(self, callback_handler, mock_update, mock_context):
        """Test trading pause callback."""
        with patch("src.database.repository.BotStatusRepository") as mock_repo_class:
            mock_repo = MagicMock()
            mock_repo_class.return_value = mock_repo

            await callback_handler.handle_trading_pause(mock_update, mock_context)

            mock_repo.set_paused.assert_called_once_with(True)
            mock_update.callback_query.edit_message_text.assert_called_once()

    @pytest.mark.asyncio
    async def test_handle_trading_scan(self, callback_handler, mock_update, mock_context):
        """Test manual scan callback."""
        await callback_handler.handle_trading_scan(mock_update, mock_context)

        callback_handler.engine.execute_pump_scan_and_trade.assert_called_once()
        mock_update.callback_query.answer.assert_called()
        mock_update.callback_query.edit_message_text.assert_called_once()
        message = mock_update.callback_query.edit_message_text.call_args[0][0]
        assert "Scan Completed" in message

    @pytest.mark.asyncio
    async def test_handle_trading_closeall(self, callback_handler, mock_update, mock_context):
        """Test close all positions callback."""
        await callback_handler.handle_trading_closeall(mock_update, mock_context)

        callback_handler.engine.close_all_positions.assert_called_once_with("manual")
        mock_update.callback_query.answer.assert_called()
        mock_update.callback_query.edit_message_text.assert_called_once()

    @pytest.mark.asyncio
    async def test_handle_scan_strategy_order_block(self, callback_handler, mock_update, mock_context):
        """Test strategy selection triggers manual scan."""
        mock_update.callback_query.data = "scan_strategy_order_block"
        with patch("src.bot.commands.BotCommands") as mock_commands_class:
            mock_commands = AsyncMock()
            mock_commands.scan = AsyncMock()
            mock_commands_class.return_value = mock_commands

            await callback_handler.handle_scan_strategy(mock_update, mock_context)

            mock_commands.scan.assert_awaited_once()
            mock_update.callback_query.edit_message_text.assert_awaited()
            assert mock_context.args == ["ob"]

    @pytest.mark.asyncio
    async def test_handle_scan_strategy_unknown(self, callback_handler, mock_update, mock_context):
        """Test unknown strategy selection shows alert."""
        mock_update.callback_query.data = "scan_strategy_unknown"

        await callback_handler.handle_scan_strategy(mock_update, mock_context)

        mock_update.callback_query.answer.assert_called_with("⚠️ Неизвестная стратегия", show_alert=True)


class TestConfirmationCallbacks:
    """Test confirmation callback handlers."""

    @pytest.mark.asyncio
    async def test_handle_confirm(self, callback_handler, mock_update, mock_context):
        """Test confirmation callback."""
        mock_update.callback_query.data = "confirm_closeall_data"

        await callback_handler.handle_confirm(mock_update, mock_context)

        mock_update.callback_query.edit_message_text.assert_called_once()
        message = mock_update.callback_query.edit_message_text.call_args[0][0]
        assert "Confirmed" in message

    @pytest.mark.asyncio
    async def test_handle_cancel(self, callback_handler, mock_update, mock_context):
        """Test cancel callback."""
        await callback_handler.handle_cancel(mock_update, mock_context)

        mock_update.callback_query.edit_message_text.assert_called_once()
        message = mock_update.callback_query.edit_message_text.call_args[0][0]
        assert "Cancelled" in message


class TestSettingCallbacks:
    """Test setting callback handlers."""

    @pytest.mark.asyncio
    async def test_handle_setting_menu(self, callback_handler, mock_update, mock_context):
        """Test setting menu callback."""
        mock_update.callback_query.data = "setting_margin"

        await callback_handler.handle_setting_menu(mock_update, mock_context)

        mock_update.callback_query.edit_message_text.assert_called_once()
        message = mock_update.callback_query.edit_message_text.call_args[0][0]
        assert "Setting: margin" in message


class TestPaginationCallbacks:
    """Test pagination callback handlers."""

    @pytest.mark.asyncio
    async def test_handle_page(self, callback_handler, mock_update, mock_context):
        """Test pagination callback."""
        mock_update.callback_query.data = "page_2"

        await callback_handler.handle_page(mock_update, mock_context)

        mock_update.callback_query.answer.assert_called()


class TestNoopCallbacks:
    """Test no-operation callback handlers."""

    @pytest.mark.asyncio
    async def test_handle_noop(self, callback_handler, mock_update, mock_context):
        """Test no-op callback."""
        await callback_handler.handle_noop(mock_update, mock_context)

        # Should just answer the query without doing anything else
        mock_update.callback_query.answer.assert_called_once()


class TestLogCallbackDecorator:
    """Test log_callback decorator."""

    @pytest.mark.asyncio
    async def test_log_callback_success(self, callback_handler, mock_update, mock_context):
        """Test decorator logs successful callback."""

        @log_callback(success=True)
        async def test_handler(self, update, context):
            return "success"

        with patch.object(callback_handler.callback_log_repo, "log") as mock_log:
            result = await test_handler(callback_handler, mock_update, mock_context)

            assert result == "success"
            mock_log.assert_called_once()
            call_kwargs = mock_log.call_args[1]
            assert call_kwargs["success"] is True

    @pytest.mark.asyncio
    async def test_log_callback_error(self, callback_handler, mock_update, mock_context):
        """Test decorator logs errors."""

        @log_callback(success=True)
        async def test_handler(self, update, context):
            raise ValueError("Test error")

        with patch.object(callback_handler.callback_log_repo, "log") as mock_log:
            with pytest.raises(ValueError):
                await test_handler(callback_handler, mock_update, mock_context)

            mock_log.assert_called_once()
            call_kwargs = mock_log.call_args[1]
            assert call_kwargs["success"] is False
            assert "Test error" in call_kwargs["error_message"]
