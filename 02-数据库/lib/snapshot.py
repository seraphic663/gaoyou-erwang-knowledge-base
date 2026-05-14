"""
Generic SQLite-to-JSON snapshot exporter.

Each bridge script calls dump_tables() to get raw table data,
then applies its own nesting / JSON-deserialization logic.
"""

import json
from pathlib import Path
from typing import List, Dict, Any, Optional

from .connection import connect, fetch_all


def dump_tables(
    db_path: Path,
    table_names: List[str],
    order_by: str = "id",
) -> Dict[str, List[Dict[str, Any]]]:
    """Dump named tables from a SQLite DB.

    Returns {table_name: [row_dicts]} for each table that exists.
    Non-existent tables are silently skipped.
    """
    conn = connect(db_path)
    try:
        result = {}
        for name in table_names:
            try:
                result[name] = fetch_all(conn, f'SELECT * FROM "{name}" ORDER BY {order_by}')
            except Exception:
                result[name] = []
        return result
    finally:
        conn.close()


def write_json(file_path: Path, data: Any):
    """Write data to a JSON file (UTF-8, indented)."""
    file_path.parent.mkdir(parents=True, exist_ok=True)
    file_path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def load_json(file_path: Path) -> Any:
    """Read and parse a JSON file."""
    return json.loads(file_path.read_text(encoding="utf-8"))


def loads_json(value: Optional[str], fallback: Any = None) -> Any:
    """Parse a JSON string column, returning fallback on failure."""
    if not value:
        return fallback
    try:
        return json.loads(value)
    except Exception:
        return fallback
