"""Read-only HTTP contract, isolated from the user's corpus and databases."""
import importlib.util
import json
import sqlite3
import tempfile
import threading
import unittest
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

spec = importlib.util.spec_from_file_location("corpus_viewer", Path(__file__).resolve().parents[1] / "server.py")
viewer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(viewer)


class ViewerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.folder = Path(cls.temp.name)
        cls.raw = "---\ntitle: 试验\n---\n甲𠀀□Ａ\r\n乙"
        start = cls.raw.index("甲")
        conn = sqlite3.connect(cls.folder / "corpus.sqlite3")
        conn.executescript("""
        CREATE TABLE sources(source_id TEXT,collection TEXT,relpath TEXT,title TEXT,
            sha256 TEXT,encoding TEXT,raw_text TEXT,body_start INTEGER,body_end INTEGER,
            codepoints INTEGER,byte_size INTEGER,line_count INTEGER,metadata_json TEXT,flags_json TEXT);
        CREATE TABLE chunks(chunk_id TEXT,source_id TEXT,ordinal INTEGER,start_cp INTEGER,
            end_cp INTEGER,reading_start_cp INTEGER,reading_end_cp INTEGER,line_start INTEGER,
            line_end INTEGER,role TEXT,flags_json TEXT,normalized_text TEXT,mapping_json TEXT);
        """)
        conn.execute("INSERT INTO sources VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)", (
            "s1", "external_high", "data/test.md", "试验", "testhash", "utf-8", cls.raw,
            start, len(cls.raw), len(cls.raw), len(cls.raw.encode()), 5, "{}", '["gap"]'))
        conn.execute("INSERT INTO chunks VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)", (
            "c1", "s1", 1, start, start + 4, start, len(cls.raw), 4, 4, "unknown", "[]", "甲𠀀□A",
            json.dumps([[0, 3, start, start + 3, "identity"], [3, 4, start + 3, start + 4, "nfkc"]])))
        conn.commit()
        conn.close()
        cls.db_before = (cls.folder / "corpus.sqlite3").read_bytes()
        cls.server = viewer.ThreadingHTTPServer(("127.0.0.1", 0), viewer.make_handler(viewer.CorpusReader(cls.folder)))
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.url = f"http://127.0.0.1:{cls.server.server_port}"

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(3)
        after = (cls.folder / "corpus.sqlite3").read_bytes()
        assert after == cls.db_before, "HTTP browsing must not mutate its release database"
        cls.temp.cleanup()

    def get(self, path):
        with urlopen(self.url + path, timeout=5) as response:
            return json.load(response)

    def test_codepoint_span_and_mapping(self):
        data = self.get("/api/chunk?id=c1")
        self.assertEqual(data["raw_text"], "甲𠀀□Ａ")
        self.assertEqual(data["end_cp"] - data["start_cp"], 4)
        self.assertEqual(data["mapping"][1]["kind"], "nfkc")
        self.assertTrue(data["span_verified"])
        self.assertNotIn("raw_text", data["source"])
        span = self.get(f'/api/span?source_id=s1&start={data["start_cp"]+1}&end={data["start_cp"]+2}')
        self.assertEqual(span["raw_text"], "𠀀")

    def test_source_query_is_literal_and_excludes_full_text(self):
        data = self.get("/api/sources?collection=external")
        self.assertEqual(data["total"], 1)
        self.assertNotIn("raw_text", data["items"][0])
        self.assertEqual(self.get("/api/sources?q=%25")["total"], 0)
        self.assertEqual(self.get("/api/sources?collection=wang")["total"], 0)

    def test_invalid_or_write_requests_rejected(self):
        for path, code in [("/api/source?id=missing", 404), ("/api/chunks?source_id=s1&page=-1", 400),
                           ("/api/span?source_id=s1&start=-1", 400), ("/../pipeline.py", 404),
                           ("/api/sources?page_size=99999", 400)]:
            with self.subTest(path=path), self.assertRaises(HTTPError) as context:
                self.get(path)
            self.assertEqual(context.exception.code, code)
        with self.assertRaises(HTTPError) as context:
            urlopen(Request(self.url + "/api/source", data=b"{}", method="POST"), timeout=5)
        self.assertEqual(context.exception.code, 405)


if __name__ == "__main__":
    unittest.main()
