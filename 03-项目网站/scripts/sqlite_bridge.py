#!/usr/bin/env python3
"""
sqlite_bridge.py

将 02-数据库/data/dictionary.db 规范化为网站后端可直接消费的五表快照。
"""

from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path


WORKSPACE_ROOT = Path(__file__).resolve().parents[2]
DB_FILE = WORKSPACE_ROOT / "02-数据库" / "data" / "dictionary.db"
SNAPSHOT_FILE = WORKSPACE_ROOT / "03-项目网站" / "data" / "sqlite-snapshot.json"


def to_dicts(rows: list[sqlite3.Row]) -> list[dict]:
    return [dict(row) for row in rows]


def load_snapshot() -> dict:
    if not DB_FILE.exists():
        raise FileNotFoundError(f"SQLite database not found: {DB_FILE}")

    conn = sqlite3.connect(str(DB_FILE))
    conn.row_factory = sqlite3.Row

    try:
        snapshot = {
            "schemaVersion": 3,
            "source": "sqlite",
            "sourceLabel": "SQLite 实库",
            "meta": {
                "dbFile": str(DB_FILE),
            },
            "tables": {
                "works": to_dicts(conn.execute("SELECT * FROM works ORDER BY id").fetchall()),
                "passages": to_dicts(conn.execute("SELECT * FROM passages ORDER BY id").fetchall()),
                "terms": to_dicts(conn.execute("SELECT * FROM terms ORDER BY id").fetchall()),
                "cases": to_dicts(conn.execute("SELECT * FROM cases ORDER BY id").fetchall()),
                "evidences": to_dicts(conn.execute("SELECT * FROM evidences ORDER BY id").fetchall()),
            },
        }
    finally:
        conn.close()

    return snapshot


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

    command = sys.argv[1] if len(sys.argv) > 1 else "snapshot"

    try:
        snapshot = load_snapshot()
        if command == "snapshot":
            print(json.dumps(snapshot, ensure_ascii=False))
            return 0

        if command == "export":
            SNAPSHOT_FILE.parent.mkdir(parents=True, exist_ok=True)
            SNAPSHOT_FILE.write_text(
                json.dumps(snapshot, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            print(
                json.dumps(
                    {
                        "ok": True,
                        "snapshotFile": str(SNAPSHOT_FILE),
                        "counts": {name: len(records) for name, records in snapshot["tables"].items()},
                    },
                    ensure_ascii=False,
                )
            )
            return 0

        print(json.dumps({"ok": False, "message": f"Unsupported command: {command}"}, ensure_ascii=False))
        return 1
    except Exception as error:
        print(str(error), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
