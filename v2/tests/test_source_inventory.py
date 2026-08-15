from __future__ import annotations

import sys
import unittest
from pathlib import Path


V2_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(V2_ROOT / "scripts"))

from audit_source_inventory import build_report  # noqa: E402


class SourceInventoryTest(unittest.TestCase):
    def test_inventory_keeps_mysql_boundary_and_current_v2_counts_explicit(self) -> None:
        report = build_report()

        search = report["mysql10_snapshot_search"]
        self.assertEqual(search["status"], "not_found_in_project_tree")
        self.assertEqual(search["mysql_named_files"], [])

        old_db = report["legacy_machine_route"]["dictionary_db_observed"]
        self.assertEqual(old_db["database_type"], "SQLite")
        self.assertEqual(old_db["table_counts"]["passages"], 0)
        self.assertEqual(old_db["table_counts"]["cases"], 815)
        self.assertEqual(old_db["table_counts"]["evidences"], 7120)

        self.assertEqual(report["legacy_ai_json"]["file_count"], 3)
        self.assertEqual(report["legacy_ai_json"]["reported_case_count"], 17)
        self.assertEqual(
            report["actual_v2_use"]["route_counts"]["original_markdown_candidates"],
            6749,
        )
        self.assertEqual(
            report["actual_v2_use"]["canonical_hash_policy"]["dushu_active"],
            "1460a906825998bf8a4bf3c51d4525fe19b8b79f377fb6d25ccdad4dc698e19e",
        )


if __name__ == "__main__":
    unittest.main()
