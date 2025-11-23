"""Telegram bot initialization and management."""

import asyncio
import logging
from typing import Optional

from telegram import Update
from telegram.ext import Application, CallbackQueryHandler, CommandHandler
from telegram.helpers import escape_markdown

from ..config import ConcurrencyConfig, TelegramConfig
from .callback_handler import CallbackHandler
from .commands import BotCommands
from .keyboard_builder import KeyboardBuilder
from .keyboard_init import init_keyboard_templates
from .scan_queue import ScanQueueManager

logger = logging.getLogger(__name__)


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
        self.keyboard_builder = KeyboardBuilder(session)
        self.application: Optional[Application] = None
        self.chat_id = config.chat_id
        self._stop_event = asyncio.Event()

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

        # Register command handlers
        app.add_handler(CommandHandler("start", self.commands.start))
        app.add_handler(CommandHandler("status", self.commands.status))
        app.add_handler(CommandHandler("positions", self.commands.positions))
        app.add_handler(CommandHandler("history", self.commands.history))
        app.add_handler(CommandHandler("stats", self.commands.stats))
        app.add_handler(CommandHandler("settings", self.commands.settings))
        app.add_handler(CommandHandler("set", self.commands.set_setting))
        app.add_handler(CommandHandler("pause", self.commands.pause))
        app.add_handler(CommandHandler("resume", self.commands.resume))
        app.add_handler(CommandHandler("scan", self.commands.scan))
        app.add_handler(CommandHandler("pairs", self.commands.top_pairs))
        app.add_handler(CommandHandler("top_pairs", self.commands.top_pairs))
        app.add_handler(CommandHandler("close", self.commands.close))
        app.add_handler(CommandHandler("closeall", self.commands.closeall))
        app.add_handler(CommandHandler("help", self.commands.start))
        app.add_handler(CommandHandler("menu", self.commands.show_menu))

        # Register callback query handler for inline keyboards
        app.add_handler(CallbackQueryHandler(self.callback_handler.handle_callback))

        logger.info("Telegram bot handlers registered (commands + callbacks)")

    async def initialize(self):
        """Initialize the telegram application."""
        logger.info("Initializing Telegram application")
        app = self._require_application()
        await app.initialize()
        await app.start()

    async def send_message(self, text: str, parse_mode: str = "Markdown"):
        """Send message to configured chat."""
        try:
            app = self.application
            if app and self.chat_id:
                await app.bot.send_message(chat_id=self.chat_id, text=text, parse_mode=parse_mode)
                logger.debug(f"Sent message to chat {self.chat_id}")
        except Exception as e:
            logger.error(f"Error sending message: {e}")

    async def notify_position_opened(self, position_info: dict):
        """Send notification when position is opened."""
        direction = position_info.get("direction", "").upper() or "N/A"
        symbol = self._escape_md(position_info["symbol"])
        message = f"""
🟢 *New Position Opened*

📊 *{symbol}*
🧭 Direction: {direction}
💰 Entry: {position_info['entry_price']:.4f}
🎯 TP: {position_info['take_profit_price']:.4f}
📈 Leverage: {position_info['leverage']}x
💵 Margin: {position_info['margin']:.2f} USDT
🔖 Order ID: {position_info.get('order_id', 'N/A')}
"""
        await self.send_message(message)

    async def notify_position_closed(self, close_info: dict):
        """Send notification when position is closed."""
        pnl_emoji = "🟢" if close_info["pnl"] > 0 else "🔴"
        symbol = self._escape_md(close_info["symbol"])
        reason = self._escape_md(close_info["reason"])

        message = f"""
🔵 *Position Closed*

📊 *{symbol}*
💰 Entry: {close_info['entry_price']:.4f}
💰 Exit: {close_info['exit_price']:.4f}
{pnl_emoji} P&L: {close_info['pnl']:.2f} USDT ({close_info['pnl_pct']:.2f}%)
📝 Reason: {reason}
🔖 ID: {close_info['position_id']}
"""
        await self.send_message(message)

    async def notify_scan_complete(self, scan_result: dict):
        """Send notification when scan is complete."""
        message = f"""
🔍 *Scan Completed*

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
                message += f"  {self._escape_md(pos['symbol'])} @ {pos['entry_price']:.4f}\n"

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
