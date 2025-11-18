# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

TopShort is an automated trading bot for Binance Futures that opens short positions on pairs cooling down after pumps. The bot runs fully automated with hourly market scans and manages positions through a Telegram interface.

**Russian documentation**: The README and most documentation is in Russian. The codebase and comments are in English.

## Essential Commands

### Running the Bot

```bash
# Start the bot
python -m src.main
# or
python src/main.py
```

### Testing

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=src --cov-report=html

# Run specific test file
pytest tests/test_position_manager.py

# Run specific test
pytest tests/test_position_manager.py::TestOpenPosition::test_open_position_success

# Run tests in parallel (faster)
pytest -n auto

# Debug mode - enter debugger on failure
pytest --pdb

# Show print statements
pytest -s

# Verbose output
pytest -v
```

### Code Quality

```bash
# Format code
black src/ tests/

# Check formatting
black --check src/ tests/

# Lint
flake8 src/

# Type checking
mypy src --ignore-missing-imports

# Sort imports
isort src/ tests/
```

### Database Migrations

**IMPORTANT**: Migrations apply automatically on bot startup. No manual intervention needed.

```bash
# Check migration status
python scripts/check_migrations.py data/topshort.db

# View migrations directly
sqlite3 data/topshort.db "SELECT * FROM schema_migrations ORDER BY version;"

# Create new migration - add to src/database/migrations/scripts/
# Format: V{XXX}__{description}.sql
# Example: V003__add_position_notes.sql
```

### Database Inspection

```bash
# Open SQLite database
sqlite3 data/topshort.db

# Useful commands inside sqlite3:
.tables                          # Show all tables
.schema positions                # Show schema
SELECT * FROM positions LIMIT 5; # View data
.exit                            # Exit
```

## Architecture Overview

### Core Components

**TradingEngine** (`src/trading/engine.py`) - Central coordinator:
- Orchestrates all components with thread-safe locks per symbol
- Manages scan-and-trade cycles
- Coordinates Scanner, RiskManager, PositionManager, and LimitOrderMonitor

**Scanner** (`src/strategy/scanner.py` + `src/strategy/detector.py`):
- Hourly market scans for pump-cooldown patterns
- Detects ≥30% price increase over 48-72h followed by volume decrease
- Returns top-N signals scored by pump magnitude and volume decrease

**PositionManager** (`src/trading/position_manager.py`):
- Opens/closes positions via Binance client
- Places limit orders for take-profit (5% default)
- Tracks positions in database with multi-source support

**RiskManager** (`src/trading/risk_manager.py`):
- Pre-trade checks for position limits and margin limits
- Validates trades before execution
- Provides risk summary metrics

**ExchangePositionSync** (`src/trading/exchange_position_sync.py`):
- Syncs local DB with actual Binance positions
- Handles external positions opened outside bot
- Critical for maintaining consistency

**LimitOrderMonitor** (`src/trading/limit_order_monitor.py`):
- Monitors status of take-profit and stop-loss orders
- Updates position status when orders fill
- Handles order failures and retries

**TelegramBot** (`src/bot/telegram_bot.py`):
- Provides full control interface via Telegram
- Commands for status, positions, settings, manual trading
- Supports dynamic interactive keyboards

**Dynamic Keyboard System** (`src/bot/keyboard_builder.py`):
- Database-driven keyboard templates and buttons
- Runtime state tracking per user/chat
- See `docs/architecture/KEYBOARD_SYSTEM.md` for details

**Scheduler** (`src/scheduler/jobs.py`):
- APScheduler manages recurring tasks
- Hourly market scans (default)
- 30-second position monitoring (default)

### Database Layer

**Models** (`src/database/models.py`):
- `Position` - Active positions with multi-source tracking
- `LimitOrder` - Take-profit/stop-loss order tracking
- `TradeHistory` - Closed trades
- `Settings` - Key-value configuration
- `MarketSignal` - Detected trading signals
- `BotStatus` - Bot state tracking
- `KeyboardTemplate`, `KeyboardButton`, `KeyboardState` - Dynamic keyboards

**Repositories** (`src/database/repository.py`):
- Repository pattern for all CRUD operations
- One repository class per model
- Handles session management

**Migration System** (`src/database/migrations/migration_manager.py`):
- Automatic migrations on startup
- SQL files in `src/database/migrations/scripts/`
- Versioned with checksums: `V{XXX}__{description}.sql`
- Creates backup before each migration

### Configuration

**Environment Variables** (`.env` file):
- All configuration via environment variables
- Copy `.env.example` to `.env` to start
- Critical: Binance API keys, Telegram bot token, trading parameters
- Runtime settings can be changed via Telegram commands

**Config System** (`src/config.py`):
- Dataclass-based configuration with validation
- Global singleton pattern via `get_config()`
- Separate configs for: Binance, Telegram, Database, Trading, Scanner, Scheduler, Logging

## Development Patterns

### Thread Safety

The TradingEngine uses per-symbol locks to prevent race conditions when multiple threads try to trade the same symbol simultaneously. Always acquire the symbol lock before position operations:

```python
symbol_lock = self._get_symbol_lock(symbol)
if symbol_lock.acquire(blocking=False):
    try:
        # Position operations here
        pass
    finally:
        symbol_lock.release()
```

### Multi-Source Position Tracking

Positions have a `source` field (`bot_auto`, `manual`, `external_system`) to track origin. This enables:
- Bot-managed positions vs manually opened positions
- External system integration
- Different handling per source type

See `docs/architecture/POSITION_TRACKING.md` for details.

### Database Sessions

Use function-scoped sessions from fixtures in tests. In production code, sessions are managed at the component level (engine, managers, repositories).

### Testing Strategy

- **160+ tests** with ~90% coverage across core modules
- Use `conftest.py` fixtures for common setups
- Mock external dependencies (Binance client, Telegram)
- Test database operations with in-memory SQLite
- Parametrized tests for different scenarios
- Factory functions for creating test objects

Key test fixtures:
- `test_db_session` - Clean in-memory database per test
- `mock_binance_client` - Mocked exchange client
- `test_config` - Standard test configuration
- `position_factory` / `limit_order_factory` - Object creation helpers

### Logging

Use structured logging throughout:

```python
import logging
logger = logging.getLogger(__name__)

logger.debug("Detailed info")
logger.info("Important event")
logger.warning("Warning")
logger.error("Error occurred")
logger.exception("Error with traceback")
```

Log level controlled via `LOG_LEVEL` in `.env`.

### Error Handling

- Gracefully handle exchange API errors
- Log errors with context
- Continue operation when possible
- Report critical errors to Telegram

## Key Implementation Details

### Position Opening Flow

1. Scanner finds signals meeting criteria
2. RiskManager validates limits
3. TradingEngine acquires symbol lock
4. PositionManager opens market order
5. PositionManager places take-profit limit order
6. Position saved to database
7. Lock released
8. Telegram notification sent

### Position Closing Flow

1. LimitOrderMonitor checks order status
2. When take-profit fills: position marked as closed
3. P&L calculated and saved
4. Trade moved to history
5. Telegram notification sent

### Keyboard System

Dynamic keyboards are stored in database and built at runtime:
- Templates define keyboard structure
- Buttons reference actions/callbacks
- State tracking per user enables context-aware buttons
- Initialized in `src/bot/keyboard_init.py` on startup

### Exchange Client

Uses CCXT library (`src/exchange/binance_client.py`):
- Wraps CCXT with bot-specific methods
- Supports testnet and production
- Methods for positions, orders, market data
- Error handling for API failures

## CI/CD

GitHub Actions workflows in `.github/workflows/`:
- **tests.yml** - Run pytest on Python 3.10, 3.11, 3.12
- **code-quality.yml** - Linting, formatting, type checking
- **deploy.yml** - Deployment automation

Tests run on push to main/develop and on PRs.

## Important Files

- `src/main.py` - Entry point
- `src/trading/engine.py` - Core trading logic coordinator
- `src/bot/telegram_bot.py` - Telegram interface
- `src/database/models.py` - Database schema
- `tests/conftest.py` - Test fixtures and configuration
- `.env.example` - Configuration template
- `pyproject.toml` - Tool configuration (black, isort, mypy, pytest, coverage)

## Common Tasks

### Adding a Telegram Command

1. Add handler in `src/bot/commands.py`
2. Register in `src/bot/telegram_bot.py` with `CommandHandler`
3. Add tests in `tests/test_commands.py`

### Adding a Callback Handler

1. Add handler in `src/bot/callback_handler.py`
2. Register with `self.register('action_name', self.handler_method)`
3. Decorate with `@log_callback` for logging
4. Add tests in `tests/test_callback_handler.py`

### Adding a Database Table

1. Add model in `src/database/models.py`
2. Create migration SQL in `src/database/migrations/scripts/V{XXX}__description.sql`
3. Add repository in `src/database/repository.py`
4. Add tests in `tests/test_database_models.py` and `tests/test_database_repository.py`
5. Restart bot - migration applies automatically

### Modifying Scanner Logic

1. Update detection logic in `src/strategy/detector.py`
2. Update scanner in `src/strategy/scanner.py`
3. Add comprehensive tests
4. Test on testnet first

## Code Style

- **Line length**: 127 characters (configured in pyproject.toml)
- **Formatter**: black with line-length=127
- **Import sorting**: isort with black profile
- **Type hints**: Encouraged but not required (mypy with loose settings)
- **Docstrings**: Use for public APIs and complex logic
- **Comments**: Russian comments acceptable in Russian documentation, English in code

## Testing on Testnet

1. Get testnet API keys from https://testnet.binancefuture.com/
2. Set `BINANCE_TESTNET=true` in `.env`
3. Use testnet keys in `.env`
4. Run bot normally - it connects to testnet

## Security Notes

- Never commit `.env` file (in `.gitignore`)
- Store API keys securely
- Use IP whitelist on Binance for API keys
- Limit API key permissions to futures trading only
- Test on testnet before production

## Documentation Structure

- `README.md` - Main documentation (Russian)
- `docs/QUICKSTART.md` - Quick start guide
- `docs/DEVELOPMENT.md` - Developer guide with detailed instructions
- `docs/architecture/` - Technical architecture documents
  - `KEYBOARD_SYSTEM.md` - Dynamic keyboard system
  - `POSITION_TRACKING.md` - Position management details
  - `TESTING.md` - Testing documentation
- `docs/CI_CD.md` - CI/CD documentation
- `DEPLOYMENT.md` - Server deployment guide
- `SSH-SETUP.md` - SSH access configuration

## Troubleshooting

### Tests Failing

- Check test database isolation - each test should use clean `test_db_session`
- Verify mocks are properly configured
- Check for race conditions in async code
- Run single test with `-v -s` for detailed output

### Bot Not Trading

- Check risk limits: max_positions, max_total_margin
- Verify bot not paused: `/resume` in Telegram
- Check scanner finds signals: `/scan` manually
- Review logs for errors

### Database Issues

- Migrations apply automatically - check logs for errors
- Backups created before migrations in `data/`
- For corruption, restore from backup
- Check schema with `sqlite3 data/topshort.db .schema`

### Exchange API Errors

- Verify API keys are correct
- Check testnet vs production mode
- Verify IP whitelist on Binance
- Check API key permissions
- Review rate limits

## Performance Considerations

- SQLite is sufficient for single-bot deployment
- Thread-safe position operations via per-symbol locks
- In-memory caching for frequently accessed settings
- Async Telegram handlers for responsiveness
- Efficient database queries with proper indexes

## Future Extensions

The codebase is designed for extensibility:
- Add new strategies by implementing scanner variants
- Support long positions (infrastructure exists)
- Add more sophisticated risk management
- Integrate additional exchanges (CCXT abstraction)
- Add web dashboard (database-driven design supports it)

## General rules
- use context7 mcp for brings up-to-date, version-specific documentation and code examples
- execute scripts/run_ci_locally.sh after complete the task to ensure the code is working as expected
- write tests for all new code
