#!/usr/bin/env python3
"""Check database migration status.

Usage:
    python scripts/check_migrations.py [database_path]

Example:
    python scripts/check_migrations.py data/topshort.db
"""

import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from database.migrations.migration_manager import MigrationManager
import logging

logging.basicConfig(level=logging.INFO, format='%(message)s')
logger = logging.getLogger(__name__)


def main():
    """Check and display migration status."""
    if len(sys.argv) > 1:
        db_path = sys.argv[1]
    else:
        db_path = "data/topshort.db"

    if not Path(db_path).exists():
        logger.error(f"❌ Database not found: {db_path}")
        logger.info(f"The database will be created automatically on first run")
        return 0

    try:
        manager = MigrationManager(db_path)
        status = manager.get_migration_status()

        logger.info("=" * 70)
        logger.info("DATABASE MIGRATION STATUS")
        logger.info("=" * 70)
        logger.info(f"Database: {status['database_path']}")
        logger.info(f"Total migrations: {status['total']}")
        logger.info(f"Successful: {status['successful']}")
        logger.info(f"Failed: {status['failed']}")
        logger.info("")

        if status['migrations']:
            logger.info("Applied Migrations:")
            logger.info("-" * 70)
            for migration in status['migrations']:
                status_icon = "✓" if migration['success'] else "✗"
                logger.info(
                    f"{status_icon} {migration['version']}: {migration['name']}"
                )
                logger.info(f"  Applied: {migration['applied_at']}")
                if migration['execution_time_ms']:
                    logger.info(f"  Time: {migration['execution_time_ms']}ms")
                logger.info("")
        else:
            logger.info("No migrations applied yet")

        logger.info("=" * 70)

        return 0 if status['failed'] == 0 else 1

    except Exception as e:
        logger.error(f"❌ Error checking migration status: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
