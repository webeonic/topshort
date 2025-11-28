"""Handler for persistent menu button messages.

This module handles text messages sent when users tap buttons
on the persistent ReplyKeyboardMarkup menu.
"""

import logging
import re
from typing import TYPE_CHECKING

from telegram import Update
from telegram.ext import ContextTypes, MessageHandler, filters

from .keyboard_builder import (
    MENU_BTN_HELP,
    MENU_BTN_HISTORY,
    MENU_BTN_POSITIONS,
    MENU_BTN_SCAN,
    MENU_BTN_SETTINGS,
    MENU_BTN_STATUS,
    MENU_BTN_TRADING,
)

if TYPE_CHECKING:
    from .commands import BotCommands

logger = logging.getLogger(__name__)


class MenuButtonHandler:
    """Handler for persistent menu button text messages.

    When users tap buttons on the persistent ReplyKeyboardMarkup,
    they send text messages matching the button labels.
    This handler routes those messages to appropriate command handlers.
    """

    def __init__(self, commands: "BotCommands"):
        """Initialize menu button handler.

        Args:
            commands: BotCommands instance to delegate to
        """
        self.commands = commands

    async def handle_menu_button(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Route menu button messages to appropriate handlers.

        Args:
            update: Telegram update with message
            context: Callback context
        """
        text = update.message.text
        logger.debug(f"Menu button pressed: {text}")

        # Route to appropriate handler based on button text
        handlers = {
            MENU_BTN_STATUS: self.commands.status,
            MENU_BTN_POSITIONS: self.commands.positions,
            MENU_BTN_SCAN: self.commands.show_scan_menu,
            MENU_BTN_SETTINGS: self.commands.settings,
            MENU_BTN_HELP: self.commands.start,
            MENU_BTN_HISTORY: self.commands.history,
            MENU_BTN_TRADING: self.commands.show_menu,
        }

        handler = handlers.get(text)
        if handler:
            await handler(update, context)
        else:
            logger.warning(f"Unknown menu button: {text}")

    def get_message_handler(self) -> MessageHandler:
        """Create MessageHandler for menu buttons.

        Returns:
            MessageHandler configured for menu button texts
        """
        # Create filter for all menu button texts
        menu_texts = [
            MENU_BTN_STATUS,
            MENU_BTN_POSITIONS,
            MENU_BTN_SCAN,
            MENU_BTN_SETTINGS,
            MENU_BTN_HELP,
            MENU_BTN_HISTORY,
            MENU_BTN_TRADING,
        ]

        # Build filter for exact text matches
        text_filter = filters.TEXT & filters.Regex(f"^({'|'.join(map(re.escape, menu_texts))})$")

        return MessageHandler(text_filter, self.handle_menu_button)
