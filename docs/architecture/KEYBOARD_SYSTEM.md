# Dynamic Keyboard System Documentation

## Overview

The TopShort Trading Bot now features a comprehensive dynamic keyboard system that provides interactive inline keyboards for user interactions. This system allows for flexible, database-driven keyboard configurations that can be easily customized and extended.

## Features

- ✅ **Dynamic Inline Keyboards** - Database-driven keyboard templates
- ✅ **Callback Handler System** - Comprehensive callback routing and processing
- ✅ **State Tracking** - Per-user keyboard state management
- ✅ **Analytics Logging** - All interactions logged for analytics
- ✅ **Template System** - Pre-defined keyboard templates
- ✅ **Runtime Customization** - Placeholders for dynamic data
- ✅ **Automatic Migration** - Database schema auto-applied on startup

## Architecture

### Components

1. **Database Models** (`src/database/models.py`)
   - `KeyboardTemplate` - Template definitions
   - `KeyboardButton` - Individual button configurations
   - `KeyboardState` - User state tracking
   - `CallbackLog` - Interaction analytics

2. **Repositories** (`src/database/repository.py`)
   - `KeyboardTemplateRepository` - Template CRUD operations
   - `KeyboardButtonRepository` - Button management
   - `KeyboardStateRepository` - State management
   - `CallbackLogRepository` - Analytics and logging

3. **Keyboard Builder** (`src/bot/keyboard_builder.py`)
   - `KeyboardBuilder` - Build keyboards from templates
   - `KeyboardTemplates` - Pre-defined template functions

4. **Callback Handler** (`src/bot/callback_handler.py`)
   - `CallbackHandler` - Route and process callbacks
   - Decorators for logging and error handling

5. **Initialization** (`src/bot/keyboard_init.py`)
   - `init_keyboard_templates()` - Initialize default templates

## Usage

### 1. Using Pre-defined Keyboards

```python
from src.bot.keyboard_builder import KeyboardBuilder, KeyboardTemplates

# Initialize builder
builder = KeyboardBuilder(session)

# Build main menu from template
keyboard = builder.build_inline_keyboard_from_template('main_menu')

# Send message with keyboard
await update.message.reply_text(
    "Choose an action:",
    reply_markup=keyboard
)
```

### 2. Creating Custom Keyboards Programmatically

```python
# Using KeyboardTemplates helper
buttons_data = KeyboardTemplates.main_menu()
keyboard = builder.create_inline_keyboard(buttons_data, n_cols=2)

# Or manually
buttons_data = [
    {'text': 'Button 1', 'callback_data': 'action1'},
    {'text': 'Button 2', 'callback_data': 'action2'},
]
keyboard = builder.create_inline_keyboard(buttons_data)
```

### 3. Dynamic Data in Keyboards

```python
# Build keyboard with dynamic data
dynamic_data = {
    'symbol': 'BTCUSDT',
    'price': '45000.00'
}

keyboard = builder.build_inline_keyboard_from_template(
    'position_actions',
    dynamic_data=dynamic_data,
    user_id=str(user.id),
    chat_id=str(chat.id)
)
```

### 4. Handling Callbacks

Callbacks are automatically routed by the `CallbackHandler`:

```python
# In callback_handler.py

# Register exact match handler
self.register('cmd_status', self.handle_status)

# Register pattern match handler
self.register_pattern('pos_details_', self.handle_position_details)
```

## Available Keyboard Templates

### 1. Main Menu (`main_menu`)
Primary navigation menu with all main commands.

Buttons:
- 📊 Status
- 💼 Positions
- 📜 History
- 📈 Stats
- ⚙️ Settings
- ❓ Help

### 2. Trading Controls (`trading_controls`)
Trading operation controls.

Buttons:
- ▶️ Resume
- ⏸️ Pause
- 🔍 Scan Now
- ❌ Close All
- 🔙 Back

### 3. Settings Menu (`settings_menu`)
Configuration options.

Buttons:
- 💰 Margin
- 📊 Max Positions
- 📈 Leverage
- 🎯 Take Profit
- 🔥 Pump Threshold
- 🔙 Back

### 4. Position Actions (`position_actions`)
Actions for individual positions (dynamic).

Buttons:
- 📊 Details
- 🔄 Refresh
- ❌ Close
- 🔙 Back

### 5. Confirmation (`confirmation`)
Generic confirmation dialog.

Buttons:
- ✅ Confirm
- ❌ Cancel

## Database Schema

### keyboard_templates
```sql
id INTEGER PRIMARY KEY
name VARCHAR(100) UNIQUE
description TEXT
keyboard_type VARCHAR(20) -- 'inline' or 'reply'
keyboard_data TEXT -- JSON
is_active BOOLEAN
created_at DATETIME
updated_at DATETIME
```

### keyboard_buttons
```sql
id INTEGER PRIMARY KEY
template_id INTEGER FK
label VARCHAR(100)
callback_data VARCHAR(200)
url VARCHAR(500)
row_position INTEGER
column_position INTEGER
button_type VARCHAR(30) -- 'callback', 'url', 'text'
action VARCHAR(100)
action_params TEXT -- JSON
is_active BOOLEAN
created_at DATETIME
updated_at DATETIME
```

### keyboard_states
```sql
id INTEGER PRIMARY KEY
user_id VARCHAR(50)
chat_id VARCHAR(50)
current_keyboard VARCHAR(100)
state_data TEXT -- JSON
last_interaction_at DATETIME
created_at DATETIME
updated_at DATETIME
UNIQUE(user_id, chat_id)
```

### callback_logs
```sql
id INTEGER PRIMARY KEY
user_id VARCHAR(50)
username VARCHAR(100)
chat_id VARCHAR(50)
callback_data VARCHAR(200)
action VARCHAR(100)
success BOOLEAN
error_message TEXT
response_time_ms INTEGER
created_at DATETIME
```

## Callback Data Conventions

### Command Callbacks
- `cmd_status` - Show bot status
- `cmd_positions` - Show open positions
- `cmd_history` - Show trade history
- `cmd_stats` - Show statistics
- `cmd_settings` - Show settings
- `cmd_help` - Show help

### Position Callbacks
- `pos_details_<symbol>` - Show position details
- `pos_refresh_<symbol>` - Refresh position data
- `pos_close_<symbol>` - Close position

### Trading Control Callbacks
- `trading_resume` - Resume trading
- `trading_pause` - Pause trading
- `trading_scan` - Manual market scan
- `trading_closeall` - Close all positions

### Utility Callbacks
- `confirm_<action>_<data>` - Confirm action
- `cancel` - Cancel action
- `noop` - No operation (display only)
- `page_<number>` - Pagination

## Creating New Templates

### 1. Database Method

```python
from src.database.repository import KeyboardTemplateRepository, KeyboardButtonRepository

template_repo = KeyboardTemplateRepository(session)
button_repo = KeyboardButtonRepository(session)

# Create template
template = template_repo.create(
    name='my_custom_menu',
    keyboard_type='inline',
    description='My custom menu',
    keyboard_data={'layout': 'grid', 'columns': 2}
)

# Add buttons
button_repo.create(
    template_id=template.id,
    label='Button 1',
    callback_data='action1',
    row_position=0,
    column_position=0,
    button_type='callback',
    action='perform_action1'
)
```

### 2. Migration Method

Add to `keyboard_init.py`:

```python
# Create template
custom_menu = template_repo.create(
    name='custom_menu',
    keyboard_type='inline',
    description='Custom menu'
)

# Define buttons
buttons = [
    ('Label 1', 'callback1', 0, 0, 'action1'),
    ('Label 2', 'callback2', 0, 1, 'action2'),
]

for label, callback_data, row, col, action in buttons:
    button_repo.create(
        template_id=custom_menu.id,
        label=label,
        callback_data=callback_data,
        row_position=row,
        column_position=col,
        button_type='callback',
        action=action
    )
```

## Adding New Callback Handlers

In `callback_handler.py`:

```python
# 1. Register in _register_default_handlers()
self.register('my_action', self.handle_my_action)
# or for patterns
self.register_pattern('my_prefix_', self.handle_my_pattern)

# 2. Implement handler
@log_callback(success=True)
async def handle_my_action(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle my custom action."""
    query = update.callback_query

    # Your logic here
    await query.edit_message_text("Action completed!")
```

## Testing

### Manual Testing Commands

```bash
# Start bot
python -m src.main

# In Telegram:
/start     # Should show welcome with keyboard
/menu      # Should show interactive menu
# Click any button to test callbacks
```

### Verify Database

```bash
# Check migration applied
sqlite3 data/topshort.db "SELECT * FROM schema_migrations WHERE version='V002';"

# Check templates created
sqlite3 data/topshort.db "SELECT * FROM keyboard_templates;"

# Check buttons
sqlite3 data/topshort.db "SELECT * FROM keyboard_buttons;"
```

## Analytics

### View Callback Logs

```python
from src.database.repository import CallbackLogRepository

log_repo = CallbackLogRepository(session)

# Get user interactions
interactions = log_repo.get_user_interactions(user_id='123456', limit=50)

# Get action statistics
stats = log_repo.get_action_stats(action='show_status', days=7)
print(f"Success rate: {stats['success_rate']:.2f}%")
```

### Query Database Directly

```sql
-- Most used actions
SELECT action, COUNT(*) as count
FROM callback_logs
WHERE created_at >= datetime('now', '-7 days')
GROUP BY action
ORDER BY count DESC
LIMIT 10;

-- Average response time
SELECT action, AVG(response_time_ms) as avg_ms
FROM callback_logs
WHERE success = 1
GROUP BY action;

-- Error rate by action
SELECT
    action,
    SUM(CASE WHEN success = 1 THEN 1 ELSE 0 END) as successful,
    SUM(CASE WHEN success = 0 THEN 1 ELSE 0 END) as failed,
    COUNT(*) as total
FROM callback_logs
GROUP BY action;
```

## Best Practices

1. **Callback Data Naming**
   - Use descriptive prefixes (`cmd_`, `pos_`, `trading_`)
   - Keep under 64 characters
   - Use underscores, not spaces

2. **Button Labels**
   - Use emojis for visual clarity
   - Keep text short (max 20 chars)
   - Be consistent across keyboards

3. **Error Handling**
   - Always use `@log_callback` decorator
   - Provide user-friendly error messages
   - Log errors for debugging

4. **Performance**
   - Cache frequently used templates
   - Use pattern matching for dynamic callbacks
   - Index callback_data in logs table

5. **Security**
   - Validate callback data
   - Use `require_auth` decorator for sensitive actions
   - Log all security-relevant actions

## Troubleshooting

### Keyboards Not Showing

1. Check migration applied:
   ```bash
   sqlite3 data/topshort.db "SELECT version FROM schema_migrations;"
   ```

2. Check templates exist:
   ```python
   template = template_repo.get_by_name('main_menu')
   print(template)
   ```

3. Check buttons:
   ```python
   buttons = button_repo.get_by_template(template.id)
   print(len(buttons))
   ```

### Callbacks Not Working

1. Check handler registered:
   ```python
   print(self.handlers.keys())
   ```

2. Check callback_logs for errors:
   ```sql
   SELECT * FROM callback_logs
   WHERE success = 0
   ORDER BY created_at DESC
   LIMIT 10;
   ```

3. Enable debug logging:
   ```python
   logging.getLogger('src.bot.callback_handler').setLevel(logging.DEBUG)
   ```

## Migration

The keyboard system automatically migrates on application startup:

1. Migration file: `src/database/migrations/scripts/V002__add_dynamic_keyboard_system.sql`
2. Automatically applied by: `create_database()` in `models.py`
3. Tracked in: `schema_migrations` table

To manually run migration:
```bash
python -c "from src.database.migrations.migration_manager import run_auto_migrations; run_auto_migrations('data/topshort.db')"
```

## Future Enhancements

Potential improvements:
- Reply keyboard support (currently inline only)
- Keyboard themes/styling
- A/B testing framework
- Keyboard analytics dashboard
- Multi-language support
- Voice command integration
- Keyboard permissions by role

## Support

For issues or questions:
1. Check logs: `logs/topshort.log`
2. Review callback_logs table
3. Verify database schema
4. Check Telegram Bot API limits

---

**Version:** 1.0
**Last Updated:** 2025-01-18
**Author:** TopShort Bot Development Team
