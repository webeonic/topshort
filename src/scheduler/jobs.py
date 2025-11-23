"""Scheduled jobs for trading automation."""

import asyncio
import logging
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from ..bot.telegram_bot import TelegramBot
from ..database.repository import BotStatusRepository, MarketSignalRepository
from ..trading.engine import TradingEngine
from ..utils.async_executor import run_blocking

logger = logging.getLogger(__name__)


class SchedulerJobs:
    """Manages scheduled trading jobs."""

    def __init__(self, session, engine: TradingEngine, telegram_bot: TelegramBot, config):
        self.session = session
        self.engine = engine
        self.telegram_bot = telegram_bot
        self.config = config
        self.bot_status_repo = BotStatusRepository(session)
        self.signal_repo = MarketSignalRepository(session)
        self.scheduler = AsyncIOScheduler()

    async def _run_blocking(self, func, *args, **kwargs):
        return await run_blocking(func, *args, **kwargs)

    def _job_start(self, name: str) -> float:
        logger.info("Starting job: %s", name)
        return time.perf_counter()

    def _job_end(self, name: str, started_at: float, warn_after: float | None = None):
        duration = time.perf_counter() - started_at
        logger.info("Job %s finished in %.2fs", name, duration)
        if warn_after and duration > warn_after:
            logger.warning("Job %s exceeded threshold %.2fs (took %.2fs)", name, warn_after, duration)

    async def scan_and_trade_job(self):
        """Scheduled job to scan market and open positions."""
        start_time = self._job_start("scan_and_trade")
        try:
            # Check if bot is active and not paused
            bot_status = await self._run_blocking(self.bot_status_repo.get)
            if not bot_status.is_active or bot_status.is_paused:
                logger.info("Bot is paused or inactive, skipping scan")
                return

            logger.info("=" * 80)
            logger.info(f"SCHEDULED SCAN - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
            logger.info("=" * 80)

            # Update last scan time
            await self._run_blocking(self.bot_status_repo.update_scan_time)

            # Execute Pump & Cooldown scan
            result = await self._run_blocking(
                lambda: self.engine.execute_pump_scan_and_trade(max_signals=30, triggered_by="scheduler")
            )

            # Send notification
            await self.telegram_bot.notify_scan_complete(result)

            # If positions were opened, send individual notifications
            if result.get("opened_positions"):
                for pos_info in result["opened_positions"]:
                    await self.telegram_bot.notify_position_opened(pos_info)

            logger.info(f"Scan job completed: {result['positions_opened']} positions opened")

        except Exception as e:
            logger.error(f"Error in scan_and_trade_job: {e}", exc_info=True)
            await self.telegram_bot.notify_error(f"Scan error: {str(e)}")
        finally:
            warn_after = self.config.scheduler.scan_interval_minutes * 60
            self._job_end("scan_and_trade", start_time, warn_after=warn_after)

    async def order_block_cycle_job(self):
        """High-frequency Order Block scanner."""
        if not self.config.order_block_strategy.enabled:
            return

        start_time = self._job_start("order_block_cycle")
        try:
            bot_status = await self._run_blocking(self.bot_status_repo.get)
            if not bot_status.is_active or bot_status.is_paused:
                logger.debug("Bot inactive/paused, skipping Order Block cycle")
                return

            result = await self._run_blocking(lambda: self.engine.execute_order_block_cycle(triggered_by="scheduler"))
            if (result.get("signals_found") or result.get("positions_opened")) and result.get(
                "strategy_mode"
            ) == "order_block":
                await self.telegram_bot.notify_scan_complete(result)

            if result.get("opened_positions"):
                for pos_info in result["opened_positions"]:
                    await self.telegram_bot.notify_position_opened(pos_info)

        except Exception as e:
            logger.error(f"Error in order_block_cycle_job: {e}", exc_info=True)
            await self.telegram_bot.notify_error(f"Order Block scan error: {str(e)}")
        finally:
            warn_after = max(5, self.config.strategy_runtime.order_block_cycle_interval_seconds)
            self._job_end("order_block_cycle", start_time, warn_after=warn_after)

    async def monitor_positions_job(self):
        """Scheduled job to monitor open positions."""
        start_time = self._job_start("monitor_positions")
        try:
            # Check if bot is active
            bot_status = await self._run_blocking(self.bot_status_repo.get)
            if not bot_status.is_active:
                return

            logger.debug("Monitoring positions...")

            # Update last monitor time
            await self._run_blocking(self.bot_status_repo.update_monitor_time)

            # Monitor and close positions if targets reached
            result = await self._run_blocking(self.engine.monitor_and_close)

            # Send notifications for closed positions
            if result.get("closed_positions"):
                for close_info in result["closed_positions"]:
                    await self.telegram_bot.notify_position_closed(close_info)

                logger.info(f"Monitor job: {result['positions_closed']} positions closed")

        except Exception as e:
            logger.error(f"Error in monitor_positions_job: {e}", exc_info=True)
        finally:
            warn_after = max(10, self.config.scheduler.monitor_interval_seconds)
            self._job_end("monitor_positions", start_time, warn_after=warn_after)

    async def cleanup_data_job(self):
        """Scheduled job to cleanup old data."""
        start_time = self._job_start("cleanup_data")
        try:
            logger.info("Running data cleanup job...")

            # Cleanup old market signals (older than 30 days)
            deleted_signals = await self._run_blocking(lambda: self.signal_repo.cleanup_old_signals(retention_days=30))

            logger.info(f"Data cleanup completed: {deleted_signals} old signals removed")

        except Exception as e:
            logger.error(f"Error in cleanup_data_job: {e}", exc_info=True)
        finally:
            self._job_end("cleanup_data", start_time, warn_after=60)

    async def refresh_top_pairs_job(self):
        """Refresh cached list of top trading pairs."""
        start_time = self._job_start("refresh_top_pairs")
        try:
            if not getattr(self.engine, "top_pairs_service", None):
                logger.warning("Top pairs service is not initialized, skipping refresh")
                return

            logger.info("Refreshing top pairs cache via scheduled job...")
            await self._run_blocking(self.engine.top_pairs_service.refresh)
            meta = await self._run_blocking(self.engine.top_pairs_service.get_metadata)
            logger.info(
                "Top pairs cache refreshed: %s pairs (source=%s, updated=%s)",
                meta.get("count"),
                meta.get("source"),
                meta.get("last_updated"),
            )
        except Exception as e:
            logger.error(f"Error refreshing top pairs cache: {e}", exc_info=True)
        finally:
            self._job_end("refresh_top_pairs", start_time, warn_after=120)

    def start(self):
        """Start scheduler with configured jobs."""
        logger.info("Starting scheduler")

        # Job 1: Market scan and trade (every hour by default)
        scan_interval_minutes = self.config.scheduler.scan_interval_minutes
        self.scheduler.add_job(
            self.scan_and_trade_job,
            trigger=IntervalTrigger(minutes=scan_interval_minutes),
            id="scan_and_trade",
            name="Market Scan and Trade",
            replace_existing=True,
            max_instances=1,  # Prevent overlapping runs
        )
        logger.info(f"Scheduled scan_and_trade job: every {scan_interval_minutes} minutes")

        # Job 1b: Continuous Order Block scan
        order_block_interval = self.config.strategy_runtime.order_block_cycle_interval_seconds
        if self.config.order_block_strategy.enabled and order_block_interval > 0:
            self.scheduler.add_job(
                self.order_block_cycle_job,
                trigger=IntervalTrigger(seconds=order_block_interval),
                id="order_block_cycle",
                name="Order Block Cycle",
                replace_existing=True,
                max_instances=1,
            )
            logger.info(
                "Scheduled order_block_cycle job: every %s seconds (top %s pairs)",
                order_block_interval,
                self.config.strategy_runtime.order_block_top_pairs,
            )

        # Job 2: Monitor positions (every 30 seconds by default)
        monitor_interval_seconds = self.config.scheduler.monitor_interval_seconds
        self.scheduler.add_job(
            self.monitor_positions_job,
            trigger=IntervalTrigger(seconds=monitor_interval_seconds),
            id="monitor_positions",
            name="Monitor Positions",
            replace_existing=True,
            max_instances=1,
        )
        logger.info(f"Scheduled monitor_positions job: every {monitor_interval_seconds} seconds")

        # Job 3: Cleanup old data (daily at 2 AM)
        self.scheduler.add_job(
            self.cleanup_data_job,
            trigger=CronTrigger(hour=2, minute=0),
            id="cleanup_data",
            name="Cleanup Old Data",
            replace_existing=True,
        )
        logger.info("Scheduled cleanup_data job: daily at 2:00 AM")

        # Job 4: Refresh top pairs list (daily at 1 AM UTC)
        self.scheduler.add_job(
            self.refresh_top_pairs_job,
            trigger=CronTrigger(hour=1, minute=0),
            id="refresh_top_pairs",
            name="Refresh Top Pairs",
            replace_existing=True,
        )
        logger.info("Scheduled refresh_top_pairs job: daily at 1:00 AM")

        # Start scheduler
        self.scheduler.start()
        logger.info("Scheduler started successfully")

    def stop(self):
        """Stop scheduler."""
        logger.info("Stopping scheduler")
        if self.scheduler.running:
            self.scheduler.shutdown()
        logger.info("Scheduler stopped")

    def pause(self):
        """Pause all jobs."""
        logger.info("Pausing scheduler jobs")
        self.scheduler.pause()

    def resume(self):
        """Resume all jobs."""
        logger.info("Resuming scheduler jobs")
        self.scheduler.resume()

    def get_jobs_status(self) -> list:
        """Get status of all jobs."""
        jobs = []
        for job in self.scheduler.get_jobs():
            jobs.append(
                {
                    "id": job.id,
                    "name": job.name,
                    "next_run": job.next_run_time.isoformat() if job.next_run_time else None,
                    "trigger": str(job.trigger),
                }
            )
        return jobs
