from __future__ import annotations

import sqlite3
import sys
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT / "03-项目网站" / "scripts"))

from v2_acceptance_bridge import build_summary, get_case, list_cases  # noqa: E402


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

        self.assertEqual(first_page["total"], 7581)
        self.assertEqual(first_page["page_count"], 380)
        self.assertEqual(len(first_page["items"]), 20)
        self.assertEqual(len(second_page["items"]), 20)
        self.assertNotEqual(first_page["items"][0]["case_id"], second_page["items"][0]["case_id"])
        self.assertIn("target_location_candidate_count", first_page["items"][0])

    def test_case_filter_is_applied_before_pagination(self) -> None:
        payload = list_cases(
            self.connection,
            query="legacy-ai:1",
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
        self.assertEqual(payload["resolution_events"], [])

    def test_candidate_shell_detail_keeps_target_location_as_machine_candidate(self) -> None:
        payload = get_case(self.connection, "candidate-shell:dushu_zazhi_0002_candidate")

        self.assertIsNotNone(payload)
        self.assertGreater(len(payload["target_location_candidates"]), 0)
        self.assertIsNone(payload["target_passage_id"])
        self.assertEqual(payload["target_work"], "")
        self.assertTrue(
            all(
                row["machine_status"] == "candidate_only"
                and row["human_status"] == "pending"
                for row in payload["target_location_candidates"]
            )
        )

    def test_summary_exposes_valid_batched_review_task_artifacts(self) -> None:
        payload = build_summary(self.connection, self.database_path)

        task_artifacts = payload["review_task_artifacts"]
        self.assertTrue(task_artifacts["valid"])
        self.assertEqual(task_artifacts["batch_size"], 100)
        self.assertEqual(task_artifacts["counts"]["case_review"], 7581)
        self.assertEqual(task_artifacts["counts"]["target_work_resolution"], 7962)
        self.assertTrue(
            any(item["key"] == "review_task_artifacts" for item in payload["checks"])
        )
        self.assertEqual(
            payload["report_context"]["review_task_manifest"]["counts"]["external_passage_resolution"],
            121,
        )


if __name__ == "__main__":
    unittest.main()
