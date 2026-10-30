#!/usr/bin/env python3
"""Read-only JSON bridge for the isolated external-classics runtime corpus."""

from __future__ import annotations

import argparse
import json
import math
import sqlite3
import sys
import unicodedata
import zlib
from collections import defaultdict
from pathlib import Path


DEFAULT_DB = Path(__file__).resolve().parents[1] / "runtime-release/harness_corpus.sqlite3"
ALLOWED_COLLECTIONS = {"external_high", "external_mid", "external_low"}
COLLECTION_ORDER = ("external_high", "external_mid", "external_low")
RETRIEVAL_ALGORITHM = "nfkc_bigram_fts5_full_postings_idf_phrase_query_variants_v2"
RETRIEVAL_LIMITATION = "仅作字面匹配线索；简繁转换由调用方提供原文、简体、繁体三路查询变体，部分混排、异体字及语义改写仍可能漏检，也不能证明证据准确。"
RUNTIME_SCHEMA_SQL = """
    CREATE TABLE sources (
      source_id TEXT PRIMARY KEY, collection TEXT NOT NULL,
      relpath TEXT NOT NULL UNIQUE, title TEXT NOT NULL, sha256 TEXT NOT NULL,
      raw_zlib BLOB NOT NULL, codepoints INTEGER NOT NULL,
      line_count INTEGER NOT NULL, chunk_count INTEGER NOT NULL
    );
    CREATE TABLE chunks (
      rowid INTEGER PRIMARY KEY, chunk_id TEXT NOT NULL UNIQUE,
      source_id TEXT NOT NULL REFERENCES sources(source_id),
      ordinal INTEGER NOT NULL, start_cp INTEGER NOT NULL,
      end_cp INTEGER NOT NULL, reading_start_cp INTEGER NOT NULL,
      reading_end_cp INTEGER NOT NULL, line_start INTEGER NOT NULL,
      line_end INTEGER NOT NULL, role TEXT NOT NULL,
      heading_path TEXT NOT NULL, UNIQUE(source_id, ordinal)
    );
    CREATE INDEX chunks_source_ordinal ON chunks(source_id, ordinal);
    CREATE VIRTUAL TABLE chunk_fts USING fts5(
      terms, content='', detail=none,
      tokenize='unicode61 remove_diacritics 0'
    );
"""


def connect(path: Path) -> sqlite3.Connection:
    if not path.is_file():
        raise FileNotFoundError(f"External corpus runtime database missing: {path}")
    db = sqlite3.connect(f"file:{path.resolve().as_posix()}?mode=ro", uri=True)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA query_only=ON")
    return db


def integer(value, default, minimum, maximum):
    try:
        number = int(value)
    except (ValueError, TypeError):
        number = default
    return max(minimum, min(number, maximum))


def selected_collections(payload):
    """Resolve the requested external tiers while keeping old single-tier calls compatible."""
    if "collections" in payload:
        values = payload.get("collections")
        if not isinstance(values, list) or any(not isinstance(value, str) for value in values):
            raise ValueError("collections_must_be_string_array")
        selected = set(values)
    else:
        single = str(payload.get("collection") or "")
        selected = {single} if single else set(COLLECTION_ORDER)
    invalid = selected - ALLOWED_COLLECTIONS
    if invalid:
        raise ValueError("invalid_collection")
    return [collection for collection in COLLECTION_ORDER if collection in selected]


def collection_placeholders(collections):
    return ",".join("?" for _ in collections)


def raw_source(db: sqlite3.Connection, source_id: str) -> tuple[sqlite3.Row, str]:
    row = db.execute("SELECT * FROM sources WHERE source_id=?", (source_id,)).fetchone()
    if row is None:
        raise ValueError("source_not_found")
    if row["collection"] not in ALLOWED_COLLECTIONS:
        raise ValueError("source_not_external")
    raw = zlib.decompress(row["raw_zlib"]).decode("utf-8")
    if len(raw) != row["codepoints"]:
        raise ValueError("runtime_source_length_mismatch")
    return row, raw


def heading_path(row: sqlite3.Row):
    try:
        return json.loads(row["heading_path"])
    except (ValueError, TypeError):
        return []


def chunk_record(row: sqlite3.Row, source: sqlite3.Row, raw: str, reading: bool = True):
    start, end = row["start_cp"], row["end_cp"]
    headings = heading_path(row)
    record = {
        "chunk_id": row["chunk_id"], "source_id": source["source_id"],
        "collection": source["collection"], "source_title": source["title"],
        "relpath": source["relpath"], "source_sha256": source["sha256"],
        "ordinal": row["ordinal"],
        "role": row["role"], "heading_path": headings,
        "chapter": " / ".join(str(item.get("title") or "") for item in headings if isinstance(item, dict)),
        "start_cp": start, "end_cp": end,
        "line_start": row["line_start"], "line_end": row["line_end"],
        "full_text": raw[start:end],
    }
    if reading:
        rs, re = row["reading_start_cp"], row["reading_end_cp"]
        record.update({
            "reading_start_cp": rs, "reading_end_cp": re,
            "reading_line_start": row["line_start"] - raw.count("\n", rs, start),
            "reading_line_end": row["line_end"] + raw.count("\n", end, re),
            "reading_text": raw[rs:re],
            "context_start_cp": rs, "context_end_cp": re,
            "context_text": raw[rs:re],
        })
    return record


def summary(db, _):
    collections = [dict(row) for row in db.execute("""
        SELECT s.collection, count(DISTINCT s.source_id) source_count,
               sum(s.chunk_count) chunk_count
        FROM sources s GROUP BY s.collection ORDER BY s.collection
    """)]
    counts = {
        "source_count": sum(row["source_count"] for row in collections),
        "chunk_count": sum(row["chunk_count"] for row in collections),
    }
    return {**counts, "counts": counts, "collections": collections}


def sources(db, payload):
    collections = selected_collections(payload)
    limit = integer(payload.get("limit"), 20, 1, 100)
    offset = integer(payload.get("offset"), 0, 0, 10_000_000)
    if not collections:
        return {"items": [], "total": 0, "limit": limit, "offset": offset,
                "collections": []}
    clauses = [f"collection IN ({collection_placeholders(collections)})"]
    params = list(collections)
    query = str(payload.get("query") or "").strip()
    if query:
        query_match = str(payload.get("query_match") or "any")
        if query_match not in {"all", "any"}:
            raise ValueError("invalid_query_match")
        terms = list(dict.fromkeys(normalized_runs(query))) or [query]
        escaped_terms = [term.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") for term in terms]
        if query_match == "all":
            title_clause = " AND ".join("title LIKE ? ESCAPE '\\'" for _ in terms)
            path_clause = " AND ".join("relpath LIKE ? ESCAPE '\\'" for _ in terms)
            clauses.append(f"(({title_clause}) OR ({path_clause}))")
            params.extend([f"%{term}%" for term in escaped_terms])
            params.extend([f"%{term}%" for term in escaped_terms])
        else:
            clauses.append("(" + " OR ".join(
                "(title LIKE ? ESCAPE '\\' OR relpath LIKE ? ESCAPE '\\')" for _ in terms
            ) + ")")
            for term in escaped_terms:
                params.extend([f"%{term}%", f"%{term}%"])
    where = " AND ".join(clauses)
    total = db.execute(f"SELECT count(*) FROM sources WHERE {where}", params).fetchone()[0]
    rows = db.execute(f"""
        SELECT source_id,collection,relpath,title,sha256,codepoints,line_count,chunk_count
        FROM sources WHERE {where} ORDER BY title,relpath LIMIT ? OFFSET ?
    """, (*params, limit, offset))
    return {"items": [dict(row) for row in rows], "total": total,
            "limit": limit, "offset": offset, "collections": collections}


def chunks(db, payload):
    source_id = str(payload.get("source_id") or "")
    source, raw = raw_source(db, source_id)
    limit = integer(payload.get("limit"), 20, 1, 100)
    offset = integer(payload.get("offset"), 0, 0, 10_000_000)
    rows = db.execute("""
        SELECT * FROM chunks WHERE source_id=? ORDER BY ordinal LIMIT ? OFFSET ?
    """, (source_id, limit, offset))
    items = []
    for row in rows:
        record = chunk_record(row, source, raw, reading=False)
        record["preview"] = record["full_text"][:160]
        del record["full_text"]
        items.append(record)
    return {"items": items, "total": source["chunk_count"],
            "limit": limit, "offset": offset, "source_id": source_id}


def chunk(db, payload):
    chunk_id = str(payload.get("chunk_id") or "")
    row = db.execute("SELECT * FROM chunks WHERE chunk_id=?", (chunk_id,)).fetchone()
    if row is None:
        raise ValueError("chunk_not_found")
    source, raw = raw_source(db, row["source_id"])
    return chunk_record(row, source, raw)


def normalized_runs(value: str):
    run = []
    for character in value:
        for part in unicodedata.normalize("NFKC", character):
            if part.isalnum():
                run.append(part.casefold())
            elif run:
                yield "".join(run)
                run.clear()
    if run:
        yield "".join(run)


def query_terms(value: str):
    terms = set()
    for run in normalized_runs(value):
        if len(run) < 2:
            continue
        if run.isascii():
            terms.add(run)
        else:
            terms.update(run[index:index + 2] for index in range(len(run) - 1))
    return terms


def query_match_groups(value: str, variants: list[str] | None = None):
    values = list(dict.fromkeys([value, *(variants or [])]))
    run_lists = [list(normalized_runs(candidate)) for candidate in values]
    groups = []
    for index in range(max((len(runs) for runs in run_lists), default=0)):
        alternatives = set()
        for runs in run_lists:
            if index >= len(runs):
                continue
            run = runs[index]
            if len(run) >= 2:
                alternatives.add(run)
        if alternatives:
            groups.append(alternatives)
    return groups


def query_group_index_terms(group):
    return set().union(*(query_terms(variant) for variant in group)) if group else set()


def search_terms(value: str) -> str:
    """The same FTS token stream used by the release builder and bundle importer."""
    return " ".join(sorted(query_terms(value)))


def query_phrases(value: str):
    phrases = set()
    for run in normalized_runs(value):
        if len(run) >= 4:
            phrases.update(run[index:index + 4] for index in range(len(run) - 3))
        if len(phrases) >= 1500:
            break
    return phrases


def fts_literal(term: str) -> str:
    return '"' + term.replace('"', '""') + '"'


def query_inputs(payload, original: str, question: str):
    supplied = payload.get("query_variants") or {}
    if not isinstance(supplied, dict):
        raise ValueError("query_variants_must_be_object")

    def collect(key: str, primary: str):
        values = supplied.get(key) or []
        if not isinstance(values, list) or any(not isinstance(value, str) for value in values):
            raise ValueError(f"query_variants_{key}_must_be_string_array")
        return list(dict.fromkeys([primary, *values[:6]]))

    return collect("original_text", original), collect("question", question)


def candidate_terms(db, originals: list[str], questions: list[str], collections: list[str], query_match="any"):
    original_terms = set().union(*(query_terms(value) for value in originals))
    question_terms = set().union(*(query_terms(value) for value in questions))
    primary_values = originals or questions
    required_groups = query_match_groups(primary_values[0], primary_values) if query_match == "all" and primary_values else []
    def sample(terms, maximum):
        ordered = sorted(terms)
        if len(ordered) <= maximum:
            return ordered
        return [ordered[index * len(ordered) // maximum] for index in range(maximum)]

    all_terms = set(sample(original_terms, 120)) | set(sample(question_terms, 40))
    if query_match == "all":
        for group in required_groups:
            ordered = sorted(query_group_index_terms(group))
            if len(ordered) <= 8:
                all_terms.update(ordered)
            else:
                all_terms.update(ordered[index * len(ordered) // 8] for index in range(8))
    if not collections:
        return []
    placeholders = collection_placeholders(collections)
    frequencies = []
    for term in sorted(all_terms):
        # A term absent from the runtime index cannot retrieve a passage.
        try:
            count = db.execute(f"""
                SELECT count(*) FROM chunk_fts
                JOIN chunks ON chunks.rowid=chunk_fts.rowid
                JOIN sources ON sources.source_id=chunks.source_id
                WHERE chunk_fts MATCH ? AND sources.collection IN ({placeholders})
            """, (fts_literal(term), *collections)).fetchone()[0]
        except sqlite3.OperationalError:
            continue
        if count:
            frequencies.append((count, 0 if term in original_terms else 1, term))
    frequencies.sort()
    if query_match == "all":
        selected = {}
        for group in required_groups:
            group_candidates = [item for item in frequencies if item[2] in query_group_index_terms(group)]
            if group_candidates:
                selected[group_candidates[0][2]] = group_candidates[0]
        for item in frequencies:
            if len(selected) >= 12:
                break
            selected.setdefault(item[2], item)
        return sorted(selected.values())
    return frequencies[:12]


def retrieve(db, payload):
    original = str(payload.get("original_text") or "")
    question = str(payload.get("question") or "")
    originals, questions = query_inputs(payload, original, question)
    query_match = str(payload.get("query_match") or "any")
    if query_match not in {"all", "any"}:
        raise ValueError("invalid_query_match")
    limit = integer(payload.get("limit"), 6, 1, 6)
    max_chars = integer(payload.get("max_chars"), 6000, 1, 6000)
    collections = selected_collections(payload)
    if not collections:
        return {"items": [], "context": "", "hit_count": 0,
                "candidate_count": 0, "reason": "no_collection_selected",
                "collections": []}
    collection_sql = collection_placeholders(collections)
    total_chunks = db.execute(f"""
        SELECT COALESCE(SUM(chunk_count),0) FROM sources
        WHERE collection IN ({collection_sql})
    """, collections).fetchone()[0]
    terms = candidate_terms(db, originals, questions, collections, query_match)
    if not any(value.strip() for value in [*originals, *questions]):
        return {"items": [], "context": "", "hit_count": 0, "reason": "empty_query"}
    if not terms:
        short = not any(query_terms(value) for value in [*originals, *questions])
        return {"items": [], "context": "", "hit_count": 0,
                "reason": "unsupported_short_query" if short else "no_match",
                "message": "单字查询暂不支持全文定位；请补充至少两个连续字符。" if short else "当前检索未找到匹配线索，不代表全库无相关材料。"}

    scores = defaultdict(float)
    matched = defaultdict(int)
    required_groups = (
        query_match_groups(original, originals) if original.strip()
        else query_match_groups(question, questions)
    )
    group_terms = [query_group_index_terms(group) for group in required_groups]
    term_groups = defaultdict(set)
    for group_index, index_terms in enumerate(group_terms):
        for term in index_terms:
            term_groups[term].add(group_index)
    matched_groups = defaultdict(set)
    for count, origin_rank, term in terms:
        weight = math.log1p(total_chunks / count) * (1.35 if origin_rank == 0 else 1.0)
        # Iterate the complete postings list. Capping by rowid loses later
        # books systematically when a common term occurs in many chunks.
        for row in db.execute(f"""
            SELECT chunk_fts.rowid FROM chunk_fts
            JOIN chunks ON chunks.rowid=chunk_fts.rowid
            JOIN sources ON sources.source_id=chunks.source_id
            WHERE chunk_fts MATCH ? AND sources.collection IN ({collection_sql})
        """, (fts_literal(term), *collections)):
            scores[row[0]] += weight
            matched[row[0]] += 1
            matched_groups[row[0]].update(term_groups.get(term, set()))
    if not scores:
        return {"items": [], "context": "", "hit_count": 0,
                "reason": "no_match", "message": "当前检索未找到匹配线索，不代表全库无相关材料。"}

    query_candidates = list(scores)
    if query_match == "all" and required_groups:
        query_candidates = [
            rid for rid in query_candidates
            if len(matched_groups[rid]) == len(required_groups)
        ]
    if not query_candidates:
        return {"items": [], "context": "", "hit_count": 0, "reason": "no_match",
                "candidate_count": 0, "candidate_count_capped": False,
                "collections": collections, "query_match": query_match,
                "message": "所有检索词未在同一段中命中。" if query_match == "all" else "未找到匹配线索。"}
    ranked_ids = sorted(query_candidates, key=lambda rid: (-matched[rid], -scores[rid], rid))[:500]
    phrase_inputs = [value for value in originals if value.strip()] or [value for value in questions if value.strip()]
    phrases = set().union(*(query_phrases(value) for value in phrase_inputs))
    placeholders = ",".join("?" for _ in ranked_ids)
    rows = {row["rowid"]: row for row in db.execute(
        f"SELECT * FROM chunks WHERE rowid IN ({placeholders})", ranked_ids)}
    by_source = defaultdict(list)
    for rid in ranked_ids:
        by_source[rows[rid]["source_id"]].append(rid)
    candidates = []
    for source_id, source_rids in by_source.items():
        source, raw = raw_source(db, source_id)
        for rid in source_rids:
            row = rows[rid]
            record = chunk_record(row, source, raw)
            # Prefer multiple independent lexical matches; never infer authority.
            chunk_runs = " ".join(normalized_runs(record["full_text"]))
            if query_match == "all" and required_groups and not all(
                any(variant in chunk_runs for variant in group) for group in required_groups
            ):
                continue
            matched_terms = sum(1 for _, _, term in terms if term in chunk_runs)
            phrase_hits = sum(1 for phrase in phrases if phrase in chunk_runs)
            lexical_score = scores[rid] + matched_terms * 4 + min(phrase_hits, 8) * 5
            record["match_cues"] = {"matched_index_terms": matched_terms,
                                    "matched_four_char_phrases": phrase_hits,
                                    "status": "lexical_match_only"}
            candidates.append((lexical_score, record))
        del raw, source
    if query_match == "all" and required_groups and not candidates:
        return {"items": [], "context": "", "hit_count": 0, "reason": "no_match",
                "candidate_count": 0, "candidate_count_capped": len(query_candidates) > 500,
                "collections": collections, "query_match": query_match,
                "message": "所有检索词未在同一段中命中。"}
    candidates.sort(key=lambda pair: (-pair[0], pair[1]["chunk_id"]))

    picked = []
    spans = []
    for _score, record in candidates:
        if len(picked) >= limit:
            break
        source_id = record["source_id"]
        start, end = record["context_start_cp"], record["context_end_cp"]
        if any(sid == source_id and start < prior_end and prior_start < end
               for sid, prior_start, prior_end, _ in spans):
            continue
        evidence_id = f"R{len(picked) + 1}"
        label = f"[{evidence_id}] {record['source_title']} | {record['relpath']} | 行{record['reading_line_start']}-{record['reading_line_end']} | 字符{start}-{end}\n"
        text = label + record["context_text"]
        proposed = sum(len(section) for _, _, _, section in spans) + len(text) + len(spans) * 2
        if proposed > max_chars:
            continue
        record["evidence_id"] = evidence_id
        record["evidence_text"] = record["context_text"]
        record["evidence_start_cp"] = record["context_start_cp"]
        record["evidence_end_cp"] = record["context_end_cp"]
        record["evidence_line_start"] = record["reading_line_start"]
        record["evidence_line_end"] = record["reading_line_end"]
        picked.append(record)
        spans.append((source_id, start, end, text))
    context = "\n\n".join(section for _, _, _, section in spans)
    return {"items": picked, "context": context, "hit_count": len(picked),
            "reason": "matched" if picked else "context_budget_too_small",
            "candidate_count": len(candidates), "candidate_count_capped": len(query_candidates) > 500,
            "collections": collections,
            "query_match": query_match,
            "terms_used": [term for _, _, term in terms],
            "retrieval_status": "lexical_match_only",
            "query_variant_count": {"original_text": len(originals), "question": len(questions)}}


COMMANDS = {"summary": summary, "sources": sources, "chunks": chunks,
            "chunk": chunk, "retrieve": retrieve}


def release_metadata(db_path: Path):
    manifest_path = db_path.parent / "manifest.json"
    if manifest_path.is_file():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        source_path = manifest.get("input") or ""
        return {"corpus_release": manifest.get("corpus_release") or Path(source_path).parent.name,
                "retrieval_algorithm": RETRIEVAL_ALGORITHM,
                "retrieval_limitation": RETRIEVAL_LIMITATION}
    return {"corpus_release": "unknown", "retrieval_algorithm": RETRIEVAL_ALGORITHM,
            "retrieval_limitation": RETRIEVAL_LIMITATION}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=COMMANDS)
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    args = parser.parse_args()
    try:
        payload = json.load(sys.stdin) if not sys.stdin.isatty() else {}
        if not isinstance(payload, dict):
            raise ValueError("request_must_be_object")
        db = connect(args.db)
        try:
            response = {"ok": True, "data": COMMANDS[args.command](db, payload)}
        finally:
            db.close()
        if args.command in {"summary", "retrieve"}:
            response["data"].update(release_metadata(args.db))
        print(json.dumps(response, ensure_ascii=False, separators=(",", ":")))
    except (OSError, ValueError, sqlite3.Error) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False))
        sys.exit(1)


if __name__ == "__main__":
    main()
