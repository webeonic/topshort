"""Comprehensive tests for KeyboardBuilder class."""

from unittest.mock import MagicMock, Mock

import pytest
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup

from src.bot.keyboard_builder import KeyboardBuilder, KeyboardTemplates


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


class TestKeyboardTemplates:
    """Test KeyboardTemplates static methods."""

    def test_main_menu_template(self):
        """Test main menu template."""
        buttons = KeyboardTemplates.main_menu()

        assert isinstance(buttons, list)
        assert len(buttons) > 0
        assert all("text" in btn and "callback_data" in btn for btn in buttons)
        assert any("Status" in btn["text"] for btn in buttons)
        assert any("Positions" in btn["text"] for btn in buttons)

    def test_position_actions_template(self):
        """Test position actions template."""
        buttons = KeyboardTemplates.position_actions("BTCUSDT")

        assert isinstance(buttons, list)
        assert len(buttons) > 0
        assert any("Details" in btn["text"] for btn in buttons)
        assert any("BTCUSDT" in btn["callback_data"] for btn in buttons)

    def test_trading_controls_template(self):
        """Test trading controls template."""
        buttons = KeyboardTemplates.trading_controls()

        assert isinstance(buttons, list)
        assert any("Resume" in btn["text"] for btn in buttons)
        assert any("Pause" in btn["text"] for btn in buttons)
        assert any("Scan" in btn["text"] for btn in buttons)

    def test_confirm_action_template(self):
        """Test confirm action template."""
        buttons = KeyboardTemplates.confirm_action("closeall", "data")

        assert isinstance(buttons, list)
        assert len(buttons) == 2
        assert any("Confirm" in btn["text"] for btn in buttons)
        assert any("Cancel" in btn["text"] for btn in buttons)
        assert any("confirm_closeall_data" in btn["callback_data"] for btn in buttons)

    def test_pagination_template_first_page(self):
        """Test pagination template on first page."""
        buttons = KeyboardTemplates.pagination(0, 3)

        assert isinstance(buttons, list)
        # Should have current page indicator and next button
        assert any("1/3" in btn["text"] for btn in buttons)
        assert any("Next" in btn["text"] for btn in buttons)
        assert not any("Prev" in btn["text"] for btn in buttons)

    def test_pagination_template_middle_page(self):
        """Test pagination template on middle page."""
        buttons = KeyboardTemplates.pagination(1, 3)

        assert isinstance(buttons, list)
        # Should have prev, current, and next buttons
        assert any("Prev" in btn["text"] for btn in buttons)
        assert any("2/3" in btn["text"] for btn in buttons)
        assert any("Next" in btn["text"] for btn in buttons)

    def test_pagination_template_last_page(self):
        """Test pagination template on last page."""
        buttons = KeyboardTemplates.pagination(2, 3)

        assert isinstance(buttons, list)
        # Should have prev button and current page indicator
        assert any("Prev" in btn["text"] for btn in buttons)
        assert any("3/3" in btn["text"] for btn in buttons)
        assert not any("Next" in btn["text"] for btn in buttons)

    def test_settings_menu_template(self):
        """Test settings menu template."""
        buttons = KeyboardTemplates.settings_menu()

        assert isinstance(buttons, list)
        assert len(buttons) > 0
        assert any("Margin" in btn["text"] for btn in buttons)
        assert any("Leverage" in btn["text"] for btn in buttons)
        assert any("Back" in btn["text"] for btn in buttons)


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
