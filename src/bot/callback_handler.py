"""Callback query handler for inline keyboard interactions."""

import logging
import time
from functools import wraps
from typing import Callable, Dict

from sqlalchemy.orm import Session
from telegram import Update
from telegram.ext import ContextTypes

from ..database.repository import CallbackLogRepository, KeyboardStateRepository
from ..trading.engine import TradingEngine

logger = logging.getLogger(__name__)


class CallbackHandler:
    """Handle callback queries from inline keyboards."""

    def __init__(self, session: Session, engine: TradingEngine):
        self.session = session
        self.engine = engine
        self.callback_log_repo = CallbackLogRepository(session)
        self.state_repo = KeyboardStateRepository(session)
        self.handlers: Dict[str, Callable] = {}
        self._register_default_handlers()

    def _register_default_handlers(self):
        """Register default callback handlers."""
        # Command callbacks
        self.register("cmd_status", self.handle_status)
        self.register("cmd_positions", self.handle_positions)
        self.register("cmd_history", self.handle_history)
        self.register("cmd_stats", self.handle_stats)
        self.register("cmd_settings", self.handle_settings)
        self.register("cmd_help", self.handle_help)

        # Position callbacks
        self.register_pattern("pos_details_", self.handle_position_details)
        self.register_pattern("pos_refresh_", self.handle_position_refresh)
        self.register_pattern("pos_close_", self.handle_position_close)

        # Trading control callbacks
        self.register("trading_resume", self.handle_trading_resume)
        self.register("trading_pause", self.handle_trading_pause)
        self.register("trading_scan", self.handle_trading_scan)
        self.register("trading_closeall", self.handle_trading_closeall)

        # Confirmation callbacks
        self.register_pattern("confirm_", self.handle_confirm)
        self.register("cancel", self.handle_cancel)

        # Setting callbacks
        self.register_pattern("setting_", self.handle_setting_menu)

        # Pagination
        self.register_pattern("page_", self.handle_page)

        # No-op for non-interactive buttons
        self.register("noop", self.handle_noop)

    def register(self, callback_data: str, handler: Callable):
        """Register a callback handler for exact match."""
        self.handlers[callback_data] = handler
        logger.debug(f"Registered callback handler: {callback_data}")

    def register_pattern(self, pattern: str, handler: Callable):
        """Register a callback handler for pattern match."""
        self.handlers[f"pattern:{pattern}"] = handler
        logger.debug(f"Registered pattern callback handler: {pattern}")

    def log_callback(self, success: bool = True):
        """Decorator to log callback interactions."""

        def decorator(func):
            @wraps(func)
            async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
                start_time = time.time()
                query = update.callback_query
                user_id = str(query.from_user.id)
                chat_id = str(query.message.chat_id)
                username = query.from_user.username

                try:
                    result = await func(update, context)
                    response_time = int((time.time() - start_time) * 1000)

                    self.callback_log_repo.log(
                        user_id=user_id,
                        chat_id=chat_id,
                        callback_data=query.data,
                        action=func.__name__,
                        username=username,
                        success=True,
                        response_time_ms=response_time,
                    )

                    return result

                except Exception as e:
                    response_time = int((time.time() - start_time) * 1000)
                    logger.error(f"Error in callback handler {func.__name__}: {e}")

                    self.callback_log_repo.log(
                        user_id=user_id,
                        chat_id=chat_id,
                        callback_data=query.data,
                        action=func.__name__,
                        username=username,
                        success=False,
                        error_message=str(e),
                        response_time_ms=response_time,
                    )

                    await query.answer("❌ Error occurred. Please try again.", show_alert=True)
                    raise

            return wrapper

        return decorator

    async def handle_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Main callback query handler that routes to specific handlers."""
        query = update.callback_query
        await query.answer()

        callback_data = query.data
        logger.info(f"Received callback: {callback_data} from user {query.from_user.id}")

        # Find exact match handler
        if callback_data in self.handlers:
            handler = self.handlers[callback_data]
            await handler(update, context)
            return

        # Find pattern match handler
        for pattern_key, handler in self.handlers.items():
            if pattern_key.startswith("pattern:"):
                pattern = pattern_key.replace("pattern:", "")
                if callback_data.startswith(pattern):
                    await handler(update, context)
                    return

        # No handler found
        logger.warning(f"No handler found for callback: {callback_data}")
        await query.edit_message_text(f"⚠️ Unknown action: {callback_data}")

    @log_callback(success=True)
    async def handle_status(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle status callback."""
        from .commands import BotCommands

        query = update.callback_query

        # Create a mock update with the query's message
        mock_update = Update(update.update_id)
        mock_update._effective_message = query.message

        commands = BotCommands(self.session, self.engine)
        await commands.status(mock_update, context)

    @log_callback(success=True)
    async def handle_positions(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle positions callback."""
        from .commands import BotCommands

        query = update.callback_query

        mock_update = Update(update.update_id)
        mock_update._effective_message = query.message

        commands = BotCommands(self.session, self.engine)
        await commands.positions(mock_update, context)

    @log_callback(success=True)
    async def handle_history(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle history callback."""
        from .commands import BotCommands

        query = update.callback_query

        mock_update = Update(update.update_id)
        mock_update._effective_message = query.message

        commands = BotCommands(self.session, self.engine)
        await commands.history(mock_update, context)

    @log_callback(success=True)
    async def handle_stats(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle stats callback."""
        from .commands import BotCommands

        query = update.callback_query

        mock_update = Update(update.update_id)
        mock_update._effective_message = query.message

        commands = BotCommands(self.session, self.engine)
        await commands.stats(mock_update, context)

    @log_callback(success=True)
    async def handle_settings(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle settings callback."""
        from .commands import BotCommands

        query = update.callback_query

        mock_update = Update(update.update_id)
        mock_update._effective_message = query.message

        commands = BotCommands(self.session, self.engine)
        await commands.settings(mock_update, context)

    @log_callback(success=True)
    async def handle_help(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle help callback."""
        from .commands import BotCommands

        query = update.callback_query

        mock_update = Update(update.update_id)
        mock_update._effective_message = query.message

        commands = BotCommands(self.session, self.engine)
        await commands.start(mock_update, context)

    @log_callback(success=True)
    async def handle_position_details(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle position details callback."""
        query = update.callback_query
        # Extract symbol from callback_data: pos_details_BTCUSDT
        symbol = query.data.replace("pos_details_", "")

        position = self.engine.position_manager.get_position_by_symbol(symbol)
        if not position:
            await query.edit_message_text(f"❌ Position not found: {symbol}")
            return

        pnl_emoji = "🟢" if position["unrealized_pnl"] > 0 else "🔴"
        message = f"""
📊 *Position Details: {position['symbol']}*

💰 Entry Price: {position['entry_price']:.4f}
📈 Current Price: {position['current_price']:.4f}
🎯 Take Profit: {position['take_profit_price']:.4f}
📊 Leverage: {position['leverage']}x
💵 Margin: {position['margin']:.2f} USDT
{pnl_emoji} Unrealized P&L: {position['unrealized_pnl']:.2f} USDT ({position['unrealized_pnl_pct']:.2f}%)
🕒 Opened: {position['opened_at']}
"""
        await query.edit_message_text(message, parse_mode="Markdown")

    @log_callback(success=True)
    async def handle_position_refresh(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle position refresh callback."""
        query = update.callback_query

        await query.answer("🔄 Refreshing position data...")
        # Trigger position update
        self.engine.position_manager.update_positions()

        # Show updated details
        await self.handle_position_details(update, context)

    @log_callback(success=True)
    async def handle_position_close(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle position close callback."""
        query = update.callback_query
        symbol = query.data.replace("pos_close_", "")

        await query.answer("Closing position...")

        result = self.engine.position_manager.close_position_by_symbol(symbol, "manual")

        if result:
            pnl_emoji = "🟢" if result["pnl"] > 0 else "🔴"
            message = f"""
✅ *Position Closed*

*{result['symbol']}*
💰 Entry: {result['entry_price']:.4f}
💰 Exit: {result['exit_price']:.4f}
{pnl_emoji} P&L: {result['pnl']:.2f} USDT ({result['pnl_pct']:.2f}%)
"""
            await query.edit_message_text(message, parse_mode="Markdown")
        else:
            await query.edit_message_text(f"❌ Failed to close position: {symbol}")

    @log_callback(success=True)
    async def handle_trading_resume(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle trading resume callback."""
        query = update.callback_query
        from ..database.repository import BotStatusRepository

        bot_status_repo = BotStatusRepository(self.session)
        bot_status_repo.set_paused(False)

        await query.edit_message_text("▶️ *Trading resumed*", parse_mode="Markdown")

    @log_callback(success=True)
    async def handle_trading_pause(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle trading pause callback."""
        query = update.callback_query
        from ..database.repository import BotStatusRepository

        bot_status_repo = BotStatusRepository(self.session)
        bot_status_repo.set_paused(True)

        await query.edit_message_text("⏸️ *Trading paused*", parse_mode="Markdown")

    @log_callback(success=True)
    async def handle_trading_scan(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle manual scan callback."""
        query = update.callback_query
        await query.answer("🔍 Starting market scan...")

        result = self.engine.execute_scan_and_trade()

        message = f"""
✅ *Scan Completed*

📊 Signals found: {result['signals_found']}
✅ Positions opened: {result['positions_opened']}
"""
        await query.edit_message_text(message, parse_mode="Markdown")

    @log_callback(success=True)
    async def handle_trading_closeall(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle close all positions callback."""
        query = update.callback_query
        await query.answer("🔄 Closing all positions...")

        result = self.engine.close_all_positions("manual")

        message = f"""
✅ *Close All Completed*

📊 Closed positions: {result['positions_closed']}/{result.get('total_positions', 0)}
"""
        await query.edit_message_text(message, parse_mode="Markdown")

    @log_callback(success=True)
    async def handle_confirm(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle confirmation callback."""
        query = update.callback_query
        # Extract action: confirm_closeall_data
        parts = query.data.split("_")
        action = parts[1] if len(parts) > 1 else "unknown"

        await query.edit_message_text(f"✅ Confirmed: {action}")

    @log_callback(success=True)
    async def handle_cancel(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle cancel callback."""
        query = update.callback_query
        await query.edit_message_text("❌ *Cancelled*", parse_mode="Markdown")

    @log_callback(success=True)
    async def handle_setting_menu(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle setting menu callback."""
        query = update.callback_query
        setting_key = query.data.replace("setting_", "")

        message = f"""
⚙️ *Setting: {setting_key}*

To change this setting, use:
`/set {setting_key} <value>`

Example: `/set margin_per_trade 150`
"""
        await query.edit_message_text(message, parse_mode="Markdown")

    @log_callback(success=True)
    async def handle_page(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle pagination callback."""
        query = update.callback_query
        page_num = int(query.data.split("_")[1])

        await query.answer(f"Loading page {page_num + 1}...")
        # Implementation depends on what's being paginated

    @log_callback(success=True)
    async def handle_noop(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle no-operation callback (for non-interactive buttons)."""
        query = update.callback_query
        await query.answer()
