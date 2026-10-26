"""Synthetic invariants only; no research cases or source corpus are read.

All mutable fixtures live under the system temporary directory. Run with
PYTHONDONTWRITEBYTECODE=1 to keep the checkout free of interpreter artifacts.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import unittest


MODULE_PATH = Path(__file__).resolve().parents[1] / "pipeline.py"
spec = importlib.util.spec_from_file_location("synthetic_pipeline_under_test", MODULE_PATH)
assert spec and spec.loader
pipeline = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = pipeline
spec.loader.exec_module(pipeline)


class NormalizationTests(unittest.TestCase):
    def assert_mapping_covers(self, raw: str, normalized: str, mapping: list, offset: int = 0):
        cursor = 0
        for norm_start, norm_end, raw_start, raw_end, kind in mapping:
            self.assertEqual(norm_start, cursor, "normalized intervals must be contiguous")
            self.assertGreater(norm_end, norm_start)
            self.assertGreater(raw_end, raw_start)
            self.assertGreaterEqual(raw_start, offset)
            self.assertLessEqual(raw_end, offset + len(raw))
            self.assertIn(kind, {"identity", "nfkc", "whitespace"})
            if kind == "identity":
                self.assertEqual(
                    normalized[norm_start:norm_end], raw[raw_start-offset:raw_end-offset]
                )
            cursor = norm_end
        self.assertEqual(cursor, len(normalized))

    def test_identity_uses_codepoints_not_utf16(self):
        raw = "甲\U00020000乙□\ue000\U0002A6D6末"
        normalized, mapping = pipeline.normalize_with_mapping(raw, raw_offset=17)
        self.assertEqual(normalized, raw)
        self.assert_mapping_covers(raw, normalized, mapping, 17)
        for start in range(len(raw)):
            for end in range(start + 1, len(raw) + 1):
                self.assertEqual(
                    pipeline.normalized_span_to_raw(mapping, start, end),
                    (17 + start, 17 + end),
                )

    def test_nfkc_expansion_projects_partial_match_to_whole_original(self):
        raw = "甲㍿乙ﬃ丙①Ｄ"
        normalized, mapping = pipeline.normalize_with_mapping(raw, raw_offset=9)
        self.assertEqual(normalized, "甲株式会社乙ffi丙1D")
        self.assert_mapping_covers(raw, normalized, mapping, 9)
        self.assertEqual(pipeline.normalized_span_to_raw(mapping, 2, 4), (10, 11))
        self.assertEqual(pipeline.normalized_span_to_raw(mapping, 6, 8), (12, 13))
        self.assertEqual(pipeline.normalized_span_to_raw(mapping, 0, 5), (9, 11))

    def test_combining_characters_are_preserved_under_per_codepoint_contract(self):
        # This implementation deliberately does not promise whole-string NFKC.
        raw = "e\u0301\u1100\u1161\U00020000"
        normalized, mapping = pipeline.normalize_with_mapping(raw)
        self.assertEqual(normalized, raw)
        self.assert_mapping_covers(raw, normalized, mapping)
        self.assertEqual(pipeline.normalized_span_to_raw(mapping, 0, 2), (0, 2))
        self.assertEqual(pipeline.normalized_span_to_raw(mapping, 1, 2), (1, 2))
        self.assertEqual(pipeline.normalized_span_to_raw(mapping, 4, 5), (4, 5))

    def test_crlf_tabs_and_compatibility_spaces_collapse_without_trimming(self):
        raw = "\r\n甲\r\n\t \u00a0\u3000乙\n"
        normalized, mapping = pipeline.normalize_with_mapping(raw, raw_offset=4)
        self.assertEqual(normalized, " 甲 乙 ")
        self.assert_mapping_covers(raw, normalized, mapping, 4)
        self.assertEqual(pipeline.normalized_span_to_raw(mapping, 2, 3), (7, 13))

    def test_compatibility_character_expanding_to_space_and_mark_is_not_lost(self):
        raw = "甲\u00a8乙"  # DIAERESIS -> SPACE + COMBINING DIAERESIS.
        normalized, mapping = pipeline.normalize_with_mapping(raw)
        self.assertEqual(normalized, "甲 \u0308乙")
        self.assert_mapping_covers(raw, normalized, mapping)
        self.assertEqual(pipeline.normalized_span_to_raw(mapping, 1, 2), (1, 2))
        self.assertEqual(pipeline.normalized_span_to_raw(mapping, 2, 3), (1, 2))

    def test_empty_text(self):
        self.assertEqual(pipeline.normalize_with_mapping(""), ("", []))
        with self.assertRaises(ValueError):
            pipeline.normalized_span_to_raw([], 0, 0)

    def test_invalid_ranges_are_rejected(self):
        _, mapping = pipeline.normalize_with_mapping("甲乙")
        for start, end in [(-1, 1), (0, 0), (1, 1), (2, 1), (0, 3), (2, 3)]:
            with self.subTest(start=start, end=end), self.assertRaises(ValueError):
                pipeline.normalized_span_to_raw(mapping, start, end)

    def test_invalid_normalization_inputs(self):
        with self.assertRaises((TypeError, ValueError)):
            pipeline.normalize_with_mapping(None)
        with self.assertRaises((TypeError, ValueError)):
            pipeline.normalize_with_mapping("甲", raw_offset=-1)


WANG_NAMES = (
    "读书杂志_王念孙.md", "广雅疏证_王念孙.md",
    "经义述闻_王引之.md", "经传释词_王引之.md",
)
TIERS = ("高频", "中频", "低频")


class CorpusBuildTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="corpus-standardization-tests-")
        self.addCleanup(self.temp.cleanup)
        self.workspace = Path(self.temp.name) / "workspace"
        self.wang = self.workspace / "data" / "A-原著原典"
        self.external = self.workspace / "data" / "daizhigev20"
        self.project = self.workspace / "solution" / "corpus-standardization"
        self.wang.mkdir(parents=True)
        self.project.mkdir(parents=True)
        for name in WANG_NAMES:
            (self.wang / name).write_bytes("# Synthetic\n甲乙\n".encode("utf-8"))
        for tier in TIERS:
            (self.external / tier).mkdir(parents=True)
        self.output = self.project / "generated" / "release"

    def source_bytes(self):
        return {
            path.relative_to(self.workspace).as_posix(): path.read_bytes()
            for path in (self.workspace / "data").rglob("*") if path.is_file()
        }

    def open_database(self):
        connection = sqlite3.connect(self.output / "corpus.sqlite3")
        connection.row_factory = sqlite3.Row
        self.addCleanup(connection.close)
        return connection

    def test_source_allowlist_excludes_noncorpus_material(self):
        expected = {self.wang / name for name in WANG_NAMES}
        for tier in TIERS:
            path = self.external / tier / "ordinary.md"
            path.write_text("synthetic material", encoding="utf-8")
            expected.add(path)
        for relative in [
            "research/answer.md", "data/0-当前阅读/annotation/answer.md",
            "data/daizhigev20/README.md", "data/daizhigev20/analysis/answer.md",
            "data/A-原著原典/unlisted.md", "data/daizhigev20/低频/not_markdown.txt",
        ]:
            path = self.workspace / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("must not enter index", encoding="utf-8")
        before = self.source_bytes()
        actual = pipeline.iter_source_paths(self.workspace)
        self.assertEqual({path.resolve() for _, path in actual}, {p.resolve() for p in expected})
        self.assertEqual(len(actual), len(expected), "no duplicate source entry")
        self.assertEqual(self.source_bytes(), before)

    def test_missing_required_source_is_not_silently_ignored(self):
        (self.wang / WANG_NAMES[0]).unlink()
        with self.assertRaises((FileNotFoundError, ValueError)):
            pipeline.iter_source_paths(self.workspace)

    def test_preserves_bytes_and_maps_raw_chunks_across_astral_and_long_line(self):
        header = "\ufeff---\r\ntitle: Synthetic\r\n---\r\n"
        body = "甲" * 599 + "\U00020000" + "乙" * 620 + "【unclosed"
        raw = header + body
        path = self.external / "高频" / "long.md"
        path.write_bytes(raw.encode("utf-8"))
        empty = self.external / "低频" / "empty.md"
        empty.write_bytes(b"")
        before = self.source_bytes()
        manifest = pipeline.build_corpus(self.workspace, self.output, "fixed")
        self.assertTrue(manifest["validation_passed"])
        self.assertEqual(before, self.source_bytes(), "building must not rewrite any source")
        connection = self.open_database()
        sources = connection.execute("SELECT * FROM sources").fetchall()
        source = next(row for row in sources if row["relpath"].endswith("/long.md"))
        self.assertEqual(source["raw_text"], raw)
        self.assertEqual(source["sha256"], hashlib.sha256(raw.encode("utf-8")).hexdigest())
        self.assertEqual(source["codepoints"], len(raw))
        self.assertEqual(source["byte_size"], len(raw.encode("utf-8")))
        self.assertEqual(source["body_start"], len(header))
        self.assertEqual(source["body_end"], len(raw))
        self.assertTrue(json.loads(source["flags_json"]).get("unmatched_bracket"))
        rows = connection.execute(
            "SELECT * FROM chunks WHERE source_id=? ORDER BY start_cp", (source["source_id"],)
        ).fetchall()
        self.assertGreaterEqual(len(rows), 3)
        self.assertEqual(rows[0]["start_cp"], source["body_start"])
        self.assertEqual(rows[-1]["end_cp"], source["body_end"])
        covered_until = source["body_start"]
        previous_start = None
        for row in rows:
            start, end = row["start_cp"], row["end_cp"]
            self.assertLessEqual(start, covered_until, "raw corpus cannot have uncovered gaps")
            self.assertGreater(end, start)
            self.assertLessEqual(end - start, 600)
            if previous_start is not None:
                self.assertEqual(start - previous_start, 500)
            previous_start = start
            covered_until = max(covered_until, end)
            self.assertLessEqual(source["body_start"], row["reading_start_cp"])
            self.assertLessEqual(row["reading_start_cp"], start)
            self.assertGreaterEqual(row["reading_end_cp"], end)
            self.assertLessEqual(row["reading_end_cp"], source["body_end"])
            normalized = row["normalized_text"]
            mapping = json.loads(row["mapping_json"])
            self.assertEqual(normalized, raw[start:end])
            self.assertEqual(pipeline.normalized_span_to_raw(mapping, 0, len(normalized)), (start, end))
        self.assertEqual(covered_until, len(raw))
        empty_source = next(row for row in sources if row["relpath"].endswith("/empty.md"))
        self.assertEqual(empty_source["raw_text"], "")
        self.assertTrue(json.loads(empty_source["flags_json"]).get("empty_body"))
        self.assertEqual(connection.execute(
            "SELECT count(*) FROM chunks WHERE source_id=?", (empty_source["source_id"],)
        ).fetchone()[0], 0)

    def test_invalid_utf8_fails_explicitly_and_preserves_source(self):
        invalid = self.external / "中频" / "invalid.md"
        invalid.write_bytes(b"prefix\xff\xfeend")
        before = self.source_bytes()
        manifest = pipeline.build_corpus(self.workspace, self.output)
        self.assertEqual(manifest["status"], "failed")
        self.assertFalse(manifest["validation_passed"])
        failure_record = json.dumps(manifest, ensure_ascii=False).lower()
        self.assertIn("invalid.md", failure_record, "failure must identify the rejected source")
        self.assertTrue(any(marker in failure_record for marker in ("utf", "decode", "unicode")))
        self.assertEqual(before, self.source_bytes())

    def test_unclosed_frontmatter_does_not_silently_discard_source(self):
        raw = "---\ntitle: unfinished\n甲乙\U00020000【未闭合"
        path = self.external / "低频" / "unfinished.md"
        path.write_bytes(raw.encode("utf-8"))
        before = self.source_bytes()
        pipeline.build_corpus(self.workspace, self.output)
        connection = self.open_database()
        source = connection.execute(
            "SELECT * FROM sources WHERE relpath LIKE '%/unfinished.md'"
        ).fetchone()
        self.assertIsNotNone(source)
        self.assertEqual(source["raw_text"], raw)
        self.assertEqual(source["body_start"], 0, "unclosed frontmatter cannot swallow content")
        self.assertTrue(json.loads(source["flags_json"]).get("unterminated_frontmatter"))
        rows = connection.execute(
            "SELECT * FROM chunks WHERE source_id=? ORDER BY start_cp", (source["source_id"],)
        ).fetchall()
        self.assertTrue(rows)
        self.assertEqual(rows[0]["start_cp"], 0)
        self.assertEqual(rows[-1]["end_cp"], len(raw))
        self.assertEqual(before, self.source_bytes())

    def test_reading_windows_preserve_crlf_boundary_and_unclosed_context(self):
        # Chunk 2 starts on LF: snapping after the preceding CR must not skip it.
        crlf = self.external / "高频" / "boundary.md"
        crlf.write_bytes(("甲" * 499 + "\r\n" + "乙" * 1000).encode("utf-8"))
        unclosed = self.external / "低频" / "open-bracket.md"
        unclosed.write_text("【" + "甲" * 2500, encoding="utf-8")
        manifest = pipeline.build_corpus(self.workspace, self.output, "fixed")
        self.assertTrue(manifest["validation_passed"])
        connection = self.open_database()
        boundary = connection.execute(
            "SELECT source_id FROM sources WHERE relpath LIKE '%/boundary.md'"
        ).fetchone()[0]
        second = connection.execute(
            "SELECT * FROM chunks WHERE source_id=? AND start_cp=500", (boundary,)
        ).fetchone()
        self.assertIsNotNone(second)
        self.assertLessEqual(second["reading_start_cp"], second["start_cp"])
        self.assertGreaterEqual(second["reading_end_cp"], second["end_cp"])
        open_source = connection.execute(
            "SELECT source_id FROM sources WHERE relpath LIKE '%/open-bracket.md'"
        ).fetchone()[0]
        later = connection.execute(
            "SELECT * FROM chunks WHERE source_id=? AND reading_start_cp>0", (open_source,)
        ).fetchall()
        self.assertTrue(later)
        for row in later:
            self.assertTrue(
                json.loads(row["flags_json"]).get("source_bracket_context_uncertain"),
                "an opening bracket before the window must not create false confidence",
            )

    def test_existing_output_is_never_overwritten(self):
        self.output.mkdir(parents=True)
        sentinel = self.output / "keep.txt"
        sentinel.write_bytes(b"preserve this output")
        before = self.source_bytes()
        with self.assertRaises(FileExistsError):
            pipeline.build_corpus(self.workspace, self.output)
        self.assertEqual(sentinel.read_bytes(), b"preserve this output")
        self.assertEqual(set(self.output.iterdir()), {sentinel})
        self.assertEqual(before, self.source_bytes())

    def test_clean_release_is_default_and_keeps_mapping(self):
        raw = "## 卷一\n\n### 条甲\n\n正文。\n\n【补注。】\n\n续文。\n"
        source_path = self.wang / WANG_NAMES[0]
        source_path.write_bytes(raw.encode("utf-8"))
        before = self.source_bytes()
        manifest = pipeline.build_corpus(self.workspace, self.output)
        self.assertTrue(manifest["validation_passed"])
        self.assertEqual(manifest["segmentation_mode"], "structure-clean")
        self.assertEqual(before, self.source_bytes(), "building must preserve the input snapshot")
        connection = self.open_database()
        source = connection.execute(
            "SELECT * FROM sources WHERE relpath=?",
            (f"data/A-原著原典/{WANG_NAMES[0]}",),
        ).fetchone()
        self.assertEqual(source["raw_text"], raw)
        chunk = connection.execute(
            "SELECT * FROM chunks WHERE source_id=? AND role='entry' LIMIT 1",
            (source["source_id"],),
        ).fetchone()
        self.assertIsNotNone(chunk)
        mapping = json.loads(chunk["mapping_json"])
        self.assertEqual(
            pipeline.normalized_span_to_raw(mapping, 0, len(chunk["normalized_text"])),
            (chunk["start_cp"], chunk["end_cp"]),
        )

    def test_outside_project_and_source_outputs_are_rejected_without_side_effects(self):
        before = self.source_bytes()
        for output in [
            self.wang / "new-output", self.external / "高频" / "new-output",
            self.workspace / "research" / "new-output", Path(self.temp.name) / "elsewhere",
            self.project / ".." / "escaped-output",
        ]:
            with self.subTest(output=str(output)), self.assertRaises(ValueError):
                pipeline.build_corpus(self.workspace, output)
            self.assertFalse(output.exists())
        self.assertEqual(before, self.source_bytes())

    def test_source_symlink_cannot_pull_in_outside_files(self):
        outside = Path(self.temp.name) / "outside.md"
        outside.write_text("not permitted", encoding="utf-8")
        link = self.external / "高频" / "linked.md"
        try:
            link.symlink_to(outside)
        except OSError as error:
            self.skipTest(f"symlinks unavailable on this host: {error}")
        with self.assertRaises((ValueError, OSError)):
            pipeline.iter_source_paths(self.workspace)

    @unittest.skipUnless(os.name == "nt", "Windows junction-specific boundary")
    def test_source_tier_junction_cannot_relabel_an_evaluation_directory(self):
        pwsh = shutil.which("pwsh.exe")
        if not pwsh:
            self.skipTest("PowerShell 7 is unavailable for a native temporary junction fixture")
        forbidden = self.workspace / "data" / "0-当前阅读" / "annotation"
        forbidden.mkdir(parents=True)
        marker = forbidden / "synthetic-forbidden.md"
        marker.write_text("not an external source", encoding="utf-8")
        tier = self.external / "高频"
        tier.rmdir()  # Empty synthetic directory inside TemporaryDirectory only.
        quote = lambda value: "'" + str(value).replace("'", "''") + "'"
        command = (
            "$ErrorActionPreference='Stop'; New-Item -ItemType Junction -Path "
            + quote(tier) + " -Target " + quote(forbidden) + " | Out-Null"
        )
        completed = subprocess.run(
            [pwsh, "-NoProfile", "-NonInteractive", "-Command", command],
            capture_output=True, text=True, timeout=15,
        )
        if completed.returncode:
            self.skipTest(f"temporary junction creation unavailable: {completed.stderr}")
        self.assertTrue(tier.is_junction())
        with self.assertRaises((ValueError, OSError)):
            pipeline.iter_source_paths(self.workspace)
        self.assertEqual(marker.read_text(encoding="utf-8"), "not an external source")

    def test_output_symlink_parent_cannot_escape_project(self):
        outside = Path(self.temp.name) / "outside-output"
        outside.mkdir()
        link = self.project / "linked-output"
        try:
            link.symlink_to(outside, target_is_directory=True)
        except OSError as error:
            self.skipTest(f"symlinks unavailable on this host: {error}")
        with self.assertRaises(ValueError):
            pipeline.build_corpus(self.workspace, link / "release")
        self.assertEqual(list(outside.iterdir()), [])


if __name__ == "__main__":
    unittest.main()
