from __future__ import annotations

import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path


V2_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(V2_ROOT / "scripts"))

from build_external_evidence_packets import (  # noqa: E402
    build_packets,
    validate_external_evidence_packets,
)


class ExternalEvidencePacketsTest(unittest.TestCase):
    def test_all_external_queue_rows_are_packetized_without_db_mutation(self) -> None:
        database_path = V2_ROOT / "data/real_runs/annotation_v2.db"
        manifest_path = V2_ROOT / "data/real_runs/external_public_candidate_manifest.json"
        with sqlite3.connect(database_path) as connection:
            before = {
                table: connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
                for table in (
                    "external_source_resolution_queue",
                    "external_passage_resolution_queue",
                    "annotation_evidences",
                )
            }

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            packet_path = root / "external_evidence_packets.v1.jsonl"
            report_path = root / "external_evidence_packets_report.json"
            report = build_packets(
                database_path=database_path,
                manifest_path=manifest_path,
                packet_path=packet_path,
                report_path=report_path,
            )
            self.assertTrue(report["valid"])
            self.assertEqual(report["counts"]["source_queue_count"], 100)
            self.assertEqual(report["counts"]["passage_queue_count"], 121)
            self.assertEqual(report["counts"]["passage_packet_count"], 121)
            self.assertEqual(report["counts"]["manifest_entry_count"], 121)
            self.assertEqual(report["source_assessment_counts"]["public_search_manifest_covered"], 100)
            self.assertEqual(report["evidence_assessment_counts"]["frozen_public_candidate_quote_match"], 15)
            validation = validate_external_evidence_packets(
                database_path=database_path,
                report_path=report_path,
                packet_path=packet_path,
            )
            self.assertTrue(validation["valid"], validation["errors"])

        with sqlite3.connect(database_path) as connection:
            after = {
                table: connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
                for table in before
            }
        self.assertEqual(before, after)


if __name__ == "__main__":
    unittest.main()
