"""Database migration script V1: Add multi-source tracking and limit order management.

This script migrates the database schema to support:
1. Multi-source position tracking (bot_auto, manual, external_system)
2. Limit order management for take-profit and stop-loss
3. Enhanced order status tracking
"""

import logging
import sqlite3
from datetime import datetime
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


def migrate_database(database_path: str):
    """Migrate database to V1 schema."""
    logger.info(f"Starting database migration for: {database_path}")

    # Backup database first
    backup_path = f"{database_path}.backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    import shutil

    shutil.copy2(database_path, backup_path)
    logger.info(f"Database backed up to: {backup_path}")

    conn = sqlite3.connect(database_path)
    cursor = conn.cursor()

    try:
        # Check if migration is needed
        cursor.execute("PRAGMA table_info(positions)")
        columns = [col[1] for col in cursor.fetchall()]

        if "source" in columns:
            logger.info("Migration already applied. Skipping.")
            return

        logger.info("Applying migration V1...")

        # Step 1: Add new columns to positions table
        logger.info("Adding new columns to positions table...")

        migrations = [
            # Multi-source tracking
            "ALTER TABLE positions ADD COLUMN source VARCHAR(30) DEFAULT 'bot_auto'",
            "ALTER TABLE positions ADD COLUMN source_metadata TEXT",
            # Take-profit limit order management
            "ALTER TABLE positions ADD COLUMN take_profit_order_id VARCHAR(100)",
            "ALTER TABLE positions ADD COLUMN take_profit_order_status VARCHAR(20) DEFAULT 'pending'",
            "ALTER TABLE positions ADD COLUMN take_profit_placed_at DATETIME",
            # Stop-loss limit order management
            "ALTER TABLE positions ADD COLUMN stop_loss_order_id VARCHAR(100)",
            "ALTER TABLE positions ADD COLUMN stop_loss_order_status VARCHAR(20)",
        ]

        for migration in migrations:
            try:
                cursor.execute(migration)
                logger.info(f"✓ {migration[:60]}...")
            except sqlite3.OperationalError as e:
                if "duplicate column name" in str(e).lower():
                    logger.warning(f"Column already exists, skipping: {migration[:60]}...")
                else:
                    raise

        # Step 2: Update existing data with default values
        logger.info("Updating existing position records...")
        cursor.execute("UPDATE positions SET source = 'bot_auto' WHERE source IS NULL")
        cursor.execute(
            "UPDATE positions SET take_profit_order_status = 'pending' WHERE status = 'open' AND take_profit_order_status IS NULL"
        )
        logger.info(f"✓ Updated {cursor.rowcount} records")

        # Step 3: Create new limit_orders table
        logger.info("Creating limit_orders table...")
        cursor.execute(
            """
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
            )
        """
        )
        logger.info("✓ limit_orders table created")

        # Step 4: Add columns to trade_history table
        logger.info("Adding new columns to trade_history table...")

        history_migrations = [
            "ALTER TABLE trade_history ADD COLUMN source VARCHAR(30) DEFAULT 'bot_auto'",
            "ALTER TABLE trade_history ADD COLUMN take_profit_order_id VARCHAR(100)",
            "ALTER TABLE trade_history ADD COLUMN stop_loss_order_id VARCHAR(100)",
        ]

        for migration in history_migrations:
            try:
                cursor.execute(migration)
                logger.info(f"✓ {migration[:60]}...")
            except sqlite3.OperationalError as e:
                if "duplicate column name" in str(e).lower():
                    logger.warning(f"Column already exists, skipping: {migration[:60]}...")
                else:
                    raise

        # Step 5: Create indexes for performance
        logger.info("Creating indexes...")

        indexes = [
            "CREATE INDEX IF NOT EXISTS idx_positions_source ON positions(source)",
            "CREATE INDEX IF NOT EXISTS idx_positions_source_status ON positions(source, status)",
            "CREATE INDEX IF NOT EXISTS idx_positions_tp_order_status ON positions(take_profit_order_status)",
            "CREATE INDEX IF NOT EXISTS idx_limit_orders_position_id ON limit_orders(position_id)",
            "CREATE INDEX IF NOT EXISTS idx_limit_orders_order_id ON limit_orders(order_id)",
            "CREATE INDEX IF NOT EXISTS idx_limit_orders_status ON limit_orders(status)",
            "CREATE INDEX IF NOT EXISTS idx_limit_orders_order_type ON limit_orders(order_type)",
        ]

        for index in indexes:
            cursor.execute(index)
            logger.info(f"✓ {index[:60]}...")

        # Commit all changes
        conn.commit()
        logger.info("✅ Migration V1 completed successfully!")

        # Verify migration
        cursor.execute("PRAGMA table_info(positions)")
        new_columns = [col[1] for col in cursor.fetchall()]
        logger.info(f"Position table now has {len(new_columns)} columns")

        cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = [row[0] for row in cursor.fetchall()]
        logger.info(f"Database tables: {', '.join(tables)}")

    except Exception as e:
        logger.error(f"❌ Migration failed: {e}")
        conn.rollback()
        raise
    finally:
        conn.close()


def verify_migration(database_path: str):
    """Verify migration was successful."""
    logger.info("Verifying migration...")

    conn = sqlite3.connect(database_path)
    cursor = conn.cursor()

    try:
        # Check positions table
        cursor.execute("PRAGMA table_info(positions)")
        columns = {col[1]: col[2] for col in cursor.fetchall()}

        required_columns = [
            "source",
            "source_metadata",
            "take_profit_order_id",
            "take_profit_order_status",
            "take_profit_placed_at",
            "stop_loss_order_id",
            "stop_loss_order_status",
        ]

        missing = [col for col in required_columns if col not in columns]
        if missing:
            logger.error(f"❌ Missing columns in positions table: {missing}")
            return False

        # Check limit_orders table exists
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='limit_orders'")
        if not cursor.fetchone():
            logger.error("❌ limit_orders table not found")
            return False

        # Check trade_history columns
        cursor.execute("PRAGMA table_info(trade_history)")
        history_columns = {col[1]: col[2] for col in cursor.fetchall()}

        required_history_columns = ["source", "take_profit_order_id", "stop_loss_order_id"]
        missing_history = [col for col in required_history_columns if col not in history_columns]
        if missing_history:
            logger.error(f"❌ Missing columns in trade_history table: {missing_history}")
            return False

        # Check indexes
        cursor.execute("SELECT name FROM sqlite_master WHERE type='index'")
        indexes = [row[0] for row in cursor.fetchall()]

        required_indexes = [
            "idx_positions_source",
            "idx_positions_source_status",
            "idx_positions_tp_order_status",
            "idx_limit_orders_position_id",
        ]

        missing_indexes = [idx for idx in required_indexes if idx not in indexes]
        if missing_indexes:
            logger.warning(f"⚠️  Missing indexes: {missing_indexes}")

        logger.info("✅ Migration verification passed!")
        return True

    except Exception as e:
        logger.error(f"❌ Verification failed: {e}")
        return False
    finally:
        conn.close()


if __name__ == "__main__":
    import sys

    # Default database path
    database_path = "data/topshort.db"

    if len(sys.argv) > 1:
        database_path = sys.argv[1]

    if not Path(database_path).exists():
        logger.error(f"Database not found: {database_path}")
        sys.exit(1)

    logger.info("=" * 60)
    logger.info("TopShort Database Migration V1")
    logger.info("=" * 60)

    try:
        migrate_database(database_path)
        if verify_migration(database_path):
            logger.info("\n✅ Migration completed and verified successfully!")
            sys.exit(0)
        else:
            logger.error("\n❌ Migration verification failed!")
            sys.exit(1)
    except Exception as e:
        logger.error(f"\n❌ Migration failed: {e}")
        sys.exit(1)
