from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path


V2_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(V2_ROOT / "src"))
sys.path.insert(0, str(V2_ROOT / "scripts"))

from build_work_queues import build_queues  # noqa: E402
from erwang_v2.database import ingest_case, ingest_passages, open_database  # noqa: E402
from erwang_v2.validate_annotation_case import load_passages_jsonl  # noqa: E402


class WorkQueueTest(unittest.TestCase):
    def test_external_candidate_status_refreshes_on_queue_rebuild(self) -> None:
        passages = list(load_passages_jsonl(V2_ROOT / "data/fixtures/passages.jsonl").values())
        case = json.loads(
            (V2_ROOT / "data/fixtures/cases/造舟于河.annotation.json").read_text(
                encoding="utf-8"
            )
        )
        case["case_id"] = "fixture_queue_refresh_0001"
        case["evidences"][0].update(
            {
                "source_work": "《外部典籍》",
                "passage_id": None,
                "quote_check": "unchecked",
                "source_resolution": "external_source_pending",
                "cited_work_match_status": "external_source_pending",
            }
        )

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            database_path = root / "annotation_v2.db"
            manifest_path = root / "external_public_candidate_manifest.json"
            output_dir = root / "queues"
            report_path = root / "work_queues_report.json"
            with open_database(database_path) as connection:
                ingest_passages(connection, passages)
                ingest_case(connection, case, origin="legacy_ai_json")
                connection.commit()

            base_manifest = {
                "schema_version": "external_public_candidate_manifest.v1",
                "source_policy": {
                    "version_rule": "fixture public page is a candidate only"
                },
                "entries": [
                    {
                        "case_id": case["case_id"],
                        "evidence_index": 0,
                        "status": "search_hit_only",
                        "candidates": [],
                    }
                ],
            }
            manifest_path.write_text(
                json.dumps(base_manifest, ensure_ascii=False), encoding="utf-8"
            )
            build_queues(
                database_path=database_path,
                manifest_path=manifest_path,
                output_dir=output_dir,
                report_path=report_path,
            )

            candidate_manifest = dict(base_manifest)
            candidate_manifest["entries"] = [
                {
                    "case_id": case["case_id"],
                    "evidence_index": 0,
                    "status": "candidate_found",
                    "candidates": [
                        {
                            "page_title": "外部典籍·卷一",
                            "raw_file": "candidate.wikitext",
                            "match_mode": "offline_contiguous",
                        }
                    ],
                }
            ]
            manifest_path.write_text(
                json.dumps(candidate_manifest, ensure_ascii=False), encoding="utf-8"
            )
            build_queues(
                database_path=database_path,
                manifest_path=manifest_path,
                output_dir=output_dir,
                report_path=report_path,
            )

            with open_database(database_path) as connection:
                source = connection.execute(
                    "SELECT queue_status, edition_status FROM external_source_resolution_queue"
                ).fetchone()
                passage = connection.execute(
                    "SELECT queue_status, edition_status, passage_status, "
                    "candidate_refs_json, candidate_passage_ids_json "
                    "FROM external_passage_resolution_queue"
                ).fetchone()
                self.assertEqual(tuple(source), ("candidate_available", "candidate_registered"))
                self.assertEqual(
                    tuple(passage[:3]),
                    ("candidate_available", "candidate_registered", "candidate_match"),
                )
                candidate_refs = json.loads(passage[3])
                self.assertEqual(candidate_refs[0]["page_title"], "外部典籍·卷一")
                connection.execute(
                    "UPDATE external_passage_resolution_queue "
                    "SET candidate_passage_ids_json = ?",
                    (json.dumps(["external-candidate:fixture:keep"]),),
                )
                connection.commit()

            # A later public search can omit a previously found page.  Queue
            # rebuilds must retain the frozen candidate instead of downgrading
            # it to pending/no-match.
            manifest_path.write_text(
                json.dumps(
                    {
                        **base_manifest,
                        "entries": [
                            {
                                "case_id": case["case_id"],
                                "evidence_index": 0,
                                "status": "no_public_match",
                                "candidates": [],
                            }
                        ],
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            build_queues(
                database_path=database_path,
                manifest_path=manifest_path,
                output_dir=output_dir,
                report_path=report_path,
            )

            with open_database(database_path) as connection:
                passage = connection.execute(
                    "SELECT queue_status, passage_status, candidate_refs_json, "
                    "candidate_passage_ids_json "
                    "FROM external_passage_resolution_queue"
                ).fetchone()
                self.assertEqual(
                    tuple(passage[:2]), ("candidate_available", "candidate_match")
                )
                self.assertEqual(
                    json.loads(passage[2])[0]["page_title"], "外部典籍·卷一"
                )
                self.assertEqual(
                    json.loads(passage[3]), ["external-candidate:fixture:keep"]
                )


if __name__ == "__main__":
    unittest.main()
