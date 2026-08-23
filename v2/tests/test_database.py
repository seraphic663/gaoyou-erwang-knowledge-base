from __future__ import annotations

import json
import hashlib
import sys
import tempfile
import unittest
from pathlib import Path


V2_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(V2_ROOT / "src"))

from erwang_v2.database import (
    apply_case_review_submission,
    apply_external_passage_resolution,
    apply_external_source_resolution,
    apply_review_event,
    apply_target_work_resolution,
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

    def test_target_work_resolution_updates_scope_without_promoting_case(self) -> None:
        passages = list(load_passages_jsonl(V2_ROOT / "data/fixtures/passages.jsonl").values())
        case = json.loads(
            (V2_ROOT / "data/fixtures/cases/造舟于河.annotation.json").read_text(
                encoding="utf-8"
            )
        )
        case["case_id"] = "fixture_target_resolution_0001"
        case["target_work"] = ""
        case["target_scope"] = {"status": "unresolved", "target_works": []}

        with tempfile.TemporaryDirectory() as directory:
            database_path = Path(directory) / "annotation_v2.db"
            with open_database(database_path) as connection:
                ingest_passages(connection, passages)
                ingest_case(connection, case, origin="fixture")
                connection.execute(
                    """
                    INSERT INTO target_work_resolution_queue(
                        queue_item_id, case_id, raw_label, normalized_label,
                        machine_candidate_work_key, machine_inference_status,
                        queue_status, evidence_indexes_json, context_json,
                        priority, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, NULL, 'unresolved', 'needs_context',
                              '[]', '{}', 90, '2026-01-01T00:00:00+00:00',
                              '2026-01-01T00:00:00+00:00')
                    """,
                    ("target-work:fixture_target_resolution_0001:fixture", case["case_id"], "", ""),
                )
                connection.commit()

                result = apply_target_work_resolution(
                    connection,
                    "target-work:fixture_target_resolution_0001:fixture",
                    reviewer="reviewer-1",
                    operation_id="target-op-0001",
                    target_work="左传",
                    target_passage_id=passages[0]["passage_id"],
                    target_scope={"status": "resolved", "target_works": ["左传"]},
                    resolution_status="resolved",
                    review_note="fixture target resolution",
                )
                repeated = apply_target_work_resolution(
                    connection,
                    "target-work:fixture_target_resolution_0001:fixture",
                    reviewer="reviewer-1",
                    operation_id="target-op-0001",
                    target_work="左传",
                    target_passage_id=passages[0]["passage_id"],
                    target_scope={"status": "resolved", "target_works": ["左传"]},
                    resolution_status="resolved",
                    review_note="fixture target resolution",
                )
                row = connection.execute(
                    "SELECT target_work, target_passage_id, human_status, lifecycle FROM annotation_cases WHERE case_id = ?",
                    (case["case_id"],),
                ).fetchone()
                queue = connection.execute(
                    "SELECT queue_status FROM target_work_resolution_queue WHERE queue_item_id = ?",
                    ("target-work:fixture_target_resolution_0001:fixture",),
                ).fetchone()
                event = connection.execute(
                    "SELECT event_kind, review_status FROM review_events WHERE operation_id = ?",
                    ("target-op-0001",),
                ).fetchone()

                self.assertFalse(result["idempotent"])
                self.assertTrue(repeated["idempotent"])
                self.assertEqual(row["target_work"], "左传")
                self.assertEqual(row["target_passage_id"], passages[0]["passage_id"])
                self.assertEqual(row["human_status"], "pending")
                self.assertEqual(row["lifecycle"], "machine_draft")
                self.assertEqual(queue["queue_status"], "resolved")
                self.assertEqual(tuple(event), ("target_work_resolution", "pending"))

    def test_case_review_submission_applies_explicit_patch_before_approval_gate(self) -> None:
        passages = list(load_passages_jsonl(V2_ROOT / "data/fixtures/passages.jsonl").values())
        case = json.loads(
            (V2_ROOT / "data/fixtures/cases/造舟于河.annotation.json").read_text(
                encoding="utf-8"
            )
        )
        case["case_id"] = "fixture_case_submission_0001"
        case["target_passage_id"] = None
        case["target_scope"] = {"status": "unresolved", "target_works": []}

        review = {
            "field_decisions": {
                field: "approved"
                for field in (
                    "source_passage", "target_work", "target_passage",
                    "evidence", "process", "conclusion",
                )
            },
            "evidence_decisions": [{
                "evidence_index": 0,
                "status": "approved",
                "passage_id": passages[0]["passage_id"],
                "quote_check": "passed",
                "source_resolution": "canonical_source_passage",
            }],
        }
        patch = {
            "target_work": "左传",
            "target_passage_id": passages[0]["passage_id"],
            "target_scope": {"status": "resolved", "target_works": ["左传"]},
            "problem_discovery": "人工确认问题",
            "research_question": "人工确认问题是什么",
            "evidence_collection": "人工确认取证",
            "reasoning": "人工确认推理",
            "conclusion": "人工确认结论",
        }

        with tempfile.TemporaryDirectory() as directory:
            database_path = Path(directory) / "annotation_v2.db"
            with open_database(database_path) as connection:
                ingest_passages(connection, passages)
                ingest_case(connection, case, origin="fixture")
                connection.commit()
                result = apply_case_review_submission(
                    connection,
                    case["case_id"],
                    reviewer="reviewer-1",
                    review_status="approved",
                    operation_id="case-op-0001",
                    review_note="fixture case approval",
                    case_patch=patch,
                    review=review,
                )
                repeated = apply_case_review_submission(
                    connection,
                    case["case_id"],
                    reviewer="reviewer-1",
                    review_status="approved",
                    operation_id="case-op-0001",
                    review_note="fixture case approval",
                    case_patch=patch,
                    review=review,
                )
                row = connection.execute(
                    "SELECT target_work, target_passage_id, human_status, lifecycle, process_text FROM annotation_cases WHERE case_id = ?",
                    (case["case_id"],),
                ).fetchone()
                self.assertFalse(result["idempotent"])
                self.assertTrue(repeated["idempotent"])
                self.assertEqual(row["target_work"], "左传")
                self.assertEqual(row["target_passage_id"], passages[0]["passage_id"])
                self.assertEqual(row["human_status"], "approved")
                self.assertEqual(row["lifecycle"], "gold")
                self.assertIn("人工确认结论", row["process_text"])

    def test_external_resolution_is_separate_and_canonical_bound(self) -> None:
        passages = list(load_passages_jsonl(V2_ROOT / "data/fixtures/passages.jsonl").values())
        case = json.loads(
            (V2_ROOT / "data/fixtures/cases/造舟于河.annotation.json").read_text(
                encoding="utf-8"
            )
        )
        case["case_id"] = "fixture_external_resolution_0001"
        case["evidences"][0].update(
            {
                "source_work": "左传",
                "passage_id": None,
                "quote_check": "unchecked",
                "source_resolution": "external_source_pending",
                "cited_work_match_status": "external_source_pending",
            }
        )

        with tempfile.TemporaryDirectory() as directory:
            database_path = Path(directory) / "annotation_v2.db"
            external_file = Path(directory) / "external.txt"
            external_file.write_text("造、次一声之转", encoding="utf-8")
            external_hash = hashlib.sha256(external_file.read_bytes()).hexdigest()
            with open_database(database_path) as connection:
                ingest_passages(connection, passages)
                ingest_case(connection, case, origin="legacy_ai_json")
                external_source_id = connection.execute(
                    "SELECT external_source_id FROM annotation_evidence_external_sources WHERE case_id = ?",
                    (case["case_id"],),
                ).fetchone()[0]
                connection.execute(
                    """
                    INSERT INTO external_source_resolution_queue(
                        queue_item_id, external_source_id, cited_work, registry_status,
                        queue_status, edition_status, evidence_count,
                        pending_evidence_count, candidate_evidence_count, context_json,
                        created_at, updated_at
                    ) SELECT ?, external_source_id, cited_work, status, 'pending', 'missing',
                             1, 1, 0, '{}', '2026-01-01T00:00:00+00:00',
                             '2026-01-01T00:00:00+00:00'
                    FROM external_source_registry WHERE external_source_id = ?
                    """,
                    (f"external-source:{external_source_id}", external_source_id),
                )
                connection.execute(
                    """
                    INSERT INTO external_passage_resolution_queue(
                        queue_item_id, external_source_id, case_id, evidence_index,
                        cited_work, quote, source_resolution, quote_check,
                        queue_status, edition_status, passage_status,
                        candidate_refs_json, context_json, created_at, updated_at
                    ) VALUES (?, ?, ?, 0, '左传', '造、次一声之转',
                              'external_source_pending', 'unchecked', 'pending',
                              'missing', 'missing', '[]', '{}',
                              '2026-01-01T00:00:00+00:00', '2026-01-01T00:00:00+00:00')
                    """,
                    (
                        f"external-passage:{case['case_id']}:0",
                        external_source_id,
                        case["case_id"],
                    ),
                )
                connection.commit()

                with self.assertRaisesRegex(ValueError, "verified_external_source_edition_required"):
                    apply_external_source_resolution(
                        connection,
                        f"external-source:{external_source_id}",
                        reviewer="reviewer-1",
                        operation_id="external-source-op-0001",
                        resolution_status="verified",
                        source_file=str(external_file),
                        source_file_sha256=external_hash,
                    )

                apply_external_source_resolution(
                    connection,
                    f"external-source:{external_source_id}",
                    reviewer="reviewer-1",
                    operation_id="external-source-op-0001",
                    resolution_status="verified",
                    source_file=str(external_file),
                    edition="fixture edition",
                )
                repeated_source = apply_external_source_resolution(
                    connection,
                    f"external-source:{external_source_id}",
                    reviewer="reviewer-1",
                    operation_id="external-source-op-0001",
                    resolution_status="verified",
                    source_file=str(external_file),
                    edition="fixture edition",
                )
                self.assertTrue(repeated_source["idempotent"])
                self.assertEqual(
                    connection.execute(
                        "SELECT source_file_sha256 FROM external_source_registry WHERE external_source_id = ?",
                        (external_source_id,),
                    ).fetchone()["source_file_sha256"],
                    external_hash,
                )

                external_passage = {
                    "passage_id": "external_zuozhuan_0001",
                    "work_key": "zuozhuan",
                    "document_title": "左传",
                    "section_title": "fixture",
                    "entry_title": "造舟于河",
                    "entry_kind": "external_canonical_passage",
                    "local_ordinal": 1,
                    "md_line_start": 1,
                    "md_line_end": 1,
                    "raw_text": "造、次一声之转",
                    "plain_text": "造、次一声之转",
                    "normalized_text": "造、次一声之转",
                    "source_file": str(external_file),
                    "source_file_sha256": external_hash,
                }
                ingest_passages(
                    connection,
                    [external_passage],
                    source_kind="original_markdown",
                    metadata={"canonical_status": "canonical_active"},
                )
                with self.assertRaisesRegex(ValueError, "verified_external_passage_source_mismatch"):
                    apply_external_passage_resolution(
                        connection,
                        f"external-passage:{case['case_id']}:0",
                        reviewer="reviewer-1",
                        operation_id="external-passage-op-mismatch",
                        resolution_status="verified",
                        selected_passage_id=passages[0]["passage_id"],
                    )
                verified_passage = apply_external_passage_resolution(
                    connection,
                    f"external-passage:{case['case_id']}:0",
                    reviewer="reviewer-1",
                    operation_id="external-passage-op-0001",
                    resolution_status="verified",
                    selected_passage_id=external_passage["passage_id"],
                )
                repeated_passage = apply_external_passage_resolution(
                    connection,
                    f"external-passage:{case['case_id']}:0",
                    reviewer="reviewer-1",
                    operation_id="external-passage-op-0001",
                    resolution_status="verified",
                    selected_passage_id=external_passage["passage_id"],
                )
                self.assertFalse(verified_passage["idempotent"])
                self.assertTrue(repeated_passage["idempotent"])
                queue = connection.execute(
                    """
                    SELECT ae.quote_check, q.queue_status, q.selected_passage_id
                    FROM annotation_evidences ae
                    JOIN external_passage_resolution_queue q
                      ON q.case_id = ae.case_id AND q.evidence_index = ae.evidence_index
                    WHERE ae.case_id = ? AND ae.evidence_index = 0
                    """,
                    (case["case_id"],),
                ).fetchone()
                self.assertEqual(queue["quote_check"], "unchecked")
                self.assertEqual(queue["queue_status"], "verified")
                self.assertEqual(queue["selected_passage_id"], external_passage["passage_id"])
                self.assertEqual(
                    connection.execute("SELECT COUNT(*) FROM resolution_events").fetchone()[0],
                    2,
                )


if __name__ == "__main__":
    unittest.main()
