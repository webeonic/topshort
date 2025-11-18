"""Telegram bot initialization and management."""

import asyncio
import logging

from telegram import Update
from telegram.ext import Application, CallbackQueryHandler, CommandHandler

from ..config import TelegramConfig
from .callback_handler import CallbackHandler
from .commands import BotCommands
from .keyboard_builder import KeyboardBuilder
from .keyboard_init import init_keyboard_templates

logger = logging.getLogger(__name__)


class TelegramBot:
    """Telegram bot manager."""

    def __init__(self, config: TelegramConfig, session, engine):
        self.config = config
        self.session = session
        self.engine = engine
        self.commands = BotCommands(session, engine)
        self.callback_handler = CallbackHandler(session, engine)
        self.keyboard_builder = KeyboardBuilder(session)
        self.application = None
        self.chat_id = config.chat_id
        self._stop_event = asyncio.Event()

        # Initialize keyboard templates
        init_keyboard_templates(session)

    def setup(self):
        """Setup bot application and handlers."""
        logger.info("Setting up Telegram bot")

        # Create application
        self.application = Application.builder().token(self.config.bot_token).build()

        # Register command handlers
        self.application.add_handler(CommandHandler("start", self.commands.start))
        self.application.add_handler(CommandHandler("status", self.commands.status))
        self.application.add_handler(CommandHandler("positions", self.commands.positions))
        self.application.add_handler(CommandHandler("history", self.commands.history))
        self.application.add_handler(CommandHandler("stats", self.commands.stats))
        self.application.add_handler(CommandHandler("settings", self.commands.settings))
        self.application.add_handler(CommandHandler("set", self.commands.set_setting))
        self.application.add_handler(CommandHandler("pause", self.commands.pause))
        self.application.add_handler(CommandHandler("resume", self.commands.resume))
        self.application.add_handler(CommandHandler("scan", self.commands.scan))
        self.application.add_handler(CommandHandler("close", self.commands.close))
        self.application.add_handler(CommandHandler("closeall", self.commands.closeall))
        self.application.add_handler(CommandHandler("help", self.commands.start))
        self.application.add_handler(CommandHandler("menu", self.commands.show_menu))

        # Register callback query handler for inline keyboards
        self.application.add_handler(CallbackQueryHandler(self.callback_handler.handle_callback))

        logger.info("Telegram bot handlers registered (commands + callbacks)")

    async def initialize(self):
        """Initialize the telegram application."""
        logger.info("Initializing Telegram application")
        await self.application.initialize()
        await self.application.start()

    async def send_message(self, text: str, parse_mode: str = "Markdown"):
        """Send message to configured chat."""
        try:
            if self.application and self.chat_id:
                await self.application.bot.send_message(chat_id=self.chat_id, text=text, parse_mode=parse_mode)
                logger.debug(f"Sent message to chat {self.chat_id}")
        except Exception as e:
            logger.error(f"Error sending message: {e}")

    async def notify_position_opened(self, position_info: dict):
        """Send notification when position is opened."""
        message = f"""
🟢 *New Position Opened*

📊 *{position_info['symbol']}*
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

        message = f"""
🔵 *Position Closed*

📊 *{close_info['symbol']}*
💰 Entry: {close_info['entry_price']:.4f}
💰 Exit: {close_info['exit_price']:.4f}
{pnl_emoji} P&L: {close_info['pnl']:.2f} USDT ({close_info['pnl_pct']:.2f}%)
📝 Reason: {close_info['reason']}
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
        if scan_result.get("positions_opened", 0) > 0:
            message += "\n🟢 New positions:\n"
            for pos in scan_result.get("opened_positions", []):
                message += f"  {pos['symbol']} @ {pos['entry_price']:.4f}\n"

        await self.send_message(message)

    async def notify_error(self, error_message: str):
        """Send error notification."""
        message = f"""
❌ *Error*

{error_message}
"""
        await self.send_message(message)

    async def start_polling(self):
        """Start bot polling."""
        logger.info("Starting Telegram bot polling")
        # Start the updater to begin polling
        await self.application.updater.start_polling(allowed_updates=Update.ALL_TYPES)

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
