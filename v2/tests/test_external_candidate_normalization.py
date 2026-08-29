from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT / "v2" / "scripts"))

from external_text_normalization import (  # noqa: E402
    compact_for_match,
    normalized_contiguous_match,
    strip_wikitext,
)
from reconcile_external_public_matches import update_registry  # noqa: E402
from erwang_v2.database import open_database  # noqa: E402


class ExternalCandidateNormalizationTest(unittest.TestCase):
    def test_simplified_quote_matches_traditional_public_text(self) -> None:
        self.assertEqual(compact_for_match("温润而泽，仁也；缜密以栗，知也"), "溫潤而澤仁也縝密以栗知也")
        matched, start, end = normalized_contiguous_match(
            "{{ProperNoun|孔}}子曰：『溫潤而澤，仁也；縝密以栗，知也。』",
            "温润而泽，仁也；缜密以栗，知也",
        )
        self.assertTrue(matched)
        self.assertIsInstance(start, int)
        self.assertGreater(end, start)

    def test_wikitext_markup_does_not_break_contiguous_locating(self) -> None:
        raw = "{{ProperNoun|李}}將軍悛悛如鄙人，口不能道辭。{{SKnotes|音注}}"
        self.assertIn("李將軍悛悛如鄙人", strip_wikitext(raw))
        matched, _, _ = normalized_contiguous_match(
            raw,
            "李将军悛悛如鄙人，口不能道辞。",
        )
        self.assertTrue(matched)

    def test_left_biography_quote_matches_traditional_public_text(self) -> None:
        matched, start, end = normalized_contiguous_match(
            "公果自言，公以告臧孫，臧孫以難。告郈孫，郈孫以可，勸。",
            "公以告臧孙，臧孙以难。告郈孙，郈孙以可，劝",
        )
        self.assertTrue(matched)
        self.assertIsInstance(start, int)
        self.assertGreater(end, start)

    def test_ellipsis_is_not_called_contiguous(self) -> None:
        matched, start, end = normalized_contiguous_match(
            "治世之音安以樂，其政和。亂世之音怨以怒，其政乖。亡國之音哀以思，其民困。",
            "治世之音安以乐，乱世之音怨以怒，亡国之音哀以思",
        )
        self.assertFalse(matched)
        self.assertIsNone(start)
        self.assertIsNone(end)

    def test_registry_metadata_is_updated_for_every_candidate_source(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            database_path = root / "annotation_v2.db"
            manifest_path = root / "external_public_candidate_manifest.json"
            with open_database(database_path) as connection:
                connection.execute(
                    """
                    INSERT INTO external_source_registry(
                        external_source_id, cited_work, normalized_work, source_kind,
                        status, metadata_json, created_at, updated_at
                    ) VALUES ('external:test-source', '《测试典籍》', '测试典籍',
                              'external_citation', 'pending', '{}', 'now', 'now')
                    """
                )
                connection.commit()
            manifest_path.write_text("{}", encoding="utf-8")
            update_registry(
                database_path,
                manifest_path,
                {
                    "entries": [
                        {
                            "external_source_id": "external:test-source",
                            "status": "candidate_found",
                            "candidates": [{"page_title": "测试典籍/卷一"}],
                        }
                    ],
                },
            )
            with open_database(database_path) as connection:
                row = connection.execute(
                    "SELECT status, source_file, metadata_json "
                    "FROM external_source_registry WHERE external_source_id='external:test-source'"
                ).fetchone()
            metadata = json.loads(row["metadata_json"])
            self.assertEqual(row["status"], "registered")
            self.assertTrue(row["source_file"])
            self.assertEqual(metadata["candidate_status"], "public_transcription_candidate")
            self.assertFalse(metadata["canonical_verified"])


if __name__ == "__main__":
    unittest.main()
