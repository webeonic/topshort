"""Telegram bot initialization and management."""
import logging
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

from ..config import TelegramConfig
from .commands import BotCommands

logger = logging.getLogger(__name__)


class TelegramBot:
    """Telegram bot manager."""

    def __init__(self, config: TelegramConfig, session, engine):
        self.config = config
        self.session = session
        self.engine = engine
        self.commands = BotCommands(session, engine)
        self.application = None
        self.chat_id = config.chat_id

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

        logger.info("Telegram bot handlers registered")

    async def send_message(self, text: str, parse_mode: str = 'Markdown'):
        """Send message to configured chat."""
        try:
            if self.application and self.chat_id:
                await self.application.bot.send_message(
                    chat_id=self.chat_id,
                    text=text,
                    parse_mode=parse_mode
                )
                logger.debug(f"Sent message to chat {self.chat_id}")
        except Exception as e:
            logger.error(f"Error sending message: {e}")

    async def notify_position_opened(self, position_info: dict):
        """Send notification when position is opened."""
        message = f"""
<• *B:@KB0 =>20O ?>78F8O*

=Í *{position_info['symbol']}*
 E>4: {position_info['entry_price']:.4f}
 TP: {position_info['take_profit_price']:.4f}
 Leverage: {position_info['leverage']}x
 0@60: {position_info['margin']:.2f} USDT
 Order ID: {position_info.get('order_id', 'N/A')}
"""
        await self.send_message(message)

    async def notify_position_closed(self, close_info: dict):
        """Send notification when position is closed."""
        pnl_emoji = "=â" if close_info['pnl'] > 0 else "=4"

        message = f"""
= *>78F8O 70:@KB0*

=Í *{close_info['symbol']}*
 E>4: {close_info['entry_price']:.4f}
 KE>4: {close_info['exit_price']:.4f}
 {pnl_emoji} P&L: {close_info['pnl']:.2f} USDT ({close_info['pnl_pct']:.2f}%)
 @8G8=0: {close_info['reason']}
 ID: {close_info['position_id']}
"""
        await self.send_message(message)

    async def notify_scan_complete(self, scan_result: dict):
        """Send notification when scan is complete."""
        message = f"""
= *!:0=8@>20=85 7025@H5=>*

=Ê 0945=> A83=0;>2: {scan_result['signals_found']}
 B:@KB> ?>78F89: {scan_result['positions_opened']}
"""
        if scan_result.get('positions_opened', 0) > 0:
            message += "\n=Ý >2K5 ?>78F88:\n"
            for pos in scan_result.get('opened_positions', []):
                message += f"" {pos['symbol']} @ {pos['entry_price']:.4f}\n"

        await self.send_message(message)

    async def notify_error(self, error_message: str):
        """Send error notification."""
        message = f"""
L *H81:0*

{error_message}
"""
        await self.send_message(message)

    async def start_polling(self):
        """Start bot polling."""
        logger.info("Starting Telegram bot polling")
        await self.application.run_polling(allowed_updates=Update.ALL_TYPES)

    async def stop(self):
        """Stop bot."""
        logger.info("Stopping Telegram bot")
        if self.application:
            await self.application.stop()
