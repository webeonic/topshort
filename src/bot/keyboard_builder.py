"""Dynamic keyboard builder for Telegram bot.

This module provides two types of keyboards:
1. ReplyKeyboardMarkup - Persistent menu at the bottom of the screen (main navigation)
2. InlineKeyboardMarkup - Context-specific inline buttons (actions, settings, confirmations)
"""

import hashlib
import logging
from typing import Dict, List, Optional, Union

from sqlalchemy.orm import Session
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram import KeyboardButton as TgKeyboardButton
from telegram import ReplyKeyboardMarkup, ReplyKeyboardRemove

from ..database.models import KeyboardButton
from ..database.repository import KeyboardButtonRepository, KeyboardStateRepository, KeyboardTemplateRepository

logger = logging.getLogger(__name__)

# =============================================================================
# CALLBACK DATA VALIDATION
# =============================================================================

# Telegram Bot API limit for callback_data (in bytes)
TELEGRAM_CALLBACK_DATA_LIMIT = 64


class CallbackDataTooLongError(Exception):
    """Raised when callback_data exceeds Telegram's 64-byte limit and raise_on_overflow is True."""

    pass


def validate_callback_data(callback_data: str, raise_on_overflow: bool = False) -> str:
    """Validate and safely truncate callback_data to fit Telegram's 64-byte limit.

    Telegram Bot API restricts callback_data to a maximum of 64 bytes (UTF-8 encoded).
    This function checks the byte length and either:
    - Returns the original string if it fits
    - Generates a shortened version using SHA256 hash if it exceeds the limit
    - Raises an exception if raise_on_overflow=True

    Args:
        callback_data: Original callback data string
        raise_on_overflow: If True, raise exception instead of truncating

    Returns:
        Valid callback_data string (≤64 bytes UTF-8)

    Raises:
        CallbackDataTooLongError: If raise_on_overflow=True and data exceeds limit

    Example:
        >>> validate_callback_data("short_data")
        'short_data'
        >>> validate_callback_data("very_long_" * 10)  # Will be hashed
        'very_h1a2b3c4'
    """
    if not callback_data:
        return callback_data

    byte_length = len(callback_data.encode("utf-8"))

    if byte_length <= TELEGRAM_CALLBACK_DATA_LIMIT:
        return callback_data

    if raise_on_overflow:
        raise CallbackDataTooLongError(
            f"callback_data '{callback_data[:30]}...' is {byte_length} bytes, "
            f"exceeds {TELEGRAM_CALLBACK_DATA_LIMIT} byte limit"
        )

    # Generate short hash (8 hex chars = 8 bytes)
    hash_suffix = hashlib.sha256(callback_data.encode("utf-8")).hexdigest()[:8]

    # Extract prefix (first part before '_') for readability, max 20 chars
    parts = callback_data.split("_")
    prefix = parts[0][:20] if parts else "cb"

    # Build new callback: prefix_h<hash>
    # Format: prefix (max 20 chars) + "_h" (2 chars) + hash (8 chars) = max 30 bytes
    new_callback = f"{prefix}_h{hash_suffix}"

    # Safety check: ensure result fits (should always pass with above limits)
    new_byte_length = len(new_callback.encode("utf-8"))
    if new_byte_length > TELEGRAM_CALLBACK_DATA_LIMIT:
        # Fallback: just use hash
        new_callback = f"h{hash_suffix}"

    logger.warning(
        f"callback_data truncated: '{callback_data[:40]}...' ({byte_length}B) -> "
        f"'{new_callback}' ({len(new_callback.encode('utf-8'))}B)"
    )

    return new_callback


# =============================================================================
# PERSISTENT REPLY KEYBOARD (always visible at bottom)
# =============================================================================

# Main menu button texts - these are matched in message handlers
MENU_BTN_STATUS = "📊 Статус"
MENU_BTN_POSITIONS = "💼 Позиции"
MENU_BTN_SCAN = "🔍 Скан"
MENU_BTN_SETTINGS = "⚙️ Настройки"
MENU_BTN_HELP = "❓ Помощь"
MENU_BTN_HISTORY = "📜 История"
MENU_BTN_TRADING = "🎮 Торговля"


class PersistentMenu:
    """Builder for persistent reply keyboard menu."""

    @staticmethod
    def main_menu() -> ReplyKeyboardMarkup:
        """Build the main persistent menu keyboard.

        This keyboard is always visible at the bottom of the chat.
        Buttons trigger text messages that are handled by MessageHandler.

        Returns:
            ReplyKeyboardMarkup with main navigation buttons
        """
        keyboard = [
            [TgKeyboardButton(MENU_BTN_STATUS), TgKeyboardButton(MENU_BTN_POSITIONS)],
            [TgKeyboardButton(MENU_BTN_SCAN), TgKeyboardButton(MENU_BTN_SETTINGS)],
            [TgKeyboardButton(MENU_BTN_HISTORY), TgKeyboardButton(MENU_BTN_HELP)],
        ]
        return ReplyKeyboardMarkup(
            keyboard,
            resize_keyboard=True,  # Fit to content
            is_persistent=True,  # Always show
        )

    @staticmethod
    def trading_menu() -> ReplyKeyboardMarkup:
        """Build trading control menu.

        Extended menu with trading controls.

        Returns:
            ReplyKeyboardMarkup with trading buttons
        """
        keyboard = [
            [TgKeyboardButton(MENU_BTN_STATUS), TgKeyboardButton(MENU_BTN_POSITIONS)],
            [TgKeyboardButton(MENU_BTN_SCAN), TgKeyboardButton(MENU_BTN_TRADING)],
            [TgKeyboardButton(MENU_BTN_SETTINGS), TgKeyboardButton(MENU_BTN_HELP)],
        ]
        return ReplyKeyboardMarkup(
            keyboard,
            resize_keyboard=True,
            is_persistent=True,
        )


# =============================================================================
# INLINE KEYBOARD TEMPLATES (context-specific)
# =============================================================================


class KeyboardBuilder:
    """Build dynamic keyboards from templates and runtime data."""

    def __init__(self, session: Session):
        self.session = session
        self.template_repo = KeyboardTemplateRepository(session)
        self.button_repo = KeyboardButtonRepository(session)
        self.state_repo = KeyboardStateRepository(session)

    def build_menu(
        self,
        buttons: List[InlineKeyboardButton],
        n_cols: int = 2,
        header_buttons: Optional[Union[InlineKeyboardButton, List[InlineKeyboardButton]]] = None,
        footer_buttons: Optional[Union[InlineKeyboardButton, List[InlineKeyboardButton]]] = None,
    ) -> List[List[InlineKeyboardButton]]:
        """Build a structured menu layout from a flat list of buttons.

        Args:
            buttons: List of InlineKeyboardButton objects
            n_cols: Number of columns in the main button grid
            header_buttons: Optional button(s) to appear at the top
            footer_buttons: Optional button(s) to appear at the bottom

        Returns:
            List of button rows for InlineKeyboardMarkup
        """
        menu = [buttons[i : i + n_cols] for i in range(0, len(buttons), n_cols)]

        if header_buttons:
            menu.insert(0, header_buttons if isinstance(header_buttons, list) else [header_buttons])

        if footer_buttons:
            menu.append(footer_buttons if isinstance(footer_buttons, list) else [footer_buttons])

        return menu

    def build_inline_keyboard_from_template(
        self,
        template_name: str,
        dynamic_data: Optional[Dict] = None,
        user_id: Optional[str] = None,
        chat_id: Optional[str] = None,
    ) -> Optional[InlineKeyboardMarkup]:
        """Build an inline keyboard from a template stored in database.

        Args:
            template_name: Name of the keyboard template
            dynamic_data: Optional runtime data to customize buttons
            user_id: Optional user ID for state tracking
            chat_id: Optional chat ID for state tracking

        Returns:
            InlineKeyboardMarkup or None if template not found
        """
        template = self.template_repo.get_by_name(template_name)
        if not template:
            logger.warning(f"Keyboard template not found: {template_name}")
            return None

        if template.keyboard_type != "inline":
            logger.error(f"Template {template_name} is not an inline keyboard")
            return None

        # Get buttons for this template
        buttons: List[KeyboardButton] = self.button_repo.get_by_template(template.id)
        if not buttons:
            logger.warning(f"No buttons found for template: {template_name}")
            return None

        # Build keyboard structure
        keyboard = self._build_keyboard_structure(buttons, dynamic_data)

        # Update user state if provided
        if user_id and chat_id:
            self.state_repo.update_state(user_id, chat_id, template_name, dynamic_data)

        return InlineKeyboardMarkup(keyboard)

    def build_reply_keyboard_from_template(
        self,
        template_name: str,
        dynamic_data: Optional[Dict] = None,
        user_id: Optional[str] = None,
        chat_id: Optional[str] = None,
        resize_keyboard: bool = True,
        one_time_keyboard: bool = False,
    ) -> Optional[ReplyKeyboardMarkup]:
        """Build a reply keyboard from a template stored in database.

        Args:
            template_name: Name of the keyboard template
            dynamic_data: Optional runtime data to customize buttons
            user_id: Optional user ID for state tracking
            chat_id: Optional chat ID for state tracking
            resize_keyboard: Resize keyboard to fit screen
            one_time_keyboard: Hide keyboard after one use

        Returns:
            ReplyKeyboardMarkup or None if template not found
        """
        template = self.template_repo.get_by_name(template_name)
        if not template:
            logger.warning(f"Keyboard template not found: {template_name}")
            return None

        if template.keyboard_type != "reply":
            logger.error(f"Template {template_name} is not a reply keyboard")
            return None

        # Get buttons for this template
        buttons: List[KeyboardButton] = self.button_repo.get_by_template(template.id)
        if not buttons:
            logger.warning(f"No buttons found for template: {template_name}")
            return None

        # Build keyboard structure (list of text strings for reply keyboard)
        keyboard: List[List[str]] = []
        current_row: List[str] = []
        last_row = -1

        for button in buttons:
            if button.row_position != last_row:
                if current_row:
                    keyboard.append(current_row)
                current_row = []
                last_row = button.row_position

            # Replace placeholders in label
            label = self._replace_placeholders(button.label, dynamic_data)
            current_row.append(label)

        if current_row:
            keyboard.append(current_row)

        # Update user state if provided
        if user_id and chat_id:
            self.state_repo.update_state(user_id, chat_id, template_name, dynamic_data)

        return ReplyKeyboardMarkup(keyboard, resize_keyboard=resize_keyboard, one_time_keyboard=one_time_keyboard)

    def _build_keyboard_structure(
        self, buttons: List[KeyboardButton], dynamic_data: Optional[Dict] = None
    ) -> List[List[InlineKeyboardButton]]:
        """Build keyboard structure from button list."""
        keyboard: List[List[InlineKeyboardButton]] = []
        current_row: List[InlineKeyboardButton] = []
        last_row = -1

        for button in buttons:
            # Start new row if needed
            if button.row_position != last_row:
                if current_row:
                    keyboard.append(current_row)
                current_row = []
                last_row = button.row_position

            # Replace placeholders in label and callback_data
            label = self._replace_placeholders(button.label, dynamic_data)
            raw_callback = self._replace_placeholders(button.callback_data, dynamic_data) if button.callback_data else None
            # Validate callback_data to ensure it fits Telegram's 64-byte limit
            callback_data = validate_callback_data(raw_callback) if raw_callback else None

            # Create button based on type
            if button.button_type == "url" and button.url:
                btn = InlineKeyboardButton(label, url=button.url)
            elif button.button_type == "callback" and callback_data:
                btn = InlineKeyboardButton(label, callback_data=callback_data)
            else:
                logger.warning(f"Invalid button configuration: {button}")
                continue

            current_row.append(btn)

        # Add last row
        if current_row:
            keyboard.append(current_row)

        return keyboard

    def _replace_placeholders(self, text: Optional[str], dynamic_data: Optional[Dict]) -> str:
        """Replace placeholders in text with dynamic data.

        Placeholders format: {key} or {nested.key}
        Example: "Balance: {balance} USDT" -> "Balance: 1000.50 USDT"
        """
        if not text or not dynamic_data:
            return text or ""

        result = text
        for key, value in dynamic_data.items():
            placeholder = "{" + key + "}"
            if placeholder in result:
                result = result.replace(placeholder, str(value))

        return result

    def create_inline_keyboard(self, buttons_data: List[Dict], n_cols: int = 2) -> InlineKeyboardMarkup:
        """Create an inline keyboard from a list of button dictionaries.

        Args:
            buttons_data: List of dicts with 'text', 'callback_data' or 'url' keys
            n_cols: Number of columns

        Example:
            buttons_data = [
                {'text': 'Button 1', 'callback_data': 'btn1'},
                {'text': 'Button 2', 'url': 'https://example.com'},
            ]
        """
        buttons = []
        for btn_data in buttons_data:
            if "url" in btn_data:
                btn = InlineKeyboardButton(btn_data["text"], url=btn_data["url"])
            elif "callback_data" in btn_data:
                # Validate callback_data to ensure it fits Telegram's 64-byte limit
                validated_callback = validate_callback_data(btn_data["callback_data"])
                btn = InlineKeyboardButton(btn_data["text"], callback_data=validated_callback)
            else:
                logger.warning(f"Invalid button data: {btn_data}")
                continue
            buttons.append(btn)

        keyboard = self.build_menu(buttons, n_cols=n_cols)
        return InlineKeyboardMarkup(keyboard)

    def remove_keyboard(self) -> ReplyKeyboardRemove:
        """Remove custom keyboard."""
        return ReplyKeyboardRemove()


class InlineTemplates:
    """Pre-defined inline keyboard templates for context-specific actions.

    These are used for:
    - Position actions (details, close, refresh)
    - Settings configuration
    - Confirmations
    - Scan strategy selection
    - Pagination
    """

    @staticmethod
    def position_actions(symbol: str) -> List[Dict]:
        """Position-specific actions keyboard.

        Args:
            symbol: Trading pair symbol (e.g., 'BTCUSDT')

        Returns:
            List of button definitions for position actions
        """
        return [
            {"text": "📊 Детали", "callback_data": validate_callback_data(f"pos_details_{symbol}")},
            {"text": "🔄 Обновить", "callback_data": validate_callback_data(f"pos_refresh_{symbol}")},
            {"text": "❌ Закрыть", "callback_data": validate_callback_data(f"pos_close_{symbol}")},
        ]

    @staticmethod
    def positions_list(positions: List[Dict]) -> List[Dict]:
        """Generate buttons for list of positions.

        Args:
            positions: List of position dicts with 'symbol' key

        Returns:
            List of button definitions
        """
        buttons = []
        for pos in positions:
            symbol = pos.get("symbol", "")
            pnl = pos.get("unrealized_pnl", 0)
            if pnl > 0:
                pnl_emoji = "🟢"
            elif pnl < 0:
                pnl_emoji = "🔴"
            else:
                pnl_emoji = "⚪"
            buttons.append({"text": f"{pnl_emoji} {symbol}", "callback_data": validate_callback_data(f"pos_select_{symbol}")})
        return buttons

    @staticmethod
    def trading_controls(is_paused: bool = False) -> List[Dict]:
        """Trading control buttons.

        Args:
            is_paused: Current trading status

        Returns:
            List of button definitions for trading controls
        """
        buttons = []
        if is_paused:
            buttons.append({"text": "▶️ Возобновить", "callback_data": "trading_resume"})
        else:
            buttons.append({"text": "⏸️ Пауза", "callback_data": "trading_pause"})
        buttons.extend(
            [
                {"text": "🔍 Скан сейчас", "callback_data": "cmd_scan"},
                {"text": "❌ Закрыть все", "callback_data": "trading_closeall"},
            ]
        )
        return buttons

    @staticmethod
    def scan_strategy_selection(order_block_enabled: bool = False) -> List[Dict]:
        """Scan strategy selection buttons.

        Args:
            order_block_enabled: Whether Order Block strategy is enabled

        Returns:
            List of button definitions for strategy selection
        """
        buttons = [
            {"text": "🚀 Pump & Cooldown", "callback_data": "scan_strategy_pump_cooldown"},
        ]
        if order_block_enabled:
            buttons.append({"text": "🧱 Order Block", "callback_data": "scan_strategy_order_block"})
        return buttons

    @staticmethod
    def confirm_action(action: str, data: str = "") -> List[Dict]:
        """Confirmation keyboard.

        Args:
            action: Action to confirm
            data: Additional data for callback

        Returns:
            List of button definitions for confirmation
        """
        raw_callback = f"confirm_{action}_{data}" if data else f"confirm_{action}"
        callback_data = validate_callback_data(raw_callback)
        return [
            {"text": "✅ Подтвердить", "callback_data": callback_data},
            {"text": "❌ Отмена", "callback_data": "cancel"},
        ]

    @staticmethod
    def pagination(current_page: int, total_pages: int, prefix: str = "page") -> List[Dict]:
        """Pagination keyboard.

        Args:
            current_page: Current page number (0-indexed)
            total_pages: Total number of pages
            prefix: Callback data prefix

        Returns:
            List of button definitions for pagination
        """
        buttons = []

        if current_page > 0:
            buttons.append({"text": "◀️ Назад", "callback_data": validate_callback_data(f"{prefix}_{current_page - 1}")})

        buttons.append({"text": f"📄 {current_page + 1}/{total_pages}", "callback_data": "noop"})

        if current_page < total_pages - 1:
            buttons.append({"text": "Далее ▶️", "callback_data": validate_callback_data(f"{prefix}_{current_page + 1}")})

        return buttons

    @staticmethod
    def settings_menu() -> List[Dict]:
        """Settings menu keyboard.

        Returns:
            List of button definitions for settings menu
        """
        return [
            {"text": "💰 Маржа", "callback_data": "setting_margin_per_trade"},
            {"text": "📊 Макс. позиции", "callback_data": "setting_max_positions"},
            {"text": "📈 Плечо", "callback_data": "setting_default_leverage"},
            {"text": "🎯 Take Profit", "callback_data": "setting_take_profit_pct"},
            {"text": "🔥 Порог пампа", "callback_data": "setting_pump_threshold_pct"},
        ]

    @staticmethod
    def back_button(callback_data: str = "cmd_main") -> Dict:
        """Single back button.

        Args:
            callback_data: Callback data for back action

        Returns:
            Button definition for back button
        """
        return {"text": "🔙 Назад", "callback_data": validate_callback_data(callback_data)}


# Alias for backwards compatibility
KeyboardTemplates = InlineTemplates
