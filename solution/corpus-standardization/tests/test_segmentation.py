"""Synthetic examples for structure, continuity, and source coordinates."""

from __future__ import annotations

import importlib.util
from contextlib import closing
import json
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest


PROJECT = Path(__file__).resolve().parents[1]


def load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


segmentation = load("synthetic_segmentation_v2", PROJECT / "segmentation_v2.py")
pipeline = load("synthetic_structure_pipeline", PROJECT / "pipeline.py")


class StructureTests(unittest.TestCase):
    def test_markdown_heading_path_keeps_entry_and_paragraphs_together(self):
        raw = "# 书\n\n## 卷一\n\n### 条甲\n\n正文一。<small>小注。</small>\n\n正文二。\n\n### 条乙\n\n正文三。\n"
        chunks = segmentation.segment_source(raw, 0, "synthetic")
        first = next(row for row in chunks if "正文一" in raw[row["start_cp"]:row["end_cp"]])
        self.assertIn("正文二", raw[first["start_cp"]:first["end_cp"]])
        self.assertEqual([item["title"] for item in first["structure"]["heading_path"]],
                         ["书", "卷一", "条甲"])
        parent = first["structure"]
        self.assertEqual(raw[parent["parent_start_cp"]:parent["parent_end_cp"]].strip(),
                         "### 条甲\n\n正文一。<small>小注。</small>\n\n正文二。")
        self.assertEqual(raw[parent["heading_path"][-1]["start_cp"]:
                             parent["heading_path"][-1]["end_cp"]], "### 条甲")
        self.assertNotIn("正文三", raw[parent["parent_start_cp"]:parent["parent_end_cp"]])

    def test_symbol_hierarchy_and_unheaded_prose_cover_source(self):
        raw = "前言。\r\n\r\n●卷一\r\n○天\r\n◇天文\r\n甲。\r\n◇地理\r\n乙。"
        chunks = segmentation.segment_source(raw, 0, "synthetic")
        self.assertEqual(chunks[0]["role"], "paragraph")
        earth = next(row for row in chunks if "乙。" in raw[row["start_cp"]:row["end_cp"]])
        self.assertEqual([item["title"] for item in earth["structure"]["heading_path"]],
                         ["卷一", "天", "地理"])
        covered = set()
        for row in chunks:
            covered.update(range(row["start_cp"], row["end_cp"]))
        self.assertEqual(covered, set(range(len(raw))))

    def test_headword_detected_by_explanation_label_without_work_name(self):
        raw = "第一部\n甲jiǎ\n注解：甲之义。\n乙yǐ\n注解：乙之义。\n"
        chunks = segmentation.segment_source(raw, 0, "synthetic")
        entry = next(row for row in chunks if "乙之义" in raw[row["start_cp"]:row["end_cp"]])
        self.assertEqual(entry["structure"]["heading_path"][-1]["kind"], "headword")
        self.assertEqual(entry["structure"]["heading_path"][-1]["title"], "乙yǐ")

    def test_short_headword_with_rhyme_and_note_line_is_candidate(self):
        raw = "卷一\n弓【居戎切】\n【古音与引文。】\n熊\n【古音长注。】\n"
        chunks = segmentation.segment_source(raw, 0, "synthetic")
        bear = next(row for row in chunks if "古音长注" in raw[row["start_cp"]:row["end_cp"]])
        self.assertEqual(bear["structure"]["heading_path"][-1]["title"], "熊")
        self.assertEqual(bear["structure"]["heading_path"][-1]["confidence"], "candidate")

    def test_multiline_note_cannot_create_heading_or_paragraph_boundary(self):
        raw = "正文【引文。\n\n### 似条头\n\n续注。】\n\n后文。\n"
        chunks = segmentation.segment_source(raw, 0, "synthetic")
        self.assertFalse(any(item["title"] == "似条头"
                             for row in chunks for item in row["structure"]["heading_path"]))
        note = next(row for row in chunks if "似条头" in raw[row["start_cp"]:row["end_cp"]])
        self.assertIn("正文【", raw[note["structure"]["parent_start_cp"]:
                                  note["structure"]["parent_end_cp"]])

    def test_unclosed_prefix_does_not_hide_later_complete_note(self):
        raw = "【残缺未闭\n### 真条\n正文【完整注\n### 注内假条\n续注】\n### 后条\n后文。\n"
        chunks = segmentation.segment_source(raw, 0, "synthetic")
        titles = [item["title"] for row in chunks for item in row["structure"]["heading_path"]]
        self.assertIn("真条", titles)
        self.assertIn("后条", titles)
        self.assertNotIn("注内假条", titles)

    def test_standalone_note_paragraph_joins_previous_unheaded_paragraph(self):
        raw = "正文。\n\n<small>补注。</small>\n\n独立短条。\n"
        chunks = segmentation.segment_source(raw, 0, "synthetic")
        note = next(row for row in chunks if "补注" in raw[row["start_cp"]:row["end_cp"]])
        self.assertIn("正文。", raw[note["structure"]["parent_start_cp"]:
                                    note["structure"]["parent_end_cp"]])
        self.assertNotIn("独立短条", raw[note["structure"]["parent_start_cp"]:
                                          note["structure"]["parent_end_cp"]])

    def test_long_note_parts_share_parent_and_mark_continuation(self):
        raw = "### 词\n正文【" + "注" * 1900 + "】结尾。\n"
        chunks = segmentation.segment_source(raw, 0, "synthetic")
        self.assertGreater(len(chunks), 1)
        self.assertTrue(all(row["end_cp"] - row["start_cp"] <= 1200 for row in chunks))
        self.assertEqual(len({row["structure"]["parent_id"] for row in chunks}), 1)
        self.assertEqual([row["structure"]["part_index"] for row in chunks],
                         list(range(1, len(chunks) + 1)))
        self.assertTrue(chunks[0]["structure"]["note_continues_next"])
        self.assertTrue(chunks[1]["structure"]["note_continued_from_previous"])
        self.assertEqual(chunks[-1]["structure"]["parent_end_cp"], len(raw))

    def test_catalog_like_heading_is_retained_as_candidate(self):
        raw = "●目录\n○篇一\n○篇二\n●卷一\n○篇一\n正文。\n"
        chunks = segmentation.segment_source(raw, 0, "synthetic")
        catalog = next(row for row in chunks if raw[row["start_cp"]:row["end_cp"]].startswith("○篇二"))
        self.assertTrue(catalog["structure"]["toc_candidate"])
        body = next(row for row in chunks if "正文。" in raw[row["start_cp"]:row["end_cp"]])
        self.assertFalse(body["structure"]["toc_candidate"])

    def test_build_writes_structure_column_and_fixed_mode_remains_selectable(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            wang = root / "data" / "A-原著原典"
            wang.mkdir(parents=True)
            for name in pipeline.WANG_NAMES:
                (wang / name).write_text("## 卷一\n### 条甲\n甲。\n", encoding="utf-8")
            for tier, _ in pipeline.TIERS:
                (root / "data" / "daizhigev20" / tier).mkdir(parents=True)
            project = root / "solution" / "corpus-standardization"
            project.mkdir(parents=True)
            structured = project / "structured"
            fixed = project / "fixed"
            self.assertTrue(pipeline.build_corpus(root, structured)["validation_passed"])
            self.assertTrue(pipeline.build_corpus(root, fixed, "fixed")["validation_passed"])
            with closing(sqlite3.connect(structured / "corpus.sqlite3")) as connection:
                row = connection.execute("SELECT structure_json FROM chunks WHERE role='entry' LIMIT 1").fetchone()
                self.assertIsNotNone(row)
                self.assertEqual(json.loads(row[0])["heading_path"][-1]["title"], "条甲")
            with closing(sqlite3.connect(fixed / "corpus.sqlite3")) as connection:
                self.assertEqual(connection.execute("SELECT structure_json FROM chunks LIMIT 1").fetchone()[0], "{}")


if __name__ == "__main__":
    unittest.main()
