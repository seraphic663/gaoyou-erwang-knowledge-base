"""Loopback-only, read-only browser for independent corpus releases."""
from __future__ import annotations

import argparse
import hashlib
import json
import mimetypes
import sqlite3
from functools import lru_cache
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

PROJECT = Path(__file__).resolve().parent
WEB = PROJECT / "web"


def decode_json(value, fallback=None):
    if value is None:
        return fallback
    if isinstance(value, (dict, list)):
        return value
    return json.loads(value)


class CorpusReader:
    def __init__(self, directory: Path):
        self.directory = directory.resolve()
        self.database = self.directory / "corpus.sqlite3"
        if not self.database.is_file():
            raise ValueError(f"No corpus.sqlite3 in {self.directory}")
        self.manifest = self.read_report("manifest.json")
        self.quality = self.read_report("quality.json")
        self.chunk_columns = {row["name"] for row in self.rows("PRAGMA table_info(chunks)")}

    def read_report(self, name):
        path = self.directory / name
        return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}

    def connect(self):
        conn = sqlite3.connect(self.database.as_uri() + "?mode=ro", uri=True)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA query_only=ON")
        return conn

    def rows(self, sql, params=()):
        conn = self.connect()
        try:
            return [dict(row) for row in conn.execute(sql, params)]
        finally:
            conn.close()

    def one(self, sql, params=()):
        rows = self.rows(sql, params)
        return rows[0] if rows else None

    @staticmethod
    def source_view(row):
        if row is None:
            raise LookupError("来源不存在")
        row = dict(row)
        row.pop("raw_text", None)
        row["flags"] = decode_json(row.pop("flags_json", None), {})
        row["metadata"] = decode_json(row.pop("metadata_json", None), {})
        return row

    def source(self, source_id):
        return self.source_view(self.one(
            "SELECT source_id, collection, relpath, title, sha256, encoding, "
            "body_start, body_end, codepoints, byte_size, line_count, metadata_json, flags_json, "
            "(SELECT count(*) FROM chunks c WHERE c.source_id=s.source_id) AS chunk_count "
            "FROM sources s WHERE source_id=?", (source_id,)))

    @lru_cache(maxsize=3)
    def raw(self, source_id):
        row = self.one("SELECT raw_text FROM sources WHERE source_id=?", (source_id,))
        if row is None:
            raise LookupError("来源不存在")
        return row["raw_text"]

    def sources(self, query, collection, page, page_size):
        conditions, params = [], []
        if query:
            escaped = query.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
            conditions.append("(title LIKE ? ESCAPE '\\' OR relpath LIKE ? ESCAPE '\\')")
            params.extend([f"%{escaped}%", f"%{escaped}%"])
        if collection:
            if collection == "external":
                conditions.append("collection <> 'wang'")
            else:
                conditions.append("collection = ?")
                params.append(collection)
        where = " WHERE " + " AND ".join(conditions) if conditions else ""
        total = self.one("SELECT count(*) AS n FROM sources" + where, params)["n"]
        rows = self.rows(
            "SELECT source_id, collection, relpath, title, sha256, encoding, body_start, "
            "body_end, codepoints, byte_size, line_count, metadata_json, flags_json, "
            "(SELECT count(*) FROM chunks c WHERE c.source_id=s.source_id) AS chunk_count "
            "FROM sources s" + where + " ORDER BY collection, title, relpath LIMIT ? OFFSET ?",
            [*params, page_size, (page - 1) * page_size])
        return {"items": [self.source_view(r) for r in rows], "total": total,
                "page": page, "page_size": page_size}

    def chunks(self, source_id, page, page_size):
        self.source(source_id)
        total = self.one("SELECT count(*) AS n FROM chunks WHERE source_id=?", (source_id,))["n"]
        rows = self.rows(
            "SELECT chunk_id, source_id, ordinal, start_cp, end_cp, line_start, line_end, "
            "role, flags_json" + (", structure_json" if "structure_json" in self.chunk_columns else "") +
            " FROM chunks WHERE source_id=? ORDER BY ordinal LIMIT ? OFFSET ?",
            (source_id, page_size, (page - 1) * page_size))
        raw = self.raw(source_id)
        for row in rows:
            row["flags"] = decode_json(row.pop("flags_json"), {})
            row["structure"] = decode_json(row.pop("structure_json", None), {})
            row["preview"] = raw[row["start_cp"]:min(row["end_cp"], row["start_cp"] + 140)]
        return {"items": rows, "total": total, "page": page, "page_size": page_size}

    def chunk(self, chunk_id):
        row = self.one("SELECT * FROM chunks WHERE chunk_id=?", (chunk_id,))
        if row is None:
            raise LookupError("切片不存在")
        raw = self.raw(row["source_id"])
        row["raw_text"] = raw[row["start_cp"]:row["end_cp"]]
        row["reading_text"] = raw[row["reading_start_cp"]:row["reading_end_cp"]]
        row["flags"] = decode_json(row.pop("flags_json"), {})
        row["structure"] = decode_json(row.pop("structure_json", None), {})
        mapping = decode_json(row.pop("mapping_json"), [])
        keys = ["norm_start", "norm_end", "raw_start", "raw_end", "kind"]
        row["mapping"] = [dict(zip(keys, item)) if isinstance(item, list) else item for item in mapping]
        row["source"] = self.source(row["source_id"])
        # This verifies reconstruction, not semantic completeness or scholarly approval.
        row["span_verified"] = len(row["raw_text"]) == row["end_cp"] - row["start_cp"]
        row["reading_notice"] = "通用边界扩展；不保证整条论证完整，角色仍待核。"
        return row

    def summary(self):
        source_stats = self.one(
            "SELECT count(*) AS sources, sum(codepoints) AS codepoints, sum(byte_size) AS byte_size FROM sources")
        source_stats["chunks"] = self.one("SELECT count(*) AS n FROM chunks")["n"]
        source_stats["collections"] = {
            r["collection"]: r["n"] for r in self.rows(
                "SELECT collection,count(*) AS n FROM sources GROUP BY collection")}
        source_stats["quality"] = self.quality
        source_stats["build"] = self.manifest
        source_stats["mode"] = "local_read_only_review"
        source_stats["notice"] = "结构校验不等于学术审定。本页面没有检索效果或AI成绩。"
        return source_stats

    def quality_view(self):
        # Pick documents using source identity, not task titles, known answers or case IDs.
        rows = self.rows("SELECT source_id,title,collection FROM sources")
        rows.sort(key=lambda r: hashlib.sha256(r["source_id"].encode()).hexdigest())
        chosen = []
        for collection in sorted({r["collection"] for r in rows}):
            chosen.extend([r for r in rows if r["collection"] == collection][:3])
        samples = []
        for source in chosen:
            count = self.one("SELECT count(*) AS n FROM chunks WHERE source_id=?", (source["source_id"],))["n"]
            if not count:
                continue
            offset = int(hashlib.sha256(source["source_id"].encode()).hexdigest()[:12], 16) % count
            item = self.one(
                "SELECT chunk_id,flags_json FROM chunks WHERE source_id=? ORDER BY ordinal LIMIT 1 OFFSET ?",
                (source["source_id"], offset))
            samples.append({**source, "chunk_id": item["chunk_id"],
                            "flags": decode_json(item["flags_json"], {}),
                            "reason": "按来源ID哈希分层取样；不读取案例清单，不按效果选优"})
        integrity_keys = ["checked_sources", "source_count_discovered", "failed_source_count",
                          "source_hash_mismatches", "raw_hash_errors", "source_coordinate_errors"]
        return {"report": self.quality, "samples": samples,
                "source_integrity": {key: self.quality.get(key) for key in integrity_keys},
                "notice": "这些是结构审阅样本，不是独立盲测题或语义质量证明。"}


def load_comparison(path: Path):
    """Load one optional, local comparison file without changing either release."""
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or not isinstance(data.get("items"), list):
        raise ValueError("对比文件须为含 items 列表的 JSON 对象")
    if data.get("schema") == "threeway.v1" and any(
        not isinstance(item, dict) or not isinstance(item.get("methods"), dict)
        or set(item["methods"]) != {"baseline", "v2", "v3"}
        for item in data["items"]
    ):
        raise ValueError("三方对比每项须包含 baseline、v2、v3")
    return data


def make_handler(reader: CorpusReader, comparison=None):
    class Handler(BaseHTTPRequestHandler):
        def send_bytes(self, status, body, content_type):
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Content-Security-Policy", "default-src 'self'; style-src 'self'; script-src 'self'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'")
            self.end_headers()
            self.wfile.write(body)

        def send_json(self, status, value):
            self.send_bytes(status, json.dumps(value, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")

        def do_POST(self):
            self.send_json(405, {"error": "只读审阅服务不接受写入"})

        def do_GET(self):
            parsed = urlsplit(self.path)
            args = parse_qs(parsed.query)

            def arg(name, default=""):
                value = args.get(name, [default])[0]
                if len(value) > 256:
                    raise ValueError("参数过长")
                return value

            def integer(name, default, low, high):
                value = int(arg(name, str(default)))
                if not low <= value <= high:
                    raise ValueError(f"{name} 超出允许范围")
                return value

            try:
                path = parsed.path
                if path == "/api/summary":
                    result = reader.summary()
                elif path == "/api/quality":
                    result = reader.quality_view()
                elif path == "/api/comparison":
                    if comparison is None:
                        raise LookupError("启动服务时未指定对比文件")
                    result = comparison
                elif path == "/api/sources":
                    result = reader.sources(arg("q"), arg("collection"), integer("page", 1, 1, 100000), integer("page_size", 30, 1, 100))
                elif path == "/api/source":
                    result = reader.source(arg("id"))
                elif path == "/api/chunks":
                    result = reader.chunks(arg("source_id"), integer("page", 1, 1, 1000000), integer("page_size", 20, 1, 100))
                elif path == "/api/chunk":
                    result = reader.chunk(arg("id"))
                elif path == "/api/span":
                    source_id = arg("source_id")
                    raw = reader.raw(source_id)
                    start = integer("start", 0, 0, len(raw))
                    end = integer("end", min(len(raw), start + 1200), start, len(raw))
                    if end - start > 12000:
                        raise ValueError("一次最多读取12000个codepoints")
                    result = {"source_id": source_id, "start_cp": start, "end_cp": end, "raw_text": raw[start:end]}
                else:
                    assets = {"/": "index.html", "/index.html": "index.html", "/app.js": "app.js", "/styles.css": "styles.css", "/comparison.css": "comparison.css"}
                    name = assets.get(path)
                    if name is None or not (WEB / name).is_file():
                        raise LookupError("页面不存在")
                    body = (WEB / name).read_bytes()
                    mime = mimetypes.guess_type(name)[0] or "application/octet-stream"
                    self.send_bytes(200, body, mime + "; charset=utf-8")
                    return
                self.send_json(200, result)
            except (ValueError, TypeError) as error:
                self.send_json(400, {"error": str(error)})
            except LookupError as error:
                self.send_json(404, {"error": str(error)})
            except (BrokenPipeError, ConnectionResetError):
                pass
            except Exception:
                self.send_json(500, {"error": "读取失败，请检查本地服务日志与发布包"})
                raise

    return Handler


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", type=Path, required=True, help="独立标准化发布目录")
    parser.add_argument("--comparison", type=Path, help="可选的本地新旧切分对比 JSON")
    parser.add_argument("--port", type=int, default=3266)
    args = parser.parse_args()
    comparison = load_comparison(args.comparison) if args.comparison else None
    server = ThreadingHTTPServer(("127.0.0.1", args.port), make_handler(CorpusReader(args.data), comparison))
    print(f"READY http://127.0.0.1:{args.port}/ | read-only | {args.data.resolve()}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
