"""Configuration management for TopShort trading bot."""
import os
from dataclasses import dataclass
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables
load_dotenv()


@dataclass
class BinanceConfig:
    """Binance API configuration."""
    api_key: str
    api_secret: str
    testnet: bool = True


@dataclass
class TelegramConfig:
    """Telegram bot configuration."""
    bot_token: str
    chat_id: str


@dataclass
class DatabaseConfig:
    """Database configuration."""
    path: str


@dataclass
class TradingConfig:
    """Trading configuration (default values, can be changed via settings)."""
    margin_per_trade: float
    max_positions: int
    max_total_margin: float
    default_leverage: int
    take_profit_pct: float


@dataclass
class ScannerConfig:
    """Market scanner configuration."""
    pump_threshold_pct: float
    pump_period_hours_min: int
    pump_period_hours_max: int
    cooldown_period_hours_min: int
    cooldown_period_hours_max: int
    volume_decrease_threshold_pct: float


@dataclass
class SchedulerConfig:
    """Scheduler configuration."""
    scan_interval_minutes: int
    monitor_interval_seconds: int


@dataclass
class LoggingConfig:
    """Logging configuration."""
    level: str
    file: str


@dataclass
class Config:
    """Main configuration container."""
    binance: BinanceConfig
    telegram: TelegramConfig
    database: DatabaseConfig
    trading: TradingConfig
    scanner: ScannerConfig
    scheduler: SchedulerConfig
    logging: LoggingConfig


def load_config() -> Config:
    """Load configuration from environment variables."""
    return Config(
        binance=BinanceConfig(
            api_key=os.getenv('BINANCE_API_KEY', ''),
            api_secret=os.getenv('BINANCE_API_SECRET', ''),
            testnet=os.getenv('BINANCE_TESTNET', 'true').lower() == 'true'
        ),
        telegram=TelegramConfig(
            bot_token=os.getenv('TELEGRAM_BOT_TOKEN', ''),
            chat_id=os.getenv('TELEGRAM_CHAT_ID', '')
        ),
        database=DatabaseConfig(
            path=os.getenv('DATABASE_PATH', './data/topshort.db')
        ),
        trading=TradingConfig(
            margin_per_trade=float(os.getenv('MARGIN_PER_TRADE', '100.0')),
            max_positions=int(os.getenv('MAX_POSITIONS', '10')),
            max_total_margin=float(os.getenv('MAX_TOTAL_MARGIN', '1000.0')),
            default_leverage=int(os.getenv('DEFAULT_LEVERAGE', '20')),
            take_profit_pct=float(os.getenv('TAKE_PROFIT_PCT', '5.0'))
        ),
        scanner=ScannerConfig(
            pump_threshold_pct=float(os.getenv('PUMP_THRESHOLD_PCT', '30.0')),
            pump_period_hours_min=int(os.getenv('PUMP_PERIOD_HOURS_MIN', '48')),
            pump_period_hours_max=int(os.getenv('PUMP_PERIOD_HOURS_MAX', '72')),
            cooldown_period_hours_min=int(os.getenv('COOLDOWN_PERIOD_HOURS_MIN', '4')),
            cooldown_period_hours_max=int(os.getenv('COOLDOWN_PERIOD_HOURS_MAX', '8')),
            volume_decrease_threshold_pct=float(os.getenv('VOLUME_DECREASE_THRESHOLD_PCT', '20.0'))
        ),
        scheduler=SchedulerConfig(
            scan_interval_minutes=int(os.getenv('SCAN_INTERVAL_MINUTES', '60')),
            monitor_interval_seconds=int(os.getenv('MONITOR_INTERVAL_SECONDS', '30'))
        ),
        logging=LoggingConfig(
            level=os.getenv('LOG_LEVEL', 'INFO'),
            file=os.getenv('LOG_FILE', './logs/topshort.log')
        )
    )


def validate_config(config: Config) -> list[str]:
    """Validate configuration and return list of errors."""
    errors = []

    if not config.binance.api_key:
        errors.append("BINANCE_API_KEY is required")
    if not config.binance.api_secret:
        errors.append("BINANCE_API_SECRET is required")
    if not config.telegram.bot_token:
        errors.append("TELEGRAM_BOT_TOKEN is required")
    if not config.telegram.chat_id:
        errors.append("TELEGRAM_CHAT_ID is required")

    if config.trading.margin_per_trade <= 0:
        errors.append("MARGIN_PER_TRADE must be positive")
    if config.trading.max_positions <= 0:
        errors.append("MAX_POSITIONS must be positive")
    if config.trading.default_leverage < 1:
        errors.append("DEFAULT_LEVERAGE must be >= 1")

    return errors


# Global config instance
_config: Config | None = None


def get_config() -> Config:
    """Get global configuration instance."""
    global _config
    if _config is None:
        _config = load_config()
        errors = validate_config(_config)
        if errors:
            raise ValueError(f"Configuration errors: {', '.join(errors)}")
    return _config
