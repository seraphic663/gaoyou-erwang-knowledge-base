"""Synthetic checks for the cleaned-source structural mode."""

from __future__ import annotations

import importlib.util
from pathlib import Path
import sys
import unittest


PROJECT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "clean_segmentation_under_test", PROJECT / "segmentation_clean.py"
)
assert SPEC and SPEC.loader
segmentation = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = segmentation
SPEC.loader.exec_module(segmentation)


class CleanStructureTests(unittest.TestCase):
    def test_bracketed_note_stays_with_entry_and_hides_heading_like_text(self):
        raw = "### 条甲\n正文【引文。\n\n### 假条头\n续注】\n\n正文续。\n"
        chunks = segmentation.segment_source(raw, 0, "synthetic")
        note = next(row for row in chunks if "假条头" in raw[row["start_cp"]:row["end_cp"]])
        self.assertIn("正文【", raw[note["structure"]["parent_start_cp"]:
                                  note["structure"]["parent_end_cp"]])
        self.assertNotIn("假条头", [item["title"] for item in note["structure"]["heading_path"]])

    def test_standalone_bracket_note_joins_previous_unheaded_paragraph(self):
        raw = "正文。\n\n【补注。】\n\n下一段。\n"
        chunks = segmentation.segment_source(raw, 0, "synthetic")
        note = next(row for row in chunks if "补注" in raw[row["start_cp"]:row["end_cp"]])
        parent = raw[note["structure"]["parent_start_cp"]:note["structure"]["parent_end_cp"]]
        self.assertIn("正文。", parent)
        self.assertNotIn("下一段。", parent)

    def test_small_markup_does_not_create_a_headword(self):
        raw = "卷一\n熊\n<small>古音注。</small>\n\n正文。\n"
        chunks = segmentation.segment_source(raw, 0, "synthetic")
        titles = [item["title"] for row in chunks for item in row["structure"]["heading_path"]]
        self.assertNotIn("熊", titles)

    def test_small_markup_does_not_join_a_standalone_paragraph(self):
        raw = "正文。\n\n<small>古音注。</small>\n\n下一段。\n"
        chunks = segmentation.segment_source(raw, 0, "synthetic")
        note = next(row for row in chunks if "古音注" in raw[row["start_cp"]:row["end_cp"]])
        parent = raw[note["structure"]["parent_start_cp"]:note["structure"]["parent_end_cp"]]
        self.assertNotIn("正文。", parent)
        self.assertNotIn("下一段。", parent)


if __name__ == "__main__":
    unittest.main()
