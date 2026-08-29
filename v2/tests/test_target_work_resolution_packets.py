from __future__ import annotations

import json
import sqlite3
import sys
import tempfile
import unittest
from contextlib import closing
from pathlib import Path


V2_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(V2_ROOT / "src"))
sys.path.insert(0, str(V2_ROOT / "scripts"))

from build_target_work_resolution_packets import (  # noqa: E402
    build_packets,
    validate_target_work_resolution_packets,
)
from erwang_v2.database import ingest_case, ingest_passages, open_database  # noqa: E402
from erwang_v2.validate_annotation_case import load_passages_jsonl  # noqa: E402


class TargetWorkResolutionPacketsTest(unittest.TestCase):
    def test_fixture_packets_are_queue_bound_and_read_only(self) -> None:
        passages = list(load_passages_jsonl(V2_ROOT / "data/fixtures/passages.jsonl").values())
        case = json.loads(
            (V2_ROOT / "data/fixtures/cases/造舟于河.annotation.json").read_text(
                encoding="utf-8"
            )
        )
        case["case_id"] = "fixture_target_packet_0001"
        case["target_work"] = ""
        case["target_scope"] = {
            "status": "machine_inferred",
            "candidate_works": ["左传"],
            "evidence_indexes": [0],
        }

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            database_path = root / "annotation_v2.db"
            packet_path = root / "target_work_resolution_packets.v1.jsonl"
            report_path = root / "target_work_resolution_packets_report.json"
            with open_database(database_path) as connection:
                ingest_passages(connection, passages)
                ingest_case(connection, case, origin="fixture_target_resolution")
                connection.execute(
                    """
                    INSERT INTO target_work_resolution_queue(
                        queue_item_id, case_id, raw_label, normalized_label,
                        machine_candidate_work_key, machine_inference_status,
                        queue_status, evidence_indexes_json, context_json,
                        priority, created_at, updated_at
                    ) VALUES (?, ?, '左传', '左传', NULL, 'machine_inferred',
                              'pending', '[0]', '{}', 55,
                              '2026-01-01T00:00:00+00:00',
                              '2026-01-01T00:00:00+00:00')
                    """,
                    ("target-work:fixture_target_packet_0001:fixture", case["case_id"]),
                )
                connection.commit()
                before = tuple(
                    tuple(row)
                    for row in connection.execute(
                        """
                        SELECT case_id, target_work, target_passage_id,
                               machine_status, human_status
                        FROM annotation_cases
                        """
                    ).fetchall()
                )

            report = build_packets(
                database_path=database_path,
                packet_path=packet_path,
                report_path=report_path,
            )
            self.assertTrue(report["valid"])
            self.assertEqual(report["counts"]["queue_count"], 1)
            self.assertEqual(report["counts"]["packet_count"], 1)
            self.assertEqual(report["counts"]["evidence_rows_embedded"], 1)

            validation = validate_target_work_resolution_packets(
                database_path=database_path,
                packet_path=packet_path,
                report_path=report_path,
            )
            self.assertTrue(validation["valid"], validation["errors"])
            packet = json.loads(packet_path.read_text(encoding="utf-8").splitlines()[0])
            self.assertEqual(
                packet["packet_id"],
                "target-work-resolution-packet:target-work:fixture_target_packet_0001:fixture",
            )
            self.assertFalse(packet["machine_only_boundary"]["database_write_performed"])
            self.assertFalse(packet["decision_contract"]["promotes_to_gold"])
            self.assertEqual(packet["evidence_context"]["count"], 1)
            self.assertEqual(packet["case_snapshot"]["target_work"], "")

            with closing(sqlite3.connect(database_path)) as connection:
                after = tuple(
                    connection.execute(
                        """
                        SELECT case_id, target_work, target_passage_id,
                               machine_status, human_status
                        FROM annotation_cases
                        """
                    ).fetchall()
                )
                self.assertEqual(before, after)
                self.assertEqual(connection.execute("SELECT COUNT(*) FROM resolution_events").fetchone()[0], 0)

    def test_proposal_index_is_full_queue_bound_and_machine_only(self) -> None:
        proposal_path = V2_ROOT / "data/real_runs/target_work_resolution_proposals.v1.jsonl"
        report_path = V2_ROOT / "data/real_runs/target_work_resolution_proposals_report.validation.json"
        self.assertTrue(proposal_path.is_file())
        self.assertTrue(report_path.is_file())
        report = json.loads(report_path.read_text(encoding="utf-8"))
        self.assertTrue(report["valid"], report["errors"])
        self.assertEqual(report["counts"]["expected_queue_count"], 7962)
        self.assertEqual(report["counts"]["proposal_count"], 7962)
        first = json.loads(proposal_path.read_text(encoding="utf-8").splitlines()[0])
        self.assertTrue(first["machine_only_boundary"]["database_write_performed"] is False)
        self.assertTrue(first["machine_only_boundary"]["candidate_identity_is_not_resolved"])


if __name__ == "__main__":
    unittest.main()
