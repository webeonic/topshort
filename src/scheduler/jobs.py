"""Scheduled jobs for trading automation."""

import asyncio
import logging
from datetime import datetime

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from ..bot.telegram_bot import TelegramBot
from ..database.repository import BotStatusRepository, MarketSignalRepository
from ..trading.engine import TradingEngine

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

    async def scan_and_trade_job(self):
        """Scheduled job to scan market and open positions."""
        try:
            # Check if bot is active and not paused
            bot_status = self.bot_status_repo.get()
            if not bot_status.is_active or bot_status.is_paused:
                logger.info("Bot is paused or inactive, skipping scan")
                return

            logger.info("=" * 80)
            logger.info(f"SCHEDULED SCAN - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
            logger.info("=" * 80)

            # Update last scan time
            self.bot_status_repo.update_scan_time()

            # Execute scan and trade
            result = self.engine.execute_scan_and_trade(max_signals=30)

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

    async def monitor_positions_job(self):
        """Scheduled job to monitor open positions."""
        try:
            # Check if bot is active
            bot_status = self.bot_status_repo.get()
            if not bot_status.is_active:
                return

            logger.debug("Monitoring positions...")

            # Update last monitor time
            self.bot_status_repo.update_monitor_time()

            # Monitor and close positions if targets reached
            result = self.engine.monitor_and_close()

            # Send notifications for closed positions
            if result.get("closed_positions"):
                for close_info in result["closed_positions"]:
                    await self.telegram_bot.notify_position_closed(close_info)

                logger.info(f"Monitor job: {result['positions_closed']} positions closed")

        except Exception as e:
            logger.error(f"Error in monitor_positions_job: {e}", exc_info=True)

    async def cleanup_data_job(self):
        """Scheduled job to cleanup old data."""
        try:
            logger.info("Running data cleanup job...")

            # Cleanup old market signals (older than 30 days)
            deleted_signals = self.signal_repo.cleanup_old_signals(retention_days=30)

            logger.info(f"Data cleanup completed: {deleted_signals} old signals removed")

        except Exception as e:
            logger.error(f"Error in cleanup_data_job: {e}", exc_info=True)

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
