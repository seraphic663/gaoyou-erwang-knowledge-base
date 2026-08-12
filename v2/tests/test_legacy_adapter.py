from __future__ import annotations

import sys
import unittest
from pathlib import Path


V2_ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = V2_ROOT.parent
sys.path.insert(0, str(V2_ROOT / "src"))

from erwang_v2.legacy_ai_adapter import adapt_legacy_case, load_legacy_ai_json
from erwang_v2.legacy_dictionary_adapter import load_legacy_dictionary_material
from erwang_v2.passage_builder import build_passages
from erwang_v2.target_inference import infer_target_scope
from erwang_v2.validate_annotation_case import validate_case


class LegacyAdapterMappingTest(unittest.TestCase):
    def _load(self, work_key: str, markdown_name: str, ai_name: str):
        markdown = PROJECT_ROOT / "04-项目文献/A-原著原典" / markdown_name
        ai_json = PROJECT_ROOT / "04-项目文献/D-标注/json/ai_json" / ai_name
        passages = build_passages(markdown, work_key)
        cases = load_legacy_ai_json(ai_json)["cases"]
        passage_map = {passage["passage_id"]: passage for passage in passages}
        return markdown, ai_json, passages, cases, passage_map

    def test_jingzhuan_cases_use_the_yiyi_entry_and_preserve_no_citation(self) -> None:
        markdown, ai_json, passages, cases, passage_map = self._load(
            "jingzhuan_shici",
            "经传释词_王引之.md",
            "经传释词第二-㠯以已_李汶灿.json",
        )

        for index in (0, 1, 8, 12):
            case = adapt_legacy_case(
                cases[index],
                passages,
                source_markdown=markdown,
                legacy_ai_json=ai_json,
                case_index=index,
            )
            self.assertEqual(case["source_passage_id"], "jingzhuan_shici_0006")
            self.assertEqual(case["target_works"], [])
            self.assertEqual(case["target_scope"]["status"], "unresolved")

        no_citation = adapt_legacy_case(
            cases[8],
            passages,
            source_markdown=markdown,
            legacy_ai_json=ai_json,
            case_index=8,
        )
        self.assertEqual(no_citation["evidence_state"], "source_no_citation")
        self.assertEqual(no_citation["evidences"], [])
        self.assertIn("source_has_no_citation", validate_case(no_citation, passage_map))

    def test_guangya_cases_use_the_case_blocks_not_short_quote_matches(self) -> None:
        markdown, ai_json, passages, cases, _ = self._load(
            "guangya_shuzheng",
            "广雅疏证_王念孙.md",
            "广雅疏证_徐健怡.json",
        )

        first = adapt_legacy_case(
            cases[0],
            passages,
            source_markdown=markdown,
            legacy_ai_json=ai_json,
            case_index=0,
        )
        second = adapt_legacy_case(
            cases[1],
            passages,
            source_markdown=markdown,
            legacy_ai_json=ai_json,
            case_index=1,
        )
        self.assertEqual(first["source_passage_id"], "guangya_shuzheng_0008")
        self.assertEqual(second["source_passage_id"], "guangya_shuzheng_0011")
        self.assertTrue(
            all(
                evidence["passage_id"] is None
                and evidence["cited_work_match_status"] == "external_source_pending"
                for evidence in first["evidences"] + second["evidences"]
            )
        )

    def test_dushu_variant_title_uses_the_target_block(self) -> None:
        markdown, ai_json, passages, cases, _ = self._load(
            "dushu_zazhi",
            "读书杂志_王念孙.md",
            "读书杂志_平原之隰-譕臣_卢飞宇.json",
        )
        case = adapt_legacy_case(
            cases[1],
            passages,
            source_markdown=markdown,
            legacy_ai_json=ai_json,
            case_index=1,
        )
        self.assertEqual(case["source_passage_id"], "dushu_zazhi_1823")

    def test_target_inference_records_candidates_without_resolving_scope(self) -> None:
        scope = infer_target_scope(
            {
                "target_work": "",
                "evidences": [
                    {"source_work": "《易·泰》六四"},
                    {"source_work": "《书·牧誓》"},
                    {"source_work": "《书·金縢》"},
                    {"source_work": "《礼记·乐记》"},
                ],
            }
        )
        self.assertEqual(scope["status"], "machine_inferred")
        self.assertEqual(
            scope["target_works"], ["易·泰", "书·牧誓", "书·金縢", "礼记·乐记"]
        )
        self.assertEqual(scope["confidence"], "candidate_only")

    def test_legacy_ai_case_has_explicit_reprocessing_provenance(self) -> None:
        markdown, ai_json, passages, cases, _ = self._load(
            "dushu_zazhi",
            "读书杂志_王念孙.md",
            "读书杂志_平原之隰-譕臣_卢飞宇.json",
        )
        case = adapt_legacy_case(
            cases[0],
            passages,
            source_markdown=markdown,
            legacy_ai_json=ai_json,
            case_index=0,
        )
        migration = case["_migration"]
        self.assertEqual(migration["source_layer"], "legacy_ai_json_output")
        self.assertEqual(migration["transformation_kind"], "legacy_ai_json_reprocessing")
        self.assertEqual(migration["provenance"]["source_file"], str(ai_json))

    def test_legacy_dictionary_materialization_binds_all_rows_without_canonical_claim(self) -> None:
        cases, source_passages, target_passages, material = load_legacy_dictionary_material(
            PROJECT_ROOT / "02-数据库/data/dictionary.db",
            source_text_path=PROJECT_ROOT / "02-数据库/main/source.txt",
            parser_path=PROJECT_ROOT / "02-数据库/main/parser.py",
        )
        self.assertEqual(len(cases), 815)
        self.assertEqual(len(source_passages), 815)
        self.assertEqual(len(target_passages), 7120)
        self.assertTrue(all(case["source_passage_id"] for case in cases))
        self.assertTrue(all(case["target_passage_id"] for case in cases))
        self.assertTrue(all(case["process_text"] for case in cases))
        self.assertTrue(
            all(
                all(case.get(field) for field in (
                    "problem_discovery",
                    "research_question",
                    "evidence_collection",
                    "reasoning",
                    "conclusion",
                ))
                for case in cases
            )
        )
        self.assertTrue(
            all(
                evidence["passage_id"]
                and evidence["quote_check"] == "unchecked"
                and evidence["source_resolution"] == "legacy_derived_passage"
                for case in cases
                for evidence in case["evidences"]
            )
        )
        self.assertEqual(len(material["catalog_terms"]), 14)
        self.assertEqual(len(material["catalog_works"]), 12)


if __name__ == "__main__":
    unittest.main()
