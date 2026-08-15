from __future__ import annotations

import json
import unittest
from pathlib import Path


V2_ROOT = Path(__file__).resolve().parents[1]
REPORT_PATH = V2_ROOT / "data/real_runs/workflow_coverage_report.v1.json"


class WorkflowCoverageReportTest(unittest.TestCase):
    def test_report_distinguishes_candidate_shells_from_review_boundaries(self) -> None:
        report = json.loads(REPORT_PATH.read_text(encoding="utf-8"))
        self.assertTrue(report["valid"])
        self.assertEqual(report["current_round_focus"]["workflow_steps"], [5, 7, 8, 10, 11])
        self.assertTrue(report["current_round_focus"]["off_track_check"]["source_chain_preserved"])
        self.assertEqual(
            report["inventory"]["candidates"]["case_origin_counts"][
                "original_markdown_candidate_shell"
            ],
            6745,
        )
        self.assertEqual(report["inventory"]["cases"]["target_passage_links"], 815)
        self.assertEqual(report["inventory"]["external"]["canonical_external_document_count"], 0)
        self.assertEqual(report["inventory"]["states"]["review_event_count"], 0)
        self.assertEqual(report["inventory"]["states"]["lifecycle_counts"].get("gold", 0), 0)


if __name__ == "__main__":
    unittest.main()
