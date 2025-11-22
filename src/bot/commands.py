"""Telegram bot command handlers."""

import asyncio
import logging
import os
import uuid
from contextlib import suppress
from functools import wraps
from typing import Dict, TypedDict

from telegram import Update
from telegram.ext import ContextTypes

from ..config import ConcurrencyConfig
from ..database.repository import (
    BotStatusRepository,
    MarketSignalRepository,
    ScanProgressRepository,
    SettingsRepository,
    TradeHistoryRepository,
)
from ..trading.engine import TradingEngine
from ..utils.async_executor import run_blocking
from .keyboard_builder import KeyboardBuilder, KeyboardTemplates
from .scan_queue import ScanQueueFullError, ScanQueueItem, ScanQueueManager

logger = logging.getLogger(__name__)

# Load authorized users from environment
AUTHORIZED_USERS = set(user_id.strip() for user_id in os.getenv("TELEGRAM_AUTHORIZED_USERS", "").split(",") if user_id.strip())


class AuditLogger:
    """Audit logger for security-relevant events."""

    @staticmethod
    def log_security_event(user_id: int, username: str, action: str, details: dict = None):
        """Log security-relevant events."""
        import json

        details_str = json.dumps(details) if details else "{}"
        logger.warning(f"SECURITY_EVENT: user_id={user_id}, username={username}, " f"action={action}, details={details_str}")


audit = AuditLogger()

# Allowed settings with their types and valid ranges
NumericCaster = type[int] | type[float]


class SettingConfig(TypedDict):
    type: NumericCaster
    min: float
    max: float
    description: str


ALLOWED_SETTINGS: Dict[str, SettingConfig] = {
    "margin_per_trade": {"type": float, "min": 1.0, "max": 10000.0, "description": "Margin per trade in USDT"},
    "max_positions": {"type": int, "min": 1, "max": 50, "description": "Maximum number of simultaneous positions"},
    "max_total_margin": {"type": float, "min": 10.0, "max": 100000.0, "description": "Maximum total margin in USDT"},
    "default_leverage": {"type": int, "min": 1, "max": 125, "description": "Default leverage for positions"},
    "take_profit_pct": {"type": float, "min": 0.1, "max": 50.0, "description": "Take profit percentage"},
    "pump_threshold_pct": {
        "type": float,
        "min": 10.0,
        "max": 200.0,
        "description": "Minimum pump percentage to trigger signal",
    },
    "pump_period_hours_min": {"type": int, "min": 1, "max": 168, "description": "Minimum hours for pump period"},
    "pump_period_hours_max": {"type": int, "min": 1, "max": 168, "description": "Maximum hours for pump period"},
    "cooldown_period_hours_min": {"type": int, "min": 1, "max": 48, "description": "Minimum hours for cooldown period"},
    "cooldown_period_hours_max": {"type": int, "min": 1, "max": 48, "description": "Maximum hours for cooldown period"},
    "volume_decrease_threshold_pct": {
        "type": float,
        "min": 0.0,
        "max": 100.0,
        "description": "Volume decrease threshold percentage",
    },
}


def require_auth(func):
    """Decorator to require authentication for sensitive commands."""

    @wraps(func)
    async def wrapper(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = str(update.effective_user.id)
        username = update.effective_user.username or "unknown"

        if not AUTHORIZED_USERS or user_id not in AUTHORIZED_USERS:
            logger.warning(
                f"SECURITY: Unauthorized access attempt - "
                f"User ID: {user_id}, Username: @{username}, "
                f"Command: {func.__name__}"
            )
            await update.effective_message.reply_text(
                "❌ *Access Denied*\n\n"
                "You are not authorized to use this command.\n"
                "Contact the administrator if you need access.",
                parse_mode="Markdown",
            )
            return

        logger.info(f"Authorized command: {func.__name__} by user {user_id} (@{username})")
        return await func(self, update, context)

    return wrapper


class BotCommands:
    """Telegram bot command handlers."""

    def __init__(
        self,
        session,
        engine: TradingEngine,
        scan_queue: ScanQueueManager | None = None,
        concurrency_config: ConcurrencyConfig | None = None,
    ):
        self.session = session
        self.engine = engine
        self.settings_repo = SettingsRepository(session)
        self.history_repo = TradeHistoryRepository(session)
        self.bot_status_repo = BotStatusRepository(session)
        self.signal_repo = MarketSignalRepository(session)
        self.scan_progress_repo = ScanProgressRepository(session)
        self.keyboard_builder = KeyboardBuilder(session)
        self.scan_queue = scan_queue
        self.concurrency_config = concurrency_config

    async def _run_blocking(self, func, *args, **kwargs):
        """Execute blocking callable in thread pool."""
        return await run_blocking(func, *args, **kwargs)

    def _resolve_strategy_mode(self, context: ContextTypes.DEFAULT_TYPE) -> str:
        allowed_modes = {"pump_cooldown", "order_block"}
        default_mode = self.engine.config.strategy_runtime.default_manual_strategy
        strategy_mode = default_mode if default_mode in allowed_modes else "pump_cooldown"
        if context.args:
            strategy_arg = context.args[0].lower()
            if strategy_arg in {"ob", "orderblock", "order_block", "smc"}:
                strategy_mode = "order_block"
            elif strategy_arg in {"pump", "cooldown", "pc"}:
                strategy_mode = "pump_cooldown"
        return strategy_mode

    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /start command."""
        welcome_message = """
🤖 *TopShort Trading Bot*

Automatic trading bot for short positions on Binance Futures.

*Available commands:*
/menu - Show interactive menu
/status - Current status and open positions
/positions - List all open positions
/history - History of last 10 trades
/stats - Trading statistics
/settings - Current settings
/set - Change settings
/pause - Pause trading
/resume - Resume trading
/scan - Start market scan manually (`/scan pc` или `/scan ob`)
/pairs - Show top pairs universe
/close - Close position by symbol
/closeall - Close all positions
/help - Help with commands

The bot automatically scans the market every hour and opens short positions on cooling pairs after pump.

💡 *Tip:* Use /menu for interactive buttons!
"""
        # Try to use keyboard from template, fallback to simple message
        keyboard = self.keyboard_builder.build_inline_keyboard_from_template("main_menu")
        if keyboard:
            await update.effective_message.reply_text(welcome_message, parse_mode="Markdown", reply_markup=keyboard)
        else:
            await update.effective_message.reply_text(welcome_message, parse_mode="Markdown")

    async def status(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /status command."""
        try:
            # Get bot status
            bot_status = await self._run_blocking(self.bot_status_repo.get)
            trading_status = await self._run_blocking(self.engine.get_status)
            risk = trading_status["risk_summary"]

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
            await update.effective_message.reply_text(message, parse_mode="Markdown")

        except Exception as e:
            logger.error(f"Error in status command: {e}")
            await update.effective_message.reply_text(f"❌ Error: {e}")

    async def positions(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /positions command."""
        try:
            positions = await self._run_blocking(self.engine.position_manager.get_all_open_positions)

            if not positions:
                await update.effective_message.reply_text("📭 No open positions")
                return

            message = f"📊 *Open positions ({len(positions)}):*\n\n"

            for pos in positions:
                pnl_emoji = "🟢" if pos["unrealized_pnl"] > 0 else "🔴"
                message += f"""
*{pos['symbol']}*
🧭 Side: {pos.get('side', 'short').upper()}
💰 Entry: {pos['entry_price']:.4f}
📈 Current: {pos['current_price']:.4f}
🎯 TP: {pos['take_profit_price']:.4f}
🛑 SL: {pos.get('stop_loss_price', 0) or '—'}
📊 Leverage: {pos['leverage']}x
💵 Margin: {pos['margin']:.2f} USDT
{pnl_emoji} P&L: {pos['unrealized_pnl']:.2f} USDT ({pos['unrealized_pnl_pct']:.2f}%)

"""

            await update.effective_message.reply_text(message, parse_mode="Markdown")

        except Exception as e:
            logger.error(f"Error in positions command: {e}")
            await update.effective_message.reply_text(f"❌ Error: {e}")

    async def history(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /history command."""
        try:
            history = await self._run_blocking(lambda: self.history_repo.get_recent(limit=10))

            if not history:
                await update.effective_message.reply_text("📭 Trade history is empty")
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

            await update.effective_message.reply_text(message, parse_mode="Markdown")

        except Exception as e:
            logger.error(f"Error in history command: {e}")
            await update.effective_message.reply_text(f"❌ Error: {e}")

    async def stats(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /stats command."""
        try:
            stats = await self._run_blocking(self.history_repo.get_statistics)

            if stats["total_trades"] == 0:
                await update.effective_message.reply_text("📭 No statistics yet")
                return

            win_emoji = "🟢" if stats["total_pnl"] > 0 else "🔴"

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
            await update.effective_message.reply_text(message, parse_mode="Markdown")

        except Exception as e:
            logger.error(f"Error in stats command: {e}")
            await update.effective_message.reply_text(f"❌ Error: {e}")

    async def top_pairs(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /pairs command to show current trading universe."""
        try:
            if not getattr(self.engine, "top_pairs_service", None):
                await update.effective_message.reply_text("⚠️ Top pairs service is not available")
                return

            force_refresh = bool(context.args and context.args[0].lower() in {"refresh", "update"})
            if force_refresh:
                pairs = await self._run_blocking(self.engine.top_pairs_service.refresh)
            else:
                pairs = await self._run_blocking(self.engine.top_pairs_service.get_pairs)

            meta = await self._run_blocking(self.engine.top_pairs_service.get_metadata)
            if not pairs:
                await update.effective_message.reply_text("📭 No pairs available yet, please try again later.")
                return

            max_preview = 25
            preview = pairs[:max_preview]
            remaining = len(pairs) - len(preview)

            header = (
                f"🏆 *Top {len(pairs)} USDT pairs*\n"
                f"Source: {meta.get('source', 'n/a')} ({meta.get('last_updated', 'unknown')})\n"
            )
            body = "\n".join(f"{idx + 1}. `{symbol}`" for idx, symbol in enumerate(preview))
            if remaining > 0:
                body += f"\n...and {remaining} more"

            footer = ""
            if force_refresh:
                footer = "\n🔄 Cache refreshed on demand."
            elif meta.get("source") == "fallback":
                footer = "\n⚠️ Currently using fallback list."

            await update.effective_message.reply_text(header + "\n" + body + footer, parse_mode="Markdown")

        except Exception as e:
            logger.error(f"Error in pairs command: {e}")
            await update.effective_message.reply_text(f"❌ Error: {e}")

    async def settings(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /settings command."""
        try:
            all_settings = await self._run_blocking(self.settings_repo.get_all)

            message = "⚙️ *Current settings:*\n\n"

            for setting in all_settings:
                message += f"  *{setting.key}*: {setting.value}\n"

            message += "\n💡 To change: /set <key> <value>"

            await update.effective_message.reply_text(message, parse_mode="Markdown")

        except Exception as e:
            logger.error(f"Error in settings command: {e}")
            await update.effective_message.reply_text(f"❌ Error: {e}")

    @require_auth
    async def set_setting(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /set command."""
        try:
            if len(context.args) < 2:
                await update.effective_message.reply_text(
                    "Usage: /set <key> <value>\n"
                    "Example: /set margin_per_trade 150\n\n"
                    "Available settings:\n" + "\n".join(f"  • {k}: {v['description']}" for k, v in ALLOWED_SETTINGS.items())
                )
                return

            key = context.args[0]
            value_str = context.args[1]

            # Validate key
            if key not in ALLOWED_SETTINGS:
                await update.effective_message.reply_text(
                    f"❌ Invalid setting key: *{key}*\n\n"
                    "Available settings:\n" + "\n".join(f"  • {k}" for k in ALLOWED_SETTINGS.keys()),
                    parse_mode="Markdown",
                )
                return

            setting_config = ALLOWED_SETTINGS[key]
            expected_type = setting_config["type"]
            min_val = setting_config["min"]
            max_val = setting_config["max"]

            # Validate type and range
            try:
                typed_value: float | int = expected_type(value_str)

                if not (min_val <= typed_value <= max_val):
                    await update.effective_message.reply_text(
                        f"❌ Value out of range for *{key}*\n\n"
                        f"Value must be between {min_val} and {max_val}\n"
                        f"You provided: {typed_value}",
                        parse_mode="Markdown",
                    )
                    return

                # Save validated setting
                await self._run_blocking(self.settings_repo.set, key, str(typed_value), setting_config["description"])

                await update.effective_message.reply_text(
                    f"✅ Setting updated successfully\n\n" f"*{key}* = {typed_value}\n" f"_{setting_config['description']}_",
                    parse_mode="Markdown",
                )

                logger.info(f"Setting updated: {key}={typed_value} by user {update.effective_user.id}")

            except (ValueError, TypeError) as e:
                await update.effective_message.reply_text(
                    f"❌ Invalid value type for *{key}*\n\n"
                    f"Expected: {expected_type.__name__}\n"
                    f"You provided: {value_str}\n"
                    f"Error: {str(e)}",
                    parse_mode="Markdown",
                )

        except Exception as e:
            logger.error(f"Error in set command: {e}")
            await update.effective_message.reply_text(f"❌ Error: {e}")

    @require_auth
    async def pause(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /pause command."""
        try:
            await self._run_blocking(self.bot_status_repo.set_paused, True)
            await update.effective_message.reply_text("⏸️ Trading paused")

        except Exception as e:
            logger.error(f"Error in pause command: {e}")
            await update.effective_message.reply_text(f"❌ Error: {e}")

    @require_auth
    async def resume(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /resume command."""
        try:
            await self._run_blocking(self.bot_status_repo.set_paused, False)
            await update.effective_message.reply_text("▶️ Trading resumed")

        except Exception as e:
            logger.error(f"Error in resume command: {e}")
            await update.effective_message.reply_text(f"❌ Error: {e}")

    def _format_progress_bar(self, progress_pct: float, width: int = 20) -> str:
        """Format a progress bar for Telegram.

        Args:
            progress_pct: Progress percentage (0-100)
            width: Width of the progress bar in characters

        Returns: Formatted progress bar string
        """
        filled = int(width * progress_pct / 100)
        empty = width - filled
        bar = "█" * filled + "░" * empty
        return f"[{bar}] {progress_pct:.1f}%"

    def _format_processed_line(self, processed: int, total: int, strategy_mode: str) -> str:
        """Format processed symbols line with optional approximation marker."""
        total_display = f"~{total}" if strategy_mode != "order_block" else str(total)
        return f"Processed: {processed}/{total_display} symbols"

    def _strategy_label(self, strategy_mode: str) -> str:
        return "Order Block Breakout" if strategy_mode == "order_block" else "Pump & Cooldown"

    async def _estimate_total_symbols(self, strategy_mode: str) -> int:
        try:
            if strategy_mode == "order_block":
                limit_value = max(self.engine.config.strategy_runtime.order_block_top_pairs or 0, 0)
                universe_limit = limit_value if limit_value > 0 else None
                symbols = await self._run_blocking(lambda: self.engine.scanner.get_order_block_universe(universe_limit))
                if not symbols and limit_value > 0:
                    return limit_value
                return len(symbols)
        except Exception as exc:
            logger.error(f"Failed to estimate universe for {strategy_mode}: {exc}")
        return 200

    async def _progress_monitor(
        self,
        scan_id: str,
        strategy_mode: str,
        message,
        stop_event: asyncio.Event,
    ):
        last_update_time = 0.0
        last_message_text = ""
        loop = asyncio.get_running_loop()

        while not stop_event.is_set():
            try:
                progress = await self._run_blocking(self.scan_progress_repo.get, scan_id)
            except Exception as exc:
                logger.error(f"Error fetching scan progress: {exc}")
                await asyncio.sleep(1)
                continue

            if not progress:
                await asyncio.sleep(0.5)
                continue

            current_time = loop.time()
            if current_time - last_update_time >= 1.0:
                progress_bar = self._format_progress_bar(progress.progress_pct)
                status_emoji = "🔍" if progress.status == "running" else "✅"
                processed_line = self._format_processed_line(progress.processed_symbols, progress.total_symbols, strategy_mode)
                message_text = (
                    f"{status_emoji} *Market scan in progress...*\n\n"
                    f"{progress_bar}\n"
                    f"{processed_line}\n"
                    f"Signals found: {progress.signals_found}"
                )

                if message_text != last_message_text:
                    try:
                        await message.edit_text(message_text, parse_mode="Markdown")
                        last_message_text = message_text
                        last_update_time = current_time
                    except Exception as exc:
                        error_msg = str(exc).lower()
                        if "message is not modified" not in error_msg:
                            logger.debug(f"Progress message update skipped: {exc}")

            await asyncio.sleep(0.5)

    async def _cleanup_task(self, task: asyncio.Task):
        try:
            await asyncio.wait_for(task, timeout=2.0)
        except asyncio.TimeoutError:
            task.cancel()
            with suppress(asyncio.CancelledError):
                await task

    async def _execute_scan_cycle(self, strategy_mode: str, scan_id: str, user_id: str) -> dict:
        def executor_fn():
            if strategy_mode == "order_block":
                return self.engine.execute_order_block_cycle(
                    max_signals=30,
                    scan_id=scan_id,
                    triggered_by=user_id,
                )
            return self.engine.execute_pump_scan_and_trade(
                max_signals=30,
                scan_id=scan_id,
                triggered_by=user_id,
            )

        return await self._run_blocking(executor_fn)

    async def _run_scan_request(
        self,
        *,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE,
        strategy_mode: str,
        scan_id: str,
        user_id: str,
        initial_message,
    ):
        strategy_label = self._strategy_label(strategy_mode)
        await initial_message.edit_text(
            "🔄 *Запуск сканирования...*\n\n" f"Стратегия: *{strategy_label}*",
            parse_mode="Markdown",
        )

        total_symbols = await self._estimate_total_symbols(strategy_mode)
        await self._run_blocking(
            self.scan_progress_repo.create,
            scan_id=scan_id,
            scan_type="manual",
            total_symbols=total_symbols,
            triggered_by=user_id,
        )

        stop_event: asyncio.Event | None = None
        progress_task: asyncio.Task | None = None
        if self.scan_queue:
            stop_event = asyncio.Event()
            progress_task = asyncio.create_task(self._progress_monitor(scan_id, strategy_mode, initial_message, stop_event))

        try:
            result = await self._execute_scan_cycle(strategy_mode, scan_id, user_id)
        except Exception as exc:
            if stop_event:
                stop_event.set()
            if progress_task:
                await self._cleanup_task(progress_task)
            logger.error(f"Error executing manual scan: {exc}", exc_info=True)
            await initial_message.edit_text(f"❌ Ошибка сканирования:\n{exc}", parse_mode="Markdown")
            return

        if stop_event:
            stop_event.set()
        if progress_task:
            await self._cleanup_task(progress_task)
        if strategy_mode == "order_block" and result.get("reason") == "Order Block cycle already running":
            await self._notify_order_block_cycle_busy(update, initial_message, result)
            return
        await self._publish_scan_result(update, initial_message, result)

    async def _notify_order_block_cycle_busy(self, update: Update, message, result: dict):
        eta_seconds = result.get("eta_seconds")
        if eta_seconds is None:
            remaining_text = "Цикл уже выполняется, дождитесь завершения текущей итерации."
        else:
            minutes = max(1, round(eta_seconds / 60))
            remaining_text = f"Цикл уже выполняется, осталось примерно {minutes} мин."

        busy_message = (
            "⏳ *Order Block цикл уже в работе*\n\n"
            f"{remaining_text}\n"
            "Новый запрос будет запущен автоматически после завершения."
        )
        try:
            await message.edit_text(busy_message, parse_mode="Markdown")
        except Exception:
            await update.effective_message.reply_text(busy_message, parse_mode="Markdown")

    async def _publish_scan_result(self, update: Update, message, result: dict | None):
        result = result or {}
        final_strategy_label = self._strategy_label(result.get("strategy_mode", "pump_cooldown"))
        summary = (
            "✅ *Scan completed*\n\n"
            f"📊 Signals found: {result.get('signals_found', 0)}\n"
            f"✅ Positions opened: {result.get('positions_opened', 0)}\n"
            f"🎯 Strategy: {final_strategy_label}\n"
        )

        if result.get("signals_found", 0) > 0 and result.get("signals"):
            summary += "\n📈 Signal pairs:\n"
            for signal in result["signals"]:
                summary += f"  • {signal['symbol']}\n"

        try:
            await message.edit_text(summary, parse_mode="Markdown")
        except Exception:
            await update.effective_message.reply_text(summary, parse_mode="Markdown")

    @require_auth
    async def scan(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /scan command with queued execution and background worker."""
        initial_message = None
        try:
            strategy_mode = self._resolve_strategy_mode(context)

            scan_id = f"scan_{uuid.uuid4().hex[:12]}"
            user_id = str(update.effective_user.id)
            logger.debug("Manual scan request: strategy=%s queue_enabled=%s", strategy_mode, bool(self.scan_queue))

            initial_message = await update.effective_message.reply_text(
                "⏳ *Запрос принят*\n\nПодготавливаем запуск сканирования...",
                parse_mode="Markdown",
            )

            if not self.scan_queue:
                await self._run_scan_request(
                    update=update,
                    context=context,
                    strategy_mode=strategy_mode,
                    scan_id=scan_id,
                    user_id=user_id,
                    initial_message=initial_message,
                )
                return

            async def handler():
                await self._run_scan_request(
                    update=update,
                    context=context,
                    strategy_mode=strategy_mode,
                    scan_id=scan_id,
                    user_id=user_id,
                    initial_message=initial_message,
                )

            queue_item = ScanQueueItem(scan_id=scan_id, strategy_mode=strategy_mode, handler=handler)
            position = await self.scan_queue.submit(queue_item)

            if position > 0:
                await initial_message.edit_text(
                    "⌛️ *Запрос добавлен в очередь*\n\n"
                    f"Текущая позиция: #{position + 1}\n"
                    "Мы сообщим о прогрессе, как только сканирование начнётся.",
                    parse_mode="Markdown",
                )
            else:
                await initial_message.edit_text(
                    "⚙️ *Готовим запуск сканирования...*\n\n" "Бот стартует анализ в ближайшие секунды.",
                    parse_mode="Markdown",
                )

        except ScanQueueFullError:
            if initial_message:
                await initial_message.edit_text(
                    "❌ Очередь сканов переполнена, попробуйте позже.",
                    parse_mode="Markdown",
                )
            else:
                await update.effective_message.reply_text("❌ Очередь сканов переполнена, попробуйте позже.")
        except Exception as e:
            logger.error(f"Error in scan command: {e}", exc_info=True)
            await update.effective_message.reply_text(f"❌ Error: {e}")

    @require_auth
    async def close(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /close command."""
        try:
            if not context.args:
                await update.effective_message.reply_text("Usage: /close <symbol>\nExample: /close BTC/USDT:USDT")
                return

            symbol = context.args[0]
            result = await self._run_blocking(self.engine.position_manager.close_position_by_symbol, symbol, "manual")

            if result:
                pnl_emoji = "🟢" if result["pnl"] > 0 else "🔴"
                message = f"""
✅ Position closed

*{result['symbol']}*
💰 Entry: {result['entry_price']:.4f}
💰 Exit: {result['exit_price']:.4f}
{pnl_emoji} P&L: {result['pnl']:.2f} USDT ({result['pnl_pct']:.2f}%)
"""
                await update.effective_message.reply_text(message, parse_mode="Markdown")
            else:
                await update.effective_message.reply_text(f"❌ Failed to close position {symbol}")

        except Exception as e:
            logger.error(f"Error in close command: {e}")
            await update.effective_message.reply_text(f"❌ Error: {e}")

    @require_auth
    async def closeall(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /closeall command."""
        try:
            # Audit log
            audit.log_security_event(
                update.effective_user.id, update.effective_user.username or "unknown", "CLOSE_ALL_POSITIONS", {}
            )

            await update.effective_message.reply_text("🔄 Closing all positions...")

            result = await self._run_blocking(self.engine.close_all_positions, "manual")

            message = f"""
✅ Closing completed

📊 Closed positions: {result['positions_closed']}/{result.get('total_positions', 0)}
"""
            await update.effective_message.reply_text(message, parse_mode="Markdown")

        except Exception as e:
            logger.error(f"Error in closeall command: {e}")
            await update.effective_message.reply_text(f"❌ Error: {e}")

    async def show_menu(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /menu command - show main interactive menu."""
        try:
            # Build main menu keyboard from template
            keyboard = self.keyboard_builder.build_inline_keyboard_from_template("main_menu")

            if keyboard:
                message = """
🎮 *Main Menu*

Choose an action from the buttons below:
"""
                await update.effective_message.reply_text(message, parse_mode="Markdown", reply_markup=keyboard)
            else:
                # Fallback: create keyboard programmatically
                buttons_data = KeyboardTemplates.main_menu()
                keyboard = self.keyboard_builder.create_inline_keyboard(buttons_data, n_cols=2)

                message = """
🎮 *Main Menu*

Choose an action from the buttons below:
"""
                await update.effective_message.reply_text(message, parse_mode="Markdown", reply_markup=keyboard)

        except Exception as e:
            logger.error(f"Error in show_menu command: {e}")
            await update.effective_message.reply_text(f"❌ Error: {e}")
