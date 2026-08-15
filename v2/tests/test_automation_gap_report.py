from __future__ import annotations

import sys
import unittest
from pathlib import Path


V2_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(V2_ROOT / "scripts"))

from build_automation_gap_report import build_report  # noqa: E402


class AutomationGapReportTest(unittest.TestCase):
    def test_report_keeps_machine_materialization_and_human_gap_separate(self) -> None:
        report = build_report()
        self.assertTrue(report["valid"])
        target_queue = report["remaining_automation_gap"]["target_work_queue"]
        self.assertEqual(target_queue["total"], 7962)
        self.assertEqual(target_queue["pending_case_count"], 7577)
        self.assertEqual(target_queue["target_passage_source_kind_counts"], {
            "legacy_derived_quote": 815,
        })
        self.assertEqual(
            report["machine_materialized"]["target_work_packets"]["counts"]["packet_count"],
            7962,
        )
        self.assertFalse(report["boundary"]["human_review_performed"])
        self.assertFalse(report["boundary"]["gold_promotion_performed"])


if __name__ == "__main__":
    unittest.main()
