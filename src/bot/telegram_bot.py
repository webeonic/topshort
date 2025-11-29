"""Telegram bot initialization and management."""

import asyncio
import logging
import time
from typing import Optional

from telegram import Update
from telegram.ext import Application, CallbackQueryHandler, CommandHandler, filters
from telegram.helpers import escape_markdown

from ..config import ConcurrencyConfig, TelegramConfig
from .callback_handler import CallbackHandler
from .commands import BotCommands, is_user_authorized
from .keyboard_builder import KeyboardBuilder, PersistentMenu
from .keyboard_init import init_keyboard_templates
from .menu_handler import MenuButtonHandler
from .scan_queue import ScanQueueManager

logger = logging.getLogger(__name__)

# Rate limiting constants for Telegram API
# Telegram allows ~30 messages per second, we use conservative limits
RATE_LIMIT_MESSAGES = 20  # Max messages per window
RATE_LIMIT_WINDOW_SECONDS = 1.0  # Window size in seconds


class AuthorizedUserFilter(filters.MessageFilter):
    """Filter that only allows messages from authorized users.

    This filter checks both username and user_id for authorization.
    Users not in AUTHORIZED_USERNAMES or AUTHORIZED_USERS will be blocked.
    """

    def filter(self, message) -> bool:
        """Check if message sender is authorized.

        Args:
            message: Telegram message object

        Returns:
            True if user is authorized, False otherwise
        """
        if not message or not message.from_user:
            return False
        return is_user_authorized(message.from_user)


# Global filter instance for authorized users
AUTHORIZED_USER_FILTER = AuthorizedUserFilter()


class TelegramBot:
    """Telegram bot manager."""

    def __init__(
        self,
        config: TelegramConfig,
        session,
        engine,
        concurrency_config: ConcurrencyConfig | None = None,
    ):
        self.config = config
        self.session = session
        self.engine = engine
        self.concurrency_config = concurrency_config

        queue_size = concurrency_config.scan_queue_per_strategy if concurrency_config else 3
        worker_delay = concurrency_config.scan_worker_delay_seconds if concurrency_config else 0.25

        self.scan_queue = ScanQueueManager(max_queue_size=queue_size, worker_delay_seconds=worker_delay)
        self.commands = BotCommands(session, engine, self.scan_queue, concurrency_config)
        self.callback_handler = CallbackHandler(session, engine, self.commands)
        self.menu_handler = MenuButtonHandler(self.commands)
        self.keyboard_builder = KeyboardBuilder(session)
        self.application: Optional[Application] = None
        self.chat_id = config.chat_id
        self._stop_event = asyncio.Event()

        # Rate limiting state for send_message
        self._message_timestamps: list[float] = []
        self._rate_limit_lock = asyncio.Lock()

        # Initialize keyboard templates
        init_keyboard_templates(session)

    @staticmethod
    def _escape_md(value: object) -> str:
        """Escape user content for Markdown parse mode."""
        return escape_markdown(str(value), version=1)

    def setup(self):
        """Setup bot application and handlers."""
        logger.info("Setting up Telegram bot")

        # Create application
        app = Application.builder().token(self.config.bot_token).build()
        self.application = app

        # Register command handlers with global authorization filter
        # All commands require user to be in AUTHORIZED_USERNAMES or AUTHORIZED_USERS
        auth_filter = AUTHORIZED_USER_FILTER
        app.add_handler(CommandHandler("start", self.commands.start, filters=auth_filter))
        app.add_handler(CommandHandler("status", self.commands.status, filters=auth_filter))
        app.add_handler(CommandHandler("positions", self.commands.positions, filters=auth_filter))
        app.add_handler(CommandHandler("history", self.commands.history, filters=auth_filter))
        app.add_handler(CommandHandler("stats", self.commands.stats, filters=auth_filter))
        app.add_handler(CommandHandler("settings", self.commands.settings, filters=auth_filter))
        app.add_handler(CommandHandler("set", self.commands.set_setting, filters=auth_filter))
        app.add_handler(CommandHandler("pause", self.commands.pause, filters=auth_filter))
        app.add_handler(CommandHandler("resume", self.commands.resume, filters=auth_filter))
        app.add_handler(CommandHandler("scan", self.commands.scan, filters=auth_filter))
        app.add_handler(CommandHandler("pairs", self.commands.top_pairs, filters=auth_filter))
        app.add_handler(CommandHandler("top_pairs", self.commands.top_pairs, filters=auth_filter))
        app.add_handler(CommandHandler("close", self.commands.close, filters=auth_filter))
        app.add_handler(CommandHandler("closeall", self.commands.closeall, filters=auth_filter))
        app.add_handler(CommandHandler("help", self.commands.start, filters=auth_filter))
        app.add_handler(CommandHandler("menu", self.commands.show_menu, filters=auth_filter))

        # Register callback query handler for inline keyboards
        app.add_handler(CallbackQueryHandler(self.callback_handler.handle_callback))

        # Register message handler for persistent menu buttons
        app.add_handler(self.menu_handler.get_message_handler())

        logger.info("Telegram bot handlers registered (commands + callbacks + menu buttons)")

    async def initialize(self):
        """Initialize the telegram application."""
        logger.info("Initializing Telegram application")
        app = self._require_application()
        await app.initialize()
        await app.start()

    async def _wait_for_rate_limit(self) -> None:
        """Wait if rate limit would be exceeded."""
        async with self._rate_limit_lock:
            now = time.monotonic()
            # Remove timestamps outside the window
            window_start = now - RATE_LIMIT_WINDOW_SECONDS
            self._message_timestamps = [ts for ts in self._message_timestamps if ts > window_start]

            # If at limit, wait until oldest timestamp exits window
            if len(self._message_timestamps) >= RATE_LIMIT_MESSAGES:
                oldest = self._message_timestamps[0]
                wait_time = (oldest + RATE_LIMIT_WINDOW_SECONDS) - now
                if wait_time > 0:
                    logger.debug(f"Rate limit reached, waiting {wait_time:.2f}s")
                    await asyncio.sleep(wait_time)
                    # Clean up after waiting
                    now = time.monotonic()
                    window_start = now - RATE_LIMIT_WINDOW_SECONDS
                    self._message_timestamps = [ts for ts in self._message_timestamps if ts > window_start]

            # Record this message timestamp
            self._message_timestamps.append(now)

    async def send_message(self, text: str, parse_mode: str = "Markdown"):
        """Send message to configured chat with rate limiting."""
        try:
            app = self.application
            if app and self.chat_id:
                await self._wait_for_rate_limit()
                await app.bot.send_message(chat_id=self.chat_id, text=text, parse_mode=parse_mode)
                logger.debug(f"Sent message to chat {self.chat_id}")
        except Exception as e:
            logger.error(f"Error sending message: {e}")

    def _format_strategy_label(self, strategy: str | None) -> str:
        """Format strategy name for display."""
        if not strategy:
            return "N/A"
        labels = {
            "pump_cooldown": "Pump & Cooldown",
            "order_block": "Order Block",
        }
        return labels.get(strategy, strategy)

    async def notify_position_opened(self, position_info: dict):
        """Send notification when position is opened."""
        direction = position_info.get("direction", "").upper() or "N/A"
        symbol = self._escape_md(position_info["symbol"])
        order_id = self._escape_md(position_info.get("order_id", "N/A"))
        strategy = self._format_strategy_label(position_info.get("strategy"))
        message = f"""
🟢 *New Position Opened*

📊 *{symbol}*
🧭 Direction: {direction}
🎲 Strategy: {strategy}
💰 Entry: {position_info['entry_price']:.4f}
🎯 TP: {position_info['take_profit_price']:.4f}
📈 Leverage: {position_info['leverage']}x
💵 Margin: {position_info['margin']:.2f} USDT
🔖 Order ID: {order_id}
"""
        await self.send_message(message)

    async def notify_position_closed(self, close_info: dict):
        """Send notification when position is closed."""
        pnl_emoji = "🟢" if close_info["pnl"] > 0 else "🔴"
        symbol = self._escape_md(close_info["symbol"])
        reason = self._escape_md(close_info["reason"])
        strategy = self._format_strategy_label(close_info.get("strategy"))

        position_id = self._escape_md(close_info["position_id"])
        message = f"""
🔵 *Position Closed*

📊 *{symbol}*
🎲 Strategy: {strategy}
💰 Entry: {close_info['entry_price']:.4f}
💰 Exit: {close_info['exit_price']:.4f}
{pnl_emoji} P&L: {close_info['pnl']:.2f} USDT ({close_info['pnl_pct']:.2f}%)
📝 Reason: {reason}
🔖 ID: {position_id}
"""
        await self.send_message(message)

    async def notify_scan_complete(self, scan_result: dict):
        """Send notification when scan is complete."""
        strategy = self._format_strategy_label(scan_result.get("strategy_mode"))
        message = f"""
🔍 *Scan Completed*

🎲 Strategy: {strategy}
📊 Signals found: {scan_result['signals_found']}
✅ Positions opened: {scan_result['positions_opened']}
"""
        # Add signal symbols if signals were found
        if scan_result.get("signals_found", 0) > 0 and scan_result.get("signals"):
            message += "\n📈 Signal pairs:\n"
            for signal in scan_result["signals"]:
                message += f"  • {self._escape_md(signal['symbol'])}\n"

        if scan_result.get("positions_opened", 0) > 0:
            message += "\n🟢 New positions:\n"
            for pos in scan_result.get("opened_positions", []):
                pos_strategy = self._format_strategy_label(pos.get("strategy"))
                message += f"  {self._escape_md(pos['symbol'])} @ {pos['entry_price']:.4f} ({pos_strategy})\n"

        await self.send_message(message)

    async def notify_error(self, error_message: str):
        """Send error notification."""
        escaped_error = self._escape_md(error_message)
        message = f"""
❌ *Error*

{escaped_error}
"""
        await self.send_message(message)

    async def start_polling(self):
        """Start bot polling."""
        logger.info("Starting Telegram bot polling")
        # Start the updater to begin polling
        app = self._require_application()
        await app.updater.start_polling(allowed_updates=Update.ALL_TYPES)

        # Keep the bot running until stop event is set
        logger.info("Bot is now polling for updates")
        await self._stop_event.wait()

    async def stop(self):
        """Stop bot."""
        logger.info("Stopping Telegram bot")
        if self.application:
            try:
                # Signal the stop event to exit the polling wait
                self._stop_event.set()

                # Stop the updater first
                if self.application.updater.running:
                    await self.application.updater.stop()
                # Then stop and shutdown the application
                await self.application.stop()
                await self.application.shutdown()
            except Exception as e:
                logger.error(f"Error stopping bot: {e}")

    def _require_application(self) -> Application:
        if not self.application:
            raise RuntimeError("Telegram application is not initialized. Call setup() first.")
        return self.application
