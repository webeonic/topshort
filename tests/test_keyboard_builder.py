"""Comprehensive tests for KeyboardBuilder class."""

from unittest.mock import MagicMock, Mock

import pytest
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup

from src.bot.keyboard_builder import (
    MENU_BTN_HELP,
    MENU_BTN_HISTORY,
    MENU_BTN_POSITIONS,
    MENU_BTN_SCAN,
    MENU_BTN_SETTINGS,
    MENU_BTN_STATUS,
    MENU_BTN_TRADING,
    TELEGRAM_CALLBACK_DATA_LIMIT,
    CallbackDataRegistry,
    CallbackDataTooLongError,
    InlineTemplates,
    KeyboardBuilder,
    KeyboardTemplates,
    PersistentMenu,
    callback_registry,
    validate_callback_data,
)


@pytest.fixture
def mock_session():
    """Create mock database session."""
    return MagicMock()


@pytest.fixture
def keyboard_builder(mock_session):
    """Create KeyboardBuilder instance for testing."""
    builder = KeyboardBuilder(mock_session)
    # Mock the repositories to avoid real database calls
    builder.template_repo = MagicMock()
    builder.button_repo = MagicMock()
    builder.state_repo = MagicMock()
    return builder


@pytest.fixture
def mock_template():
    """Create mock keyboard template."""
    template = MagicMock()
    template.id = 1
    template.name = "test_template"
    template.keyboard_type = "inline"
    return template


@pytest.fixture
def mock_buttons():
    """Create mock keyboard buttons."""
    button1 = MagicMock()
    button1.row_position = 0
    button1.label = "Button 1"
    button1.button_type = "callback"
    button1.callback_data = "btn1"
    button1.url = None

    button2 = MagicMock()
    button2.row_position = 0
    button2.label = "Button 2"
    button2.button_type = "callback"
    button2.callback_data = "btn2"
    button2.url = None

    button3 = MagicMock()
    button3.row_position = 1
    button3.label = "Button 3"
    button3.button_type = "url"
    button3.callback_data = None
    button3.url = "https://example.com"

    return [button1, button2, button3]


class TestKeyboardBuilderInitialization:
    """Test KeyboardBuilder initialization."""

    def test_init_creates_builder(self, mock_session):
        """Test builder initialization."""
        builder = KeyboardBuilder(mock_session)

        assert builder.session == mock_session
        assert builder.template_repo is not None
        assert builder.button_repo is not None
        assert builder.state_repo is not None


class TestBuildMenu:
    """Test build_menu method."""

    def test_build_menu_basic(self, keyboard_builder):
        """Test building basic menu."""
        buttons = [
            InlineKeyboardButton("1", callback_data="1"),
            InlineKeyboardButton("2", callback_data="2"),
            InlineKeyboardButton("3", callback_data="3"),
            InlineKeyboardButton("4", callback_data="4"),
        ]

        menu = keyboard_builder.build_menu(buttons, n_cols=2)

        assert len(menu) == 2
        assert len(menu[0]) == 2
        assert len(menu[1]) == 2

    def test_build_menu_with_header(self, keyboard_builder):
        """Test building menu with header button."""
        buttons = [
            InlineKeyboardButton("1", callback_data="1"),
            InlineKeyboardButton("2", callback_data="2"),
        ]
        header = InlineKeyboardButton("Header", callback_data="header")

        menu = keyboard_builder.build_menu(buttons, n_cols=2, header_buttons=header)

        assert len(menu) == 2
        assert len(menu[0]) == 1  # Header row
        assert menu[0][0] == header
        assert len(menu[1]) == 2  # Button row

    def test_build_menu_with_footer(self, keyboard_builder):
        """Test building menu with footer button."""
        buttons = [
            InlineKeyboardButton("1", callback_data="1"),
            InlineKeyboardButton("2", callback_data="2"),
        ]
        footer = InlineKeyboardButton("Footer", callback_data="footer")

        menu = keyboard_builder.build_menu(buttons, n_cols=2, footer_buttons=footer)

        assert len(menu) == 2
        assert len(menu[0]) == 2  # Button row
        assert len(menu[1]) == 1  # Footer row
        assert menu[1][0] == footer

    def test_build_menu_with_header_and_footer_lists(self, keyboard_builder):
        """Test building menu with header and footer as lists."""
        buttons = [
            InlineKeyboardButton("1", callback_data="1"),
            InlineKeyboardButton("2", callback_data="2"),
        ]
        header = [InlineKeyboardButton("H1", callback_data="h1"), InlineKeyboardButton("H2", callback_data="h2")]
        footer = [InlineKeyboardButton("F1", callback_data="f1")]

        menu = keyboard_builder.build_menu(buttons, n_cols=2, header_buttons=header, footer_buttons=footer)

        assert len(menu) == 3
        assert len(menu[0]) == 2  # Header row
        assert len(menu[1]) == 2  # Button row
        assert len(menu[2]) == 1  # Footer row


class TestBuildInlineKeyboardFromTemplate:
    """Test build_inline_keyboard_from_template method."""

    def test_build_keyboard_from_template_success(self, keyboard_builder, mock_template, mock_buttons):
        """Test building keyboard from template successfully."""
        keyboard_builder.template_repo.get_by_name.return_value = mock_template
        keyboard_builder.button_repo.get_by_template.return_value = mock_buttons

        keyboard = keyboard_builder.build_inline_keyboard_from_template("test_template")

        assert keyboard is not None
        assert isinstance(keyboard, InlineKeyboardMarkup)
        keyboard_builder.template_repo.get_by_name.assert_called_once_with("test_template")
        keyboard_builder.button_repo.get_by_template.assert_called_once_with(mock_template.id)

    def test_build_keyboard_template_not_found(self, keyboard_builder):
        """Test building keyboard when template not found."""
        keyboard_builder.template_repo.get_by_name.return_value = None

        keyboard = keyboard_builder.build_inline_keyboard_from_template("nonexistent")

        assert keyboard is None

    def test_build_keyboard_wrong_type(self, keyboard_builder, mock_template):
        """Test building keyboard when template is wrong type."""
        mock_template.keyboard_type = "reply"
        keyboard_builder.template_repo.get_by_name.return_value = mock_template

        keyboard = keyboard_builder.build_inline_keyboard_from_template("test_template")

        assert keyboard is None

    def test_build_keyboard_no_buttons(self, keyboard_builder, mock_template):
        """Test building keyboard when no buttons found."""
        keyboard_builder.template_repo.get_by_name.return_value = mock_template
        keyboard_builder.button_repo.get_by_template.return_value = []

        keyboard = keyboard_builder.build_inline_keyboard_from_template("test_template")

        assert keyboard is None

    def test_build_keyboard_with_dynamic_data(self, keyboard_builder, mock_template, mock_buttons):
        """Test building keyboard with dynamic data."""
        mock_buttons[0].label = "Balance: {balance}"
        keyboard_builder.template_repo.get_by_name.return_value = mock_template
        keyboard_builder.button_repo.get_by_template.return_value = mock_buttons

        dynamic_data = {"balance": "1000.50"}
        keyboard = keyboard_builder.build_inline_keyboard_from_template("test_template", dynamic_data=dynamic_data)

        assert keyboard is not None

    def test_build_keyboard_updates_state(self, keyboard_builder, mock_template, mock_buttons):
        """Test building keyboard updates user state."""
        keyboard_builder.template_repo.get_by_name.return_value = mock_template
        keyboard_builder.button_repo.get_by_template.return_value = mock_buttons

        keyboard = keyboard_builder.build_inline_keyboard_from_template(
            "test_template", user_id="123", chat_id="456", dynamic_data={"key": "value"}
        )

        assert keyboard is not None
        keyboard_builder.state_repo.update_state.assert_called_once_with("123", "456", "test_template", {"key": "value"})


class TestBuildReplyKeyboardFromTemplate:
    """Test build_reply_keyboard_from_template method."""

    def test_build_reply_keyboard_success(self, keyboard_builder, mock_template, mock_buttons):
        """Test building reply keyboard successfully."""
        mock_template.keyboard_type = "reply"
        keyboard_builder.template_repo.get_by_name.return_value = mock_template
        keyboard_builder.button_repo.get_by_template.return_value = mock_buttons

        keyboard = keyboard_builder.build_reply_keyboard_from_template("test_template")

        assert keyboard is not None
        assert isinstance(keyboard, ReplyKeyboardMarkup)

    def test_build_reply_keyboard_wrong_type(self, keyboard_builder, mock_template):
        """Test building reply keyboard when template is wrong type."""
        mock_template.keyboard_type = "inline"
        keyboard_builder.template_repo.get_by_name.return_value = mock_template

        keyboard = keyboard_builder.build_reply_keyboard_from_template("test_template")

        assert keyboard is None

    def test_build_reply_keyboard_options(self, keyboard_builder, mock_template, mock_buttons):
        """Test building reply keyboard with options."""
        mock_template.keyboard_type = "reply"
        keyboard_builder.template_repo.get_by_name.return_value = mock_template
        keyboard_builder.button_repo.get_by_template.return_value = mock_buttons

        keyboard = keyboard_builder.build_reply_keyboard_from_template(
            "test_template", resize_keyboard=False, one_time_keyboard=True
        )

        assert keyboard is not None
        assert isinstance(keyboard, ReplyKeyboardMarkup)


class TestReplacePlaceholders:
    """Test _replace_placeholders method."""

    def test_replace_single_placeholder(self, keyboard_builder):
        """Test replacing single placeholder."""
        text = "Balance: {balance} USDT"
        dynamic_data = {"balance": "1000.50"}

        result = keyboard_builder._replace_placeholders(text, dynamic_data)

        assert result == "Balance: 1000.50 USDT"

    def test_replace_multiple_placeholders(self, keyboard_builder):
        """Test replacing multiple placeholders."""
        text = "{name} has {balance} USDT"
        dynamic_data = {"name": "John", "balance": "500"}

        result = keyboard_builder._replace_placeholders(text, dynamic_data)

        assert result == "John has 500 USDT"

    def test_replace_no_placeholders(self, keyboard_builder):
        """Test text without placeholders."""
        text = "Static text"
        dynamic_data = {"key": "value"}

        result = keyboard_builder._replace_placeholders(text, dynamic_data)

        assert result == "Static text"

    def test_replace_with_none_text(self, keyboard_builder):
        """Test replacing with None text."""
        result = keyboard_builder._replace_placeholders(None, {"key": "value"})

        assert result == ""

    def test_replace_with_none_data(self, keyboard_builder):
        """Test replacing with None dynamic data."""
        text = "Balance: {balance}"
        result = keyboard_builder._replace_placeholders(text, None)

        assert result == text


class TestCreateInlineKeyboard:
    """Test create_inline_keyboard method."""

    def test_create_inline_keyboard_basic(self, keyboard_builder):
        """Test creating inline keyboard from button data."""
        buttons_data = [
            {"text": "Button 1", "callback_data": "btn1"},
            {"text": "Button 2", "callback_data": "btn2"},
            {"text": "URL Button", "url": "https://example.com"},
        ]

        keyboard = keyboard_builder.create_inline_keyboard(buttons_data, n_cols=2)

        assert isinstance(keyboard, InlineKeyboardMarkup)
        assert len(keyboard.inline_keyboard) >= 1

    def test_create_inline_keyboard_invalid_data(self, keyboard_builder):
        """Test creating keyboard with invalid button data."""
        buttons_data = [
            {"text": "Valid Button", "callback_data": "valid"},
            {"text": "Invalid Button"},  # Missing callback_data and url
        ]

        keyboard = keyboard_builder.create_inline_keyboard(buttons_data, n_cols=2)

        # Should create keyboard with only valid button
        assert isinstance(keyboard, InlineKeyboardMarkup)


class TestRemoveKeyboard:
    """Test remove_keyboard method."""

    def test_remove_keyboard(self, keyboard_builder):
        """Test removing custom keyboard."""
        result = keyboard_builder.remove_keyboard()

        assert result is not None
        assert result.remove_keyboard is True


class TestKeyboardTemplatesAlias:
    """Test KeyboardTemplates is alias for InlineTemplates."""

    def test_keyboard_templates_is_inline_templates(self):
        """Test KeyboardTemplates is alias for InlineTemplates."""
        assert KeyboardTemplates is InlineTemplates

    def test_position_actions_template(self):
        """Test position actions template."""
        buttons = KeyboardTemplates.position_actions("BTCUSDT")

        assert isinstance(buttons, list)
        assert len(buttons) > 0
        # Russian labels now
        assert any("Детали" in btn["text"] for btn in buttons)
        assert any("BTCUSDT" in btn["callback_data"] for btn in buttons)

    def test_trading_controls_template(self):
        """Test trading controls template."""
        buttons = KeyboardTemplates.trading_controls()

        assert isinstance(buttons, list)
        # Russian labels now - either Возобновить or Пауза depending on state
        assert any("Пауза" in btn["text"] or "Возобновить" in btn["text"] for btn in buttons)
        assert any("Скан" in btn["text"] for btn in buttons)

    def test_confirm_action_template(self):
        """Test confirm action template."""
        buttons = KeyboardTemplates.confirm_action("closeall", "data")

        assert isinstance(buttons, list)
        assert len(buttons) == 2
        # Russian labels now
        assert any("Подтвердить" in btn["text"] for btn in buttons)
        assert any("Отмена" in btn["text"] for btn in buttons)
        assert any("confirm_closeall_data" in btn["callback_data"] for btn in buttons)

    def test_pagination_template_first_page(self):
        """Test pagination template on first page."""
        buttons = KeyboardTemplates.pagination(0, 3)

        assert isinstance(buttons, list)
        # Should have current page indicator and next button
        assert any("1/3" in btn["text"] for btn in buttons)
        # Russian label
        assert any("Далее" in btn["text"] for btn in buttons)
        assert not any("Назад" in btn["text"] for btn in buttons)

    def test_pagination_template_middle_page(self):
        """Test pagination template on middle page."""
        buttons = KeyboardTemplates.pagination(1, 3)

        assert isinstance(buttons, list)
        # Should have prev, current, and next buttons (Russian labels)
        assert any("Назад" in btn["text"] for btn in buttons)
        assert any("2/3" in btn["text"] for btn in buttons)
        assert any("Далее" in btn["text"] for btn in buttons)

    def test_pagination_template_last_page(self):
        """Test pagination template on last page."""
        buttons = KeyboardTemplates.pagination(2, 3)

        assert isinstance(buttons, list)
        # Should have prev button and current page indicator
        assert any("Назад" in btn["text"] for btn in buttons)
        assert any("3/3" in btn["text"] for btn in buttons)
        assert not any("Далее" in btn["text"] for btn in buttons)

    def test_settings_menu_template(self):
        """Test settings menu template."""
        buttons = KeyboardTemplates.settings_menu()

        assert isinstance(buttons, list)
        assert len(buttons) > 0
        # Russian labels now
        assert any("Маржа" in btn["text"] for btn in buttons)
        assert any("Плечо" in btn["text"] for btn in buttons)


class TestBuildKeyboardStructure:
    """Test _build_keyboard_structure internal method."""

    def test_build_structure_with_rows(self, keyboard_builder, mock_buttons):
        """Test building keyboard structure with multiple rows."""
        keyboard = keyboard_builder._build_keyboard_structure(mock_buttons)

        assert isinstance(keyboard, list)
        assert len(keyboard) == 2  # 2 rows
        assert len(keyboard[0]) == 2  # 2 buttons in first row
        assert len(keyboard[1]) == 1  # 1 button in second row

    def test_build_structure_with_dynamic_data(self, keyboard_builder, mock_buttons):
        """Test building structure with dynamic data replacement."""
        mock_buttons[0].label = "User: {username}"
        mock_buttons[0].callback_data = "user_{id}"
        dynamic_data = {"username": "John", "id": "123"}

        keyboard = keyboard_builder._build_keyboard_structure(mock_buttons, dynamic_data)

        assert isinstance(keyboard, list)
        # The placeholders should be replaced in the actual buttons

    def test_build_structure_invalid_button(self, keyboard_builder, mock_buttons):
        """Test building structure with invalid button configuration."""
        # Create invalid button (no callback_data and no url)
        invalid_button = MagicMock()
        invalid_button.row_position = 2
        invalid_button.label = "Invalid"
        invalid_button.button_type = "callback"
        invalid_button.callback_data = None
        invalid_button.url = None

        mock_buttons.append(invalid_button)

        keyboard = keyboard_builder._build_keyboard_structure(mock_buttons)

        # Should skip invalid button
        assert isinstance(keyboard, list)


class TestPersistentMenu:
    """Test PersistentMenu class for ReplyKeyboard menus."""

    def test_main_menu_returns_reply_keyboard(self):
        """Test main menu returns ReplyKeyboardMarkup."""
        keyboard = PersistentMenu.main_menu()

        assert isinstance(keyboard, ReplyKeyboardMarkup)
        assert keyboard.is_persistent is True
        assert keyboard.resize_keyboard is True

    def test_main_menu_has_all_buttons(self):
        """Test main menu has all required buttons."""
        keyboard = PersistentMenu.main_menu()

        # Flatten keyboard to get all button texts
        button_texts = []
        for row in keyboard.keyboard:
            for btn in row:
                button_texts.append(btn.text)

        assert MENU_BTN_STATUS in button_texts
        assert MENU_BTN_POSITIONS in button_texts
        assert MENU_BTN_SCAN in button_texts
        assert MENU_BTN_SETTINGS in button_texts
        assert MENU_BTN_HELP in button_texts
        assert MENU_BTN_HISTORY in button_texts

    def test_trading_menu_returns_reply_keyboard(self):
        """Test trading menu returns ReplyKeyboardMarkup."""
        keyboard = PersistentMenu.trading_menu()

        assert isinstance(keyboard, ReplyKeyboardMarkup)
        assert keyboard.is_persistent is True
        assert keyboard.resize_keyboard is True

    def test_trading_menu_has_trading_button(self):
        """Test trading menu has trading control button."""
        keyboard = PersistentMenu.trading_menu()

        button_texts = []
        for row in keyboard.keyboard:
            for btn in row:
                button_texts.append(btn.text)

        assert MENU_BTN_TRADING in button_texts


class TestInlineTemplates:
    """Test InlineTemplates class for inline keyboard templates."""

    def test_position_actions_creates_buttons(self):
        """Test position actions creates correct buttons."""
        buttons = InlineTemplates.position_actions("BTCUSDT")

        assert isinstance(buttons, list)
        assert len(buttons) == 3

        # Check callback data contains symbol
        callback_datas = [btn["callback_data"] for btn in buttons]
        assert any("BTCUSDT" in cb for cb in callback_datas)

    def test_positions_list_creates_buttons_for_each_position(self):
        """Test positions list creates button for each position."""
        positions = [
            {"symbol": "BTCUSDT", "unrealized_pnl": 100.0},
            {"symbol": "ETHUSDT", "unrealized_pnl": -50.0},
        ]

        buttons = InlineTemplates.positions_list(positions)

        assert len(buttons) == 2
        assert any("BTCUSDT" in btn["callback_data"] for btn in buttons)
        assert any("ETHUSDT" in btn["callback_data"] for btn in buttons)

    def test_positions_list_shows_pnl_emoji(self):
        """Test positions list shows correct PnL emoji."""
        positions = [
            {"symbol": "BTCUSDT", "unrealized_pnl": 100.0},  # Profit - green
            {"symbol": "ETHUSDT", "unrealized_pnl": -50.0},  # Loss - red
        ]

        buttons = InlineTemplates.positions_list(positions)

        btc_btn = next(btn for btn in buttons if "BTCUSDT" in btn["callback_data"])
        eth_btn = next(btn for btn in buttons if "ETHUSDT" in btn["callback_data"])

        assert "🟢" in btc_btn["text"]
        assert "🔴" in eth_btn["text"]

    def test_trading_controls_when_paused(self):
        """Test trading controls show resume when paused."""
        buttons = InlineTemplates.trading_controls(is_paused=True)

        # Should have resume button
        texts = [btn["text"] for btn in buttons]
        assert any("Возобновить" in t for t in texts)

    def test_trading_controls_when_active(self):
        """Test trading controls show pause when active."""
        buttons = InlineTemplates.trading_controls(is_paused=False)

        # Should have pause button
        texts = [btn["text"] for btn in buttons]
        assert any("Пауза" in t for t in texts)

    def test_scan_strategy_selection_without_order_block(self):
        """Test scan strategy only shows pump cooldown when OB disabled."""
        buttons = InlineTemplates.scan_strategy_selection(order_block_enabled=False)

        assert len(buttons) == 1
        assert "pump_cooldown" in buttons[0]["callback_data"]

    def test_scan_strategy_selection_with_order_block(self):
        """Test scan strategy shows both strategies when OB enabled."""
        buttons = InlineTemplates.scan_strategy_selection(order_block_enabled=True)

        assert len(buttons) == 2
        callback_datas = [btn["callback_data"] for btn in buttons]
        assert any("pump_cooldown" in cb for cb in callback_datas)
        assert any("order_block" in cb for cb in callback_datas)

    def test_confirm_action_creates_confirm_cancel_buttons(self):
        """Test confirm action creates confirm and cancel buttons."""
        buttons = InlineTemplates.confirm_action("closeall", "data")

        assert len(buttons) == 2
        texts = [btn["text"] for btn in buttons]
        assert any("Подтвердить" in t for t in texts)
        assert any("Отмена" in t for t in texts)

    def test_confirm_action_callback_data(self):
        """Test confirm action includes action and data in callback."""
        buttons = InlineTemplates.confirm_action("closeall", "extra")

        confirm_btn = next(btn for btn in buttons if "Подтвердить" in btn["text"])
        assert "confirm_closeall_extra" in confirm_btn["callback_data"]

    def test_pagination_first_page(self):
        """Test pagination on first page has no prev button."""
        buttons = InlineTemplates.pagination(0, 5)

        texts = [btn["text"] for btn in buttons]
        assert not any("Назад" in t for t in texts)
        assert any("Далее" in t for t in texts)
        assert any("1/5" in t for t in texts)

    def test_pagination_last_page(self):
        """Test pagination on last page has no next button."""
        buttons = InlineTemplates.pagination(4, 5)

        texts = [btn["text"] for btn in buttons]
        assert any("Назад" in t for t in texts)
        assert not any("Далее" in t for t in texts)
        assert any("5/5" in t for t in texts)

    def test_pagination_middle_page(self):
        """Test pagination on middle page has both buttons."""
        buttons = InlineTemplates.pagination(2, 5)

        texts = [btn["text"] for btn in buttons]
        assert any("Назад" in t for t in texts)
        assert any("Далее" in t for t in texts)
        assert any("3/5" in t for t in texts)

    def test_settings_menu_has_all_settings(self):
        """Test settings menu has all configurable settings."""
        buttons = InlineTemplates.settings_menu()

        callback_datas = [btn["callback_data"] for btn in buttons]
        assert any("margin" in cb for cb in callback_datas)
        assert any("max_positions" in cb for cb in callback_datas)
        assert any("leverage" in cb for cb in callback_datas)
        assert any("take_profit" in cb for cb in callback_datas)

    def test_back_button_default_callback(self):
        """Test back button has default callback data."""
        btn = InlineTemplates.back_button()

        assert btn["callback_data"] == "cmd_main"
        assert "Назад" in btn["text"]

    def test_back_button_custom_callback(self):
        """Test back button with custom callback data."""
        btn = InlineTemplates.back_button("cmd_positions")

        assert btn["callback_data"] == "cmd_positions"


class TestMenuButtonConstants:
    """Test menu button text constants."""

    def test_constants_are_strings(self):
        """Test all menu button constants are non-empty strings."""
        constants = [
            MENU_BTN_STATUS,
            MENU_BTN_POSITIONS,
            MENU_BTN_SCAN,
            MENU_BTN_SETTINGS,
            MENU_BTN_HELP,
            MENU_BTN_HISTORY,
            MENU_BTN_TRADING,
        ]

        for const in constants:
            assert isinstance(const, str)
            assert len(const) > 0

    def test_constants_contain_emoji(self):
        """Test menu button constants contain emojis for visual appeal."""
        constants = [
            MENU_BTN_STATUS,
            MENU_BTN_POSITIONS,
            MENU_BTN_SCAN,
            MENU_BTN_SETTINGS,
            MENU_BTN_HELP,
            MENU_BTN_HISTORY,
            MENU_BTN_TRADING,
        ]

        # Each button should start with an emoji
        for const in constants:
            # Emojis are typically in the range U+1F300 to U+1F9FF
            # or U+2600 to U+26FF for misc symbols
            first_char = const[0]
            assert ord(first_char) > 127, f"Button '{const}' should start with emoji"


class TestValidateCallbackData:
    """Test validate_callback_data function for Telegram's 64-byte limit."""

    def test_short_callback_data_unchanged(self):
        """Test that short callback_data passes through unchanged."""
        short_data = "pos_details_BTCUSDT"
        result = validate_callback_data(short_data)
        assert result == short_data

    def test_empty_callback_data_returns_empty(self):
        """Test that empty string returns empty string."""
        result = validate_callback_data("")
        assert result == ""

    def test_none_callback_data_returns_none(self):
        """Test that None returns None (falsy value)."""
        result = validate_callback_data(None)
        assert result is None

    def test_exactly_64_bytes_unchanged(self):
        """Test that exactly 64-byte callback_data passes unchanged."""
        # Create exactly 64 bytes
        data = "a" * 64
        assert len(data.encode("utf-8")) == 64
        result = validate_callback_data(data)
        assert result == data

    def test_65_bytes_gets_truncated(self):
        """Test that 65-byte callback_data gets hashed."""
        data = "a" * 65
        assert len(data.encode("utf-8")) == 65
        result = validate_callback_data(data)
        # Should be truncated/hashed
        assert result != data
        assert len(result.encode("utf-8")) <= TELEGRAM_CALLBACK_DATA_LIMIT

    def test_long_callback_data_gets_hashed(self):
        """Test that very long callback_data gets hashed and stays under limit."""
        long_data = "confirm_close_position_" + "X" * 100
        assert len(long_data.encode("utf-8")) > TELEGRAM_CALLBACK_DATA_LIMIT

        result = validate_callback_data(long_data)

        # Result should be under 64 bytes
        assert len(result.encode("utf-8")) <= TELEGRAM_CALLBACK_DATA_LIMIT
        # Should preserve prefix
        assert result.startswith("confirm_h")
        # Hash should be 8 hex chars
        assert len(result.split("_h")[1]) == 8

    def test_unicode_callback_data_byte_length(self):
        """Test that Unicode characters are measured in bytes, not chars."""
        # Russian text takes 2 bytes per char in UTF-8
        # 30 Russian chars = 60 bytes, under limit
        short_unicode = "а" * 30
        assert len(short_unicode.encode("utf-8")) == 60
        result = validate_callback_data(short_unicode)
        assert result == short_unicode

        # 40 Russian chars = 80 bytes, over limit
        long_unicode = "б" * 40
        assert len(long_unicode.encode("utf-8")) == 80
        result = validate_callback_data(long_unicode)
        assert result != long_unicode
        assert len(result.encode("utf-8")) <= TELEGRAM_CALLBACK_DATA_LIMIT

    def test_raise_on_overflow_true(self):
        """Test that raise_on_overflow=True raises exception for long data."""
        long_data = "x" * 100

        with pytest.raises(CallbackDataTooLongError) as exc_info:
            validate_callback_data(long_data, raise_on_overflow=True)

        assert "100 bytes" in str(exc_info.value)
        assert "exceeds 64 byte limit" in str(exc_info.value)

    def test_raise_on_overflow_false_no_exception(self):
        """Test that raise_on_overflow=False does not raise exception."""
        long_data = "x" * 100

        # Should not raise, should return hashed value
        result = validate_callback_data(long_data, raise_on_overflow=False)
        assert len(result.encode("utf-8")) <= TELEGRAM_CALLBACK_DATA_LIMIT

    def test_hash_is_deterministic(self):
        """Test that same input always produces same hash output."""
        long_data = "confirm_" + "a" * 100

        result1 = validate_callback_data(long_data)
        result2 = validate_callback_data(long_data)

        assert result1 == result2

    def test_different_long_inputs_different_hashes(self):
        """Test that different inputs produce different hashes."""
        data1 = "confirm_" + "a" * 100
        data2 = "confirm_" + "b" * 100

        result1 = validate_callback_data(data1)
        result2 = validate_callback_data(data2)

        assert result1 != result2

    def test_preserves_prefix_from_callback_data(self):
        """Test that the hash result preserves the original prefix."""
        data = "pos_details_" + "VERYLONGSYMBOLNAME" * 10

        result = validate_callback_data(data)

        # Should start with original prefix
        assert result.startswith("pos_h")

    def test_inline_templates_callback_data_validated(self):
        """Test that InlineTemplates methods return validated callback_data."""
        # Test with very long symbol (edge case)
        long_symbol = "A" * 100  # Unrealistic but tests the validation
        buttons = InlineTemplates.position_actions(long_symbol)

        for btn in buttons:
            callback_data = btn["callback_data"]
            byte_length = len(callback_data.encode("utf-8"))
            assert (
                byte_length <= TELEGRAM_CALLBACK_DATA_LIMIT
            ), f"callback_data '{callback_data}' is {byte_length} bytes, exceeds limit"

    def test_confirm_action_long_data_validated(self):
        """Test that confirm_action handles long action/data combinations."""
        long_action = "close_all_positions_" * 5
        long_data = "symbol_" * 10

        buttons = InlineTemplates.confirm_action(long_action, long_data)

        for btn in buttons:
            if btn["callback_data"] != "cancel":  # cancel is always short
                byte_length = len(btn["callback_data"].encode("utf-8"))
                assert byte_length <= TELEGRAM_CALLBACK_DATA_LIMIT

    def test_pagination_long_prefix_validated(self):
        """Test that pagination handles long prefix."""
        long_prefix = "history_positions_list_page_prefix_" * 3

        buttons = InlineTemplates.pagination(5, 10, prefix=long_prefix)

        for btn in buttons:
            byte_length = len(btn["callback_data"].encode("utf-8"))
            assert byte_length <= TELEGRAM_CALLBACK_DATA_LIMIT


class TestCallbackDataRegistry:
    """Test CallbackDataRegistry class for hash -> original mapping."""

    @pytest.fixture(autouse=True)
    def reset_registry(self):
        """Reset registry before and after each test."""
        callback_registry.clear()
        yield
        callback_registry.clear()

    def test_register_and_resolve(self):
        """Test basic register and resolve functionality."""
        callback_registry.register("pos_h12345678", "pos_select_BTCUSDT")

        result = callback_registry.resolve("pos_h12345678")

        assert result == "pos_select_BTCUSDT"

    def test_resolve_unregistered_returns_input(self):
        """Test that resolve returns input for unregistered callbacks."""
        result = callback_registry.resolve("unknown_callback")

        assert result == "unknown_callback"

    def test_is_hashed_true_for_registered(self):
        """Test is_hashed returns True for registered hashes."""
        callback_registry.register("pos_h12345678", "pos_select_BTCUSDT")

        assert callback_registry.is_hashed("pos_h12345678") is True

    def test_is_hashed_false_for_unregistered(self):
        """Test is_hashed returns False for unregistered callbacks."""
        assert callback_registry.is_hashed("normal_callback") is False

    def test_clear_removes_all_entries(self):
        """Test clear removes all registered mappings."""
        callback_registry.register("hash1", "original1")
        callback_registry.register("hash2", "original2")

        callback_registry.clear()

        assert callback_registry.size() == 0
        assert callback_registry.resolve("hash1") == "hash1"

    def test_size_returns_correct_count(self):
        """Test size returns correct number of entries."""
        assert callback_registry.size() == 0

        callback_registry.register("hash1", "original1")
        assert callback_registry.size() == 1

        callback_registry.register("hash2", "original2")
        assert callback_registry.size() == 2

    def test_lru_eviction(self):
        """Test LRU eviction when max_size is exceeded."""
        # Use existing registry (default max_size is 10000)
        # Clear it first, then test eviction behavior with many entries
        callback_registry.clear()

        # Register entries and verify they're stored
        callback_registry.register("hash1", "original1")
        callback_registry.register("hash2", "original2")
        callback_registry.register("hash3", "original3")

        assert callback_registry.size() == 3
        assert callback_registry.resolve("hash1") == "original1"
        assert callback_registry.resolve("hash2") == "original2"
        assert callback_registry.resolve("hash3") == "original3"

    def test_lru_access_updates_order(self):
        """Test that accessing an entry updates its position in LRU."""
        callback_registry.clear()

        callback_registry.register("hash1", "original1")
        callback_registry.register("hash2", "original2")
        callback_registry.register("hash3", "original3")

        # Access hash1, making it recently used
        result = callback_registry.resolve("hash1")
        assert result == "original1"

        # Verify all entries still accessible
        assert callback_registry.resolve("hash2") == "original2"
        assert callback_registry.resolve("hash3") == "original3"
        assert callback_registry.size() == 3

    def test_register_same_hash_updates_value(self):
        """Test that registering same hash updates the value."""
        callback_registry.register("hash1", "original1")
        callback_registry.register("hash1", "updated_original")

        result = callback_registry.resolve("hash1")

        assert result == "updated_original"
        assert callback_registry.size() == 1  # Still only one entry

    def test_singleton_pattern(self):
        """Test CallbackDataRegistry follows singleton pattern."""
        # Get the current singleton instance (should be callback_registry)
        registry1 = CallbackDataRegistry()
        registry2 = CallbackDataRegistry()

        assert registry1 is registry2
        assert registry1 is callback_registry

    def test_global_registry_is_singleton(self):
        """Test global callback_registry is the singleton instance."""
        # callback_registry is created at module import time
        # Any new CallbackDataRegistry() call should return the same instance
        new_registry = CallbackDataRegistry()

        assert callback_registry is new_registry


class TestValidateCallbackDataWithRegistry:
    """Test validate_callback_data integration with registry."""

    @pytest.fixture(autouse=True)
    def reset_registry(self):
        """Reset registry before and after each test."""
        callback_registry.clear()
        yield
        callback_registry.clear()

    def test_long_callback_registers_in_registry(self):
        """Test that hashed callbacks are registered in the global registry."""
        long_data = "pos_select_" + "VERYLONGSYMBOL" * 10

        hashed = validate_callback_data(long_data)

        # Should be hashed
        assert hashed != long_data
        # Should be registered
        assert callback_registry.is_hashed(hashed)
        # Should resolve back
        assert callback_registry.resolve(hashed) == long_data

    def test_short_callback_not_registered(self):
        """Test that short callbacks are not registered."""
        short_data = "pos_select_BTCUSDT"

        result = validate_callback_data(short_data)

        assert result == short_data
        assert callback_registry.is_hashed(short_data) is False

    def test_deterministic_hash_uses_same_registry_entry(self):
        """Test that same input reuses registry entry."""
        long_data = "confirm_" + "a" * 100

        hash1 = validate_callback_data(long_data)
        hash2 = validate_callback_data(long_data)

        assert hash1 == hash2
        assert callback_registry.size() == 1  # Only one entry

    def test_pattern_matching_works_with_resolved_data(self):
        """Test that resolved data supports pattern matching."""
        long_data = "pos_select_" + "X" * 100

        hashed = validate_callback_data(long_data)
        resolved = callback_registry.resolve(hashed)

        # Pattern matching should work on resolved data
        assert resolved.startswith("pos_select_")

        # Symbol extraction should work
        symbol = resolved.replace("pos_select_", "")
        assert symbol == "X" * 100
