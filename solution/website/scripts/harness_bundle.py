#!/usr/bin/env python3
"""One-time XZ transport for the verified external-classics runtime corpus.

Pack reads the existing runtime database only.  Unpack creates a fresh
database with the same schema and search tokenization as harness_corpus.py.
Neither command reads the original mapping database, annotations, or cases.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import lzma
import os
import sqlite3
import time
import zlib
from pathlib import Path

from harness_corpus import RUNTIME_SCHEMA_SQL, RETRIEVAL_ALGORITHM, search_terms


SITE = Path(__file__).resolve().parents[1]
DEFAULT_DB = SITE / "runtime-release/harness_corpus.sqlite3"
DEFAULT_BUNDLE = SITE / "runtime-bundle/harness_corpus.jsonl.xz"
FORMAT = "harness-corpus-transfer.v1"
ALLOWED_COLLECTIONS = {"external_high", "external_mid", "external_low"}
MAX_BUNDLE_BYTES = 90_000_000


def json_line(value) -> bytes:
    return (json.dumps(value, ensure_ascii=False, separators=(",", ":")) + "\n").encode("utf-8")


def source_id_for(relpath: str) -> str:
    return "src_" + hashlib.sha256(relpath.encode("utf-8")).hexdigest()


def chunk_id_for(source_id: str, digest: str, start: int, end: int) -> str:
    return "chk_" + hashlib.sha256(f"{source_id}:{digest}:{start}:{end}".encode("utf-8")).hexdigest()


def read_manifest(db_path: Path) -> dict:
    path = db_path.parent / "manifest.json"
    if not path.is_file():
        raise FileNotFoundError(f"Runtime manifest missing: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def pack(db_path: Path, output: Path, preset: int, max_bytes: int) -> dict:
    if not db_path.is_file():
        raise FileNotFoundError(db_path)
    if output.exists():
        raise FileExistsError(f"Refusing to overwrite bundle: {output}")
    partial = output.with_name(output.name + ".partial")
    if partial.exists():
        raise FileExistsError(f"Prior partial bundle retained: {partial}")
    manifest = read_manifest(db_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    started = time.perf_counter()
    db = sqlite3.connect(f"file:{db_path.resolve().as_posix()}?mode=ro", uri=True)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA query_only=ON")
    source_count = db.execute("SELECT count(*) FROM sources").fetchone()[0]
    chunk_count = db.execute("SELECT count(*) FROM chunks").fetchone()[0]
    if source_count != manifest.get("source_count") or chunk_count != manifest.get("chunk_count"):
        raise ValueError("Runtime counts differ from its manifest")
    if db.execute("SELECT count(*) FROM sources WHERE collection='wang'").fetchone()[0]:
        raise ValueError("Wang source found in external-only runtime")
    global_rowid = 0
    actual_sources = 0
    raw_jsonl_bytes = 0
    try:
        with partial.open("xb") as file:
            with lzma.LZMAFile(file, mode="wb", format=lzma.FORMAT_XZ,
                               check=lzma.CHECK_CRC64, preset=preset) as compressed:
                def write(value):
                    nonlocal raw_jsonl_bytes
                    data = json_line(value)
                    compressed.write(data)
                    raw_jsonl_bytes += len(data)

                write(["h", FORMAT, manifest["corpus_release"],
                       manifest.get("retrieval_algorithm", RETRIEVAL_ALGORITHM),
                       source_count, chunk_count])
                for source in db.execute("SELECT * FROM sources ORDER BY source_id"):
                    sid = source["source_id"]
                    if source["collection"] not in ALLOWED_COLLECTIONS:
                        raise ValueError(f"Unexpected collection: {source['collection']}")
                    if sid != source_id_for(source["relpath"]):
                        raise ValueError(f"Source ID is not derivable: {sid}")
                    raw = zlib.decompress(source["raw_zlib"]).decode("utf-8")
                    if len(raw) != source["codepoints"]:
                        raise ValueError(f"Raw length mismatch: {sid}")
                    write(["s", sid, source["collection"], source["relpath"],
                           source["title"], source["sha256"], source["codepoints"],
                           source["line_count"], source["chunk_count"], raw])
                    actual_sources += 1
                    ordinal = 0
                    for chunk in db.execute(
                        "SELECT * FROM chunks WHERE source_id=? ORDER BY ordinal", (sid,)
                    ):
                        ordinal += 1
                        global_rowid += 1
                        start, end = chunk["start_cp"], chunk["end_cp"]
                        if (chunk["source_id"] != sid or chunk["rowid"] != global_rowid
                                or chunk["ordinal"] != ordinal
                                or chunk["chunk_id"] != chunk_id_for(sid, source["sha256"], start, end)):
                            raise ValueError(f"Chunk ID or order is not derivable: {chunk['chunk_id']}")
                        rs, re = chunk["reading_start_cp"], chunk["reading_end_cp"]
                        if not (0 <= rs <= start < end <= re <= len(raw)):
                            raise ValueError(f"Invalid source coordinates: {chunk['chunk_id']}")
                        headings = json.loads(chunk["heading_path"])
                        if json.dumps(headings, ensure_ascii=False, separators=(",", ":")) != chunk["heading_path"]:
                            raise ValueError(f"Heading path is not canonical: {chunk['chunk_id']}")
                        write(["c", start, end, rs, re, chunk["line_start"],
                               chunk["line_end"], chunk["role"], headings])
                    if ordinal != source["chunk_count"]:
                        raise ValueError(f"Chunk count mismatch: {sid}")
                    if actual_sources % 25 == 0:
                        print(json.dumps({"packed_sources": actual_sources,
                                          "chunks": global_rowid}), flush=True)
            file.flush()
            os.fsync(file.fileno())
        if (actual_sources, global_rowid) != (source_count, chunk_count):
            raise ValueError("Bundle count mismatch")
        bundle_bytes = partial.stat().st_size
        if bundle_bytes >= max_bytes:
            raise ValueError(f"Bundle {bundle_bytes} bytes exceeds limit {max_bytes}; partial retained")
        partial.rename(output)
        return {"bundle": str(output.resolve()), "bundle_bytes": bundle_bytes,
                "source_count": actual_sources, "chunk_count": global_rowid,
                "raw_jsonl_bytes": raw_jsonl_bytes,
                "seconds": round(time.perf_counter() - started, 2)}
    finally:
        db.close()


def next_record(stream):
    line = stream.readline()
    if not line:
        raise ValueError("Bundle ended before declared counts")
    value = json.loads(line)
    if not isinstance(value, list):
        raise ValueError("Invalid bundle record")
    return value


def unpack(bundle: Path, output_dir: Path) -> dict:
    if not bundle.is_file():
        raise FileNotFoundError(bundle)
    if output_dir.exists():
        raise FileExistsError(f"Refusing to replace existing output: {output_dir}")
    output_dir.mkdir(parents=True)
    target = output_dir / "harness_corpus.sqlite3"
    started = time.perf_counter()
    db = sqlite3.connect(target)
    db.execute("PRAGMA journal_mode=DELETE")
    db.execute("PRAGMA synchronous=NORMAL")
    db.executescript(RUNTIME_SCHEMA_SQL)
    source_count = chunk_count = 0
    previous_sid = ""
    try:
        with lzma.open(bundle, "rb") as stream:
            header = next_record(stream)
            if len(header) != 6 or header[0:2] != ["h", FORMAT]:
                raise ValueError("Unsupported bundle format")
            _, _, corpus_release, algorithm, expected_sources, expected_chunks = header
            if algorithm != RETRIEVAL_ALGORITHM:
                raise ValueError(f"Search algorithm mismatch: {algorithm}")
            if not (0 < expected_sources <= 100000 and 0 < expected_chunks <= 10000000):
                raise ValueError("Invalid declared corpus counts")
            db.execute("BEGIN")
            for _ in range(expected_sources):
                source = next_record(stream)
                if len(source) != 10 or source[0] != "s":
                    raise ValueError("Expected source record")
                (_, sid, collection, relpath, title, digest, codepoints,
                 line_count, source_chunks, raw) = source
                if (collection not in ALLOWED_COLLECTIONS or sid != source_id_for(relpath)
                        or sid <= previous_sid or len(raw) != codepoints
                        or not isinstance(source_chunks, int) or source_chunks < 1):
                    raise ValueError(f"Invalid source record: {sid}")
                previous_sid = sid
                db.execute("INSERT INTO sources VALUES (?,?,?,?,?,?,?,?,?)",
                           (sid, collection, relpath, title, digest,
                            zlib.compress(raw.encode("utf-8"), 6), codepoints,
                            line_count, source_chunks))
                source_count += 1
                for ordinal in range(1, source_chunks + 1):
                    chunk = next_record(stream)
                    if len(chunk) != 9 or chunk[0] != "c":
                        raise ValueError(f"Expected chunk record: {sid}:{ordinal}")
                    (_, start, end, rs, re, line_start, line_end,
                     role, headings) = chunk
                    if not (0 <= rs <= start < end <= re <= codepoints):
                        raise ValueError(f"Invalid chunk coordinates: {sid}:{ordinal}")
                    chunk_count += 1
                    cid = chunk_id_for(sid, digest, start, end)
                    heading_path = json.dumps(headings, ensure_ascii=False, separators=(",", ":"))
                    db.execute("INSERT INTO chunks VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                               (chunk_count, cid, sid, ordinal, start, end, rs, re,
                                line_start, line_end, role, heading_path))
                    db.execute("INSERT INTO chunk_fts(rowid,terms) VALUES (?,?)",
                               (chunk_count, search_terms(raw[start:end])))
                if source_count % 25 == 0:
                    print(json.dumps({"unpacked_sources": source_count,
                                      "chunks": chunk_count}), flush=True)
            if stream.readline():
                raise ValueError("Bundle contains extra records")
        if (source_count, chunk_count) != (expected_sources, expected_chunks):
            raise ValueError("Bundle count mismatch")
        db.commit()
        db.execute("INSERT INTO chunk_fts(chunk_fts) VALUES ('optimize')")
        db.commit()
        db.execute("VACUUM")
        if db.execute("SELECT count(*) FROM chunk_fts").fetchone()[0] != chunk_count:
            raise ValueError("FTS count mismatch")
        db.execute("INSERT INTO chunk_fts(chunk_fts) VALUES ('integrity-check')")
        db.commit()
        if db.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            raise ValueError("SQLite integrity check failed")
        if db.execute("PRAGMA foreign_key_check").fetchall():
            raise ValueError("Foreign-key check failed")
        manifest = {"corpus_release": corpus_release,
                    "retrieval_algorithm": algorithm,
                    "source_count": source_count, "chunk_count": chunk_count,
                    "runtime_bytes": target.stat().st_size,
                    "bundle_bytes": bundle.stat().st_size,
                    "build_seconds": round(time.perf_counter() - started, 2),
                    "scope": "external_high, external_mid, external_low only",
                    "method": "reconstructed from one-time transport bundle"}
        (output_dir / "manifest.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        return {"runtime": str(target.resolve()), **manifest}
    finally:
        db.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    pack_parser = subparsers.add_parser("pack")
    pack_parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    pack_parser.add_argument("--output", type=Path, default=DEFAULT_BUNDLE)
    pack_parser.add_argument("--preset", type=int, choices=range(0, 10), default=9)
    pack_parser.add_argument("--max-bytes", type=int, default=MAX_BUNDLE_BYTES)
    unpack_parser = subparsers.add_parser("unpack")
    unpack_parser.add_argument("--bundle", type=Path, default=DEFAULT_BUNDLE)
    unpack_parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.command == "pack":
        result = pack(args.db, args.output, args.preset, args.max_bytes)
    else:
        result = unpack(args.bundle, args.output)
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
