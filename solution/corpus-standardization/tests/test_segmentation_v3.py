"""Synthetic counterexamples for general v3 structure rules."""

from __future__ import annotations

import importlib.util
from contextlib import closing
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest


PROJECT = Path(__file__).resolve().parents[1]


def load(name: str):
    spec = importlib.util.spec_from_file_location(name, PROJECT / f"{name}.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


segmentation = load("segmentation")
pipeline = load("pipeline")


def containing(raw: str, chunks: list[dict], needle: str) -> dict:
    return next(chunk for chunk in chunks
                if needle in raw[chunk["start_cp"]:chunk["end_cp"]])


class SegmentationV3Tests(unittest.TestCase):
    def test_explicit_catalog_does_not_leak_into_body(self):
        raw = ("荀子目录\n卷一\n劝学篇第一\n卷二\n修身篇第二\n\n"
               "某氏序\n序言。\n卷一\n劝学篇第一\n正文。\n")
        chunks = segmentation.segment_source(raw, 0, "book")
        self.assertEqual(containing(raw, chunks, "修身篇第二")["role"], "toc")
        self.assertEqual(containing(raw, chunks, "序言。")["role"], "paratext")
        body = containing(raw, chunks, "正文。")
        self.assertEqual([h["title"] for h in body["structure"]["heading_path"]],
                         ["卷一", "劝学篇第一"])

    def test_unlabeled_catalog_needs_repeated_body_titles(self):
        names = [f"甲部 乙篇 第{number}首" for number in "一二三四五六七八"]
        catalog = "\n".join(names)
        body = "\n\n".join(f"{title}\n正文有标点。" for title in names[:3])
        raw = catalog + "\n\n" + body
        chunks = segmentation.segment_source(raw, 0, "book")
        self.assertEqual(containing(raw, chunks, names[3])["role"], "toc")
        self.assertNotEqual(containing(raw, chunks, "正文有标点。")["role"], "toc")

    def test_catalog_with_blank_lines_ends_before_repeated_body(self):
        raw = ("目录\n卷一\n篇一\n\n卷二\n篇二\n\n卷三\n篇三\n\n"
               "前序\n序言。\n卷一\n篇一\n正文。\n")
        chunks = segmentation.segment_source(raw, 0, "book")
        self.assertEqual(containing(raw, chunks, "篇三")["role"], "toc")
        self.assertEqual(containing(raw, chunks, "序言。")["role"], "paratext")
        self.assertNotEqual(containing(raw, chunks, "正文。")["role"], "toc")

    def test_titles_repeated_only_before_a_short_run_do_not_prove_catalog(self):
        earlier = "甲题\n正文。\n乙题\n正文。\n丙题\n正文。\n"
        later = "\n".join(["甲题", "乙题", "丙题", "丁题", "戊题", "己题", "庚题", "辛题"])
        raw = earlier + later + "\n\n末段。"
        chunks = segmentation.segment_source(raw, 0, "book")
        self.assertFalse(any(chunk["role"] == "toc" for chunk in chunks))

    def test_short_unmarked_verse_is_not_catalog(self):
        raw = "\n".join(["清风入竹林", "明月照溪水", "山中闻夜钟", "远客思故乡"] * 3) + "\n后文。"
        chunks = segmentation.segment_source(raw, 0, "verse")
        self.assertFalse(any(chunk["role"] == "toc" for chunk in chunks))

    def test_cross_format_volume_and_article_reset_old_parent(self):
        raw = "# 书\n## 卷一\n### 旧条\n甲。\n卷之二\n列传第三\n乙。\n"
        chunks = segmentation.segment_source(raw, 0, "book")
        path = [h["title"] for h in containing(raw, chunks, "乙。")["structure"]["heading_path"]]
        self.assertEqual(path, ["书", "卷之二", "列传第三"])

    def test_closer_stops_old_article_and_does_not_open_later_prose(self):
        raw = "# 书\n卷一\n某篇第一\n甲。\n右章第一\n过渡说明。\n卷二\n新篇第二\n乙。\n"
        chunks = segmentation.segment_source(raw, 0, "book")
        self.assertEqual(containing(raw, chunks, "右章第一")["role"], "closure")
        self.assertEqual(containing(raw, chunks, "过渡说明。")["structure"]["heading_path"], [])
        self.assertEqual([h["title"] for h in containing(raw, chunks, "乙。")["structure"]["heading_path"]],
                         ["卷二", "新篇第二"])

    def test_paratext_is_separate_and_embedded_character_is_not_heading(self):
        raw = "# 书\n卷一\n某篇第一\n正文提到跋字。\n\n跋\n后序内容。\n\n新章第二\n正文。\n"
        chunks = segmentation.segment_source(raw, 0, "book")
        self.assertEqual(containing(raw, chunks, "后序内容。")["role"], "paratext")
        self.assertEqual(containing(raw, chunks, "正文提到跋字。")["role"], "entry")
        self.assertNotIn("某篇第一", [h["title"] for h in
                                     containing(raw, chunks, "正文。")["structure"]["heading_path"]])

    def test_quote_and_standalone_explanation_stay_together_when_possible(self):
        raw = "### 词\n" + "前句。" * 34 + "《某书》曰：「此句。」\n甲乙案：此句应如此解。" + "后句。" * 40
        chunks = segmentation.segment_source(raw, 0, "book", target=110, maximum=200)
        linked = containing(raw, chunks, "《某书》曰")
        self.assertIn("甲乙案：", raw[linked["start_cp"]:linked["end_cp"]])
        self.assertTrue(any(link["basis"] == "quote_explanation"
                            for link in linked["structure"]["association_links"]))
        self.assertTrue(all(c["end_cp"] - c["start_cp"] <= 200 for c in chunks))

    def test_multisentence_explanation_stays_with_citation(self):
        raw = ("### 词\n" + "前句。" * 25 + "《某书》曰：「引文。」\n"
               + "甲乙案：" + "解说甲。" * 12 + "\n" + "后句。" * 40)
        chunks = segmentation.segment_source(raw, 0, "book", target=110, maximum=170)
        citation = containing(raw, chunks, "《某书》曰")
        self.assertIn("解说甲。" * 12, raw[citation["start_cp"]:citation["end_cp"]])
        self.assertTrue(any(link["basis"] == "quote_explanation" and link["within_limit"]
                            for link in citation["structure"]["association_links"]))

    def test_association_range_ends_after_explanation_line_for_each_newline(self):
        for newline in ("\n", "\r\n", "\r", ""):
            with self.subTest(newline=repr(newline)):
                raw = ("《某书》曰：「引文。」" + newline +
                       "甲乙案：第一句。第二句。" + newline + "尾段。")
                links = segmentation._association_links(raw, 0, len(raw))
                ranges = [(left, right) for basis, left, right in links.values()
                          if basis == "quote_explanation"]
                self.assertTrue(ranges)
                expected_end = raw.index("尾段。") if newline else len(raw)
                self.assertEqual(ranges[0][1], expected_end)

    def test_forced_long_explanation_has_continuation_with_1200_cap(self):
        raw = "### 词\n《某书》曰：「短句。」\n甲乙案：" + "解释" * 750 + "。"
        chunks = segmentation.segment_source(raw, 0, "book")
        self.assertTrue(all(c["end_cp"] - c["start_cp"] <= 1200 for c in chunks))
        self.assertTrue(all(c["structure"]["part_count"] == len(chunks) for c in chunks))
        self.assertIn("甲乙案：", raw[chunks[0]["start_cp"]:chunks[0]["end_cp"]])

    def test_unavoidable_quote_explanation_split_records_both_sides(self):
        raw = "### 词\n《某书》曰：「" + "引文" * 90 + "。」\n甲乙案：" + "解释" * 200
        chunks = segmentation.segment_source(raw, 0, "book", target=120, maximum=300)
        linked = [(left, right) for left, right in zip(chunks, chunks[1:])
                  if left["structure"]["association_continues_next"] == "quote_explanation"]
        self.assertTrue(linked)
        self.assertEqual(linked[0][1]["structure"]["association_continued_from_previous"],
                         "quote_explanation")

    def test_build_keeps_mapping_and_full_raw_coverage(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            wang = root / "data" / "A-原著原典"
            wang.mkdir(parents=True)
            raw = "# 书\n卷一\n某篇第一\nＡ。<small>注。</small>\n"
            for name in pipeline.WANG_NAMES:
                (wang / name).write_text(raw, encoding="utf-8")
            for tier, _ in pipeline.TIERS:
                (root / "data" / "daizhigev20" / tier).mkdir(parents=True)
            output = root / "solution" / "corpus-standardization" / "v3"
            output.parent.mkdir(parents=True)
            manifest = pipeline.build_corpus(root, output, "structure-v3")
            self.assertTrue(manifest["validation_passed"])
            self.assertEqual(manifest["pipeline_version"], "corpus-standardization-v3")
            self.assertEqual(manifest["segmentation_mode"], "structure-v3")
            with closing(sqlite3.connect(output / "corpus.sqlite3")) as db:
                row = db.execute("SELECT normalized_text,mapping_json,structure_json FROM chunks "
                                 "WHERE normalized_text LIKE '%A%' LIMIT 1").fetchone()
                self.assertIsNotNone(row)
                self.assertIn("A", row[0])
                self.assertTrue(json.loads(row[1]))
                self.assertTrue(json.loads(row[2]))


if __name__ == "__main__":
    unittest.main()
