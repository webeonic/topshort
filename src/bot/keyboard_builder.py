"""Dynamic keyboard builder for Telegram bot."""

import logging
from typing import Dict, List, Optional, Union

from sqlalchemy.orm import Session
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, ReplyKeyboardRemove

from ..database.models import KeyboardButton
from ..database.repository import KeyboardButtonRepository, KeyboardStateRepository, KeyboardTemplateRepository

logger = logging.getLogger(__name__)


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
            callback_data = self._replace_placeholders(button.callback_data, dynamic_data) if button.callback_data else None

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
                btn = InlineKeyboardButton(btn_data["text"], callback_data=btn_data["callback_data"])
            else:
                logger.warning(f"Invalid button data: {btn_data}")
                continue
            buttons.append(btn)

        keyboard = self.build_menu(buttons, n_cols=n_cols)
        return InlineKeyboardMarkup(keyboard)

    def remove_keyboard(self) -> ReplyKeyboardRemove:
        """Remove custom keyboard."""
        return ReplyKeyboardRemove()


class KeyboardTemplates:
    """Pre-defined keyboard templates for common bot actions."""

    @staticmethod
    def main_menu() -> List[Dict]:
        """Main menu keyboard."""
        return [
            {"text": "📊 Status", "callback_data": "cmd_status"},
            {"text": "💼 Positions", "callback_data": "cmd_positions"},
            {"text": "📜 History", "callback_data": "cmd_history"},
            {"text": "📈 Stats", "callback_data": "cmd_stats"},
            {"text": "🔍 Scan", "callback_data": "cmd_scan"},
            {"text": "⚙️ Settings", "callback_data": "cmd_settings"},
            {"text": "❓ Help", "callback_data": "cmd_help"},
        ]

    @staticmethod
    def position_actions(symbol: str) -> List[Dict]:
        """Position-specific actions keyboard."""
        return [
            {"text": "📊 Details", "callback_data": f"pos_details_{symbol}"},
            {"text": "🔄 Refresh", "callback_data": f"pos_refresh_{symbol}"},
            {"text": "❌ Close", "callback_data": f"pos_close_{symbol}"},
            {"text": "🔙 Back", "callback_data": "cmd_positions"},
        ]

    @staticmethod
    def trading_controls() -> List[Dict]:
        """Trading control buttons."""
        return [
            {"text": "▶️ Resume", "callback_data": "trading_resume"},
            {"text": "⏸️ Pause", "callback_data": "trading_pause"},
            {"text": "🔍 Scan Now", "callback_data": "trading_scan"},
            {"text": "❌ Close All", "callback_data": "trading_closeall"},
        ]

    @staticmethod
    def confirm_action(action: str, data: str = "") -> List[Dict]:
        """Confirmation keyboard."""
        return [
            {"text": "✅ Confirm", "callback_data": f"confirm_{action}_{data}"},
            {"text": "❌ Cancel", "callback_data": "cancel"},
        ]

    @staticmethod
    def pagination(current_page: int, total_pages: int, prefix: str = "page") -> List[Dict]:
        """Pagination keyboard."""
        buttons = []

        if current_page > 0:
            buttons.append({"text": "◀️ Prev", "callback_data": f"{prefix}_{current_page - 1}"})

        buttons.append({"text": f"📄 {current_page + 1}/{total_pages}", "callback_data": "noop"})

        if current_page < total_pages - 1:
            buttons.append({"text": "Next ▶️", "callback_data": f"{prefix}_{current_page + 1}"})

        return buttons

    @staticmethod
    def settings_menu() -> List[Dict]:
        """Settings menu keyboard."""
        return [
            {"text": "💰 Margin", "callback_data": "setting_margin"},
            {"text": "📊 Max Positions", "callback_data": "setting_max_positions"},
            {"text": "📈 Leverage", "callback_data": "setting_leverage"},
            {"text": "🎯 Take Profit", "callback_data": "setting_take_profit"},
            {"text": "🔥 Pump Threshold", "callback_data": "setting_pump_threshold"},
            {"text": "🔙 Back", "callback_data": "cmd_main"},
        ]
