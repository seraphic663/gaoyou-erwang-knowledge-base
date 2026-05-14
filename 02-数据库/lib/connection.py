"""
Shared SQLite connection and query helpers.

Used by: main/importer.py, main/database.py, annotation/importer.py,
         scripts/sqlite_bridge.py, scripts/annotation_bridge.py
"""

import sqlite3
from pathlib import Path
from typing import Optional, List, Dict, Any


def connect(db_path: Path) -> sqlite3.Connection:
    """Open a SQLite connection with row_factory set."""
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    return conn


def fetch_all(conn: sqlite3.Connection, sql: str, params=()) -> List[Dict[str, Any]]:
    """Execute a query and return all rows as list of dicts."""
    return [dict(row) for row in conn.execute(sql, params).fetchall()]


def fetch_one(conn: sqlite3.Connection, sql: str, params=()) -> Optional[Dict[str, Any]]:
    """Execute a query and return the first row as dict, or None."""
    row = conn.execute(sql, params).fetchone()
    return dict(row) if row else None


def execute(conn: sqlite3.Connection, sql: str, params=()):
    """Execute a statement and commit."""
    conn.execute(sql, params)
    conn.commit()
