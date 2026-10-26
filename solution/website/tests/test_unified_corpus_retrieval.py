"""Focused tests for title/body modes and pre-ranking external-tier filters."""

from __future__ import annotations

import sqlite3
import sys
import tempfile
import unittest
import zlib
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPT_DIR))

import corpus_retrieval_bridge as original_bridge  # noqa: E402
import harness_corpus as external_bridge  # noqa: E402


class UnifiedCorpusRetrievalTests(unittest.TestCase):
    def make_original_db(self, path: Path):
        db = sqlite3.connect(path)
        db.executescript("""
            CREATE TABLE source_documents (
              source_document_id TEXT PRIMARY KEY, source_file TEXT, source_kind TEXT,
              canonical_status TEXT, work_key TEXT
            );
            CREATE TABLE passages (
              passage_id TEXT PRIMARY KEY, source_document_id TEXT, work_key TEXT,
              document_title TEXT, section_title TEXT, entry_title TEXT,
              local_ordinal INTEGER, md_line_start INTEGER, md_line_end INTEGER,
              raw_text TEXT, plain_text TEXT, normalized_text TEXT
            );
        """)
        db.execute("INSERT INTO source_documents VALUES (?,?,?,?,?)",
                   ("doc-1", "readings.md", "canonical", "canonical_active", "dushu_zazhi"))
        db.execute("INSERT INTO passages VALUES (?,?,?,?,?,?,?,?,?,?,?,?)", (
            "passage-title", "doc-1", "dushu_zazhi", "读书杂志_王念孙", "卷一", "第一条",
            1, 1, 2, "原典正文内容甲乙丙丁。", "原典正文内容甲乙丙丁。", "原典正文内容甲乙丙丁。",
        ))
        db.commit()
        db.close()
        return original_bridge.connect(path)

    def make_external_db(self, path: Path):
        db = sqlite3.connect(path)
        db.executescript(external_bridge.RUNTIME_SCHEMA_SQL)
        text = "甲乙丙丁戊己，供合成检索使用。"
        for index, collection in enumerate(external_bridge.COLLECTION_ORDER, start=1):
            source_id = f"source-{collection}"
            db.execute("""
                INSERT INTO sources VALUES (?,?,?,?,?,?,?,?,?)
            """, (
                source_id, collection, f"{collection}/fixture.md", f"测试书名-{collection}",
                f"sha-{index}", zlib.compress(text.encode("utf-8")), len(text), 1, 1,
            ))
            chunk_id = f"chunk-{collection}"
            db.execute("""
                INSERT INTO chunks VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
            """, (
                index, chunk_id, source_id, 1, 0, len(text), 0, len(text),
                1, 1, "body", "[]",
            ))
            db.execute("INSERT INTO chunk_fts(rowid, terms) VALUES (?,?)",
                       (index, external_bridge.search_terms(text)))
        db.commit()
        db.row_factory = sqlite3.Row
        return db

    def test_original_title_and_body_are_searched_in_the_selected_fields(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "original.sqlite3"
            db = self.make_original_db(path)
            try:
                title = original_bridge.retrieve(db, query="读书杂志", search_mode="title")
                body = original_bridge.retrieve(db, query="读书杂志", search_mode="body")
                unified = original_bridge.retrieve(db, query="读书杂志")
                self.assertEqual([item["passage_id"] for item in title["items"]], ["passage-title"])
                self.assertEqual(title["items"][0]["match_reason"], "篇目标题命中")
                self.assertEqual(body["items"], [])
                self.assertEqual([item["passage_id"] for item in unified["items"]], ["passage-title"])
                self.assertEqual(unified["search_mode"], "unified")
            finally:
                db.close()

    def test_external_tier_filter_applies_before_candidate_ranking(self):
        with tempfile.TemporaryDirectory() as directory:
            db = self.make_external_db(Path(directory) / "external.sqlite3")
            try:
                high_only = external_bridge.retrieve(db, {
                    "original_text": "甲乙丙丁戊己",
                    "collections": ["external_high"],
                })
                all_tiers = external_bridge.retrieve(db, {"original_text": "甲乙丙丁戊己"})
                self.assertEqual({item["collection"] for item in high_only["items"]}, {"external_high"})
                self.assertEqual(high_only["candidate_count"], 1)
                self.assertEqual({item["collection"] for item in all_tiers["items"]}, set(external_bridge.COLLECTION_ORDER))
            finally:
                db.close()

    def test_external_title_search_respects_selected_tiers_and_empty_scope(self):
        with tempfile.TemporaryDirectory() as directory:
            db = self.make_external_db(Path(directory) / "external.sqlite3")
            try:
                title_page = external_bridge.sources(db, {
                    "query": "测试书名",
                    "collections": ["external_mid"],
                    "limit": 10,
                })
                empty_page = external_bridge.sources(db, {"query": "测试书名", "collections": []})
                self.assertEqual([item["collection"] for item in title_page["items"]], ["external_mid"])
                self.assertEqual(empty_page["items"], [])
                self.assertEqual(empty_page["total"], 0)
            finally:
                db.close()


if __name__ == "__main__":
    unittest.main()
