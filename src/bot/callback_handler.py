"""Callback query handler for inline keyboard interactions."""

from __future__ import annotations

import logging
import time
from functools import wraps
from typing import TYPE_CHECKING, Callable, Dict

from sqlalchemy.orm import Session
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from ..database.repository import CallbackLogRepository, KeyboardStateRepository
from ..trading.engine import TradingEngine
from ..utils.async_executor import run_blocking
from . import commands as bot_commands_module
from .keyboard_builder import InlineTemplates, KeyboardBuilder, callback_registry
from .scan_queue import ScanQueueManager

if TYPE_CHECKING:
    from ..config import ConcurrencyConfig
    from .commands import BotCommands

logger = logging.getLogger(__name__)


def log_callback(success: bool = True):
    """Decorator to log callback interactions."""

    def decorator(func):
        @wraps(func)
        async def wrapper(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
            start_time = time.time()
            query = update.callback_query
            user_id = str(query.from_user.id)
            chat_id = str(query.message.chat_id)
            username = query.from_user.username

            try:
                result = await func(self, update, context)
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


class CallbackHandler:
    """Handle callback queries from inline keyboards."""

    def __init__(self, session: Session, engine: TradingEngine, commands: "BotCommands" | None = None):
        self.session = session
        self.engine = engine
        self._scan_queue = commands.scan_queue if commands else None
        self._concurrency_config: "ConcurrencyConfig | None" = commands.concurrency_config if commands else None
        if not self._concurrency_config:
            self._concurrency_config = getattr(getattr(engine, "config", None), "concurrency", None)
        self._commands_instance = commands
        self.callback_log_repo = CallbackLogRepository(session)
        self.state_repo = KeyboardStateRepository(session)
        self.handlers: Dict[str, Callable] = {}
        self._register_default_handlers()

    def _get_commands(self) -> "BotCommands":
        if self._commands_instance:
            return self._commands_instance
        commands = bot_commands_module.BotCommands(
            self.session,
            self.engine,
            self._scan_queue,
            self._concurrency_config,
        )
        self._commands_instance = commands
        # Ensure queue reference stays in sync for future lazy initializations
        if not self._scan_queue:
            self._scan_queue = getattr(commands, "scan_queue", None)
        return self._commands_instance

    def _register_default_handlers(self):
        """Register default callback handlers."""
        # Command callbacks
        self.register("cmd_status", self.handle_status)
        self.register("cmd_positions", self.handle_positions)
        self.register("cmd_history", self.handle_history)
        self.register("cmd_stats", self.handle_stats)
        self.register("cmd_settings", self.handle_settings)
        self.register("cmd_help", self.handle_help)
        self.register("cmd_main", self.handle_main_menu)
        self.register("cmd_scan", self.handle_scan_menu)

        # Position callbacks
        self.register_pattern("pos_select_", self.handle_position_select)
        self.register_pattern("pos_details_", self.handle_position_details)
        self.register_pattern("pos_refresh_", self.handle_position_refresh)
        self.register_pattern("pos_close_", self.handle_position_close)

        # Trading control callbacks
        self.register("trading_resume", self.handle_trading_resume)
        self.register("trading_pause", self.handle_trading_pause)
        self.register("trading_scan", self.handle_trading_scan)
        self.register("trading_closeall", self.handle_trading_closeall)
        self.register_pattern("scan_strategy_", self.handle_scan_strategy)

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

    async def handle_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Main callback query handler that routes to specific handlers.

        This method resolves hashed callback_data back to original values
        before routing, ensuring pattern matching and data extraction work
        correctly even when callback_data was truncated due to Telegram's
        64-byte limit.
        """
        query = update.callback_query
        await query.answer()

        raw_callback_data = query.data
        # Resolve hashed callback_data to original value if registered
        callback_data = callback_registry.resolve(raw_callback_data)

        if callback_data != raw_callback_data:
            logger.debug(f"Resolved hashed callback: {raw_callback_data} -> {callback_data}")

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
                    # Store resolved callback_data in context for handlers
                    context.user_data["_resolved_callback"] = callback_data
                    await handler(update, context)
                    return

        # No handler found
        logger.warning(f"No handler found for callback: {callback_data}")
        await query.edit_message_text(f"⚠️ Unknown action: {callback_data}")

    @log_callback(success=True)
    async def handle_status(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle status callback."""
        await self._get_commands().status(update, context)

    @log_callback(success=True)
    async def handle_positions(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle positions callback."""
        await self._get_commands().positions(update, context)

    @log_callback(success=True)
    async def handle_history(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle history callback."""
        await self._get_commands().history(update, context)

    @log_callback(success=True)
    async def handle_stats(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle stats callback."""
        await self._get_commands().stats(update, context)

    @log_callback(success=True)
    async def handle_settings(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle settings callback."""
        await self._get_commands().settings(update, context)

    @log_callback(success=True)
    async def handle_help(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle help callback."""
        await self._get_commands().start(update, context)

    @log_callback(success=True)
    async def handle_main_menu(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle return to main menu."""
        await self._get_commands().show_menu(update, context)

    @log_callback(success=True)
    async def handle_scan_menu(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Show strategy selection for manual scan."""
        query = update.callback_query

        strategies = [
            ("🚀 Pump & Cooldown", "pump_cooldown"),
        ]
        if getattr(getattr(self.engine.config, "order_block_strategy", None), "enabled", False):
            strategies.append(("🧱 Order Block", "order_block"))

        buttons = [[InlineKeyboardButton(label, callback_data=f"scan_strategy_{mode}")] for label, mode in strategies]
        buttons.append([InlineKeyboardButton("🔙 Back", callback_data="cmd_main")])

        keyboard = InlineKeyboardMarkup(buttons)
        await query.edit_message_text(
            "🔍 *Ручной скан*\n\nВыберите стратегию и бот сразу запустит анализ.",
            reply_markup=keyboard,
            parse_mode="Markdown",
        )

    @log_callback(success=True)
    async def handle_scan_strategy(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Execute manual scan for selected strategy."""
        query = update.callback_query
        # Use resolved callback_data from context (handles hashed callbacks)
        callback_data = context.user_data.get("_resolved_callback", query.data)
        strategy_mode = callback_data.replace("scan_strategy_", "", 1)
        alias_map = {"pump_cooldown": "pc", "order_block": "ob"}
        label_map = {
            "pump_cooldown": "Pump & Cooldown",
            "order_block": "Order Block",
        }

        if strategy_mode not in alias_map:
            await query.answer("⚠️ Неизвестная стратегия", show_alert=True)
            return

        await query.edit_message_text(
            f"⏳ Запускаю *{label_map[strategy_mode]}* сканирование...",
            parse_mode="Markdown",
        )

        context.args = [alias_map[strategy_mode]]
        await self._get_commands().scan(update, context)

    @log_callback(success=True)
    async def handle_position_select(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle position selection from list - show action buttons."""
        query = update.callback_query
        # Use resolved callback_data from context (handles hashed callbacks)
        callback_data = context.user_data.get("_resolved_callback", query.data)
        symbol = callback_data.replace("pos_select_", "")

        position = await run_blocking(self.engine.position_manager.get_position_by_symbol, symbol)
        if not position:
            await query.edit_message_text(f"❌ Позиция не найдена: {symbol}")
            return

        pnl = position["unrealized_pnl"]
        if pnl > 0:
            pnl_emoji = "🟢"
        elif pnl < 0:
            pnl_emoji = "🔴"
        else:
            pnl_emoji = "⚪"
        message = f"""
📊 *{position['symbol']}*

💰 Вход: {position['entry_price']:.4f}
📈 Текущая: {position['current_price']:.4f}
🎯 TP: {position['take_profit_price']:.4f}
📊 Плечо: {position['leverage']}x
💵 Маржа: {position['margin']:.2f} USDT
{pnl_emoji} P&L: {position['unrealized_pnl']:.2f} USDT ({position['unrealized_pnl_pct']:.2f}%)

Выберите действие:
"""
        # Build inline keyboard with position action buttons
        builder = KeyboardBuilder(self.session)
        buttons = InlineTemplates.position_actions(symbol)
        buttons.append(InlineTemplates.back_button("cmd_positions"))
        keyboard = builder.create_inline_keyboard(buttons, n_cols=3)

        await query.edit_message_text(message, parse_mode="Markdown", reply_markup=keyboard)

    @log_callback(success=True)
    async def handle_position_details(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle position details callback."""
        query = update.callback_query
        # Use resolved callback_data from context (handles hashed callbacks)
        callback_data = context.user_data.get("_resolved_callback", query.data)
        symbol = callback_data.replace("pos_details_", "")

        position = await run_blocking(self.engine.position_manager.get_position_by_symbol, symbol)
        if not position:
            await query.edit_message_text(f"❌ Позиция не найдена: {symbol}")
            return

        pnl = position["unrealized_pnl"]
        if pnl > 0:
            pnl_emoji = "🟢"
        elif pnl < 0:
            pnl_emoji = "🔴"
        else:
            pnl_emoji = "⚪"
        message = f"""
📊 *Детали позиции: {position['symbol']}*

💰 Цена входа: {position['entry_price']:.4f}
📈 Текущая цена: {position['current_price']:.4f}
🎯 Take Profit: {position['take_profit_price']:.4f}
📊 Плечо: {position['leverage']}x
💵 Маржа: {position['margin']:.2f} USDT
{pnl_emoji} Нереализованный P&L: {position['unrealized_pnl']:.2f} USDT ({position['unrealized_pnl_pct']:.2f}%)
🕒 Открыта: {position['opened_at']}
"""
        # Add back button
        from .keyboard_builder import InlineTemplates, KeyboardBuilder

        builder = KeyboardBuilder(self.session)
        buttons = [InlineTemplates.back_button(f"pos_select_{symbol}")]
        keyboard = builder.create_inline_keyboard(buttons, n_cols=1)

        await query.edit_message_text(message, parse_mode="Markdown", reply_markup=keyboard)

    @log_callback(success=True)
    async def handle_position_refresh(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle position refresh callback."""
        query = update.callback_query
        # Use resolved callback_data from context (handles hashed callbacks)
        callback_data = context.user_data.get("_resolved_callback", query.data)
        # Store resolved data for handle_position_details call
        context.user_data["_resolved_callback"] = callback_data.replace("pos_refresh_", "pos_details_")

        await query.answer("🔄 Refreshing position data...")
        # Trigger position update
        await run_blocking(self.engine.position_manager.update_positions)

        # Show updated details
        await self.handle_position_details(update, context)

    @log_callback(success=True)
    async def handle_position_close(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle position close callback."""
        query = update.callback_query
        # Use resolved callback_data from context (handles hashed callbacks)
        callback_data = context.user_data.get("_resolved_callback", query.data)
        symbol = callback_data.replace("pos_close_", "")

        await query.answer("Закрываю позицию...")

        result = await run_blocking(self.engine.position_manager.close_position_by_symbol, symbol, "manual")

        if result:
            pnl_emoji = "🟢" if result["pnl"] > 0 else "🔴"
            message = f"""
✅ *Позиция закрыта*

*{result['symbol']}*
💰 Вход: {result['entry_price']:.4f}
💰 Выход: {result['exit_price']:.4f}
{pnl_emoji} P&L: {result['pnl']:.2f} USDT ({result['pnl_pct']:.2f}%)
"""
            await query.edit_message_text(message, parse_mode="Markdown")
        else:
            await query.edit_message_text(f"❌ Не удалось закрыть позицию: {symbol}")

    @log_callback(success=True)
    async def handle_trading_resume(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle trading resume callback."""
        query = update.callback_query
        from ..database.repository import BotStatusRepository

        bot_status_repo = BotStatusRepository(self.session)
        await run_blocking(bot_status_repo.set_paused, False)

        await query.edit_message_text("▶️ *Trading resumed*", parse_mode="Markdown")

    @log_callback(success=True)
    async def handle_trading_pause(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle trading pause callback."""
        query = update.callback_query
        from ..database.repository import BotStatusRepository

        bot_status_repo = BotStatusRepository(self.session)
        await run_blocking(bot_status_repo.set_paused, True)

        await query.edit_message_text("⏸️ *Trading paused*", parse_mode="Markdown")

    @log_callback(success=True)
    async def handle_trading_scan(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle manual scan callback."""
        query = update.callback_query
        await query.answer("🔍 Starting market scan...")

        await self._get_commands().scan(update, context)

    @log_callback(success=True)
    async def handle_trading_closeall(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle close all positions callback."""
        query = update.callback_query
        await query.answer("🔄 Closing all positions...")

        result = await run_blocking(self.engine.close_all_positions, "manual")

        message = f"""
✅ *Close All Completed*

📊 Closed positions: {result['positions_closed']}/{result.get('total_positions', 0)}
"""
        await query.edit_message_text(message, parse_mode="Markdown")

    @log_callback(success=True)
    async def handle_confirm(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle confirmation callback."""
        query = update.callback_query
        # Use resolved callback_data from context (handles hashed callbacks)
        callback_data = context.user_data.get("_resolved_callback", query.data)
        # Extract action: confirm_closeall_data
        parts = callback_data.split("_")
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
        # Use resolved callback_data from context (handles hashed callbacks)
        callback_data = context.user_data.get("_resolved_callback", query.data)
        setting_key = callback_data.replace("setting_", "")

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
        # Use resolved callback_data from context (handles hashed callbacks)
        callback_data = context.user_data.get("_resolved_callback", query.data)
        page_num = int(callback_data.split("_")[1])

        await query.answer(f"Loading page {page_num + 1}...")
        # Implementation depends on what's being paginated

    @log_callback(success=True)
    async def handle_noop(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle no-operation callback (for non-interactive buttons)."""
        query = update.callback_query
        await query.answer()
