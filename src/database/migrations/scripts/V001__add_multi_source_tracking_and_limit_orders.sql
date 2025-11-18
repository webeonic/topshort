-- Migration V001: Add multi-source position tracking and limit order management
-- Description: Adds source tracking, limit order fields, and creates limit_orders table

-- Step 1: Add new columns to positions table
ALTER TABLE positions ADD COLUMN source VARCHAR(30) DEFAULT 'bot_auto';
ALTER TABLE positions ADD COLUMN source_metadata TEXT;
ALTER TABLE positions ADD COLUMN take_profit_order_id VARCHAR(100);
ALTER TABLE positions ADD COLUMN take_profit_order_status VARCHAR(20) DEFAULT 'pending';
ALTER TABLE positions ADD COLUMN take_profit_placed_at DATETIME;
ALTER TABLE positions ADD COLUMN stop_loss_order_id VARCHAR(100);
ALTER TABLE positions ADD COLUMN stop_loss_order_status VARCHAR(20);

-- Step 2: Update existing data with default values
UPDATE positions SET source = 'bot_auto' WHERE source IS NULL;
UPDATE positions SET take_profit_order_status = 'pending' WHERE status = 'open' AND take_profit_order_status IS NULL;

-- Step 3: Create new limit_orders table
CREATE TABLE IF NOT EXISTS limit_orders (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    position_id INTEGER NOT NULL,
    order_id VARCHAR(100) UNIQUE NOT NULL,
    symbol VARCHAR(50) NOT NULL,
    order_type VARCHAR(20) NOT NULL,
    side VARCHAR(10) NOT NULL,
    price FLOAT NOT NULL,
    quantity FLOAT NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'pending',
    filled_quantity FLOAT DEFAULT 0,
    avg_fill_price FLOAT,
    exchange_status VARCHAR(50),
    error_message TEXT,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    filled_at DATETIME,
    cancelled_at DATETIME,
    FOREIGN KEY (position_id) REFERENCES positions(id) ON DELETE CASCADE
);

-- Step 4: Add new columns to trade_history table
ALTER TABLE trade_history ADD COLUMN source VARCHAR(30) DEFAULT 'bot_auto';
ALTER TABLE trade_history ADD COLUMN take_profit_order_id VARCHAR(100);
ALTER TABLE trade_history ADD COLUMN stop_loss_order_id VARCHAR(100);

-- Step 5: Create indexes for performance
CREATE INDEX IF NOT EXISTS idx_positions_source ON positions(source);
CREATE INDEX IF NOT EXISTS idx_positions_source_status ON positions(source, status);
CREATE INDEX IF NOT EXISTS idx_positions_tp_order_status ON positions(take_profit_order_status);
CREATE INDEX IF NOT EXISTS idx_limit_orders_position_id ON limit_orders(position_id);
CREATE INDEX IF NOT EXISTS idx_limit_orders_order_id ON limit_orders(order_id);
CREATE INDEX IF NOT EXISTS idx_limit_orders_status ON limit_orders(status);
CREATE INDEX IF NOT EXISTS idx_limit_orders_order_type ON limit_orders(order_type);
