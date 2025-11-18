-- Migration: Add dynamic keyboard system tables
-- Version: V002
-- Description: Creates tables for dynamic keyboard templates, buttons, state tracking, and callback logging
-- Author: TopShort Bot
-- Date: 2025-01-18

-- =============================================================================
-- KEYBOARD TEMPLATES
-- =============================================================================
-- Table for storing keyboard templates (inline and reply keyboards)
CREATE TABLE IF NOT EXISTS keyboard_templates (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name VARCHAR(100) NOT NULL UNIQUE,
    description TEXT,
    keyboard_type VARCHAR(20) NOT NULL DEFAULT 'inline' CHECK(keyboard_type IN ('inline', 'reply')),
    keyboard_data TEXT NOT NULL, -- JSON string with keyboard structure
    is_active BOOLEAN NOT NULL DEFAULT 1,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_keyboard_templates_name ON keyboard_templates(name);
CREATE INDEX IF NOT EXISTS idx_keyboard_templates_active ON keyboard_templates(is_active);

-- =============================================================================
-- KEYBOARD BUTTONS
-- =============================================================================
-- Table for individual keyboard buttons with dynamic configuration
CREATE TABLE IF NOT EXISTS keyboard_buttons (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    template_id INTEGER NOT NULL,
    label VARCHAR(100) NOT NULL,
    callback_data VARCHAR(200), -- For inline keyboards
    url VARCHAR(500), -- For URL buttons
    row_position INTEGER NOT NULL DEFAULT 0,
    column_position INTEGER NOT NULL DEFAULT 0,
    button_type VARCHAR(30) NOT NULL DEFAULT 'callback' CHECK(button_type IN ('callback', 'url', 'text', 'contact', 'location')),
    action VARCHAR(100), -- Action to perform on click
    action_params TEXT, -- JSON string with action parameters
    is_active BOOLEAN NOT NULL DEFAULT 1,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (template_id) REFERENCES keyboard_templates(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_keyboard_buttons_template ON keyboard_buttons(template_id);
CREATE INDEX IF NOT EXISTS idx_keyboard_buttons_template_position ON keyboard_buttons(template_id, row_position, column_position);
CREATE INDEX IF NOT EXISTS idx_keyboard_buttons_active ON keyboard_buttons(is_active);

-- =============================================================================
-- KEYBOARD STATE TRACKING
-- =============================================================================
-- Table to track keyboard states per user for dynamic behavior
CREATE TABLE IF NOT EXISTS keyboard_states (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id VARCHAR(50) NOT NULL,
    chat_id VARCHAR(50) NOT NULL,
    current_keyboard VARCHAR(100), -- Current keyboard template name
    state_data TEXT, -- JSON string with state-specific data
    last_interaction_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(user_id, chat_id)
);

CREATE INDEX IF NOT EXISTS idx_keyboard_states_user ON keyboard_states(user_id);
CREATE INDEX IF NOT EXISTS idx_keyboard_states_chat ON keyboard_states(chat_id);
CREATE UNIQUE INDEX IF NOT EXISTS idx_keyboard_states_user_chat ON keyboard_states(user_id, chat_id);

-- =============================================================================
-- CALLBACK INTERACTION LOGS
-- =============================================================================
-- Table to log all callback interactions for analytics and debugging
CREATE TABLE IF NOT EXISTS callback_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id VARCHAR(50) NOT NULL,
    username VARCHAR(100),
    chat_id VARCHAR(50) NOT NULL,
    callback_data VARCHAR(200) NOT NULL,
    action VARCHAR(100),
    success BOOLEAN NOT NULL DEFAULT 1,
    error_message TEXT,
    response_time_ms INTEGER,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_callback_logs_user ON callback_logs(user_id);
CREATE INDEX IF NOT EXISTS idx_callback_logs_callback_data ON callback_logs(callback_data);
CREATE INDEX IF NOT EXISTS idx_callback_logs_created ON callback_logs(created_at);
CREATE INDEX IF NOT EXISTS idx_callback_logs_action ON callback_logs(action);

-- =============================================================================
-- DEFAULT KEYBOARD TEMPLATES
-- =============================================================================
-- Insert default main menu keyboard template
INSERT OR IGNORE INTO keyboard_templates (name, description, keyboard_type, keyboard_data)
VALUES (
    'main_menu',
    'Main menu with primary bot commands',
    'inline',
    '{}'
);

-- Get the template ID for main_menu
-- Insert main menu buttons
INSERT OR IGNORE INTO keyboard_buttons (template_id, label, callback_data, row_position, column_position, button_type, action)
SELECT
    (SELECT id FROM keyboard_templates WHERE name = 'main_menu'),
    '📊 Status',
    'cmd_status',
    0,
    0,
    'callback',
    'show_status'
UNION ALL SELECT
    (SELECT id FROM keyboard_templates WHERE name = 'main_menu'),
    '💼 Positions',
    'cmd_positions',
    0,
    1,
    'callback',
    'show_positions'
UNION ALL SELECT
    (SELECT id FROM keyboard_templates WHERE name = 'main_menu'),
    '📜 History',
    'cmd_history',
    1,
    0,
    'callback',
    'show_history'
UNION ALL SELECT
    (SELECT id FROM keyboard_templates WHERE name = 'main_menu'),
    '📈 Stats',
    'cmd_stats',
    1,
    1,
    'callback',
    'show_stats'
UNION ALL SELECT
    (SELECT id FROM keyboard_templates WHERE name = 'main_menu'),
    '⚙️ Settings',
    'cmd_settings',
    2,
    0,
    'callback',
    'show_settings'
UNION ALL SELECT
    (SELECT id FROM keyboard_templates WHERE name = 'main_menu'),
    '❓ Help',
    'cmd_help',
    2,
    1,
    'callback',
    'show_help';

-- Insert trading controls keyboard template
INSERT OR IGNORE INTO keyboard_templates (name, description, keyboard_type, keyboard_data)
VALUES (
    'trading_controls',
    'Trading control buttons',
    'inline',
    '{}'
);

-- Insert trading control buttons
INSERT OR IGNORE INTO keyboard_buttons (template_id, label, callback_data, row_position, column_position, button_type, action)
SELECT
    (SELECT id FROM keyboard_templates WHERE name = 'trading_controls'),
    '▶️ Resume',
    'trading_resume',
    0,
    0,
    'callback',
    'resume_trading'
UNION ALL SELECT
    (SELECT id FROM keyboard_templates WHERE name = 'trading_controls'),
    '⏸️ Pause',
    'trading_pause',
    0,
    1,
    'callback',
    'pause_trading'
UNION ALL SELECT
    (SELECT id FROM keyboard_templates WHERE name = 'trading_controls'),
    '🔍 Scan Now',
    'trading_scan',
    1,
    0,
    'callback',
    'scan_market'
UNION ALL SELECT
    (SELECT id FROM keyboard_templates WHERE name = 'trading_controls'),
    '❌ Close All',
    'trading_closeall',
    1,
    1,
    'callback',
    'close_all_positions';

-- =============================================================================
-- MIGRATION COMPLETE
-- =============================================================================
-- This migration adds comprehensive dynamic keyboard system with:
-- - Keyboard templates (inline and reply)
-- - Configurable buttons with positions and actions
-- - User state tracking for dynamic keyboards
-- - Callback interaction logging for analytics
-- - Default main menu and trading controls keyboards
