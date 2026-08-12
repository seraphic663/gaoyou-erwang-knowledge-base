from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path


V2_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(V2_ROOT / "src"))
sys.path.insert(0, str(V2_ROOT / "scripts"))

from build_work_registry import RegistryBuilder  # noqa: E402
from infer_candidate_target_locations import canonical_work_for_label, extract_book_labels  # noqa: E402
from materialize_all_candidate_batches import materialize_all_batches  # noqa: E402
from materialize_candidate_batch import build_candidate_shell  # noqa: E402
from plan_candidate_materialization import plan_candidates  # noqa: E402
from erwang_v2.database import ingest_candidate_items, ingest_passages, open_database  # noqa: E402
from erwang_v2.passage_builder import build_passages  # noqa: E402


class ArchitectureLayerTest(unittest.TestCase):
    def test_target_location_extraction_is_conservative(self) -> None:
        labels = extract_book_labels("见《经义述闻·左传》；又见《礼记》与《读书杂志》。")

        self.assertEqual(
            [(row["normalized_label"], row["work_identity_status"]) for row in labels],
            [("经义述闻·左传", "canonical"), ("礼记", "candidate"), ("读书杂志", "canonical")],
        )
        self.assertEqual(
            canonical_work_for_label("经义述闻·左传")[0],
            "jingyi_shuwen",
        )
        self.assertEqual(canonical_work_for_label("经义述闻左传")[0], None)

    def test_work_registry_keeps_ambiguous_label_as_candidate(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            database_path = Path(directory) / "annotation_v2.db"
            with open_database(database_path) as connection:
                builder = RegistryBuilder(connection)
                builder.seed_known_identities()
                resolved = builder.resolve_label("《读书杂志》")
                unresolved = builder.resolve_label("礼记·檀弓")

                self.assertEqual(resolved[:2], ("dushu_zazhi", "canonical"))
                self.assertIsNone(unresolved[0])
                self.assertEqual(unresolved[1], "candidate")
                self.assertEqual(
                    connection.execute("SELECT COUNT(*) FROM work_registry").fetchone()[0],
                    4,
                )

    def test_candidate_materialization_plan_is_read_only_and_batched(self) -> None:
        source = V2_ROOT / "data/fixtures/sources/jingyi_shuwen.sample.md"
        passages = build_passages(source, "jingyi_shuwen")
        with tempfile.TemporaryDirectory() as directory:
            database_path = Path(directory) / "annotation_v2.db"
            with open_database(database_path) as connection:
                source_document_id = ingest_passages(connection, passages)
                ingest_candidate_items(
                    connection,
                    [
                        {
                            "candidate_id": "candidate:test:1",
                            "passage_id": passages[0]["passage_id"],
                            "work_key": "jingyi_shuwen",
                            "source_work": "经义述闻",
                            "candidate_text": "户瓜反",
                            "candidate_status": "approved",
                            "rule_hits": ["inline_note"],
                            "risk_flags": [],
                            "provenance": {"fixture": True},
                        }
                    ],
                    source_document_id=source_document_id,
                    origin="original_markdown_machine_extraction",
                )
                connection.commit()

            plans, report = plan_candidates(database_path, batch_size=1)

            self.assertEqual(len(plans), 1)
            self.assertEqual(report["counts"]["ready_candidate_shell"], 1)
            self.assertEqual(plans[0]["planned_case_id"], "candidate-shell:candidate:test:1")
            self.assertEqual(plans[0]["case_shell_policy"]["human_status"], "pending")
            with open_database(database_path) as connection:
                self.assertEqual(
                    connection.execute("SELECT COUNT(*) FROM annotation_cases").fetchone()[0],
                    0,
                )

    def test_candidate_shell_preserves_source_boundary_without_target_resolution(self) -> None:
        source = V2_ROOT / "data/fixtures/sources/jingyi_shuwen.sample.md"
        passages = build_passages(source, "jingyi_shuwen")
        passage = dict(passages[0])
        passage.update(
            {
                "source_file": str(source),
                "source_file_sha256": "fixture-sha256",
                "canonical_status": "canonical_active",
            }
        )
        plan = {
            "planned_case_id": "candidate-shell:fixture:1",
            "candidate_id": "fixture:1",
            "batch_id": "fixture-batch-0001",
            "source_work_raw": "经义述闻",
            "source_document_id": "jingyi_shuwen:fixture",
            "source_passage_id": passage["passage_id"],
            "candidate_text": passage["plain_text"],
            "candidate_status": "approved",
            "rule_hits": ["inline_note"],
            "risk_flags": ["fixture"],
            "risk_class": "risk_bearing",
            "source": {
                "source_file": str(source),
                "source_file_sha256": "fixture-sha256",
                "canonical_status": "canonical_active",
            },
        }
        case = build_candidate_shell(plan, passage)
        self.assertEqual(case["target_work"], "")
        self.assertEqual(case["target_scope"]["status"], "unresolved")
        self.assertEqual(case["machine_result"]["status"], "draft")
        self.assertFalse(case["_migration"]["provenance"]["ai_generation_performed"])
        self.assertEqual(case["evidences"][0]["source_resolution"], "canonical_source_passage")
        self.assertEqual(case["evidences"][0]["semantic_role"], "context_only")

    def test_all_candidate_batches_materialize_idempotently_and_preserve_review_boundary(self) -> None:
        source = V2_ROOT / "data/fixtures/sources/jingyi_shuwen.sample.md"
        passages = build_passages(source, "jingyi_shuwen")
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            database_path = root / "annotation_v2.db"
            plan_path = root / "candidate_plan.jsonl"
            with open_database(database_path) as connection:
                source_document_id = ingest_passages(connection, passages)
                ingest_candidate_items(
                    connection,
                    [
                        {
                            "candidate_id": f"candidate:test:{index}",
                            "passage_id": passages[0]["passage_id"],
                            "work_key": "jingyi_shuwen",
                            "source_work": "经义述闻",
                            "candidate_text": "户瓜反",
                            "candidate_status": "approved",
                            "rule_hits": ["inline_note"],
                            "risk_flags": [],
                            "provenance": {"fixture": True, "index": index},
                        }
                        for index in range(3)
                    ],
                    source_document_id=source_document_id,
                    origin="original_markdown_machine_extraction",
                )
                connection.commit()

            plans, _ = plan_candidates(database_path, batch_size=2)
            plan_path.write_text(
                "\n".join(json.dumps(plan, ensure_ascii=False) for plan in plans) + "\n",
                encoding="utf-8",
            )
            output_dir = root / "batches"
            first = materialize_all_batches(
                database_path=database_path,
                plan_path=plan_path,
                output_dir=output_dir,
            )
            second = materialize_all_batches(
                database_path=database_path,
                plan_path=plan_path,
                output_dir=output_dir,
            )

            self.assertEqual(first["counts"]["planned_ready_candidate_shell"], 3)
            self.assertEqual(first["counts"]["materialized_now"], 3)
            self.assertEqual(first["counts"]["candidate_output_links"], 3)
            self.assertTrue((output_dir / "candidate_shell_all_batches_report.json").exists())
            self.assertEqual(second["counts"]["materialized_now"], 0)
            self.assertEqual(second["counts"]["skipped_existing"], 3)
            with open_database(database_path) as connection:
                self.assertEqual(
                    connection.execute("SELECT COUNT(*) FROM annotation_cases").fetchone()[0],
                    3,
                )
                self.assertEqual(
                    connection.execute(
                        "SELECT COUNT(*) FROM annotation_cases WHERE machine_status='draft' AND human_status='pending' AND lifecycle='machine_draft'"
                    ).fetchone()[0],
                    3,
                )
                self.assertEqual(
                    connection.execute(
                        "SELECT COUNT(*) FROM candidate_items WHERE output_case_id IS NOT NULL"
                    ).fetchone()[0],
                    3,
                )


if __name__ == "__main__":
    unittest.main()
