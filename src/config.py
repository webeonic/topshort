"""Configuration management for TopShort trading bot."""

import os
from dataclasses import dataclass, field
from typing import List

from dotenv import load_dotenv

# Load environment variables
load_dotenv()


DEFAULT_FALLBACK_PAIRS = [
    "BTC/USDT:USDT",
    "ETH/USDT:USDT",
    "BNB/USDT:USDT",
    "XRP/USDT:USDT",
    "SOL/USDT:USDT",
    "ADA/USDT:USDT",
    "DOGE/USDT:USDT",
    "AVAX/USDT:USDT",
    "DOT/USDT:USDT",
    "LINK/USDT:USDT",
]

DEFAULT_SILVER_BULLET_SESSIONS = [
    ("London", "08:00", "09:00"),
    ("NewYorkAM", "15:00", "16:00"),
    ("NewYorkPM", "19:00", "20:00"),
]


@dataclass
class SessionWindow:
    """Trading session window in UTC."""

    name: str
    start_utc: str
    end_utc: str


@dataclass
class PairsConfig:
    """Configuration for managing top market pairs."""

    top_n: int
    cache_path: str
    refresh_interval_hours: int
    coingecko_url: str
    coingecko_vs_currency: str
    coingecko_order: str
    http_timeout_seconds: int
    fallback_pairs: List[str] = field(default_factory=list)


@dataclass
class OrderBlockStrategyConfig:
    """Order Block Breakout strategy configuration."""

    enabled: bool
    lookback_months: int
    swing_length: int
    min_fvg_size_pct: float
    min_ob_score: float
    volume_ma_period: int
    volume_spike_threshold: float
    high_volume_threshold: float
    atr_period: int
    atr_stop_multiplier: float
    atr_target_multiplier: float
    risk_per_trade_pct: float
    max_signals: int
    max_workers: int
    chunk_size: int
    chunk_pause_ms: int
    timeframes: List[str] = field(default_factory=list)
    entry_timeframe: str = "15m"
    confirmation_timeframe: str = "5m"
    sessions_utc: List[SessionWindow] = field(default_factory=list)


@dataclass
class BinanceConfig:
    """Binance API configuration."""

    api_key: str
    api_secret: str
    testnet: bool = True


@dataclass
class ExchangeConfig:
    """Exchange client configuration for caching and pre-filtering."""

    # OHLCV cache settings
    ohlcv_cache_enabled: bool = True
    ohlcv_cache_max_entries: int = 5000

    # Pre-filter settings (reduce API calls during scans)
    prefilter_min_change_pct: float = 10.0
    prefilter_min_volume_usdt: float = 100000.0


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
class StrategyRuntimeConfig:
    """Runtime tuning parameters for strategy execution."""

    default_manual_strategy: str
    order_block_cycle_interval_seconds: int
    order_block_top_pairs: int


@dataclass
class SchedulerConfig:
    """Scheduler configuration."""

    scan_interval_minutes: int
    monitor_interval_seconds: int
    signal_retention_days: int  # Days to keep old market signals before cleanup


@dataclass
class ConcurrencyConfig:
    """Global concurrency controls."""

    blocking_workers: int
    scheduler_workers: int
    scan_queue_per_strategy: int
    scan_worker_delay_seconds: float


@dataclass
class LoggingConfig:
    """Logging configuration."""

    level: str
    file: str


@dataclass
class Config:
    """Main configuration container."""

    binance: BinanceConfig
    exchange: ExchangeConfig
    telegram: TelegramConfig
    database: DatabaseConfig
    trading: TradingConfig
    scanner: ScannerConfig
    strategy_runtime: StrategyRuntimeConfig
    pairs: PairsConfig
    order_block_strategy: OrderBlockStrategyConfig
    scheduler: SchedulerConfig
    concurrency: ConcurrencyConfig
    logging: LoggingConfig


def load_config() -> Config:
    """Load configuration from environment variables."""
    default_ob_workers = _default_order_block_workers()
    return Config(
        binance=BinanceConfig(
            api_key=os.getenv("BINANCE_API_KEY", ""),
            api_secret=os.getenv("BINANCE_API_SECRET", ""),
            testnet=os.getenv("BINANCE_TESTNET", "true").lower() == "true",
        ),
        exchange=ExchangeConfig(
            ohlcv_cache_enabled=os.getenv("OHLCV_CACHE_ENABLED", "true").lower() == "true",
            ohlcv_cache_max_entries=int(os.getenv("OHLCV_CACHE_MAX_ENTRIES", "5000")),
            prefilter_min_change_pct=float(os.getenv("PREFILTER_MIN_CHANGE_PCT", "10.0")),
            prefilter_min_volume_usdt=float(os.getenv("PREFILTER_MIN_VOLUME_USDT", "100000.0")),
        ),
        telegram=TelegramConfig(bot_token=os.getenv("TELEGRAM_BOT_TOKEN", ""), chat_id=os.getenv("TELEGRAM_CHAT_ID", "")),
        database=DatabaseConfig(path=os.getenv("DATABASE_PATH", "./data/topshort.db")),
        trading=TradingConfig(
            margin_per_trade=float(os.getenv("MARGIN_PER_TRADE", "100.0")),
            max_positions=int(os.getenv("MAX_POSITIONS", "10")),
            max_total_margin=float(os.getenv("MAX_TOTAL_MARGIN", "1000.0")),
            default_leverage=int(os.getenv("DEFAULT_LEVERAGE", "20")),
            take_profit_pct=float(os.getenv("TAKE_PROFIT_PCT", "5.0")),
        ),
        scanner=ScannerConfig(
            pump_threshold_pct=float(os.getenv("PUMP_THRESHOLD_PCT", "30.0")),
            pump_period_hours_min=int(os.getenv("PUMP_PERIOD_HOURS_MIN", "48")),
            pump_period_hours_max=int(os.getenv("PUMP_PERIOD_HOURS_MAX", "72")),
            cooldown_period_hours_min=int(os.getenv("COOLDOWN_PERIOD_HOURS_MIN", "4")),
            cooldown_period_hours_max=int(os.getenv("COOLDOWN_PERIOD_HOURS_MAX", "8")),
            volume_decrease_threshold_pct=float(os.getenv("VOLUME_DECREASE_THRESHOLD_PCT", "20.0")),
        ),
        strategy_runtime=StrategyRuntimeConfig(
            default_manual_strategy=os.getenv("DEFAULT_MANUAL_STRATEGY_MODE", "pump_cooldown"),
            order_block_cycle_interval_seconds=int(os.getenv("OB_CYCLE_INTERVAL_SECONDS", "60")),
            order_block_top_pairs=int(os.getenv("OB_TOP_PAIRS_LIMIT", "50")),
        ),
        scheduler=SchedulerConfig(
            scan_interval_minutes=int(os.getenv("SCAN_INTERVAL_MINUTES", "60")),
            monitor_interval_seconds=int(os.getenv("MONITOR_INTERVAL_SECONDS", "30")),
            signal_retention_days=int(os.getenv("SIGNAL_RETENTION_DAYS", "30")),
        ),
        concurrency=ConcurrencyConfig(
            blocking_workers=int(os.getenv("ASYNC_BLOCKING_WORKERS", str(_default_blocking_workers()))),
            scheduler_workers=int(os.getenv("SCHEDULER_MAX_WORKERS", "2")),
            scan_queue_per_strategy=int(os.getenv("SCAN_QUEUE_PER_STRATEGY", "3")),
            scan_worker_delay_seconds=float(os.getenv("SCAN_WORKER_DELAY_SECONDS", "0.25")),
        ),
        logging=LoggingConfig(level=os.getenv("LOG_LEVEL", "INFO"), file=os.getenv("LOG_FILE", "./logs/topshort.log")),
        pairs=PairsConfig(
            top_n=int(os.getenv("TOP_PAIRS_COUNT", "50")),
            cache_path=os.getenv("TOP_PAIRS_CACHE_PATH", "./data/top_pairs_cache.json"),
            refresh_interval_hours=int(os.getenv("TOP_PAIRS_REFRESH_HOURS", "24")),
            coingecko_url=os.getenv("COINGECKO_MARKETS_URL", "https://api.coingecko.com/api/v3/coins/markets"),
            coingecko_vs_currency=os.getenv("COINGECKO_VS_CURRENCY", "usd"),
            coingecko_order=os.getenv("COINGECKO_MARKETS_ORDER", "market_cap_desc"),
            http_timeout_seconds=int(os.getenv("COINGECKO_HTTP_TIMEOUT", "15")),
            fallback_pairs=_parse_pairs(os.getenv("TOP_PAIRS_FALLBACK", "")),
        ),
        order_block_strategy=OrderBlockStrategyConfig(
            enabled=os.getenv("OB_STRATEGY_ENABLED", "true").lower() == "true",
            lookback_months=int(os.getenv("OB_LOOKBACK_MONTHS", "6")),
            swing_length=int(os.getenv("OB_SWING_LENGTH", "10")),
            min_fvg_size_pct=float(os.getenv("OB_MIN_FVG_SIZE_PCT", "0.3")),
            min_ob_score=float(os.getenv("OB_MIN_OB_SCORE", "0.5")),
            volume_ma_period=int(os.getenv("OB_VOLUME_MA_PERIOD", "20")),
            volume_spike_threshold=float(os.getenv("OB_VOLUME_SPIKE_THRESHOLD", "1.2")),
            high_volume_threshold=float(os.getenv("OB_HIGH_VOLUME_THRESHOLD", "1.5")),
            atr_period=int(os.getenv("OB_ATR_PERIOD", "14")),
            atr_stop_multiplier=float(os.getenv("OB_ATR_STOP_MULTIPLIER", "1.5")),
            atr_target_multiplier=float(os.getenv("OB_ATR_TARGET_MULTIPLIER", "2.0")),
            risk_per_trade_pct=float(os.getenv("OB_RISK_PER_TRADE_PCT", "1.0")),
            max_signals=int(os.getenv("OB_MAX_SIGNALS", "10")),
            max_workers=int(os.getenv("OB_MAX_WORKERS", str(default_ob_workers))),
            chunk_size=int(os.getenv("OB_CHUNK_SIZE", "10")),
            chunk_pause_ms=int(os.getenv("OB_CHUNK_PAUSE_MS", "0")),
            timeframes=_parse_timeframes(os.getenv("OB_TIMEFRAMES", "1d,4h,1h,15m,5m")),
            entry_timeframe=os.getenv("OB_ENTRY_TIMEFRAME", "15m"),
            confirmation_timeframe=os.getenv("OB_CONFIRMATION_TIMEFRAME", "5m"),
            sessions_utc=_parse_sessions(
                os.getenv(
                    "OB_SESSION_WINDOWS",
                    "London:08:00-09:00,NewYorkAM:15:00-16:00,NewYorkPM:19:00-20:00",
                )
            ),
        ),
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


def _parse_pairs(value: str) -> List[str]:
    """Parse comma-separated list of trading pairs."""
    if not value:
        return DEFAULT_FALLBACK_PAIRS.copy()
    pairs = [pair.strip().upper() for pair in value.split(",") if pair.strip()]
    return pairs or DEFAULT_FALLBACK_PAIRS.copy()


def _parse_timeframes(value: str) -> List[str]:
    """Parse comma-separated timeframes."""
    if not value:
        return ["1d", "4h", "1h", "15m", "5m"]
    return [tf.strip() for tf in value.split(",") if tf.strip()]


def _parse_sessions(value: str) -> List[SessionWindow]:
    """Parse session windows defined as Name:HH:MM-HH:MM."""
    sessions: List[SessionWindow] = []
    if not value:
        value = ",".join([f"{name}:{start}-{end}" for name, start, end in DEFAULT_SILVER_BULLET_SESSIONS])

    segments = [segment.strip() for segment in value.split(",") if segment.strip()]
    for segment in segments:
        try:
            name_part, hours_part = segment.split(":")
            start_part, end_part = hours_part.split("-")
            sessions.append(SessionWindow(name=name_part, start_utc=start_part, end_utc=end_part))
        except ValueError:
            # Skip malformed entries
            continue

    if not sessions:
        sessions = [
            SessionWindow(name=name, start_utc=start, end_utc=end) for name, start, end in DEFAULT_SILVER_BULLET_SESSIONS
        ]

    return sessions


def _default_order_block_workers() -> int:
    """Calculate default worker pool size for Order Block scans."""
    cpu_count = os.cpu_count() or 4
    return max(8, cpu_count * 2)


def _default_blocking_workers() -> int:
    """Default size for shared blocking executor."""
    cpu_count = os.cpu_count() or 4
    return max(4, cpu_count)


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
