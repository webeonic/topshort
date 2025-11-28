-- V004: Add strategy field to trade_history table
-- This migration adds a strategy column to track which trading strategy
-- was used to open each position (pump_cooldown, order_block, etc.)

-- Add strategy column to trade_history
ALTER TABLE trade_history ADD COLUMN strategy VARCHAR(50);

-- Create index for filtering by strategy
CREATE INDEX IF NOT EXISTS idx_trade_history_strategy ON trade_history(strategy);
