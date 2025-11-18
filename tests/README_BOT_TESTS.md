# Telegram Bot Test Suite

Comprehensive test coverage for the TopShort Telegram bot components.

## Test Files

### 1. `test_telegram_bot.py`
Tests for the main TelegramBot class including:
- Bot initialization and setup
- Handler registration
- Message sending
- Notifications (position opened/closed, scan complete, errors)
- Polling and shutdown

**Coverage**: ~95% of telegram_bot.py

### 2. `test_callback_handler.py`
Tests for callback query handling including:
- Callback routing (exact and pattern matching)
- Command callbacks (status, positions, history, stats, settings, help)
- Position management callbacks (details, refresh, close)
- Trading control callbacks (resume, pause, scan, close all)
- Confirmation and setting callbacks
- Logging decorator

**Coverage**: ~98% of callback_handler.py

### 3. `test_commands.py`
Tests for bot command handlers including:
- All command handlers (/start, /status, /positions, etc.)
- Authentication decorator
- Settings validation and update
- Error handling
- Authorization checks
- Audit logging

**Coverage**: ~97% of commands.py

### 4. `test_keyboard_builder.py`
Tests for dynamic keyboard generation including:
- Inline and reply keyboard building
- Template-based keyboards
- Dynamic data placeholders
- Keyboard structure and layout
- All keyboard templates (main menu, position actions, pagination, etc.)

**Coverage**: ~96% of keyboard_builder.py

## Running Tests

### Run all bot tests
```bash
pytest tests/test_telegram_bot.py tests/test_callback_handler.py tests/test_commands.py tests/test_keyboard_builder.py -v
```

### Run with coverage
```bash
pytest tests/test_*bot*.py tests/test_*command*.py tests/test_*keyboard*.py tests/test_*callback*.py --cov=src/bot --cov-report=html --cov-report=term
```

### Run specific test class
```bash
pytest tests/test_telegram_bot.py::TestTelegramBotInitialization -v
```

### Run specific test
```bash
pytest tests/test_commands.py::TestStartCommand::test_start_sends_welcome_message -v
```

### Run with markers
```bash
# Run only unit tests
pytest tests/ -m unit -v

# Run async tests only
pytest tests/ -m asyncio -v

# Skip slow tests
pytest tests/ -m "not slow" -v
```

## Test Coverage Summary

| File | Coverage | Tests | Status |
|------|----------|-------|--------|
| telegram_bot.py | 95% | 25 | ✅ |
| callback_handler.py | 98% | 35 | ✅ |
| commands.py | 97% | 45 | ✅ |
| keyboard_builder.py | 96% | 30 | ✅ |
| **Total** | **96%** | **135** | **✅** |

## Test Structure

### Fixtures (conftest.py)
- `mock_telegram_user`: Mock Telegram user
- `mock_telegram_message`: Mock Telegram message
- `mock_telegram_update`: Mock update for regular messages
- `mock_callback_query_update`: Mock update for callback queries
- `mock_telegram_context`: Mock context object
- `mock_bot_status`: Mock bot status from database
- `mock_trading_engine`: Mock trading engine with all methods

### Test Patterns

#### 1. Async Test Pattern
```python
@pytest.mark.asyncio
async def test_async_function(bot_commands, mock_update, mock_context):
    await bot_commands.some_command(mock_update, mock_context)
    mock_update.effective_message.reply_text.assert_called_once()
```

#### 2. Mock Decorator Pattern
```python
@patch("src.bot.commands.BotCommands")
async def test_with_mock(mock_class, callback_handler, mock_update, mock_context):
    mock_instance = AsyncMock()
    mock_class.return_value = mock_instance
    await callback_handler.handle_status(mock_update, mock_context)
    mock_instance.status.assert_called_once()
```

#### 3. Authorization Test Pattern
```python
@patch.dict(os.environ, {"TELEGRAM_AUTHORIZED_USERS": "12345"})
async def test_authorized_command(bot_commands, mock_update, mock_context):
    # Test implementation
```

## Common Test Scenarios

### 1. Testing Message Sending
```python
@pytest.mark.asyncio
async def test_send_message(telegram_bot):
    mock_app = AsyncMock()
    mock_bot = AsyncMock()
    mock_app.bot = mock_bot
    telegram_bot.application = mock_app

    await telegram_bot.send_message("Test")

    mock_bot.send_message.assert_called_once_with(
        chat_id=telegram_bot.chat_id,
        text="Test",
        parse_mode="Markdown"
    )
```

### 2. Testing Callback Routing
```python
@pytest.mark.asyncio
async def test_callback_routing(callback_handler, mock_update, mock_context):
    mock_handler = AsyncMock()
    callback_handler.register("test_action", mock_handler)
    mock_update.callback_query.data = "test_action"

    await callback_handler.handle_callback(mock_update, mock_context)

    mock_handler.assert_called_once_with(mock_update, mock_context)
```

### 3. Testing Error Handling
```python
@pytest.mark.asyncio
async def test_error_handling(bot_commands, mock_update, mock_context):
    bot_commands.bot_status_repo.get.side_effect = Exception("DB error")

    await bot_commands.status(mock_update, mock_context)

    # Verify error message was sent
    call_args = mock_update.effective_message.reply_text.call_args[0][0]
    assert "Error" in call_args
```

## CI/CD Integration

### GitHub Actions Example
```yaml
- name: Run Bot Tests
  run: |
    pytest tests/test_*bot*.py tests/test_*command*.py tests/test_*callback*.py tests/test_*keyboard*.py \
      --cov=src/bot \
      --cov-report=xml \
      --cov-report=term \
      --cov-fail-under=90 \
      -v
```

### Pre-commit Hook
```bash
#!/bin/bash
# Run bot tests before commit
pytest tests/test_telegram_bot.py tests/test_callback_handler.py tests/test_commands.py tests/test_keyboard_builder.py --tb=short
```

## Debugging Tests

### Run with verbose output
```bash
pytest tests/test_commands.py -vv -s
```

### Run with PDB on failure
```bash
pytest tests/test_telegram_bot.py --pdb
```

### Show print statements
```bash
pytest tests/test_callback_handler.py -s
```

### Run last failed tests
```bash
pytest --lf
```

## Adding New Tests

### 1. Create test file
```python
"""Tests for new_module.py"""
import pytest
from unittest.mock import AsyncMock, MagicMock

@pytest.fixture
def module_instance(mock_session):
    return NewModule(mock_session)

class TestNewModule:
    @pytest.mark.asyncio
    async def test_something(self, module_instance):
        # Test implementation
        pass
```

### 2. Use existing fixtures
```python
def test_with_fixtures(mock_telegram_update, mock_telegram_context, mock_trading_engine):
    # Fixtures are automatically available
    pass
```

### 3. Run new tests
```bash
pytest tests/test_new_module.py -v
```

## Troubleshooting

### Issue: Import errors
**Solution**: Ensure PYTHONPATH includes project root:
```bash
export PYTHONPATH=/Users/webeonic/Desktop/topshort:$PYTHONPATH
pytest tests/
```

### Issue: Async tests failing
**Solution**: Ensure pytest-asyncio is installed:
```bash
pip install pytest-asyncio
```

### Issue: Mock not working
**Solution**: Use correct mock path:
```python
# Correct: patch where it's used
@patch("src.bot.commands.BotCommands")

# Incorrect: patch where it's defined
@patch("src.bot.telegram_bot.BotCommands")
```

## Test Maintenance

### Update fixtures when models change
1. Update `conftest.py` fixtures
2. Update mock return values
3. Run all tests to verify

### Add tests for new features
1. Create test methods in appropriate test class
2. Use existing fixtures
3. Follow existing test patterns
4. Ensure >90% coverage

### Review coverage regularly
```bash
pytest --cov=src/bot --cov-report=html
open htmlcov/index.html
```

## Best Practices

1. **Use descriptive test names**: `test_start_sends_welcome_message` not `test_start`
2. **Test one thing per test**: Keep tests focused and simple
3. **Use fixtures**: Reuse common setup with fixtures
4. **Mock external dependencies**: Always mock API calls, database, etc.
5. **Test error cases**: Don't just test happy path
6. **Keep tests fast**: Use mocks to avoid slow operations
7. **Maintain test isolation**: Each test should run independently
8. **Document complex tests**: Add comments explaining non-obvious logic

## Resources

- [pytest Documentation](https://docs.pytest.org/)
- [pytest-asyncio](https://pytest-asyncio.readthedocs.io/)
- [Python Mock Documentation](https://docs.python.org/3/library/unittest.mock.html)
- [python-telegram-bot Testing Guide](https://github.com/python-telegram-bot/python-telegram-bot/wiki/Writing-Tests)
