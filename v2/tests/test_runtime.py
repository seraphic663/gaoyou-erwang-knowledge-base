from __future__ import annotations

import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path


V2_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(V2_ROOT / "src"))

from erwang_v2.runtime import connect_read_only, parse_json, relative_path  # noqa: E402


class RuntimeHelpersTest(unittest.TestCase):
    def test_relative_path_and_parse_json_are_stable(self) -> None:
        self.assertEqual(relative_path(Path("v2/README.md")), "v2/README.md")
        self.assertIsNone(relative_path(None))
        self.assertEqual(parse_json({"ok": True}, {}), {"ok": True})
        self.assertEqual(parse_json("not-json", []), [])

    def test_connect_read_only_enables_query_only(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            database_path = Path(directory) / "runtime.db"
            with sqlite3.connect(database_path) as connection:
                connection.execute("CREATE TABLE sample(value TEXT)")
                connection.execute("INSERT INTO sample VALUES ('ok')")

            with connect_read_only(database_path) as connection:
                self.assertEqual(connection.execute("SELECT value FROM sample").fetchone()[0], "ok")
                with self.assertRaises(sqlite3.OperationalError):
                    connection.execute("INSERT INTO sample VALUES ('blocked')")


if __name__ == "__main__":
    unittest.main()
