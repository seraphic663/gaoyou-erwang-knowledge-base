"""Synthetic same-anchor three-way packaging and review; no project data is modified."""
import importlib.util
import json
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "evaluation"))
from prepare_threeway import prepare  # noqa: E402
from finalize_threeway import finalize  # noqa: E402

spec = importlib.util.spec_from_file_location("threeway_server", ROOT / "server.py")
server = importlib.util.module_from_spec(spec)
spec.loader.exec_module(server)


def release(folder, title, start, end, role):
    folder.mkdir()
    db = sqlite3.connect(folder / "corpus.sqlite3")
    db.executescript("""
        CREATE TABLE sources(source_id TEXT, relpath TEXT, title TEXT, raw_text TEXT, body_start INTEGER);
        CREATE TABLE chunks(chunk_id TEXT, source_id TEXT, start_cp INTEGER, end_cp INTEGER,
            reading_start_cp INTEGER, reading_end_cp INTEGER, role TEXT, structure_json TEXT);
    """)
    db.execute("INSERT INTO sources VALUES(?,?,?,?,?)", ("s", "book.md", title, "甲乙丙丁戊己庚辛", 0))
    structure = {"heading_path": [{"text": title}], "association_links": [
        {"at_cp": 3, "basis": "quote_explanation", "range_start_cp": 1,
         "range_end_cp": 7, "within_limit": False}],
        "association_continued_from_previous": "attached_note", "association_continues_next": None}
    db.execute("INSERT INTO chunks VALUES(?,?,?,?,?,?,?,?)", (
        title, "s", start, end, 0, 8, role, json.dumps(structure)))
    db.commit()
    db.close()


class ThreewayTests(unittest.TestCase):
    def test_packaging_anonymous_annotation_and_review(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            for method, title, start, end, role in (
                ("baseline", "旧题", 0, 6, "paragraph"),
                ("v2", "中题", 1, 5, "notes"),
                ("v3", "新题", 2, 4, "paratext")
            ):
                release(root / method, title, start, end, role)
            positions = root / "positions.json"
            positions.write_text(json.dumps({"items": [{"id": "p1", "path": "book.md", "anchor": 3,
                "collection": "wang", "form": "条目"}]}, ensure_ascii=False), encoding="utf-8")
            output = root / "run"
            self.assertEqual(prepare(positions, root / "baseline", root / "v2", root / "v3", output)["samples"], 1)
            blind = json.loads((output / "blind_packets.json").read_text(encoding="utf-8"))
            key = json.loads((output / "method_key.json").read_text(encoding="utf-8"))["p1"]
            data = server.load_comparison(output / "comparison.json")
            self.assertEqual(data["schema"], "threeway.v1")
            item = data["items"][0]
            self.assertEqual(item["methods"]["v3"]["text"], "丙丁")
            self.assertEqual(item["methods"]["v3"]["source_title"], "新题")
            self.assertEqual(item["methods"]["v3"]["role"], "paratext")
            self.assertEqual(item["methods"]["v3"]["structure"]["association_links"][0]["basis"], "quote_explanation")
            self.assertEqual(item["methods"]["v3"]["structure"]["association_links"][0]["range_end_cp"], 7)
            self.assertEqual(item["source_context"], "甲乙丙丁戊己庚辛")
            self.assertEqual({blind["items"][0][label]["source_title"] for label in "ABC"}, {"旧题", "中题", "新题"})
            self.assertEqual({blind["items"][0][label]["role"] for label in "ABC"}, {"paragraph", "notes", "paratext"})
            self.assertNotIn("methods", blind["items"][0])
            self.assertNotIn("v3", json.dumps(blind, ensure_ascii=False))

            scores = {name: 0 for name in ("missing_heading", "cut_note", "detached_note", "unrelated", "cut_body")}
            labels = {name: label for label, name in key.items()}
            pairwise = {}
            for pair in ("A:B", "A:C", "B:C"):
                names = {key[label] for label in pair.split(":")}
                preferred = (labels["v3"] if names == {"v3", "v2"} else "tie"
                             if names == {"v3", "baseline"} else labels["v2"])
                pairwise[pair] = {"preferred": preferred, "reason": "按边界判断"}
            rating = {"id": "p1", "pairwise": pairwise}
            rating.update({label: {"scores": scores, "reason": "逐维说明"} for label in "ABC"})
            annotation_path = root / "annotations.json"
            annotation_path.write_text(json.dumps({"items": [rating]}, ensure_ascii=False), encoding="utf-8")
            review_path = root / "reviews.json"
            review_path.write_text(json.dumps({"items": [{"id": "p1", "status": "reviewed", "note": "边界复核",
                "annotation": {"methods": {"v3": {"scores": {"cut_body": 1}}},
                               "comparisons": {"baseline": {"verdict": "regressed", "reason": "原文复核"}}}}]},
                ensure_ascii=False), encoding="utf-8")
            summary = finalize(output, [annotation_path], review_path)
            result = server.load_comparison(output / "comparison.json")["items"][0]
            self.assertEqual(result["initial_annotation"]["comparisons"]["v2"]["verdict"], "improved")
            self.assertEqual(result["initial_annotation"]["comparisons"]["baseline"]["verdict"], "tied")
            self.assertEqual(result["annotation"]["comparisons"]["baseline"]["verdict"], "regressed")
            self.assertEqual(result["initial_annotation"]["methods"]["v3"]["scores"]["cut_body"], 0)
            self.assertEqual(result["annotation"]["methods"]["v3"]["scores"]["cut_body"], 1)
            self.assertEqual(summary["changed_verdict_ids"], {"v2": [], "baseline": ["p1"]})
            self.assertNotIn("pairwise", result["annotation"])
            self.assertEqual(len(result["initial_annotation"]["pairwise"]), 3)
            self.assertEqual(summary["lengths"], {
                "baseline": {"mean": 6, "median": 6, "min": 6, "max": 6},
                "v2": {"mean": 4, "median": 4, "min": 4, "max": 4},
                "v3": {"mean": 2, "median": 2, "min": 2, "max": 2},
            })

    def test_old_comparison_schema_still_loads(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "old.json"
            old = {"items": [{"old": {"text": "甲"}, "new": {"text": "甲乙"}}]}
            path.write_text(json.dumps(old, ensure_ascii=False), encoding="utf-8")
            self.assertEqual(server.load_comparison(path), old)


if __name__ == "__main__":
    unittest.main()
