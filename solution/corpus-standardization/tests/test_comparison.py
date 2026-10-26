"""Optional comparison endpoint and structure fields, using synthetic text only."""
import importlib.util
import json
import sqlite3
import tempfile
import threading
import unittest
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import urlopen


spec = importlib.util.spec_from_file_location("corpus_comparison_view", Path(__file__).resolve().parents[1] / "server.py")
viewer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(viewer)


class ComparisonTests(unittest.TestCase):
    def test_optional_file_and_structure(self):
        with tempfile.TemporaryDirectory() as temp:
            folder = Path(temp)
            conn = sqlite3.connect(folder / "corpus.sqlite3")
            conn.executescript("""
                CREATE TABLE sources(source_id TEXT,collection TEXT,relpath TEXT,title TEXT,
                    sha256 TEXT,encoding TEXT,raw_text TEXT,body_start INTEGER,body_end INTEGER,
                    codepoints INTEGER,byte_size INTEGER,line_count INTEGER,metadata_json TEXT,flags_json TEXT);
                CREATE TABLE chunks(chunk_id TEXT,source_id TEXT,ordinal INTEGER,start_cp INTEGER,
                    end_cp INTEGER,reading_start_cp INTEGER,reading_end_cp INTEGER,line_start INTEGER,
                    line_end INTEGER,role TEXT,flags_json TEXT,normalized_text TEXT,mapping_json TEXT,
                    structure_json TEXT);
            """)
            conn.execute("INSERT INTO sources VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                         ("s", "external_high", "synthetic.md", "示例", "", "utf-8", "甲乙丙", 0, 3, 3, 9, 1, "{}", "[]"))
            structure = {"heading_path": [{"text": "卷一", "start": 0, "end": 2}], "part_index": 1, "part_count": 2}
            conn.execute("INSERT INTO chunks VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                         ("c", "s", 1, 0, 2, 0, 3, 1, 1, "body", "[]", "甲乙", "[]", json.dumps(structure)))
            conn.commit()
            conn.close()

            comparison = {"summary": {}, "methodology": {}, "items": [{"id": "example", "path": "synthetic.md",
                          "anchor": 1, "source_context": "甲乙丙", "context_start": 0,
                          "old": {"start": 0, "end": 2, "text": "甲乙"},
                          "new": {"start": 0, "end": 3, "text": "甲乙丙"},
                          "annotation": {"verdict": "undetermined"}}]}
            path = folder / "comparison.json"
            path.write_text(json.dumps(comparison, ensure_ascii=False), encoding="utf-8")
            reader = viewer.CorpusReader(folder)
            self.assertEqual(reader.chunk("c")["structure"], structure)
            self.assertEqual(reader.chunks("s", 1, 20)["items"][0]["structure"], structure)
            loaded = viewer.load_comparison(path)
            server = viewer.ThreadingHTTPServer(("127.0.0.1", 0), viewer.make_handler(reader, loaded))
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                with urlopen(f"http://127.0.0.1:{server.server_port}/api/comparison") as response:
                    self.assertEqual(json.load(response), comparison)
                with urlopen(f"http://127.0.0.1:{server.server_port}/comparison.css") as response:
                    self.assertIn(b"comparison-layout", response.read())
            finally:
                server.shutdown()
                server.server_close()
                thread.join(3)

            missing = viewer.ThreadingHTTPServer(("127.0.0.1", 0), viewer.make_handler(reader))
            thread = threading.Thread(target=missing.serve_forever, daemon=True)
            thread.start()
            try:
                with self.assertRaises(HTTPError) as context:
                    urlopen(f"http://127.0.0.1:{missing.server_port}/api/comparison")
                self.assertEqual(context.exception.code, 404)
            finally:
                missing.shutdown()
                missing.server_close()
                thread.join(3)


if __name__ == "__main__":
    unittest.main()
