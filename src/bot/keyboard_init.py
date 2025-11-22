"""Initialize keyboard templates in database."""

import logging

from sqlalchemy.orm import Session

from ..database.repository import KeyboardButtonRepository, KeyboardTemplateRepository

logger = logging.getLogger(__name__)


def init_keyboard_templates(session: Session):
    """Initialize default keyboard templates if they don't exist.

    This function creates predefined keyboard templates for the bot:
    - Main menu
    - Trading controls
    - Settings menu
    - Position actions
    """
    template_repo = KeyboardTemplateRepository(session)
    button_repo = KeyboardButtonRepository(session)

    # Check if templates already exist
    if template_repo.get_by_name("main_menu"):
        logger.info("Keyboard templates already initialized")
        return

    logger.info("Initializing keyboard templates...")

    # =============================================================================
    # MAIN MENU
    # =============================================================================
    main_menu = template_repo.create(
        name="main_menu",
        keyboard_type="inline",
        description="Main menu with primary bot commands",
        keyboard_data={"layout": "grid", "columns": 2},
    )

    buttons_main = [
        ("📊 Status", "cmd_status", 0, 0, "show_status"),
        ("💼 Positions", "cmd_positions", 0, 1, "show_positions"),
        ("📜 History", "cmd_history", 1, 0, "show_history"),
        ("📈 Stats", "cmd_stats", 1, 1, "show_stats"),
        ("🔍 Scan", "cmd_scan", 2, 0, "show_scan_menu"),
        ("⚙️ Settings", "cmd_settings", 2, 1, "show_settings"),
        ("❓ Help", "cmd_help", 3, 0, "show_help"),
    ]

    for label, callback_data, row, col, action in buttons_main:
        button_repo.create(
            template_id=main_menu.id,
            label=label,
            callback_data=callback_data,
            row_position=row,
            column_position=col,
            button_type="callback",
            action=action,
        )

    logger.info("✓ Main menu template created")

    # =============================================================================
    # TRADING CONTROLS
    # =============================================================================
    trading_controls = template_repo.create(
        name="trading_controls",
        keyboard_type="inline",
        description="Trading control buttons",
        keyboard_data={"layout": "grid", "columns": 2},
    )

    buttons_trading = [
        ("▶️ Resume", "trading_resume", 0, 0, "resume_trading"),
        ("⏸️ Pause", "trading_pause", 0, 1, "pause_trading"),
        ("🔍 Scan Now", "trading_scan", 1, 0, "scan_market"),
        ("❌ Close All", "trading_closeall", 1, 1, "close_all_positions"),
        ("🔙 Back", "cmd_main", 2, 0, "show_main_menu"),
    ]

    for label, callback_data, row, col, action in buttons_trading:
        button_repo.create(
            template_id=trading_controls.id,
            label=label,
            callback_data=callback_data,
            row_position=row,
            column_position=col,
            button_type="callback",
            action=action,
        )

    logger.info("✓ Trading controls template created")

    # =============================================================================
    # SETTINGS MENU
    # =============================================================================
    settings_menu = template_repo.create(
        name="settings_menu",
        keyboard_type="inline",
        description="Settings configuration menu",
        keyboard_data={"layout": "grid", "columns": 2},
    )

    buttons_settings = [
        ("💰 Margin", "setting_margin_per_trade", 0, 0, "config_margin"),
        ("📊 Max Positions", "setting_max_positions", 0, 1, "config_max_positions"),
        ("📈 Leverage", "setting_default_leverage", 1, 0, "config_leverage"),
        ("🎯 Take Profit", "setting_take_profit_pct", 1, 1, "config_take_profit"),
        ("🔥 Pump Threshold", "setting_pump_threshold_pct", 2, 0, "config_pump_threshold"),
        ("🔙 Back", "cmd_main", 3, 0, "show_main_menu"),
    ]

    for label, callback_data, row, col, action in buttons_settings:
        button_repo.create(
            template_id=settings_menu.id,
            label=label,
            callback_data=callback_data,
            row_position=row,
            column_position=col,
            button_type="callback",
            action=action,
        )

    logger.info("✓ Settings menu template created")

    # =============================================================================
    # POSITION ACTIONS (Dynamic - uses placeholder for symbol)
    # =============================================================================
    position_actions = template_repo.create(
        name="position_actions",
        keyboard_type="inline",
        description="Actions for individual positions",
        keyboard_data={"layout": "grid", "columns": 2, "dynamic": True},
    )

    buttons_position = [
        ("📊 Details", "pos_details_{symbol}", 0, 0, "show_position_details"),
        ("🔄 Refresh", "pos_refresh_{symbol}", 0, 1, "refresh_position"),
        ("❌ Close", "pos_close_{symbol}", 1, 0, "close_position"),
        ("🔙 Back", "cmd_positions", 1, 1, "show_positions"),
    ]

    for label, callback_data, row, col, action in buttons_position:
        button_repo.create(
            template_id=position_actions.id,
            label=label,
            callback_data=callback_data,
            row_position=row,
            column_position=col,
            button_type="callback",
            action=action,
        )

    logger.info("✓ Position actions template created")

    # =============================================================================
    # CONFIRMATION DIALOG
    # =============================================================================
    confirmation = template_repo.create(
        name="confirmation",
        keyboard_type="inline",
        description="Generic confirmation dialog",
        keyboard_data={"layout": "inline", "columns": 2},
    )

    buttons_confirmation = [
        ("✅ Confirm", "confirm_{action}", 0, 0, "confirm_action"),
        ("❌ Cancel", "cancel", 0, 1, "cancel_action"),
    ]

    for label, callback_data, row, col, action in buttons_confirmation:
        button_repo.create(
            template_id=confirmation.id,
            label=label,
            callback_data=callback_data,
            row_position=row,
            column_position=col,
            button_type="callback",
            action=action,
        )

    logger.info("✓ Confirmation template created")

    logger.info("✅ All keyboard templates initialized successfully")


def update_keyboard_templates(session: Session):
    """Update existing keyboard templates with new buttons or configurations.

    This function can be called to update templates without recreating them.
    """
    template_repo = KeyboardTemplateRepository(session)
    button_repo = KeyboardButtonRepository(session)

    logger.info("Checking for keyboard template updates...")

    # Example: Add new buttons to main menu if they don't exist
    main_menu = template_repo.get_by_name("main_menu")
    if main_menu:
        # Check if trading controls button exists
        existing_buttons = button_repo.get_by_template(main_menu.id)
        has_trading_button = any(b.callback_data == "cmd_trading" for b in existing_buttons)

        if not has_trading_button:
            button_repo.create(
                template_id=main_menu.id,
                label="🎮 Trading",
                callback_data="cmd_trading",
                row_position=3,
                column_position=0,
                button_type="callback",
                action="show_trading_controls",
            )
            logger.info("✓ Added trading button to main menu")

        has_scan_button = any(b.callback_data == "cmd_scan" for b in existing_buttons)
        if not has_scan_button:
            button_repo.create(
                template_id=main_menu.id,
                label="🔍 Scan",
                callback_data="cmd_scan",
                row_position=2,
                column_position=0,
                button_type="callback",
                action="show_scan_menu",
            )
            logger.info("✓ Added scan button to main menu")

    logger.info("✅ Keyboard templates update complete")
