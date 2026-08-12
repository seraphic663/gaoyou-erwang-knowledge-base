from __future__ import annotations

import sqlite3
import sys
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT / "03-项目网站" / "scripts"))

from v2_acceptance_bridge import get_case, list_cases  # noqa: E402


class V2AcceptanceBridgeTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.database_path = PROJECT_ROOT / "v2/data/real_runs/annotation_v2.db"

    def setUp(self) -> None:
        self.connection = sqlite3.connect(f"file:{self.database_path}?mode=ro", uri=True)
        self.connection.row_factory = sqlite3.Row

    def tearDown(self) -> None:
        self.connection.close()

    def test_cases_are_pageable_without_changing_total(self) -> None:
        first_page = list_cases(self.connection, page=1, page_size=20)
        second_page = list_cases(self.connection, page=2, page_size=20)

        self.assertEqual(first_page["total"], 936)
        self.assertEqual(first_page["page_count"], 47)
        self.assertEqual(len(first_page["items"]), 20)
        self.assertEqual(len(second_page["items"]), 20)
        self.assertNotEqual(first_page["items"][0]["case_id"], second_page["items"][0]["case_id"])

    def test_case_filter_is_applied_before_pagination(self) -> None:
        payload = list_cases(
            self.connection,
            query="平原",
            source_work="读书杂志",
            machine_status="draft",
            page=1,
            page_size=20,
        )

        self.assertEqual(payload["total"], 1)
        self.assertEqual(len(payload["items"]), 1)
        self.assertEqual(payload["items"][0]["case_id"], "legacy-ai:1")

    def test_case_detail_keeps_evidence_summary_for_collapsed_view(self) -> None:
        payload = get_case(self.connection, "legacy-ai:16")

        self.assertIsNotNone(payload)
        self.assertEqual(payload["evidence_summary"], {
            "secondary_citation_match": 8,
            "external_source_pending": 14,
        })
        self.assertEqual(len(payload["evidences"]), 22)

    def test_legacy_case_detail_exposes_both_passage_links_and_full_payload(self) -> None:
        payload = get_case(self.connection, "legacy-dictionary:1")

        self.assertIsNotNone(payload)
        self.assertIsNotNone(payload["source_passage"])
        self.assertIsNotNone(payload["target_passage"])
        self.assertEqual(len(payload["terms"]), 22)
        self.assertEqual(len(payload["process_steps"]), 5)
        self.assertIn("_migration", payload["case_data"])
        self.assertIn("source_file_sha256", payload["provenance"])


if __name__ == "__main__":
    unittest.main()
