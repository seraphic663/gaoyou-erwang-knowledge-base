from __future__ import annotations

import sys
import unittest
from pathlib import Path


V2_ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = V2_ROOT.parent
sys.path.insert(0, str(V2_ROOT / "src"))
sys.path.insert(0, str(V2_ROOT / "scripts"))

from erwang_v2.legacy_ai_adapter import adapt_legacy_case, load_legacy_ai_json
from erwang_v2.original_candidate_adapter import fill_missing_process_fields
from erwang_v2.passage_builder import build_passages
from erwang_v2.validate_annotation_case import classify_machine_status
from run_batch_migration import _full_json_context_match


PROCESS_FIELDS = (
    "problem_discovery",
    "research_question",
    "evidence_collection",
    "reasoning",
    "conclusion",
)


class MachineCompletionFieldsTest(unittest.TestCase):
    def test_full_json_context_retains_source_and_character_offsets(self) -> None:
        context = {
            17: {
                "text": "甲。心服曰畏。乙。",
                "paragraph_index": 17,
                "source_file": "04-项目文献/D-标注/json/full_json/sample.json",
                "source_file_sha256": "full-json-hash",
                "source_schema_version": "annotation_docx_full_json_v1",
            }
        }
        result = _full_json_context_match("心服曰畏。", [17], context)
        self.assertEqual(result["status"], "exact")
        self.assertEqual(result["source_file"], context[17]["source_file"])
        self.assertEqual(result["source_file_sha256"], "full-json-hash")
        self.assertEqual(result["paragraph_indexes"], [17])
        self.assertEqual(result["matches"][0]["start_char"], 2)
        self.assertEqual(result["matches"][0]["end_char"], 7)

    def test_legacy_ai_mapping_has_all_machine_process_fields(self) -> None:
        markdown = PROJECT_ROOT / "04-项目文献/A-原著原典/经传释词_王引之.md"
        ai_json = PROJECT_ROOT / "04-项目文献/D-标注/json/ai_json/经传释词第二-㠯以已_李汶灿.json"
        passages = build_passages(markdown, "jingzhuan_shici")
        legacy_case = load_legacy_ai_json(ai_json)["cases"][8]
        case = adapt_legacy_case(
            legacy_case,
            passages,
            source_markdown=markdown,
            legacy_ai_json=ai_json,
            case_index=8,
        )
        self.assertTrue(all(case.get(field) for field in PROCESS_FIELDS))
        self.assertTrue(case.get("process_text"))
        self.assertIn("machine_synthesized", case["_migration"]["machine_filled_process_fields"].values())
        self.assertEqual(case["human_review"]["status"], "pending")

    def test_original_candidate_completion_is_explicitly_machine_only(self) -> None:
        case = {
            "source_work": "读书杂志",
            "target_text": "示例",
            "evidences": [],
            "problem_discovery": None,
            "research_question": None,
            "evidence_collection": None,
            "reasoning": None,
            "conclusion": "",
            "_migration": {},
        }
        completed = fill_missing_process_fields(case)
        self.assertTrue(all(completed.get(field) for field in PROCESS_FIELDS))
        self.assertTrue(completed["process_text"])
        self.assertTrue(all(status == "machine_synthesized" for status in completed["_migration"]["machine_filled_process_fields"].values()))

    def test_review_boundary_errors_are_draft_not_automated_rejection(self) -> None:
        self.assertEqual(
            classify_machine_status(
                [
                    "target_scope_not_resolved:machine_inferred",
                    "missing_evidence_passage:0:None",
                ]
            ),
            "draft",
        )
        self.assertEqual(
            classify_machine_status(["unresolved_target_work", "source_has_no_citation"]),
            "draft",
        )
        self.assertEqual(classify_machine_status(["quote_hash_mismatch:0"]), "rejected")


if __name__ == "__main__":
    unittest.main()
