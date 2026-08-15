from __future__ import annotations

import json
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
REPORT_PATH = PROJECT_ROOT / "v2/data/real_runs/v2_validation_report.json"


class TargetLocationValidationReportTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.report = json.loads(REPORT_PATH.read_text(encoding="utf-8"))
        cls.validation = cls.report["candidate_target_location_validation"]

    def test_report_distinguishes_candidate_match_ambiguity(self) -> None:
        self.assertEqual(self.validation["canonical_candidate_match_row_count"], 139)
        self.assertEqual(self.validation["canonical_singleton_candidate_row_count"], 111)
        self.assertEqual(self.validation["canonical_ambiguous_candidate_row_count"], 28)
        self.assertEqual(self.validation["canonical_candidate_case_count"], 107)
        self.assertEqual(self.validation["canonical_singleton_candidate_case_count"], 90)
        self.assertEqual(self.validation["canonical_ambiguous_candidate_case_count"], 20)
        self.assertEqual(self.validation["canonical_candidate_without_selected_passage_count"], 27)

    def test_candidate_target_policy_has_no_automatic_promotion(self) -> None:
        self.assertEqual(self.validation["automatic_promotion_count"], 0)
        self.assertEqual(
            self.validation["automatic_promotion_policy"],
            "candidate_only_until_target_work_edition_and_quote_review",
        )


if __name__ == "__main__":
    unittest.main()
