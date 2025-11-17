"""Telegram bot command handlers."""
import os
import logging
from functools import wraps
from telegram import Update
from telegram.ext import ContextTypes

from ..database.repository import (
    SettingsRepository, TradeHistoryRepository,
    BotStatusRepository, MarketSignalRepository
)
from ..trading.engine import TradingEngine

logger = logging.getLogger(__name__)

# Load authorized users from environment
AUTHORIZED_USERS = set(
    user_id.strip()
    for user_id in os.getenv('TELEGRAM_AUTHORIZED_USERS', '').split(',')
    if user_id.strip()
)


class AuditLogger:
    """Audit logger for security-relevant events."""

    @staticmethod
    def log_security_event(user_id: int, username: str, action: str, details: dict = None):
        """Log security-relevant events."""
        import json
        details_str = json.dumps(details) if details else '{}'
        logger.warning(
            f"SECURITY_EVENT: user_id={user_id}, username={username}, "
            f"action={action}, details={details_str}"
        )


audit = AuditLogger()

# Allowed settings with their types and valid ranges
ALLOWED_SETTINGS = {
    'margin_per_trade': {
        'type': float,
        'min': 1.0,
        'max': 10000.0,
        'description': 'Margin per trade in USDT'
    },
    'max_positions': {
        'type': int,
        'min': 1,
        'max': 50,
        'description': 'Maximum number of simultaneous positions'
    },
    'max_total_margin': {
        'type': float,
        'min': 10.0,
        'max': 100000.0,
        'description': 'Maximum total margin in USDT'
    },
    'default_leverage': {
        'type': int,
        'min': 1,
        'max': 125,
        'description': 'Default leverage for positions'
    },
    'take_profit_pct': {
        'type': float,
        'min': 0.1,
        'max': 50.0,
        'description': 'Take profit percentage'
    },
    'pump_threshold_pct': {
        'type': float,
        'min': 10.0,
        'max': 200.0,
        'description': 'Minimum pump percentage to trigger signal'
    },
    'pump_period_hours_min': {
        'type': int,
        'min': 1,
        'max': 168,
        'description': 'Minimum hours for pump period'
    },
    'pump_period_hours_max': {
        'type': int,
        'min': 1,
        'max': 168,
        'description': 'Maximum hours for pump period'
    },
    'cooldown_period_hours_min': {
        'type': int,
        'min': 1,
        'max': 48,
        'description': 'Minimum hours for cooldown period'
    },
    'cooldown_period_hours_max': {
        'type': int,
        'min': 1,
        'max': 48,
        'description': 'Maximum hours for cooldown period'
    },
    'volume_decrease_threshold_pct': {
        'type': float,
        'min': 0.0,
        'max': 100.0,
        'description': 'Volume decrease threshold percentage'
    }
}


def require_auth(func):
    """Decorator to require authentication for sensitive commands."""
    @wraps(func)
    async def wrapper(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = str(update.effective_user.id)
        username = update.effective_user.username or 'unknown'

        if not AUTHORIZED_USERS or user_id not in AUTHORIZED_USERS:
            logger.warning(
                f"SECURITY: Unauthorized access attempt - "
                f"User ID: {user_id}, Username: @{username}, "
                f"Command: {func.__name__}"
            )
            await update.message.reply_text(
                "❌ *Access Denied*\n\n"
                "You are not authorized to use this command.\n"
                "Contact the administrator if you need access.",
                parse_mode='Markdown'
            )
            return

        logger.info(f"Authorized command: {func.__name__} by user {user_id} (@{username})")
        return await func(self, update, context)

    return wrapper


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

    @require_auth
    async def set_setting(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /set command."""
        try:
            if len(context.args) < 2:
                await update.message.reply_text(
                    "Usage: /set <key> <value>\n"
                    "Example: /set margin_per_trade 150\n\n"
                    "Available settings:\n" +
                    "\n".join(f"  • {k}: {v['description']}" for k, v in ALLOWED_SETTINGS.items())
                )
                return

            key = context.args[0]
            value_str = context.args[1]

            # Validate key
            if key not in ALLOWED_SETTINGS:
                await update.message.reply_text(
                    f"❌ Invalid setting key: *{key}*\n\n"
                    "Available settings:\n" +
                    "\n".join(f"  • {k}" for k in ALLOWED_SETTINGS.keys()),
                    parse_mode='Markdown'
                )
                return

            setting_config = ALLOWED_SETTINGS[key]
            expected_type = setting_config['type']
            min_val = setting_config['min']
            max_val = setting_config['max']

            # Validate type and range
            try:
                typed_value = expected_type(value_str)

                if not (min_val <= typed_value <= max_val):
                    await update.message.reply_text(
                        f"❌ Value out of range for *{key}*\n\n"
                        f"Value must be between {min_val} and {max_val}\n"
                        f"You provided: {typed_value}",
                        parse_mode='Markdown'
                    )
                    return

                # Save validated setting
                self.settings_repo.set(key, str(typed_value), setting_config['description'])

                await update.message.reply_text(
                    f"✅ Setting updated successfully\n\n"
                    f"*{key}* = {typed_value}\n"
                    f"_{setting_config['description']}_",
                    parse_mode='Markdown'
                )

                logger.info(
                    f"Setting updated: {key}={typed_value} by user {update.effective_user.id}"
                )

            except (ValueError, TypeError) as e:
                await update.message.reply_text(
                    f"❌ Invalid value type for *{key}*\n\n"
                    f"Expected: {expected_type.__name__}\n"
                    f"You provided: {value_str}\n"
                    f"Error: {str(e)}",
                    parse_mode='Markdown'
                )

        except Exception as e:
            logger.error(f"Error in set command: {e}")
            await update.message.reply_text(f"❌ Error: {e}")

    @require_auth
    async def pause(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /pause command."""
        try:
            self.bot_status_repo.set_paused(True)
            await update.message.reply_text("⏸️ Trading paused")

        except Exception as e:
            logger.error(f"Error in pause command: {e}")
            await update.message.reply_text(f"❌ Error: {e}")

    @require_auth
    async def resume(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /resume command."""
        try:
            self.bot_status_repo.set_paused(False)
            await update.message.reply_text("▶️ Trading resumed")

        except Exception as e:
            logger.error(f"Error in resume command: {e}")
            await update.message.reply_text(f"❌ Error: {e}")

    @require_auth
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

    @require_auth
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

    @require_auth
    async def closeall(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /closeall command."""
        try:
            # Audit log
            audit.log_security_event(
                update.effective_user.id,
                update.effective_user.username or 'unknown',
                'CLOSE_ALL_POSITIONS',
                {}
            )

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
