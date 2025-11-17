"""Telegram bot command handlers."""
import logging
from telegram import Update
from telegram.ext import ContextTypes

from ..database.repository import (
    SettingsRepository, TradeHistoryRepository,
    BotStatusRepository, MarketSignalRepository
)
from ..trading.engine import TradingEngine

logger = logging.getLogger(__name__)


class BotCommands:
    """Telegram bot command handlers."""

    def __init__(self, session, engine: TradingEngine):
        self.session = session
        self.engine = engine
        self.settings_repo = SettingsRepository(session)
        self.history_repo = TradeHistoryRepository(session)
        self.bot_status_repo = BotStatusRepository(session)
        self.signal_repo = MarketSignalRepository(session)

    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /start command."""
        welcome_message = """
🤖 *TopShort Trading Bot*

Automatic trading bot for short positions on Binance Futures.

*Available commands:*
/status - Current status and open positions
/positions - List all open positions
/history - History of last 10 trades
/stats - Trading statistics
/settings - Current settings
/set - Change settings
/pause - Pause trading
/resume - Resume trading
/scan - Start market scan manually
/close - Close position by symbol
/closeall - Close all positions
/help - Help with commands

The bot automatically scans the market every hour and opens short positions on cooling pairs after pump.
"""
        await update.message.reply_text(welcome_message, parse_mode='Markdown')

    async def status(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /status command."""
        try:
            # Get bot status
            bot_status = self.bot_status_repo.get()
            trading_status = self.engine.get_status()
            risk = trading_status['risk_summary']

            status_emoji = "🟢" if bot_status.is_active and not bot_status.is_paused else "🔴"
            status_text = "Active" if bot_status.is_active and not bot_status.is_paused else "Paused"

            message = f"""
📊 *Bot Status*

{status_emoji} Status: {status_text}
🚀 Started: {bot_status.started_at.strftime('%Y-%m-%d %H:%M')}
📈 Total opened: {bot_status.total_positions_opened}
📉 Total closed: {bot_status.total_positions_closed}
💰 Total P&L: {bot_status.total_pnl:.2f} USDT

*Current positions:*
📊 Open: {risk['current_positions']}/{risk['max_positions']}
💵 Margin: {risk['current_margin']:.2f}/{risk['max_margin']:.2f} USDT
📈 Slots utilization: {risk['positions_utilization_pct']:.1f}%
💸 Margin utilization: {risk['margin_utilization_pct']:.1f}%
"""
            await update.message.reply_text(message, parse_mode='Markdown')

        except Exception as e:
            logger.error(f"Error in status command: {e}")
            await update.message.reply_text(f"❌ Error: {e}")

    async def positions(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /positions command."""
        try:
            positions = self.engine.position_manager.get_all_open_positions()

            if not positions:
                await update.message.reply_text("📭 No open positions")
                return

            message = f"📊 *Open positions ({len(positions)}):*\n\n"

            for pos in positions:
                pnl_emoji = "🟢" if pos['unrealized_pnl'] > 0 else "🔴"
                message += f"""
*{pos['symbol']}*
💰 Entry: {pos['entry_price']:.4f}
📈 Current: {pos['current_price']:.4f}
🎯 TP: {pos['take_profit_price']:.4f}
📊 Leverage: {pos['leverage']}x
💵 Margin: {pos['margin']:.2f} USDT
{pnl_emoji} P&L: {pos['unrealized_pnl']:.2f} USDT ({pos['unrealized_pnl_pct']:.2f}%)

"""

            await update.message.reply_text(message, parse_mode='Markdown')

        except Exception as e:
            logger.error(f"Error in positions command: {e}")
            await update.message.reply_text(f"❌ Error: {e}")

    async def history(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /history command."""
        try:
            history = self.history_repo.get_recent(limit=10)

            if not history:
                await update.message.reply_text("📭 Trade history is empty")
                return

            message = f"📜 *History of last {len(history)} trades:*\n\n"

            for trade in history:
                pnl_emoji = "🟢" if trade.pnl > 0 else "🔴"
                message += f"""
*{trade.symbol}*
💰 Entry: {trade.entry_price:.4f}
💰 Exit: {trade.exit_price:.4f}
{pnl_emoji} P&L: {trade.pnl:.2f} USDT ({trade.pnl_pct:.2f}%)
📝 Reason: {trade.close_reason}
🕒 Closed: {trade.closed_at.strftime('%Y-%m-%d %H:%M')}

"""

            await update.message.reply_text(message, parse_mode='Markdown')

        except Exception as e:
            logger.error(f"Error in history command: {e}")
            await update.message.reply_text(f"❌ Error: {e}")

    async def stats(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /stats command."""
        try:
            stats = self.history_repo.get_statistics()

            if stats['total_trades'] == 0:
                await update.message.reply_text("📭 No statistics yet")
                return

            win_emoji = "🟢" if stats['total_pnl'] > 0 else "🔴"

            message = f"""
📊 *Trading Statistics*

📈 Total trades: {stats['total_trades']}
🟢 Profitable: {stats['winning_trades']}
🔴 Losing: {stats['losing_trades']}
📊 Win rate: {stats['win_rate']:.2f}%

{win_emoji} Total P&L: {stats['total_pnl']:.2f} USDT
💰 Average P&L: {stats['avg_pnl']:.2f} USDT
📊 Average P&L %: {stats['avg_pnl_pct']:.2f}%
"""
            await update.message.reply_text(message, parse_mode='Markdown')

        except Exception as e:
            logger.error(f"Error in stats command: {e}")
            await update.message.reply_text(f"❌ Error: {e}")

    async def settings(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /settings command."""
        try:
            all_settings = self.settings_repo.get_all()

            message = "⚙️ *Current settings:*\n\n"

            for setting in all_settings:
                message += f"  *{setting.key}*: {setting.value}\n"

            message += "\n💡 To change: /set <key> <value>"

            await update.message.reply_text(message, parse_mode='Markdown')

        except Exception as e:
            logger.error(f"Error in settings command: {e}")
            await update.message.reply_text(f"❌ Error: {e}")

    async def set_setting(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /set command."""
        try:
            if len(context.args) < 2:
                await update.message.reply_text(
                    "Usage: /set <key> <value>\n"
                    "Example: /set margin_per_trade 150"
                )
                return

            key = context.args[0]
            value = context.args[1]

            self.settings_repo.set(key, value)

            await update.message.reply_text(f"✅ Setting {key} = {value}")

        except Exception as e:
            logger.error(f"Error in set command: {e}")
            await update.message.reply_text(f"❌ Error: {e}")

    async def pause(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /pause command."""
        try:
            self.bot_status_repo.set_paused(True)
            await update.message.reply_text("⏸️ Trading paused")

        except Exception as e:
            logger.error(f"Error in pause command: {e}")
            await update.message.reply_text(f"❌ Error: {e}")

    async def resume(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /resume command."""
        try:
            self.bot_status_repo.set_paused(False)
            await update.message.reply_text("▶️ Trading resumed")

        except Exception as e:
            logger.error(f"Error in resume command: {e}")
            await update.message.reply_text(f"❌ Error: {e}")

    async def scan(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /scan command."""
        try:
            await update.message.reply_text("🔍 Starting market scan...")

            result = self.engine.execute_scan_and_trade()

            message = f"""
✅ *Scan completed*

📊 Signals found: {result['signals_found']}
✅ Positions opened: {result['positions_opened']}
"""
            await update.message.reply_text(message, parse_mode='Markdown')

        except Exception as e:
            logger.error(f"Error in scan command: {e}")
            await update.message.reply_text(f"❌ Error: {e}")

    async def close(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /close command."""
        try:
            if not context.args:
                await update.message.reply_text("Usage: /close <symbol>\nExample: /close BTC/USDT:USDT")
                return

            symbol = context.args[0]
            result = self.engine.position_manager.close_position_by_symbol(symbol, 'manual')

            if result:
                pnl_emoji = "🟢" if result['pnl'] > 0 else "🔴"
                message = f"""
✅ Position closed

*{result['symbol']}*
💰 Entry: {result['entry_price']:.4f}
💰 Exit: {result['exit_price']:.4f}
{pnl_emoji} P&L: {result['pnl']:.2f} USDT ({result['pnl_pct']:.2f}%)
"""
                await update.message.reply_text(message, parse_mode='Markdown')
            else:
                await update.message.reply_text(f"❌ Failed to close position {symbol}")

        except Exception as e:
            logger.error(f"Error in close command: {e}")
            await update.message.reply_text(f"❌ Error: {e}")

    async def closeall(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /closeall command."""
        try:
            await update.message.reply_text("🔄 Closing all positions...")

            result = self.engine.close_all_positions('manual')

            message = f"""
✅ Closing completed

📊 Closed positions: {result['positions_closed']}/{result.get('total_positions', 0)}
"""
            await update.message.reply_text(message, parse_mode='Markdown')

        except Exception as e:
            logger.error(f"Error in closeall command: {e}")
            await update.message.reply_text(f"❌ Error: {e}")
