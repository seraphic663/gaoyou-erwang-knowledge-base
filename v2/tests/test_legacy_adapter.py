from __future__ import annotations

import sys
import unittest
from pathlib import Path


V2_ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = V2_ROOT.parent
sys.path.insert(0, str(V2_ROOT / "src"))

from erwang_v2.legacy_ai_adapter import adapt_legacy_case, load_legacy_ai_json
from erwang_v2.passage_builder import build_passages
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


if __name__ == "__main__":
    unittest.main()
