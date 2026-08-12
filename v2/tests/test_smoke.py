from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path


V2_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(V2_ROOT / "src"))

from erwang_v2.candidate_auditor import audit_candidates
from erwang_v2.candidate_extractor import extract_candidates
from erwang_v2.passage_builder import build_passages
from erwang_v2.validate_annotation_case import load_passages_jsonl, validate_case


class V2SmokeTest(unittest.TestCase):
    def test_passage_builder_preserves_small_text_and_note(self) -> None:
        source = V2_ROOT / "data/fixtures/sources/jingyi_shuwen.sample.md"
        passages = build_passages(source, "jingyi_shuwen")
        self.assertEqual(len(passages), 1)
        passage = passages[0]
        self.assertIn("户瓜反", passage["plain_text"])
        self.assertEqual(len(passage["inline_notes"]), 1)
        self.assertEqual(passage["inline_notes"][0]["text"], "户瓜反")

    def test_candidate_and_audit_layers(self) -> None:
        source = V2_ROOT / "data/fixtures/sources/jingyi_shuwen.sample.md"
        passages = build_passages(source, "jingyi_shuwen")
        layers = extract_candidates(passages)
        candidates = layers["parsed_items"] + layers["candidate_items"]
        self.assertTrue(candidates)
        audit = audit_candidates(candidates, passages)
        self.assertTrue(audit)
        self.assertTrue(all(item["machine_status"] == "approved" for item in audit))

    def test_fixture_cases_pass_structural_and_quote_checks(self) -> None:
        passages = load_passages_jsonl(V2_ROOT / "data/fixtures/passages.jsonl")
        case_dir = V2_ROOT / "data/fixtures/cases"
        cases = [json.loads(path.read_text(encoding="utf-8")) for path in case_dir.glob("*.json")]
        self.assertEqual(len(cases), 2)
        for case in cases:
            self.assertEqual(validate_case(case, passages), [])

    def test_noncanonical_passage_cannot_be_marked_quote_passed(self) -> None:
        passages = load_passages_jsonl(V2_ROOT / "data/fixtures/passages.jsonl")
        case = json.loads(
            (V2_ROOT / "data/fixtures/cases/造舟于河.annotation.json").read_text(
                encoding="utf-8"
            )
        )
        evidence = case["evidences"][0]
        evidence["source_resolution"] = "legacy_derived_passage"
        evidence["quote_check"] = "passed"
        errors = validate_case(case, passages)
        self.assertIn("noncanonical_quote_cannot_pass:0:legacy_derived_passage", errors)


if __name__ == "__main__":
    unittest.main()
