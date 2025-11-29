"""Comprehensive tests for BotCommands class."""

import os
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest
from telegram import Message, Update, User

from src.bot.commands import ALLOWED_SETTINGS, AuditLogger, BotCommands, require_auth


@pytest.fixture
def mock_session():
    """Create mock database session."""
    return MagicMock()


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
    engine.position_manager.get_all_open_positions.return_value = [
        {
            "symbol": "BTCUSDT",
            "entry_price": 50000.0,
            "current_price": 49000.0,
            "take_profit_price": 48000.0,
            "leverage": 10,
            "margin": 100.0,
            "unrealized_pnl": 100.0,
            "unrealized_pnl_pct": 10.0,
        }
    ]
    engine.execute_pump_scan_and_trade.return_value = {
        "signals_found": 5,
        "positions_opened": 2,
        "strategy_mode": "pump_cooldown",
    }
    engine.execute_order_block_cycle.return_value = {
        "signals_found": 2,
        "positions_opened": 1,
        "strategy_mode": "order_block",
    }
    engine.close_all_positions.return_value = {"positions_closed": 3, "total_positions": 3}
    engine.position_manager.close_position_by_symbol.return_value = {
        "symbol": "BTCUSDT",
        "entry_price": 50000.0,
        "exit_price": 49000.0,
        "pnl": 100.0,
        "pnl_pct": 10.0,
    }
    engine.scanner = MagicMock()
    engine.scanner.get_order_block_universe.return_value = ["BTC/USDT:USDT"] * 50
    engine.config = MagicMock()
    engine.config.strategy_runtime.default_manual_strategy = "pump_cooldown"
    engine.config.strategy_runtime.order_block_top_pairs = 50
    return engine


@pytest.fixture
def bot_commands(mock_session, mock_engine):
    """Create BotCommands instance for testing."""
    commands = BotCommands(mock_session, mock_engine)
    # Mock the repositories to avoid real database calls
    commands.settings_repo = MagicMock()
    commands.history_repo = MagicMock()
    commands.bot_status_repo = MagicMock()
    commands.signal_repo = MagicMock()
    commands.scan_progress_repo = MagicMock()
    commands.keyboard_builder = MagicMock()
    return commands


@pytest.fixture
def mock_update():
    """Create mock Update object."""
    update = Mock(spec=Update)
    update.effective_user = Mock(spec=User)
    update.effective_user.id = 12345
    update.effective_user.username = "testuser"

    message = AsyncMock(spec=Message)
    update.effective_message = message

    return update


@pytest.fixture
def mock_context():
    """Create mock context object."""
    context = MagicMock()
    context.args = []
    return context


@pytest.fixture
def mock_bot_status():
    """Create mock bot status."""
    status = MagicMock()
    status.is_active = True
    status.is_paused = False
    status.started_at = datetime(2024, 1, 1, 10, 0, 0)
    status.total_positions_opened = 10
    status.total_positions_closed = 8
    status.total_pnl = 150.0
    return status


@pytest.fixture
def mock_trade_history():
    """Create mock trade history."""
    trade = MagicMock()
    trade.symbol = "BTCUSDT"
    trade.entry_price = 50000.0
    trade.exit_price = 49000.0
    trade.pnl = 100.0
    trade.pnl_pct = 10.0
    trade.close_reason = "take_profit"
    trade.closed_at = datetime(2024, 1, 1, 11, 0, 0)
    return [trade]


@pytest.fixture
def mock_statistics():
    """Create mock statistics."""
    return {
        "total_trades": 10,
        "winning_trades": 6,
        "losing_trades": 4,
        "win_rate": 60.0,
        "total_pnl": 150.0,
        "avg_pnl": 15.0,
        "avg_pnl_pct": 5.0,
    }


class TestBotCommandsInitialization:
    """Test BotCommands initialization."""

    def test_init_creates_command_handler(self, mock_session, mock_engine):
        """Test command handler initialization."""
        commands = BotCommands(mock_session, mock_engine)

        assert commands.session == mock_session
        assert commands.engine == mock_engine
        assert commands.settings_repo is not None
        assert commands.history_repo is not None
        assert commands.bot_status_repo is not None
        assert commands.signal_repo is not None
        assert commands.keyboard_builder is not None


class TestStartCommand:
    """Test /start command."""

    @pytest.mark.asyncio
    async def test_start_sends_welcome_message(self, bot_commands, mock_update, mock_context):
        """Test start command sends welcome message with persistent menu."""
        await bot_commands.start(mock_update, mock_context)

        mock_update.effective_message.reply_text.assert_called_once()
        message = mock_update.effective_message.reply_text.call_args[0][0]
        assert "TopShort Trading Bot" in message
        # Russian message now
        assert "Доступные команды" in message

    @pytest.mark.asyncio
    async def test_start_with_persistent_keyboard(self, bot_commands, mock_update, mock_context):
        """Test start command sets persistent reply keyboard."""
        await bot_commands.start(mock_update, mock_context)

        mock_update.effective_message.reply_text.assert_called_once()
        call_kwargs = mock_update.effective_message.reply_text.call_args[1]
        # Should have ReplyKeyboardMarkup (persistent menu)
        assert "reply_markup" in call_kwargs
        assert call_kwargs["reply_markup"] is not None


class TestStatusCommand:
    """Test /status command."""

    @pytest.mark.asyncio
    async def test_status_displays_bot_info(self, bot_commands, mock_update, mock_context, mock_bot_status):
        """Test status command displays bot information."""
        bot_commands.bot_status_repo.get.return_value = mock_bot_status

        await bot_commands.status(mock_update, mock_context)

        mock_update.effective_message.reply_text.assert_called_once()
        message = mock_update.effective_message.reply_text.call_args[0][0]
        assert "Bot Status" in message
        assert "Active" in message
        assert "150.00 USDT" in message

    @pytest.mark.asyncio
    async def test_status_handles_error(self, bot_commands, mock_update, mock_context):
        """Test status command handles errors."""
        bot_commands.bot_status_repo.get.side_effect = Exception("Database error")

        await bot_commands.status(mock_update, mock_context)

        # Should send generic error message (not exposing internal details)
        mock_update.effective_message.reply_text.assert_called_once()
        message = mock_update.effective_message.reply_text.call_args[0][0]
        assert "error occurred" in message


class TestPositionsCommand:
    """Test /positions command."""

    @pytest.mark.asyncio
    async def test_positions_displays_open_positions(self, bot_commands, mock_update, mock_context):
        """Test positions command displays open positions."""
        await bot_commands.positions(mock_update, mock_context)

        mock_update.effective_message.reply_text.assert_called_once()
        message = mock_update.effective_message.reply_text.call_args[0][0]
        # Russian labels now
        assert "Открытые позиции" in message
        assert "BTCUSDT" in message
        assert "50000" in message

    @pytest.mark.asyncio
    async def test_positions_no_positions(self, bot_commands, mock_update, mock_context):
        """Test positions command with no positions."""
        bot_commands.engine.position_manager.get_all_open_positions.return_value = []

        await bot_commands.positions(mock_update, mock_context)

        mock_update.effective_message.reply_text.assert_called_once()
        message = mock_update.effective_message.reply_text.call_args[0][0]
        # Russian labels now
        assert "Нет открытых позиций" in message


class TestHistoryCommand:
    """Test /history command."""

    @pytest.mark.asyncio
    async def test_history_displays_trades(self, bot_commands, mock_update, mock_context, mock_trade_history):
        """Test history command displays trade history."""
        bot_commands.history_repo.get_recent.return_value = mock_trade_history

        await bot_commands.history(mock_update, mock_context)

        mock_update.effective_message.reply_text.assert_called_once()
        message = mock_update.effective_message.reply_text.call_args[0][0]
        assert "History" in message
        assert "BTCUSDT" in message
        assert "take_profit" in message

    @pytest.mark.asyncio
    async def test_history_empty(self, bot_commands, mock_update, mock_context):
        """Test history command with empty history."""
        bot_commands.history_repo.get_recent.return_value = []

        await bot_commands.history(mock_update, mock_context)

        mock_update.effective_message.reply_text.assert_called_once()
        message = mock_update.effective_message.reply_text.call_args[0][0]
        assert "empty" in message


class TestStatsCommand:
    """Test /stats command."""

    @pytest.mark.asyncio
    async def test_stats_displays_statistics(self, bot_commands, mock_update, mock_context, mock_statistics):
        """Test stats command displays statistics."""
        bot_commands.history_repo.get_statistics.return_value = mock_statistics

        await bot_commands.stats(mock_update, mock_context)

        mock_update.effective_message.reply_text.assert_called_once()
        message = mock_update.effective_message.reply_text.call_args[0][0]
        assert "Trading Statistics" in message
        assert "10" in message  # total trades
        assert "60.00%" in message  # win rate

    @pytest.mark.asyncio
    async def test_stats_no_trades(self, bot_commands, mock_update, mock_context):
        """Test stats command with no trades."""
        bot_commands.history_repo.get_statistics.return_value = {"total_trades": 0}

        await bot_commands.stats(mock_update, mock_context)

        mock_update.effective_message.reply_text.assert_called_once()
        message = mock_update.effective_message.reply_text.call_args[0][0]
        assert "No statistics" in message


class TestSettingsCommand:
    """Test /settings command."""

    @pytest.mark.asyncio
    async def test_settings_displays_all_settings(self, bot_commands, mock_update, mock_context):
        """Test settings command displays all settings."""
        mock_setting = MagicMock()
        mock_setting.key = "margin_per_trade"
        mock_setting.value = "100"
        bot_commands.settings_repo.get_all.return_value = [mock_setting]

        await bot_commands.settings(mock_update, mock_context)

        mock_update.effective_message.reply_text.assert_called_once()
        message = mock_update.effective_message.reply_text.call_args[0][0]
        # Russian labels now
        assert "Текущие настройки" in message
        assert "margin_per_trade" in message


class TestSetSettingCommand:
    """Test /set command."""

    @pytest.mark.asyncio
    @patch("src.bot.commands.AUTHORIZED_USERS", {"12345"})
    async def test_set_valid_setting(self, bot_commands, mock_update, mock_context):
        """Test setting a valid setting."""
        mock_context.args = ["margin_per_trade", "150"]

        await bot_commands.set_setting(mock_update, mock_context)

        bot_commands.settings_repo.set.assert_called_once()
        mock_update.effective_message.reply_text.assert_called_once()
        message = mock_update.effective_message.reply_text.call_args[0][0]
        assert "Setting updated successfully" in message

    @pytest.mark.asyncio
    @patch("src.bot.commands.AUTHORIZED_USERS", {"12345"})
    async def test_set_invalid_key(self, bot_commands, mock_update, mock_context):
        """Test setting with invalid key."""
        mock_context.args = ["invalid_key", "150"]

        await bot_commands.set_setting(mock_update, mock_context)

        # Check error message was sent
        calls = mock_update.effective_message.reply_text.call_args_list
        assert len(calls) >= 1
        message = calls[0][0][0]
        assert "Invalid setting key" in message

    @pytest.mark.asyncio
    @patch("src.bot.commands.AUTHORIZED_USERS", {"12345"})
    async def test_set_out_of_range(self, bot_commands, mock_update, mock_context):
        """Test setting value out of range."""
        mock_context.args = ["margin_per_trade", "99999"]

        await bot_commands.set_setting(mock_update, mock_context)

        # Check error message was sent
        calls = mock_update.effective_message.reply_text.call_args_list
        assert len(calls) >= 1
        message = calls[0][0][0]
        assert "out of range" in message

    @pytest.mark.asyncio
    @patch("src.bot.commands.AUTHORIZED_USERS", {"12345"})
    async def test_set_invalid_type(self, bot_commands, mock_update, mock_context):
        """Test setting with invalid type."""
        mock_context.args = ["margin_per_trade", "not_a_number"]

        await bot_commands.set_setting(mock_update, mock_context)

        # Check error message was sent
        calls = mock_update.effective_message.reply_text.call_args_list
        assert len(calls) >= 1

    @pytest.mark.asyncio
    @patch("src.bot.commands.AUTHORIZED_USERS", {"12345"})
    async def test_set_missing_args(self, bot_commands, mock_update, mock_context):
        """Test /set with missing arguments."""
        mock_context.args = []

        await bot_commands.set_setting(mock_update, mock_context)

        mock_update.effective_message.reply_text.assert_called_once()
        message = mock_update.effective_message.reply_text.call_args[0][0]
        assert "Usage" in message

    @pytest.mark.asyncio
    @patch("src.bot.commands.AUTHORIZED_USERS", {"99999"})
    async def test_set_blocks_unauthorized_user(self, bot_commands, mock_update, mock_context):
        """Test /set blocks unauthorized user."""
        mock_context.args = ["margin_per_trade", "150"]

        await bot_commands.set_setting(mock_update, mock_context)

        # Should return None and send access denied message
        bot_commands.settings_repo.set.assert_not_called()
        mock_update.effective_message.reply_text.assert_called_once()
        message = mock_update.effective_message.reply_text.call_args[0][0]
        assert "Access Denied" in message


class TestPauseResumeCommands:
    """Test /pause and /resume commands."""

    @pytest.mark.asyncio
    @patch("src.bot.commands.AUTHORIZED_USERS", {"12345"})
    async def test_pause_trading(self, bot_commands, mock_update, mock_context):
        """Test pause trading command."""
        await bot_commands.pause(mock_update, mock_context)

        bot_commands.bot_status_repo.set_paused.assert_called_once_with(True)
        mock_update.effective_message.reply_text.assert_called_once()

    @pytest.mark.asyncio
    @patch("src.bot.commands.AUTHORIZED_USERS", {"12345"})
    async def test_resume_trading(self, bot_commands, mock_update, mock_context):
        """Test resume trading command."""
        await bot_commands.resume(mock_update, mock_context)

        bot_commands.bot_status_repo.set_paused.assert_called_once_with(False)
        mock_update.effective_message.reply_text.assert_called_once()


class TestScanCommand:
    """Test /scan command."""

    @pytest.mark.asyncio
    @patch("src.bot.commands.AUTHORIZED_USERS", {"12345"})
    async def test_scan_executes_scan(self, bot_commands, mock_update, mock_context):
        """Test scan command executes market scan with progress bar."""
        # Mock the message object returned by reply_text
        mock_message = AsyncMock()
        mock_message.edit_text = AsyncMock()
        mock_update.effective_message.reply_text.return_value = mock_message

        await bot_commands.scan(mock_update, mock_context)

        # Verify Pump & Cooldown scan was executed by default
        bot_commands.engine.execute_pump_scan_and_trade.assert_called_once()

        # Verify initial message was sent
        mock_update.effective_message.reply_text.assert_called_once()
        initial_message = mock_update.effective_message.reply_text.call_args[0][0]
        assert "Запрос принят" in initial_message

        # Verify final message was edited
        assert mock_message.edit_text.called

    def test_format_processed_line_pump_mode(self, bot_commands):
        """Pump & Cooldown mode uses approximate totals."""
        assert bot_commands._format_processed_line(5, 200, "pump_cooldown") == "Processed: 5/~200 symbols"

    def test_format_processed_line_order_block_mode(self, bot_commands):
        """Order Block mode uses exact totals."""
        assert bot_commands._format_processed_line(3, 50, "order_block") == "Processed: 3/50 symbols"

    @pytest.mark.asyncio
    @patch("src.bot.commands.AUTHORIZED_USERS", {"12345"})
    async def test_scan_order_block_mode(self, bot_commands, mock_update, mock_context):
        """Ensure /scan ob triggers Order Block strategy."""
        mock_context.args = ["ob"]
        mock_message = AsyncMock()
        mock_message.edit_text = AsyncMock()
        mock_update.effective_message.reply_text.return_value = mock_message

        await bot_commands.scan(mock_update, mock_context)

        bot_commands.engine.execute_order_block_cycle.assert_called_once()
        mock_message.edit_text.assert_called()

    @pytest.mark.asyncio
    @patch("src.bot.commands.AUTHORIZED_USERS", {"12345"})
    async def test_scan_order_block_empty_universe(self, bot_commands, mock_update, mock_context):
        """Order Block scan should report 0 symbols when universe is empty and limit is 0."""
        mock_context.args = ["ob"]
        bot_commands.engine.config.strategy_runtime.order_block_top_pairs = 0
        bot_commands.engine.scanner.get_order_block_universe.return_value = []
        mock_message = AsyncMock()
        mock_message.edit_text = AsyncMock()
        mock_update.effective_message.reply_text.return_value = mock_message

        await bot_commands.scan(mock_update, mock_context)

        bot_commands.engine.execute_order_block_cycle.assert_called_once()
        create_kwargs = bot_commands.scan_progress_repo.create.call_args.kwargs
        assert create_kwargs["total_symbols"] == 0

    @pytest.mark.asyncio
    @patch("src.bot.commands.AUTHORIZED_USERS", {"12345"})
    async def test_run_scan_request_reports_setup_error(self, bot_commands, mock_update, mock_context):
        """Early failures should notify user about scan error."""

        async def immediate(func, *args, **kwargs):
            return func(*args, **kwargs)

        bot_commands._run_blocking = immediate
        bot_commands.scan_progress_repo.create.side_effect = Exception("db down")

        initial_message = AsyncMock()
        initial_message.edit_text = AsyncMock()

        await bot_commands._run_scan_request(
            update=mock_update,
            context=mock_context,
            strategy_mode="pump_cooldown",
            scan_id="scan_123",
            user_id="user",
            initial_message=initial_message,
        )

        assert any("Ошибка сканирования" in args.args[0] for args in initial_message.edit_text.await_args_list)

    @pytest.mark.asyncio
    @patch("src.bot.commands.AUTHORIZED_USERS", {"12345"})
    async def test_run_scan_request_falls_back_to_reply_on_edit_error(self, bot_commands, mock_update, mock_context):
        """If editing fails, fallback message is sent via reply."""

        async def immediate(func, *args, **kwargs):
            return func(*args, **kwargs)

        bot_commands._run_blocking = immediate

        initial_message = AsyncMock()
        initial_message.edit_text = AsyncMock(side_effect=RuntimeError("cannot edit"))

        await bot_commands._run_scan_request(
            update=mock_update,
            context=mock_context,
            strategy_mode="pump_cooldown",
            scan_id="scan_123",
            user_id="user",
            initial_message=initial_message,
        )

        mock_update.effective_message.reply_text.assert_awaited()

    @pytest.mark.asyncio
    @patch("src.bot.commands.AUTHORIZED_USERS", {"12345"})
    async def test_run_scan_request_starts_progress_monitor_without_queue(self, bot_commands, mock_update, mock_context):
        """Progress monitor should run even without scan queue."""

        async def immediate(func, *args, **kwargs):
            return func(*args, **kwargs)

        bot_commands.scan_queue = None
        bot_commands._run_blocking = immediate
        bot_commands._progress_monitor = AsyncMock()

        initial_message = AsyncMock()
        initial_message.edit_text = AsyncMock()

        await bot_commands._run_scan_request(
            update=mock_update,
            context=mock_context,
            strategy_mode="pump_cooldown",
            scan_id="scan_123",
            user_id="user",
            initial_message=initial_message,
        )

        bot_commands._progress_monitor.assert_awaited_once()


class TestCloseCommand:
    """Test /close command."""

    @pytest.mark.asyncio
    @patch("src.bot.commands.AUTHORIZED_USERS", {"12345"})
    async def test_close_position_success(self, bot_commands, mock_update, mock_context):
        """Test closing a position successfully."""
        mock_context.args = ["BTCUSDT"]

        await bot_commands.close(mock_update, mock_context)

        bot_commands.engine.position_manager.close_position_by_symbol.assert_called_once_with("BTCUSDT", "manual")
        mock_update.effective_message.reply_text.assert_called_once()
        message = mock_update.effective_message.reply_text.call_args[0][0]
        assert "Position closed" in message

    @pytest.mark.asyncio
    @patch("src.bot.commands.AUTHORIZED_USERS", {"12345"})
    async def test_close_position_failed(self, bot_commands, mock_update, mock_context):
        """Test closing position that fails."""
        mock_context.args = ["BTCUSDT"]
        bot_commands.engine.position_manager.close_position_by_symbol.return_value = None

        await bot_commands.close(mock_update, mock_context)

        message = mock_update.effective_message.reply_text.call_args[0][0]
        assert "Failed" in message

    @pytest.mark.asyncio
    @patch("src.bot.commands.AUTHORIZED_USERS", {"12345"})
    async def test_close_missing_symbol(self, bot_commands, mock_update, mock_context):
        """Test close command without symbol."""
        mock_context.args = []

        await bot_commands.close(mock_update, mock_context)

        mock_update.effective_message.reply_text.assert_called_once()
        message = mock_update.effective_message.reply_text.call_args[0][0]
        assert "Usage" in message


class TestCloseAllCommand:
    """Test /closeall command."""

    @pytest.mark.asyncio
    @patch("src.bot.commands.AUTHORIZED_USERS", {"12345"})
    async def test_closeall_closes_positions(self, bot_commands, mock_update, mock_context):
        """Test closing all positions."""
        await bot_commands.closeall(mock_update, mock_context)

        bot_commands.engine.close_all_positions.assert_called_once_with("manual")
        # Should be called twice: once for starting, once for result
        assert mock_update.effective_message.reply_text.call_count == 2


class TestShowMenuCommand:
    """Test /menu command - trading controls menu."""

    @pytest.mark.asyncio
    async def test_show_menu_displays_trading_controls(self, bot_commands, mock_update, mock_context, mock_bot_status):
        """Test menu command shows trading controls with inline keyboard."""
        bot_commands.bot_status_repo.get.return_value = mock_bot_status
        mock_keyboard = MagicMock()
        bot_commands.keyboard_builder.create_inline_keyboard.return_value = mock_keyboard

        await bot_commands.show_menu(mock_update, mock_context)

        mock_update.effective_message.reply_text.assert_called_once()
        message = mock_update.effective_message.reply_text.call_args[0][0]
        # Russian labels now
        assert "Управление торговлей" in message
        call_kwargs = mock_update.effective_message.reply_text.call_args[1]
        assert call_kwargs["reply_markup"] == mock_keyboard

    @pytest.mark.asyncio
    async def test_show_menu_creates_inline_keyboard(self, bot_commands, mock_update, mock_context, mock_bot_status):
        """Test menu command creates inline keyboard for trading controls."""
        bot_commands.bot_status_repo.get.return_value = mock_bot_status

        await bot_commands.show_menu(mock_update, mock_context)

        bot_commands.keyboard_builder.create_inline_keyboard.assert_called_once()


class TestRequireAuthDecorator:
    """Test require_auth decorator."""

    @pytest.mark.asyncio
    @patch("src.bot.commands.AUTHORIZED_USERS", {"12345"})
    async def test_auth_allows_authorized_user(self, bot_commands, mock_update, mock_context):
        """Test decorator allows authorized user."""

        @require_auth
        async def test_command(self, update, context):
            return "success"

        result = await test_command(bot_commands, mock_update, mock_context)
        assert result == "success"

    @pytest.mark.asyncio
    @patch("src.bot.commands.AUTHORIZED_USERS", {"99999"})
    async def test_auth_blocks_unauthorized_user(self, bot_commands, mock_update, mock_context):
        """Test decorator blocks unauthorized user."""

        @require_auth
        async def test_command(self, update, context):
            return "success"

        result = await test_command(bot_commands, mock_update, mock_context)

        # Should return None and send access denied message
        assert result is None
        mock_update.effective_message.reply_text.assert_called_once()
        message = mock_update.effective_message.reply_text.call_args[0][0]
        assert "Access Denied" in message

    @pytest.mark.asyncio
    @patch("src.bot.commands.AUTHORIZED_USERS", set())
    async def test_auth_blocks_when_no_users_configured(self, bot_commands, mock_update, mock_context):
        """Test decorator blocks when no authorized users configured."""

        @require_auth
        async def test_command(self, update, context):
            return "success"

        result = await test_command(bot_commands, mock_update, mock_context)
        assert result is None


class TestIsUserAuthorized:
    """Test is_user_authorized function."""

    @patch("src.bot.commands.AUTHORIZED_USERS", {"12345", "67890"})
    def test_authorized_by_user_id(self):
        """Test user authorized by user_id."""
        from src.bot.commands import is_user_authorized

        mock_user = MagicMock()
        mock_user.id = 12345

        assert is_user_authorized(mock_user) is True

    @patch("src.bot.commands.AUTHORIZED_USERS", {"12345"})
    def test_unauthorized_user(self):
        """Test unauthorized user is rejected."""
        from src.bot.commands import is_user_authorized

        mock_user = MagicMock()
        mock_user.id = 99999

        assert is_user_authorized(mock_user) is False

    @patch("src.bot.commands.AUTHORIZED_USERS", set())
    def test_empty_authorized_users_rejects_all(self):
        """Test that empty AUTHORIZED_USERS rejects all users."""
        from src.bot.commands import is_user_authorized

        mock_user = MagicMock()
        mock_user.id = 12345

        assert is_user_authorized(mock_user) is False

    def test_none_user(self):
        """Test None user is rejected."""
        from src.bot.commands import is_user_authorized

        assert is_user_authorized(None) is False


class TestAuditLogger:
    """Test AuditLogger class."""

    def test_log_security_event(self):
        """Test security event logging."""
        with patch("src.bot.commands.logger") as mock_logger:
            audit = AuditLogger()
            audit.log_security_event(12345, "testuser", "TEST_ACTION", {"key": "value"})

            mock_logger.warning.assert_called_once()
            call_args = mock_logger.warning.call_args[0][0]
            assert "SECURITY_EVENT" in call_args
            assert "12345" in call_args
            assert "testuser" in call_args
            assert "TEST_ACTION" in call_args


class TestAllowedSettings:
    """Test ALLOWED_SETTINGS configuration."""

    def test_allowed_settings_structure(self):
        """Test that ALLOWED_SETTINGS has correct structure."""
        assert isinstance(ALLOWED_SETTINGS, dict)

        for key, config in ALLOWED_SETTINGS.items():
            assert "type" in config
            assert "min" in config
            assert "max" in config
            assert "description" in config
            assert config["type"] in [int, float]
            assert config["min"] < config["max"]

    def test_allowed_settings_contains_expected_keys(self):
        """Test that ALLOWED_SETTINGS contains expected keys."""
        expected_keys = [
            "margin_per_trade",
            "max_positions",
            "max_total_margin",
            "default_leverage",
            "take_profit_pct",
        ]

        for key in expected_keys:
            assert key in ALLOWED_SETTINGS
