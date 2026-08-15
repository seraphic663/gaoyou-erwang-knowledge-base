from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path


V2_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(V2_ROOT / "src"))
sys.path.insert(0, str(V2_ROOT / "scripts"))

from erwang_v2.database import ingest_case, ingest_passages, open_database  # noqa: E402
from erwang_v2.validate_annotation_case import load_passages_jsonl  # noqa: E402
from v2_review_bridge import find_task, read_tasks, submit_payload  # noqa: E402


class V2ReviewBridgeTest(unittest.TestCase):
    @staticmethod
    def _target_manifest(directory: Path, task: dict[str, str]) -> Path:
        stream_path = directory / "target_work_resolution.review_task.v1.jsonl"
        stream_path.write_text(json.dumps(task, ensure_ascii=False) + "\n", encoding="utf-8")
        manifest_path = directory / "review_task_manifest.review.v1.json"
        manifest_path.write_text(
            json.dumps(
                {
                    "streams": [
                        "case_review",
                        "target_work_resolution",
                        "external_source_resolution",
                        "external_passage_resolution",
                    ],
                    "batch_size": 100,
                    "outputs": {
                        "target_work_resolution": {
                            "path": stream_path.name,
                            "batches": [
                                {
                                    "batch_id": "target_work_resolution.review_task.v1.batch-0001",
                                    "batch_number": 1,
                                    "task_count": 1,
                                }
                            ],
                        }
                    },
                    "manifest_sha256": "fixture",
                    "policy": {"task_artifacts_are_not_review_events": True},
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        return manifest_path

    def test_reads_persisted_tasks_by_stream_and_batch(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            manifest_path = root / "review_task_manifest.review.v1.json"
            stream_path = root / "case_review.review_task.v1.jsonl"
            tasks = [
                {
                    "task_id": "case-review:fixture-1",
                    "task_type": "case_review",
                    "batch_number": 1,
                    "batch_id": "case_review.review_task.v1.batch-0001",
                },
                {
                    "task_id": "case-review:fixture-2",
                    "task_type": "case_review",
                    "batch_number": 2,
                    "batch_id": "case_review.review_task.v1.batch-0002",
                },
            ]
            stream_path.write_text(
                "\n".join(json.dumps(task, ensure_ascii=False) for task in tasks) + "\n",
                encoding="utf-8",
            )
            manifest_path.write_text(
                json.dumps(
                    {
                        "streams": [
                            "case_review",
                            "target_work_resolution",
                            "external_source_resolution",
                            "external_passage_resolution",
                        ],
                        "batch_size": 1,
                        "outputs": {
                            "case_review": {
                                "path": stream_path.name,
                                "batches": [
                                    {"batch_id": task["batch_id"], "batch_number": task["batch_number"], "task_count": 1}
                                    for task in tasks
                                ],
                            }
                        },
                        "manifest_sha256": "fixture",
                        "policy": {"task_artifacts_are_not_review_events": True},
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            result = read_tasks(manifest_path=manifest_path, stream="case_review", batch_number=2)
            self.assertEqual(result["task_count"], 1)
            self.assertEqual(result["tasks"][0]["task_id"], "case-review:fixture-2")
            selected = find_task(manifest_path=manifest_path, task_id="case-review:fixture-1")
            self.assertEqual(selected["stream"], "case_review")

    def test_target_submission_keeps_case_machine_draft_and_is_idempotent(self) -> None:
        passages = list(load_passages_jsonl(V2_ROOT / "data/fixtures/passages.jsonl").values())
        case = json.loads(
            (V2_ROOT / "data/fixtures/cases/造舟于河.annotation.json").read_text(
                encoding="utf-8"
            )
        )
        case["case_id"] = "fixture_bridge_target_0001"
        case["target_work"] = ""
        case["target_scope"] = {"status": "unresolved", "target_works": []}

        with tempfile.TemporaryDirectory() as directory:
            database_path = Path(directory) / "annotation_v2.db"
            queue_item_id = "target-work:fixture_bridge_target_0001:fixture"
            payload = {
                "task_type": "target_work_resolution",
                "task_id": queue_item_id,
                "queue_item_id": queue_item_id,
                "reviewer": "reviewer-bridge",
                "operation_id": "bridge-target-op-0001",
                "resolution_status": "resolved",
                "target_work": "左传",
                "target_passage_id": passages[0]["passage_id"],
                "target_scope": {"status": "resolved", "target_works": ["左传"]},
            }
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
                    ) VALUES (?, ?, '', '', NULL, 'unresolved', 'needs_context',
                              '[]', '{}', 90, '2026-01-01T00:00:00+00:00',
                              '2026-01-01T00:00:00+00:00')
                    """,
                    (queue_item_id, case["case_id"]),
                )
                connection.commit()

            manifest_path = self._target_manifest(
                Path(directory),
                {
                    "task_id": queue_item_id,
                    "task_type": "target_work_resolution",
                    "queue_item_id": queue_item_id,
                    "case_id": case["case_id"],
                },
            )
            mismatch = dict(payload, queue_item_id="target-work:wrong")
            with self.assertRaisesRegex(ValueError, "review_task_queue_item_mismatch"):
                submit_payload(database_path, mismatch, manifest_path=manifest_path)

            result = submit_payload(database_path, payload, manifest_path=manifest_path)
            repeated = submit_payload(database_path, payload, manifest_path=manifest_path)
            self.assertTrue(result["ok"])
            self.assertFalse(result["result"]["idempotent"])
            self.assertTrue(repeated["result"]["idempotent"])
            with open_database(database_path) as connection:
                row = connection.execute(
                    "SELECT target_work, target_passage_id, human_status, lifecycle "
                    "FROM annotation_cases WHERE case_id = ?",
                    (case["case_id"],),
                ).fetchone()
                self.assertEqual(row["target_work"], "左传")
                self.assertEqual(row["target_passage_id"], passages[0]["passage_id"])
                self.assertEqual(row["human_status"], "pending")
                self.assertEqual(row["lifecycle"], "machine_draft")
                self.assertEqual(connection.execute("SELECT COUNT(*) FROM review_events").fetchone()[0], 1)

    def test_case_submission_rejects_missing_reviewer_before_database_write(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(ValueError, "reviewer_required_for_decision"):
                submit_payload(
                    Path(directory) / "missing.db",
                    {
                        "task_type": "case_review",
                        "task_id": "case-review:fixture",
                        "case_id": "fixture",
                        "review_status": "uncertain",
                        "operation_id": "bridge-case-op-0001",
                        "review": {},
                    },
                    manifest_path=None,
                )


if __name__ == "__main__":
    unittest.main()
