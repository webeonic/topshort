"""Automatic database migration manager.

This module handles automatic database migrations on application startup.
Migrations are applied sequentially and tracked in the database.
"""

import hashlib
import logging
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


class MigrationManager:
    """Manages database migrations automatically."""

    def __init__(self, database_path: str):
        """Initialize migration manager.

        Args:
            database_path: Path to SQLite database file
        """
        self.database_path = database_path
        self.migrations_dir = Path(__file__).parent / "scripts"
        self.migrations_dir.mkdir(exist_ok=True)

    def ensure_migrations_table(self, conn: sqlite3.Connection):
        """Create migrations tracking table if it doesn't exist.

        Args:
            conn: Database connection
        """
        cursor = conn.cursor()
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS schema_migrations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                version VARCHAR(50) NOT NULL UNIQUE,
                name VARCHAR(255) NOT NULL,
                checksum VARCHAR(64) NOT NULL,
                applied_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                execution_time_ms INTEGER,
                success BOOLEAN NOT NULL DEFAULT 1
            )
        """
        )
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_migrations_version ON schema_migrations(version)")
        conn.commit()
        logger.debug("Migrations tracking table ready")

    def get_applied_migrations(self, conn: sqlite3.Connection) -> List[str]:
        """Get list of already applied migration versions.

        Args:
            conn: Database connection

        Returns:
            List of applied migration versions
        """
        cursor = conn.cursor()
        cursor.execute("SELECT version FROM schema_migrations WHERE success = 1 ORDER BY version")
        return [row[0] for row in cursor.fetchall()]

    def get_pending_migrations(self) -> List[Dict[str, str]]:
        """Get list of pending migrations that need to be applied.

        Returns:
            List of migration dicts with 'version', 'name', 'path'
        """
        # Get all migration files
        migration_files = sorted(self.migrations_dir.glob("*.sql"))

        migrations = []
        for file_path in migration_files:
            # Parse filename: V001__description.sql or V001_description.sql
            filename = file_path.stem
            parts = filename.split("__") if "__" in filename else filename.split("_", 1)

            if len(parts) >= 2:
                version = parts[0]
                name = parts[1] if len(parts) > 1 else filename
                migrations.append({"version": version, "name": name, "path": str(file_path)})

        return migrations

    def calculate_checksum(self, file_path: str) -> str:
        """Calculate SHA256 checksum of migration file.

        Args:
            file_path: Path to migration file

        Returns:
            Hexadecimal checksum string
        """
        sha256 = hashlib.sha256()
        with open(file_path, "rb") as f:
            sha256.update(f.read())
        return sha256.hexdigest()

    def apply_migration(self, conn: sqlite3.Connection, migration: Dict[str, str]) -> bool:
        """Apply a single migration.

        Args:
            conn: Database connection
            migration: Migration dict with version, name, path

        Returns:
            True if successful, False otherwise
        """
        version = migration["version"]
        name = migration["name"]
        file_path = migration["path"]

        logger.info(f"Applying migration {version}: {name}")

        try:
            # Read migration SQL
            with open(file_path, "r", encoding="utf-8") as f:
                sql = f.read()

            # Calculate checksum
            checksum = self.calculate_checksum(file_path)

            # Execute migration
            cursor = conn.cursor()
            start_time = datetime.now()

            # Split and execute statements
            statements = [s.strip() for s in sql.split(";") if s.strip()]
            for statement in statements:
                if statement:
                    cursor.execute(statement)

            execution_time = int((datetime.now() - start_time).total_seconds() * 1000)

            # Record migration
            cursor.execute(
                """
                INSERT INTO schema_migrations (version, name, checksum, execution_time_ms, success)
                VALUES (?, ?, ?, ?, 1)
            """,
                (version, name, checksum, execution_time),
            )

            conn.commit()
            logger.info(f"✓ Migration {version} applied successfully ({execution_time}ms)")
            return True

        except Exception as e:
            logger.error(f"✗ Migration {version} failed: {e}")
            conn.rollback()

            # Record failed migration
            try:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    INSERT INTO schema_migrations (version, name, checksum, success)
                    VALUES (?, ?, ?, 0)
                """,
                    (version, name, self.calculate_checksum(file_path)),
                )
                conn.commit()
            except:
                pass

            return False

    def run_migrations(self, force: bool = False) -> Dict[str, Any]:
        """Run all pending migrations.

        Args:
            force: If True, reapply all migrations (USE WITH CAUTION)

        Returns:
            Dict with migration results
        """
        logger.info("=" * 60)
        logger.info("Starting automatic database migration")
        logger.info("=" * 60)

        # Create database file if it doesn't exist
        db_path = Path(self.database_path)
        if not db_path.parent.exists():
            db_path.parent.mkdir(parents=True, exist_ok=True)
            logger.info(f"Created database directory: {db_path.parent}")

        # Connect to database
        conn = sqlite3.connect(self.database_path)

        try:
            # Ensure migrations table exists
            self.ensure_migrations_table(conn)

            # Get applied migrations
            applied = [] if force else self.get_applied_migrations(conn)
            logger.info(f"Already applied migrations: {len(applied)}")

            # Get all migrations
            all_migrations = self.get_pending_migrations()
            logger.info(f"Total migrations available: {len(all_migrations)}")

            # Filter pending migrations
            pending = [m for m in all_migrations if m["version"] not in applied]

            if not pending:
                logger.info("✓ Database is up to date - no migrations needed")
                return {"success": True, "applied": 0, "failed": 0, "total": len(all_migrations)}

            logger.info(f"Pending migrations to apply: {len(pending)}")

            # Apply migrations
            applied_count = 0
            failed_count = 0

            for migration in pending:
                if self.apply_migration(conn, migration):
                    applied_count += 1
                else:
                    failed_count += 1
                    logger.error(f"Migration {migration['version']} failed, stopping")
                    break

            # Summary
            logger.info("=" * 60)
            if failed_count == 0:
                logger.info(f"✓ All migrations applied successfully!")
                logger.info(f"  - Applied: {applied_count}")
                logger.info(f"  - Total: {len(all_migrations)}")
            else:
                logger.error(f"✗ Migration process stopped with errors")
                logger.error(f"  - Applied: {applied_count}")
                logger.error(f"  - Failed: {failed_count}")

            logger.info("=" * 60)

            return {
                "success": failed_count == 0,
                "applied": applied_count,
                "failed": failed_count,
                "total": len(all_migrations),
            }

        finally:
            conn.close()

    def get_migration_status(self) -> Dict[str, Any]:
        """Get current migration status.

        Returns:
            Dict with migration status information
        """
        conn = sqlite3.connect(self.database_path)

        try:
            self.ensure_migrations_table(conn)

            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT version, name, applied_at, execution_time_ms, success
                FROM schema_migrations
                ORDER BY version
            """
            )

            migrations = []
            for row in cursor.fetchall():
                migrations.append(
                    {
                        "version": row[0],
                        "name": row[1],
                        "applied_at": row[2],
                        "execution_time_ms": row[3],
                        "success": bool(row[4]),
                    }
                )

            return {
                "database_path": self.database_path,
                "migrations": migrations,
                "total": len(migrations),
                "successful": sum(1 for m in migrations if m["success"]),
                "failed": sum(1 for m in migrations if not m["success"]),
            }

        finally:
            conn.close()

    def create_backup(self) -> Optional[str]:
        """Create backup of database before migration.

        Returns:
            Path to backup file or None if failed
        """
        try:
            if not Path(self.database_path).exists():
                logger.info("Database doesn't exist yet, skipping backup")
                return None

            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            backup_path = f"{self.database_path}.backup_{timestamp}"

            import shutil

            shutil.copy2(self.database_path, backup_path)

            logger.info(f"✓ Database backed up to: {backup_path}")
            return backup_path

        except Exception as e:
            logger.error(f"Failed to create backup: {e}")
            return None


def run_auto_migrations(database_path: str, create_backup: bool = True) -> bool:
    """Run automatic migrations on application startup.

    Args:
        database_path: Path to database file
        create_backup: Whether to create backup before migration

    Returns:
        True if migrations successful, False otherwise
    """
    try:
        manager = MigrationManager(database_path)

        # Create backup if database exists
        if create_backup:
            manager.create_backup()

        # Run migrations
        result = manager.run_migrations()

        return result["success"]

    except Exception as e:
        logger.error(f"Auto-migration failed: {e}")
        return False


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1:
        db_path = sys.argv[1]
    else:
        db_path = "data/topshort.db"

    success = run_auto_migrations(db_path)
    sys.exit(0 if success else 1)
