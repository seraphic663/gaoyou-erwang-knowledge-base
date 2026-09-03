"""Shared runtime helpers for V2 command-line reports and bridges.

These helpers deliberately contain no project-specific business rules. They
keep timestamp, path, JSON and read-only SQLite behavior consistent while
leaving each report responsible for its own validation semantics.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[3]


def now() -> str:
    """Return an ISO-8601 UTC timestamp for generated artifacts."""

    return datetime.now(timezone.utc).isoformat()


def relative_path(
    value: str | Path | None,
    *,
    project_root: Path = PROJECT_ROOT,
) -> str | None:
    """Render a path relative to the project when possible."""

    if value is None:
        return None
    path = Path(value)
    try:
        return path.resolve().relative_to(project_root.resolve()).as_posix()
    except ValueError:
        return path.as_posix()


def parse_json(value: Any, fallback: Any) -> Any:
    """Parse a JSON value while preserving the caller's fallback policy."""

    if isinstance(value, (dict, list)):
        return value
    try:
        return json.loads(value or "")
    except (TypeError, ValueError):
        return fallback


def load_json(path: str | Path) -> dict[str, Any]:
    """Load an object-shaped JSON artifact, or return an empty object."""

    json_path = Path(path)
    if not json_path.is_file():
        return {}
    try:
        value = json.loads(json_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return value if isinstance(value, dict) else {}


def connect_read_only(
    database_path: str | Path,
    *,
    missing_error: str = "V2 database not found",
) -> sqlite3.Connection:
    """Open a V2 database without enabling writes."""

    path = Path(database_path).resolve()
    if not path.is_file():
        raise FileNotFoundError(f"{missing_error}:{path}")
    connection = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA query_only = ON")
    connection.execute("PRAGMA foreign_keys = ON")
    return connection
