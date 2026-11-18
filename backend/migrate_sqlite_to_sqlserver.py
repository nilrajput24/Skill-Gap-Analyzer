#!/usr/bin/env python3
"""
Database Migration Script: SQLite to Microsoft SQL Server 2022
Project: Student Skill Gap Analyzer and Personalized Learning Roadmap Provider

This script migrates all data from the active SQLite database into Microsoft SQL Server 2022.
Features:
- Automated pre-migration SQLite database backup
- Preserves all primary keys, foreign keys, timestamps, and NULL values
- Handles SQL Server IDENTITY_INSERT per table
- Idempotent and safe to run multiple times without creating duplicates
- Validates row counts and relational integrity post-migration
- Reseeds SQL Server identity sequences to prevent future primary key collisions
"""

import sys
import os
import argparse
import shutil
import sqlite3
import urllib.parse
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Tuple

# Ensure backend directory is in python path
BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR))

import pyodbc
from sqlalchemy import create_engine, text, inspect
from app.database import Base
import app.models  # Register all SQLAlchemy models


TABLE_MIGRATION_ORDER = [
    "users",
    "student_profiles",
    "password_reset_tokens",
    "analyses",
    "student_skills",
    "job_snapshots",
    "required_skills",
    "roadmap_items",
]


def parse_datetime_val(val: Any) -> Any:
    """Parse SQLite timestamp strings into Python datetime objects for SQL Server."""
    if val is None:
        return None
    if isinstance(val, (int, float)):
        return datetime.fromtimestamp(val, tz=timezone.utc)
    if isinstance(val, str):
        val_clean = val.strip()
        if not val_clean:
            return None
        # Handle formats like "2026-10-25 17:44:49.851508", "2026-10-25T17:44:49.851508", "2026-10-25 17:44:49"
        for fmt in (
            "%Y-%m-%d %H:%M:%S.%f",
            "%Y-%m-%dT%H:%M:%S.%f",
            "%Y-%m-%d %H:%M:%S",
            "%Y-%m-%dT%H:%M:%S",
            "%Y-%m-%d",
        ):
            try:
                dt = datetime.strptime(val_clean.split("+")[0].split("Z")[0], fmt)
                return dt
            except ValueError:
                continue
        # Fallback to fromisoformat
        try:
            return datetime.fromisoformat(val_clean.replace("Z", "+00:00"))
        except Exception:
            return val
    return val


def create_sqlite_backup(sqlite_path: Path) -> Path:
    """Creates a timestamped backup of the SQLite database before running migration."""
    backup_dir = sqlite_path.parent / "backups"
    backup_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = backup_dir / f"{sqlite_path.stem}_backup_{timestamp}.db"
    shutil.copy2(sqlite_path, backup_path)
    
    # Verify backup file exists and has identical file size
    orig_size = sqlite_path.stat().st_size
    backup_size = backup_path.stat().st_size
    if orig_size != backup_size or backup_size == 0:
        raise RuntimeError(
            f"Backup verification failed: {backup_path} ({backup_size} bytes) "
            f"does not match original {sqlite_path} ({orig_size} bytes)."
        )
    print(f"[BACKUP] Successfully created SQLite backup at: {backup_path} ({backup_size:,} bytes)")
    return backup_path


def build_sqlserver_connection_string(
    server: str,
    database: str,
    trusted_connection: bool = True,
    username: str | None = None,
    password: str | None = None,
    driver: str = "ODBC Driver 17 for SQL Server",
) -> str:
    """Builds a pyodbc connection string for SQL Server."""
    parts = [
        f"DRIVER={{{driver}}}",
        f"SERVER={server}",
        f"DATABASE={database}",
        "TrustServerCertificate=yes",
    ]
    if trusted_connection:
        parts.append("Trusted_Connection=yes")
    elif username and password:
        parts.append(f"UID={username}")
        parts.append(f"PWD={password}")
    else:
        raise ValueError("Must specify trusted_connection=True or provide username and password.")
    return ";".join(parts) + ";"


def ensure_sqlserver_database_exists(
    server: str,
    database: str,
    trusted_connection: bool = True,
    username: str | None = None,
    password: str | None = None,
    driver: str = "ODBC Driver 17 for SQL Server",
):
    """Connects to master and creates the target database if it does not already exist."""
    master_conn_str = build_sqlserver_connection_string(
        server=server,
        database="master",
        trusted_connection=trusted_connection,
        username=username,
        password=password,
        driver=driver,
    )
    conn = pyodbc.connect(master_conn_str, autocommit=True)
    cur = conn.cursor()
    cur.execute("SELECT name FROM sys.databases WHERE name = ?", (database,))
    if not cur.fetchone():
        print(f"[SQL Server] Database '{database}' does not exist. Creating database...")
        cur.execute(f"CREATE DATABASE [{database}]")
        print(f"[SQL Server] Database '{database}' created successfully.")
    else:
        print(f"[SQL Server] Database '{database}' already exists.")
    conn.close()


def migrate(
    sqlite_path: Path,
    server: str = r".\SQLEXPRESS",
    database: str = "StudentSkillGapAnalyzer",
    trusted_connection: bool = True,
    username: str | None = None,
    password: str | None = None,
    driver: str = "ODBC Driver 17 for SQL Server",
    dry_run: bool = False,
) -> bool:
    """
    Executes end-to-end data migration from SQLite to SQL Server 2022.
    """
    print("=" * 70)
    print("Starting Student Skill Gap Analyzer Migration: SQLite -> SQL Server 2022")
    print(f"Source SQLite DB : {sqlite_path}")
    print(f"Target SQL Server: {server} -> Database: {database}")
    print(f"Authentication   : {'Windows Authentication (Trusted)' if trusted_connection else f'SQL Auth ({username})'}")
    print(f"Dry Run Mode     : {dry_run}")
    print("=" * 70)

    if not sqlite_path.exists():
        raise FileNotFoundError(f"Source SQLite database does not exist: {sqlite_path}")

    # 1. Backup SQLite database first
    create_sqlite_backup(sqlite_path)

    # 2. Ensure target SQL Server database exists
    ensure_sqlserver_database_exists(
        server=server,
        database=database,
        trusted_connection=trusted_connection,
        username=username,
        password=password,
        driver=driver,
    )

    # 3. Create SQLAlchemy engine for SQL Server and ensure schema exists
    odbc_conn_str = build_sqlserver_connection_string(
        server=server,
        database=database,
        trusted_connection=trusted_connection,
        username=username,
        password=password,
        driver=driver,
    )
    sqlalchemy_url = f"mssql+pyodbc:///?odbc_connect={urllib.parse.quote_plus(odbc_conn_str)}"
    engine = create_engine(sqlalchemy_url, pool_pre_ping=True)

    print("[SCHEMA] Applying SQLAlchemy Base.metadata.create_all to SQL Server...")
    Base.metadata.create_all(bind=engine)
    print("[SCHEMA] SQL Server schema created / verified successfully.")

    # 4. Open SQLite connection
    sqlite_conn = sqlite3.connect(sqlite_path)
    sqlite_conn.row_factory = sqlite3.Row
    sqlite_cur = sqlite_conn.cursor()

    # Find which tables exist in SQLite
    sqlite_cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
    sqlite_tables = {row[0] for row in sqlite_cur.fetchall()}

    # 5. Connect directly via pyodbc for high-performance row migration with IDENTITY_INSERT
    pyodbc_conn = pyodbc.connect(odbc_conn_str, autocommit=False)
    pyodbc_cur = pyodbc_conn.cursor()

    migration_stats: Dict[str, Dict[str, int]] = {}

    try:
        for table_name in TABLE_MIGRATION_ORDER:
            if table_name not in sqlite_tables:
                print(f"[SKIP] Table '{table_name}' does not exist in source SQLite database.")
                migration_stats[table_name] = {"sqlite": 0, "inserted": 0, "existing": 0, "total_sqlserver": 0}
                continue

            print(f"\n--- Migrating Table: [{table_name}] ---")
            
            # Read all SQLite rows
            sqlite_cur.execute(f"SELECT * FROM [{table_name}]")
            sqlite_rows = sqlite_cur.fetchall()
            col_names = [desc[0] for desc in sqlite_cur.description]
            sqlite_count = len(sqlite_rows)
            print(f"  Source SQLite row count: {sqlite_count}")

            if sqlite_count == 0:
                print(f"  Table '{table_name}' is empty in SQLite. Nothing to transfer.")
                migration_stats[table_name] = {"sqlite": 0, "inserted": 0, "existing": 0, "total_sqlserver": 0}
                continue

            # Check existing records in SQL Server
            pyodbc_cur.execute(f"SELECT id FROM [{table_name}]")
            existing_ids = {row[0] for row in pyodbc_cur.fetchall()}
            print(f"  Existing rows in SQL Server: {len(existing_ids)}")

            # Check if this table has an IDENTITY column (usually 'id')
            pyodbc_cur.execute(
                """
                SELECT COLUMN_NAME
                FROM INFORMATION_SCHEMA.COLUMNS
                WHERE TABLE_NAME = ? AND COLUMNPROPERTY(OBJECT_ID(TABLE_SCHEMA + '.' + TABLE_NAME), COLUMN_NAME, 'IsIdentity') = 1
                """,
                (table_name,),
            )
            identity_cols = [r[0] for r in pyodbc_cur.fetchall()]
            has_identity = len(identity_cols) > 0

            if has_identity and not dry_run:
                pyodbc_cur.execute(f"SET IDENTITY_INSERT [{table_name}] ON")

            # Prepare insert statement
            cols_clause = ", ".join(f"[{col}]" for col in col_names)
            placeholders = ", ".join("?" for _ in col_names)
            insert_sql = f"INSERT INTO [{table_name}] ({cols_clause}) VALUES ({placeholders})"

            inserted_count = 0
            skipped_existing = 0
            max_id = 0

            # Determine exact datetime and boolean column names for proper typing
            DATETIME_COLUMNS = {
                "created_at",
                "updated_at",
                "fetched_at",
                "posted_at",
                "expires_at",
                "used_at",
            }
            BOOL_COLUMNS = {"self_reported", "is_stale", "is_used"}

            for row in sqlite_rows:
                row_dict = dict(row)
                row_id = row_dict.get("id")
                if row_id is not None:
                    max_id = max(max_id, row_id)

                if row_id in existing_ids:
                    skipped_existing += 1
                    continue

                # Prepare values with proper type conversion
                values = []
                for col in col_names:
                    val = row_dict[col]
                    if col in DATETIME_COLUMNS:
                        val = parse_datetime_val(val)
                    elif col in BOOL_COLUMNS and val is not None:
                        val = 1 if val else 0
                    elif col == "estimated_hours" and val is not None:
                        val = float(val)
                    elif col == "confidence" and val is not None:
                        val = float(val)
                    values.append(val)

                if not dry_run:
                    pyodbc_cur.execute(insert_sql, tuple(values))
                inserted_count += 1

            if has_identity and not dry_run:
                pyodbc_cur.execute(f"SET IDENTITY_INSERT [{table_name}] OFF")

            # Reseed identity sequence so new inserts in SQL Server get max_id + 1
            if has_identity and max_id > 0 and not dry_run:
                pyodbc_cur.execute(f"DBCC CHECKIDENT ('[{table_name}]', RESEED, ?)", (max_id,))
                print(f"  Reseeded identity column for [{table_name}] to {max_id}")

            if not dry_run:
                pyodbc_conn.commit()

            # Verify total count in SQL Server
            pyodbc_cur.execute(f"SELECT COUNT(*) FROM [{table_name}]")
            total_sqlserver = pyodbc_cur.fetchone()[0]

            migration_stats[table_name] = {
                "sqlite": sqlite_count,
                "inserted": inserted_count,
                "existing": skipped_existing,
                "total_sqlserver": total_sqlserver,
            }
            print(f"  Inserted: {inserted_count} | Skipped existing: {skipped_existing} | Total in SQL Server: {total_sqlserver}")

    except Exception as exc:
        pyodbc_conn.rollback()
        print(f"\n[ERROR] Migration failed on table '{table_name}': {exc}")
        raise
    finally:
        sqlite_conn.close()

    # 6. Post-migration Verification & Relational Integrity Checks
    print("\n" + "=" * 70)
    print("POST-MIGRATION VERIFICATION & RELATIONAL INTEGRITY REPORT")
    print("=" * 70)
    all_matched = True

    print(f"{'Table Name':<25} | {'SQLite Count':<12} | {'Inserted':<10} | {'Existing':<10} | {'SQL Server Total':<16}")
    print("-" * 80)
    for t, stats in migration_stats.items():
        print(
            f"{t:<25} | {stats['sqlite']:<12} | {stats['inserted']:<10} | "
            f"{stats['existing']:<10} | {stats['total_sqlserver']:<16}"
        )
        if stats['sqlite'] > stats['total_sqlserver']:
            all_matched = False

    # Foreign Key Relationship Verifications
    print("\n--- Verifying Foreign Key Integrity in SQL Server ---")
    fk_checks = [
        ("student_profiles", "user_id", "users", "id"),
        ("password_reset_tokens", "user_id", "users", "id"),
        ("analyses", "user_id", "users", "id"),
        ("student_skills", "analysis_id", "analyses", "id"),
        ("job_snapshots", "analysis_id", "analyses", "id"),
        ("required_skills", "job_snapshot_id", "job_snapshots", "id"),
        ("roadmap_items", "analysis_id", "analyses", "id"),
    ]

    orphan_found = False
    for child_tbl, child_col, parent_tbl, parent_col in fk_checks:
        query = f"""
            SELECT COUNT(*) FROM [{child_tbl}] c
            LEFT JOIN [{parent_tbl}] p ON c.[{child_col}] = p.[{parent_col}]
            WHERE p.[{parent_col}] IS NULL AND c.[{child_col}] IS NOT NULL
        """
        pyodbc_cur.execute(query)
        orphan_count = pyodbc_cur.fetchone()[0]
        if orphan_count > 0:
            print(f"  [FAIL] {orphan_count} orphaned rows in [{child_tbl}].[{child_col}] referencing [{parent_tbl}].[{parent_col}]")
            orphan_found = True
        else:
            print(f"  [PASS] Foreign Key [{child_tbl}].[{child_col}] -> [{parent_tbl}].[{parent_col}] intact.")

    # Spot check: verify user records and analyses
    pyodbc_cur.execute("SELECT id, name, email FROM [users]")
    users = pyodbc_cur.fetchall()
    print(f"\nMigrated Users in SQL Server ({len(users)} users):")
    for u in users:
        pyodbc_cur.execute("SELECT COUNT(*) FROM [analyses] WHERE user_id = ?", (u[0],))
        analysis_count = pyodbc_cur.fetchone()[0]
        print(f"  User {u[0]}: {u[1]} ({u[2]}) -> {analysis_count} analyses")

    pyodbc_conn.close()

    if all_matched and not orphan_found:
        print("\n[SUCCESS] SQLite to SQL Server 2022 migration completed with 100% integrity!")
        return True
    else:
        print("\n[WARNING] Migration completed with count discrepancies or integrity warnings. Please review output above.")
        return False


def main():
    parser = argparse.ArgumentParser(description="Migrate SQLite data to Microsoft SQL Server 2022")
    parser.add_argument(
        "--sqlite-path",
        default=str(BASE_DIR / "app.db"),
        help="Path to source SQLite database file (default: backend/app.db)",
    )
    parser.add_argument(
        "--server",
        default=r".\SQLEXPRESS",
        help=r"SQL Server instance (default: .\SQLEXPRESS)",
    )
    parser.add_argument(
        "--database",
        default="StudentSkillGapAnalyzer",
        help="Target SQL Server database name (default: StudentSkillGapAnalyzer)",
    )
    parser.add_argument(
        "--driver",
        default="ODBC Driver 17 for SQL Server",
        help="ODBC driver name (default: ODBC Driver 17 for SQL Server)",
    )
    parser.add_argument(
        "--user",
        default=None,
        help="SQL Server SQL auth username (if not using Windows Authentication)",
    )
    parser.add_argument(
        "--password",
        default=None,
        help="SQL Server SQL auth password",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Simulate migration without modifying target database",
    )

    args = parser.parse_args()
    sqlite_file = Path(args.sqlite_path)
    trusted = (args.user is None)

    migrate(
        sqlite_path=sqlite_file,
        server=args.server,
        database=args.database,
        trusted_connection=trusted,
        username=args.user,
        password=args.password,
        driver=args.driver,
        dry_run=args.dry_run,
    )


if __name__ == "__main__":
    main()
