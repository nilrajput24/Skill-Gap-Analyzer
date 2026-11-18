#!/usr/bin/env python3
"""
Convenience entry point for SQLite to SQL Server 2022 migration.
Delegates to backend/migrate_sqlite_to_sqlserver.py.
"""
import sys
from pathlib import Path

backend_dir = Path(__file__).resolve().parent / "backend"
sys.path.insert(0, str(backend_dir))

from migrate_sqlite_to_sqlserver import main

if __name__ == "__main__":
    main()
