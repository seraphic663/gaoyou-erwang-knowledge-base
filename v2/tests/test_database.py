from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path


V2_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(V2_ROOT / "src"))

from erwang_v2.database import (
    apply_review_event,
    database_counts,
    ingest_case,
    ingest_passages,
    open_database,
)
from erwang_v2.validate_annotation_case import load_passages_jsonl


class UnifiedDatabaseTest(unittest.TestCase):
    def test_machine_case_enters_shared_db_without_becoming_gold(self) -> None:
        passages = list(load_passages_jsonl(V2_ROOT / "data/fixtures/passages.jsonl").values())
        case = json.loads(
            (V2_ROOT / "data/fixtures/cases/造舟于河.annotation.json").read_text(
                encoding="utf-8"
            )
        )

        with tempfile.TemporaryDirectory() as directory:
            database_path = Path(directory) / "annotation_v2.db"
            with open_database(database_path) as connection:
                ingest_passages(connection, passages)
                stored = ingest_case(connection, case, origin="candidate_ai")
                connection.commit()

                self.assertEqual(stored["origin"], "candidate_ai")
                self.assertEqual(stored["lifecycle"], "machine_draft")
                self.assertEqual(stored["machine_status"], "pending")
                self.assertEqual(stored["human_status"], "pending")
                self.assertEqual(database_counts(connection)["annotation_cases"], 1)
                self.assertEqual(connection.execute("SELECT COUNT(*) FROM v_gold_cases").fetchone()[0], 0)

    def test_external_evidence_is_registered_as_pending(self) -> None:
        passages = list(load_passages_jsonl(V2_ROOT / "data/fixtures/passages.jsonl").values())
        case = json.loads(
            (V2_ROOT / "data/fixtures/cases/造舟于河.annotation.json").read_text(
                encoding="utf-8"
            )
        )
        case["case_id"] = "fixture_external_0001"
        case["machine_result"] = {"status": "draft"}
        evidence = case["evidences"][0]
        evidence.update(
            {
                "source_work": "左传",
                "passage_id": None,
                "quote_check": "unchecked",
                "source_resolution": "secondary_citation_match",
                "cited_work_match_status": "external_source_pending",
                "secondary_citation_passage_id": "jingyi_shuwen_0001",
            }
        )

        with tempfile.TemporaryDirectory() as directory:
            database_path = Path(directory) / "annotation_v2.db"
            with open_database(database_path) as connection:
                ingest_passages(connection, passages)
                ingest_case(connection, case, origin="legacy_ai_json")
                connection.commit()

                self.assertEqual(
                    connection.execute("SELECT COUNT(*) FROM external_source_registry").fetchone()[0],
                    1,
                )
                self.assertEqual(
                    connection.execute(
                        "SELECT COUNT(*) FROM annotation_evidence_external_sources"
                    ).fetchone()[0],
                    1,
                )
                stored_json = connection.execute(
                    "SELECT case_json FROM annotation_cases WHERE case_id = ?",
                    ("fixture_external_0001",),
                ).fetchone()[0]
                self.assertIn("external_source_id", stored_json)

    def test_review_event_is_transactional_and_idempotent(self) -> None:
        passages = list(load_passages_jsonl(V2_ROOT / "data/fixtures/passages.jsonl").values())
        case = json.loads(
            (V2_ROOT / "data/fixtures/cases/造舟于河.annotation.json").read_text(
                encoding="utf-8"
            )
        )
        case["case_id"] = "fixture_review_0001"
        case["target_passage_id"] = passages[0]["passage_id"]
        case["target_scope"] = {"status": "resolved", "target_works": [case["target_work"]]}
        case["evidences"][0].update(
            {
                "quote_check": "passed",
                "source_resolution": "canonical_source_passage",
            }
        )

        review = {
            "field_decisions": {
                "source_passage": "approved",
                "target_work": "approved",
                "target_passage": "approved",
                "evidence": "approved",
                "process": "approved",
                "conclusion": "approved",
            },
            "evidence_decisions": [{"evidence_index": 0, "status": "approved"}],
        }
        with tempfile.TemporaryDirectory() as directory:
            database_path = Path(directory) / "annotation_v2.db"
            with open_database(database_path) as connection:
                ingest_passages(connection, passages)
                ingest_case(connection, case, origin="fixture")
                connection.commit()
                result = apply_review_event(
                    connection,
                    case["case_id"],
                    reviewer="reviewer-1",
                    review_status="approved",
                    operation_id="review-op-0001",
                    review_note="fixture approval",
                    review=review,
                )
                repeated = apply_review_event(
                    connection,
                    case["case_id"],
                    reviewer="reviewer-1",
                    review_status="approved",
                    operation_id="review-op-0001",
                    review_note="fixture approval",
                    review=review,
                )
                self.assertFalse(result["idempotent"])
                self.assertTrue(repeated["idempotent"])
                self.assertEqual(connection.execute("SELECT COUNT(*) FROM review_events").fetchone()[0], 1)
                self.assertEqual(connection.execute("SELECT COUNT(*) FROM v_gold_cases").fetchone()[0], 1)

    def test_review_approval_cannot_promote_unresolved_candidate_shell(self) -> None:
        passages = list(load_passages_jsonl(V2_ROOT / "data/fixtures/passages.jsonl").values())
        case = json.loads(
            (V2_ROOT / "data/fixtures/cases/造舟于河.annotation.json").read_text(
                encoding="utf-8"
            )
        )
        case["case_id"] = "fixture_review_blocked_0001"
        with tempfile.TemporaryDirectory() as directory:
            database_path = Path(directory) / "annotation_v2.db"
            with open_database(database_path) as connection:
                ingest_passages(connection, passages)
                ingest_case(connection, case, origin="candidate_shell")
                connection.commit()
                with self.assertRaisesRegex(ValueError, "target_passage_not_bound"):
                    apply_review_event(
                        connection,
                        case["case_id"],
                        reviewer="reviewer-1",
                        review_status="approved",
                        operation_id="review-op-blocked-0001",
                        review={
                            "field_decisions": {
                                field: "approved"
                                for field in (
                                    "source_passage", "target_work", "target_passage",
                                    "evidence", "process", "conclusion",
                                )
                            },
                            "evidence_decisions": [],
                        },
                    )
                self.assertEqual(connection.execute("SELECT COUNT(*) FROM review_events").fetchone()[0], 0)


if __name__ == "__main__":
    unittest.main()
