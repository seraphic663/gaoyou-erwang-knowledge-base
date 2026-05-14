#!/usr/bin/env python3
"""
sqlite_bridge.py

将 02-数据库/data/dictionary.db 规范化为网站后端可直接消费的五表快照。
使用 02-数据库/lib/ 共享工具层。
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

# 将 02-数据库/ 加入 sys.path，以便导入 lib/
WORKSPACE_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(WORKSPACE_ROOT / "02-数据库"))

from lib.connection import connect, fetch_all
from lib.snapshot import write_json

DB_FILE = WORKSPACE_ROOT / "02-数据库" / "data" / "dictionary.db"
SNAPSHOT_FILE = WORKSPACE_ROOT / "03-项目网站" / "data" / "sqlite-snapshot.json"


def load_snapshot() -> dict:
    if not DB_FILE.exists():
        raise FileNotFoundError(f"SQLite database not found: {DB_FILE}")

    conn = connect(DB_FILE)
    try:
        snapshot = {
            "schemaVersion": 3,
            "source": "sqlite",
            "sourceLabel": "SQLite 实库",
            "meta": {
                "dbFile": str(DB_FILE.relative_to(WORKSPACE_ROOT)),
            },
            "tables": {
                "works": fetch_all(conn, "SELECT * FROM works ORDER BY id"),
                "passages": fetch_all(conn, "SELECT * FROM passages ORDER BY id"),
                "terms": fetch_all(conn, "SELECT * FROM terms ORDER BY id"),
                "cases": fetch_all(conn, "SELECT * FROM cases ORDER BY id"),
                "evidences": fetch_all(conn, "SELECT * FROM evidences ORDER BY id"),
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
            write_json(SNAPSHOT_FILE, snapshot)
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
