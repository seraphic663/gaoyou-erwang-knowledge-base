#!/usr/bin/env python3
"""Build a separate, external-classics-only runtime corpus.

The input release is opened read-only.  No evaluation, case, annotation, or
Wang collection is consulted.  The output directory must not exist already.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
import time
import zlib
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "solution/website/scripts"))
from harness_corpus import RUNTIME_SCHEMA_SQL, search_terms  # noqa: E402

DEFAULT_INPUT = ROOT / "solution/corpus-standardization/generated/release-20261025-small-clean/corpus.sqlite3"
DEFAULT_OUTPUT = ROOT / "solution/website/runtime-release"


def build(input_path: Path, output_dir: Path) -> dict:
    if output_dir.exists():
        raise FileExistsError(f"Refusing to replace existing output: {output_dir}")
    if not input_path.is_file():
        raise FileNotFoundError(input_path)
    output_dir.mkdir(parents=True)
    target = output_dir / "harness_corpus.sqlite3"
    started = time.perf_counter()
    source = sqlite3.connect(f"file:{input_path.resolve().as_posix()}?mode=ro", uri=True)
    source.execute("PRAGMA query_only=ON")
    dest = sqlite3.connect(target)
    dest.execute("PRAGMA journal_mode=DELETE")
    dest.execute("PRAGMA synchronous=NORMAL")
    dest.executescript(RUNTIME_SCHEMA_SQL)
    source_rows = source.execute("""
        SELECT s.source_id,s.collection,s.relpath,s.title,s.sha256,s.raw_text,
               s.codepoints,s.line_count,
               (SELECT count(*) FROM chunks c WHERE c.source_id=s.source_id)
        FROM sources s WHERE s.collection != 'wang' ORDER BY s.source_id
    """)
    source_count = 0
    chunk_count = 0
    rowid = 0
    try:
        dest.execute("BEGIN")
        for source_row in source_rows:
            (source_id, collection, relpath, title, sha256, raw_text,
             codepoints, line_count, count) = source_row
            if collection not in {"external_high", "external_mid", "external_low"}:
                raise ValueError(f"Unexpected collection: {collection}")
            if len(raw_text) != codepoints:
                raise ValueError(f"Source length mismatch: {source_id}")
            dest.execute(
                "INSERT INTO sources VALUES (?,?,?,?,?,?,?,?,?)",
                (source_id, collection, relpath, title, sha256,
                 zlib.compress(raw_text.encode("utf-8"), 6), codepoints,
                 line_count, count),
            )
            source_count += 1
            for chunk in source.execute("""
                SELECT chunk_id,ordinal,start_cp,end_cp,reading_start_cp,
                       reading_end_cp,line_start,line_end,role,structure_json,
                       normalized_text
                FROM chunks WHERE source_id=? ORDER BY ordinal
            """, (source_id,)):
                (chunk_id, ordinal, start_cp, end_cp, reading_start_cp,
                 reading_end_cp, line_start, line_end, role, structure_json,
                 normalized_text) = chunk
                if not (0 <= reading_start_cp <= start_cp < end_cp <= reading_end_cp <= codepoints):
                    raise ValueError(f"Invalid chunk coordinates: {chunk_id}")
                heading_path = json.dumps(
                    json.loads(structure_json).get("heading_path", []),
                    ensure_ascii=False, separators=(",", ":"),
                )
                rowid += 1
                dest.execute(
                    "INSERT INTO chunks VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                    (rowid, chunk_id, source_id, ordinal, start_cp, end_cp,
                     reading_start_cp, reading_end_cp, line_start, line_end,
                     role, heading_path),
                )
                dest.execute("INSERT INTO chunk_fts(rowid,terms) VALUES (?,?)",
                             (rowid, search_terms(normalized_text)))
                chunk_count += 1
            if chunk_count % 10000 < count:
                print(f"indexed {source_count} sources, {chunk_count} chunks", flush=True)
        dest.commit()
        dest.execute("INSERT INTO chunk_fts(chunk_fts) VALUES ('optimize')")
        dest.commit()
        dest.execute("VACUUM")
        actual_source_count = dest.execute("SELECT count(*) FROM sources").fetchone()[0]
        actual_chunk_count = dest.execute("SELECT count(*) FROM chunks").fetchone()[0]
        assert (actual_source_count, actual_chunk_count) == (source_count, chunk_count)
        assert dest.execute("SELECT count(*) FROM chunk_fts").fetchone()[0] == chunk_count
        dest.execute("INSERT INTO chunk_fts(chunk_fts) VALUES ('integrity-check')")
        dest.commit()
        assert dest.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        assert dest.execute("PRAGMA foreign_key_check").fetchall() == []
        assert dest.execute("SELECT count(*) FROM sources WHERE collection='wang'").fetchone()[0] == 0
        summary = {
            "input": str(input_path.resolve()), "source_count": source_count,
            "chunk_count": chunk_count, "runtime_bytes": target.stat().st_size,
            "build_seconds": round(time.perf_counter() - started, 2),
            "corpus_release": input_path.parent.name,
            "retrieval_algorithm": "nfkc_bigram_fts5_full_postings_idf_phrase_query_variants_v2",
            "scope": "external_high, external_mid, external_low only",
        }
        (output_dir / "manifest.json").write_text(
            json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        return summary
    finally:
        dest.close()
        source.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    print(json.dumps(build(args.input, args.output), ensure_ascii=False))


if __name__ == "__main__":
    main()
