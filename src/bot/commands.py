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
> *TopShort Trading Bot*

2B><0B8G5A:89 B>@3>2K9 1>B 4;O H>@B-?>78F89 =0 Binance Futures.

*>ABC?=K5 :><0=4K:*
/status - "5:CI89 AB0BCA 8 >B:@KBK5 ?>78F88
/positions - !?8A>: 2A5E >B:@KBKE ?>78F89
/history - AB>@8O ?>A;54=8E 10 A45;>:
/stats - !B0B8AB8:0 B>@3>2;8
/settings - "5:CI85 =0AB@>9:8
/set - 7<5=8BL =0AB@>9:8
/pause - @8>AB0=>28BL B>@3>2;N
/resume - >7>1=>28BL B>@3>2;N
/scan - 0?CAB8BL A:0=8@>20=85 @K=:0 2@CG=CN
/close - 0:@KBL ?>78F8N ?> A8<2>;C
/closeall - 0:@KBL 2A5 ?>78F88
/help - !?@02:0 ?> :><0=40<

>B 02B><0B8G5A:8 A:0=8@C5B @K=>: :064K9 G0A 8 >B:@K205B H>@B-?>78F88 =0 >ABK20NI8E ?0@0E ?>A;5 ?0<?0.
"""
        await update.message.reply_text(welcome_message, parse_mode='Markdown')

    async def status(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /status command."""
        try:
            # Get bot status
            bot_status = self.bot_status_repo.get()
            trading_status = self.engine.get_status()
            risk = trading_status['risk_summary']

            status_emoji = "" if bot_status.is_active and not bot_status.is_paused else "ø"
            status_text = ":B825=" if bot_status.is_active and not bot_status.is_paused else "@8>AB0=>2;5="

            message = f"""
=Ê *!B0BCA 1>B0*

{status_emoji} !B0BCA: {status_text}
=P 0?CI5=: {bot_status.started_at.strftime('%Y-%m-%d %H:%M')}
=È A53> >B:@KB>: {bot_status.total_positions_opened}
=É A53> 70:@KB>: {bot_status.total_positions_closed}
=° 1I89 P&L: {bot_status.total_pnl:.2f} USDT

*"5:CI85 ?>78F88:*
=Í B:@KB>: {risk['current_positions']}/{risk['max_positions']}
=µ 0@60: {risk['current_margin']:.2f}/{risk['max_margin']:.2f} USDT
=Ê #B8;870F8O A;>B>2: {risk['positions_utilization_pct']:.1f}%
=° #B8;870F8O <0@68: {risk['margin_utilization_pct']:.1f}%
"""
            await update.message.reply_text(message, parse_mode='Markdown')

        except Exception as e:
            logger.error(f"Error in status command: {e}")
            await update.message.reply_text(f"H81:0: {e}")

    async def positions(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /positions command."""
        try:
            positions = self.engine.position_manager.get_all_open_positions()

            if not positions:
                await update.message.reply_text("=í 5B >B:@KBKE ?>78F89")
                return

            message = f"=Í *B:@KBK5 ?>78F88 ({len(positions)}):*\n\n"

            for pos in positions:
                pnl_emoji = "=â" if pos['unrealized_pnl'] > 0 else "=4"
                message += f"""
*{pos['symbol']}*
 E>4: {pos['entry_price']:.4f}
 "5:CI0O: {pos['current_price']:.4f}
 TP: {pos['take_profit_price']:.4f}
 Leverage: {pos['leverage']}x
 0@60: {pos['margin']:.2f} USDT
 {pnl_emoji} P&L: {pos['unrealized_pnl']:.2f} USDT ({pos['unrealized_pnl_pct']:.2f}%)

"""

            await update.message.reply_text(message, parse_mode='Markdown')

        except Exception as e:
            logger.error(f"Error in positions command: {e}")
            await update.message.reply_text(f"H81:0: {e}")

    async def history(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /history command."""
        try:
            history = self.history_repo.get_recent(limit=10)

            if not history:
                await update.message.reply_text("=í AB>@8O A45;>: ?CAB0")
                return

            message = f"=Ü *AB>@8O ?>A;54=8E {len(history)} A45;>::*\n\n"

            for trade in history:
                pnl_emoji = "=â" if trade.pnl > 0 else "=4"
                message += f"""
*{trade.symbol}*
 E>4: {trade.entry_price:.4f}
 KE>4: {trade.exit_price:.4f}
 {pnl_emoji} P&L: {trade.pnl:.2f} USDT ({trade.pnl_pct:.2f}%)
 @8G8=0: {trade.close_reason}
 0:@KB0: {trade.closed_at.strftime('%Y-%m-%d %H:%M')}

"""

            await update.message.reply_text(message, parse_mode='Markdown')

        except Exception as e:
            logger.error(f"Error in history command: {e}")
            await update.message.reply_text(f"H81:0: {e}")

    async def stats(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /stats command."""
        try:
            stats = self.history_repo.get_statistics()

            if stats['total_trades'] == 0:
                await update.message.reply_text("=Ê >:0 =5B AB0B8AB8:8")
                return

            win_emoji = "=â" if stats['total_pnl'] > 0 else "=4"

            message = f"""
=Ê *!B0B8AB8:0 B>@3>2;8*

=È A53> A45;>:: {stats['total_trades']}
=â @81K;L=KE: {stats['winning_trades']}
=4 #1KB>G=KE: {stats['losing_trades']}
<¯ 8=@59B: {stats['win_rate']:.2f}%

{win_emoji} 1I89 P&L: {stats['total_pnl']:.2f} USDT
=Ê !@54=89 P&L: {stats['avg_pnl']:.2f} USDT
=È !@54=89 P&L %: {stats['avg_pnl_pct']:.2f}%
"""
            await update.message.reply_text(message, parse_mode='Markdown')

        except Exception as e:
            logger.error(f"Error in stats command: {e}")
            await update.message.reply_text(f"H81:0: {e}")

    async def settings(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /settings command."""
        try:
            all_settings = self.settings_repo.get_all()

            message = "™ *"5:CI85 =0AB@>9:8:*\n\n"

            for setting in all_settings:
                message += f"" *{setting.key}*: {setting.value}\n"

            message += "\n=¡ 7<5=8BL: /set <:;NG> <7=0G5=85>"

            await update.message.reply_text(message, parse_mode='Markdown')

        except Exception as e:
            logger.error(f"Error in settings command: {e}")
            await update.message.reply_text(f"H81:0: {e}")

    async def set_setting(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /set command."""
        try:
            if len(context.args) < 2:
                await update.message.reply_text(
                    "A?>;L7>20=85: /set <:;NG> <7=0G5=85>\n"
                    "@8<5@: /set margin_per_trade 150"
                )
                return

            key = context.args[0]
            value = context.args[1]

            self.settings_repo.set(key, value)

            await update.message.reply_text(f" 0AB@>9:0 {key} = {value}")

        except Exception as e:
            logger.error(f"Error in set command: {e}")
            await update.message.reply_text(f"H81:0: {e}")

    async def pause(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /pause command."""
        try:
            self.bot_status_repo.set_paused(True)
            await update.message.reply_text("ø ">@3>2;O ?@8>AB0=>2;5=0")

        except Exception as e:
            logger.error(f"Error in pause command: {e}")
            await update.message.reply_text(f"H81:0: {e}")

    async def resume(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /resume command."""
        try:
            self.bot_status_repo.set_paused(False)
            await update.message.reply_text("¶ ">@3>2;O 2>7>1=>2;5=0")

        except Exception as e:
            logger.error(f"Error in resume command: {e}")
            await update.message.reply_text(f"H81:0: {e}")

    async def scan(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /scan command."""
        try:
            await update.message.reply_text("= 0?CA:0N A:0=8@>20=85 @K=:0...")

            result = self.engine.execute_scan_and_trade()

            message = f"""
 *!:0=8@>20=85 7025@H5=>*

=Ê 0945=> A83=0;>2: {result['signals_found']}
 B:@KB> ?>78F89: {result['positions_opened']}
"""
            await update.message.reply_text(message, parse_mode='Markdown')

        except Exception as e:
            logger.error(f"Error in scan command: {e}")
            await update.message.reply_text(f"H81:0: {e}")

    async def close(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /close command."""
        try:
            if not context.args:
                await update.message.reply_text("A?>;L7>20=85: /close <A8<2>;>\n@8<5@: /close BTC/USDT:USDT")
                return

            symbol = context.args[0]
            result = self.engine.position_manager.close_position_by_symbol(symbol, 'manual')

            if result:
                pnl_emoji = "=â" if result['pnl'] > 0 else "=4"
                message = f"""
 >78F8O 70:@KB0

*{result['symbol']}*
 E>4: {result['entry_price']:.4f}
 KE>4: {result['exit_price']:.4f}
 {pnl_emoji} P&L: {result['pnl']:.2f} USDT ({result['pnl_pct']:.2f}%)
"""
                await update.message.reply_text(message, parse_mode='Markdown')
            else:
                await update.message.reply_text(f"L 5 C40;>AL 70:@KBL ?>78F8N {symbol}")

        except Exception as e:
            logger.error(f"Error in close command: {e}")
            await update.message.reply_text(f"H81:0: {e}")

    async def closeall(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /closeall command."""
        try:
            await update.message.reply_text("= 0:@K20N 2A5 ?>78F88...")

            result = self.engine.close_all_positions('manual')

            message = f"""
 0:@KB85 7025@H5=>

=Ê 0:@KB> ?>78F89: {result['positions_closed']}/{result.get('total_positions', 0)}
"""
            await update.message.reply_text(message, parse_mode='Markdown')

        except Exception as e:
            logger.error(f"Error in closeall command: {e}")
            await update.message.reply_text(f"H81:0: {e}")
