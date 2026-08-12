from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path


V2_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(V2_ROOT / "src"))
sys.path.insert(0, str(V2_ROOT / "scripts"))

from build_review_task_batches import build_review_task_artifacts  # noqa: E402
from erwang_v2.database import ingest_case, ingest_passages, open_database  # noqa: E402
from erwang_v2.validate_annotation_case import load_passages_jsonl  # noqa: E402


class ReviewTaskBatchTest(unittest.TestCase):
    def test_build_is_read_only_batched_and_covers_pending_work(self) -> None:
        passages = list(load_passages_jsonl(V2_ROOT / "data/fixtures/passages.jsonl").values())
        case_paths = [
            V2_ROOT / "data/fixtures/cases/造舟于河.annotation.json",
            V2_ROOT / "data/fixtures/cases/平原之隰.annotation.json",
        ]
        cases = []
        for index, path in enumerate(case_paths, start=1):
            case = json.loads(path.read_text(encoding="utf-8"))
            case["case_id"] = f"fixture_review_task_{index:04d}"
            cases.append(case)

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            database_path = root / "annotation_v2.db"
            output_dir = root / "review_batches"
            with open_database(database_path) as connection:
                ingest_passages(connection, passages)
                for case in cases:
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
                        (f"target-work:{case['case_id']}:fixture", case["case_id"]),
                    )
                connection.commit()
                before = tuple(
                    connection.execute(
                        "SELECT case_id, lifecycle, machine_status, human_status, target_work, target_passage_id FROM annotation_cases ORDER BY case_id"
                    ).fetchall()
                )

            report = build_review_task_artifacts(
                database_path=database_path,
                output_dir=output_dir,
                batch_size=1,
            )

            self.assertEqual(report["counts"]["case_review"], 2)
            self.assertEqual(report["counts"]["target_work_resolution"], 2)
            self.assertEqual(report["counts"]["external_source_resolution"], 0)
            self.assertEqual(report["counts"]["external_passage_resolution"], 0)
            self.assertEqual(report["validation"]["valid"], True)
            self.assertEqual(report["policy"]["database_write_performed"], False)

            manifest = json.loads(
                (output_dir / "review_task_manifest.review.v1.json").read_text(encoding="utf-8")
            )
            self.assertEqual(manifest["batch_size"], 1)
            self.assertEqual(set(manifest["streams"]), {
                "case_review",
                "target_work_resolution",
                "external_source_resolution",
                "external_passage_resolution",
            })
            self.assertTrue(manifest["coverage"]["all_pending_tasks_linked"])

            for stream in manifest["streams"]:
                path = output_dir / manifest["outputs"][stream]["path"]
                rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
                self.assertLessEqual(max((int(row["batch_size"]) for row in rows), default=0), 1)
                self.assertTrue(all(row["task_id"] and row["batch_id"] for row in rows))

            with open_database(database_path) as connection:
                after = tuple(
                    connection.execute(
                        "SELECT case_id, lifecycle, machine_status, human_status, target_work, target_passage_id FROM annotation_cases ORDER BY case_id"
                    ).fetchall()
                )
                self.assertEqual(before, after)
                self.assertEqual(connection.execute("SELECT COUNT(*) FROM review_events").fetchone()[0], 0)


if __name__ == "__main__":
    unittest.main()
