"""Main entry point for TopShort trading bot."""
import sys
import logging
import asyncio
import signal
from pathlib import Path

import colorlog

from .config import get_config
from .database.models import create_database, get_session, init_default_settings
from .exchange.binance_client import BinanceClient
from .trading.engine import TradingEngine
from .bot.telegram_bot import TelegramBot
from .scheduler.jobs import SchedulerJobs


def setup_logging(config):
    """Setup logging configuration."""
    # Create logs directory if it doesn't exist
    log_file = Path(config.logging.file)
    log_file.parent.mkdir(parents=True, exist_ok=True)

    # Create formatter
    formatter = colorlog.ColoredFormatter(
        '%(log_color)s%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S',
        log_colors={
            'DEBUG': 'cyan',
            'INFO': 'green',
            'WARNING': 'yellow',
            'ERROR': 'red',
            'CRITICAL': 'red,bg_white',
        }
    )

    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)

    # File handler
    file_handler = logging.FileHandler(config.logging.file)
    file_handler.setFormatter(logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    ))

    # Root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(getattr(logging, config.logging.level))
    root_logger.addHandler(console_handler)
    root_logger.addHandler(file_handler)

    # Reduce verbosity of some libraries
    logging.getLogger('ccxt').setLevel(logging.WARNING)
    logging.getLogger('telegram').setLevel(logging.WARNING)
    logging.getLogger('apscheduler').setLevel(logging.INFO)


class TopShortBot:
    """Main application class."""

    def __init__(self):
        self.config = None
        self.engine_db = None
        self.session = None
        self.client = None
        self.engine = None
        self.telegram_bot = None
        self.scheduler = None
        self.logger = logging.getLogger(__name__)

    def initialize(self):
        """Initialize all components."""
        self.logger.info("=" * 80)
        self.logger.info("TopShort Trading Bot - Initializing")
        self.logger.info("=" * 80)

        # Load configuration
        self.logger.info("Loading configuration...")
        self.config = get_config()

        # Setup logging
        setup_logging(self.config)

        # Initialize database
        self.logger.info(f"Initializing database: {self.config.database.path}")
        database_path = Path(self.config.database.path)
        database_path.parent.mkdir(parents=True, exist_ok=True)

        database_url = f'sqlite:///{self.config.database.path}'
        self.engine_db = create_database(database_url)
        self.session = get_session(self.engine_db)

        # Initialize default settings
        self.logger.info("Initializing default settings...")
        init_default_settings(self.session)

        # Initialize Binance client
        self.logger.info("Initializing Binance client...")
        self.client = BinanceClient(
            api_key=self.config.binance.api_key,
            api_secret=self.config.binance.api_secret,
            testnet=self.config.binance.testnet
        )

        # Load markets
        self.logger.info("Loading markets from Binance...")
        self.client.load_markets()

        # Initialize trading engine
        self.logger.info("Initializing trading engine...")
        self.engine = TradingEngine(self.session, self.client, self.config)

        # Initialize Telegram bot
        self.logger.info("Initializing Telegram bot...")
        self.telegram_bot = TelegramBot(self.config.telegram, self.session, self.engine)
        self.telegram_bot.setup()

        # Initialize scheduler
        self.logger.info("Initializing scheduler...")
        self.scheduler = SchedulerJobs(self.session, self.engine, self.telegram_bot, self.config)

        self.logger.info("=" * 80)
        self.logger.info("Initialization complete")
        self.logger.info("=" * 80)

    async def start(self):
        """Start the bot."""
        self.logger.info("Starting TopShort Trading Bot...")

        # Initialize telegram bot application
        await self.telegram_bot.initialize()

        # Send startup notification
        await self.telegram_bot.send_message(
            "🚀 *TopShort Bot started*\n\n"
            f"Testnet: {self.config.binance.testnet}\n"
            f"Scan interval: every {self.config.scheduler.scan_interval_minutes} min\n"
            f"Monitor interval: every {self.config.scheduler.monitor_interval_seconds} sec"
        )

        # Start scheduler
        self.scheduler.start()

        # Start Telegram bot (blocking)
        self.logger.info("Starting Telegram bot polling...")
        await self.telegram_bot.start_polling()

    async def stop(self):
        """Stop the bot gracefully."""
        self.logger.info("Stopping TopShort Trading Bot...")

        # Stop scheduler
        if self.scheduler:
            self.scheduler.stop()

        # Stop Telegram bot
        if self.telegram_bot:
            await self.telegram_bot.stop()

        # Close database session
        if self.session:
            self.session.close()

        # Send shutdown notification
        try:
            await self.telegram_bot.send_message("🛑 *TopShort Bot stopped*")
        except:
            pass

        self.logger.info("TopShort Trading Bot stopped")

    def run(self):
        """Run the bot."""
        try:
            # Initialize
            self.initialize()

            # Run async event loop with proper signal handling
            asyncio.run(self._run_with_signals())

        except KeyboardInterrupt:
            self.logger.info("Keyboard interrupt received")
        except Exception as e:
            self.logger.error(f"Fatal error: {e}", exc_info=True)
            sys.exit(1)

    async def _run_with_signals(self):
        """Run the bot with proper signal handling."""
        # Setup signal handlers for graceful shutdown
        loop = asyncio.get_running_loop()

        def signal_handler():
            self.logger.info("Received shutdown signal, stopping...")
            asyncio.create_task(self.stop())

        # Register signal handlers
        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(sig, signal_handler)

        try:
            await self.start()
        finally:
            # Cleanup signal handlers
            for sig in (signal.SIGINT, signal.SIGTERM):
                loop.remove_signal_handler(sig)


def main():
    """Main entry point."""
    bot = TopShortBot()
    bot.run()


if __name__ == '__main__':
    main()
