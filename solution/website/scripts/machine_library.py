"""Build and query the independent, run-scoped machine dictionary/case library."""

from __future__ import annotations

import argparse
import concurrent.futures
import hashlib
import json
import math
import os
import re
import shutil
import sqlite3
import sys
import time
import unicodedata
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable


ROOT = Path(__file__).resolve().parents[3]
BASE = ROOT / "solution" / "corpus-standardization" / "evaluation" / "parsebench-20261030"
DEFAULT_SOURCE_DB = BASE / "full_four_book_dictionary" / "new_parser_case_candidates_full_four_book.db"
DEFAULT_TERM_DB = BASE / "full_four_book_dictionary" / "new_parser_full_four_book_full.db"
DEFAULT_DB = ROOT / "solution" / "website" / "runtime-bundle" / "machine-library.sqlite3"
DEFAULT_LOG_DIR = BASE / "machine-library-implementation-20261031" / "database"
SCHEMA_VERSION = "machine-library-v1"
NORMALIZATION_VERSION = "nfkc-v1"
WORK_ORDER = ("dushu_zazhi", "guangya_shuzheng", "jingyi_shuwen", "jingzhuan_shici")
EXPECTED_WORK_COUNTS = {
    "dushu_zazhi": 4987,
    "guangya_shuzheng": 428,
    "jingyi_shuwen": 1967,
    "jingzhuan_shici": 150,
}

sys.path.insert(0, str(ROOT / "solution" / "website" / "scripts"))
from relation_parser import DEFAULT_MODULES, analyze_relation_candidates  # noqa: E402

from relation_identity import relation_identity as _relation_identity  # noqa: E402


def stable_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_only_connection(path: Path) -> sqlite3.Connection:
    uri_path = path.resolve().as_posix().replace("?", "%3f")
    connection = sqlite3.connect(f"file:{uri_path}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA query_only = ON")
    return connection


def source_sha256_text(text: str) -> str:
    return sha256_bytes(text.encode("utf-8"))


def _markdown_paragraphs(lines: list[str]) -> dict[int, tuple[int, int, int]]:
    """Map zero-based markdown line indexes to nonblank paragraph bounds and size."""
    output: dict[int, tuple[int, int, int]] = {}
    index = 0
    while index < len(lines):
        if not lines[index].strip():
            index += 1
            continue
        start = index
        while index < len(lines) and lines[index].strip():
            index += 1
        end = index - 1
        length = sum(len(lines[i]) for i in range(start, end + 1)) + max(0, end - start)
        bounds = (start + 1, end + 1, length)
        for i in range(start, end + 1):
            output[i] = bounds
    return output


def _align_passage_lines(
    raw_text: str, source_lines: list[str], paragraph_map: dict[int, tuple[int, int, int]],
    md_line_start: int | None, md_line_end: int | None,
) -> list[dict[str, Any]]:
    """Align stored raw passage lines monotonically to exact source Markdown lines."""
    if md_line_start is None or md_line_end is None:
        return []
    cursor = max(0, int(md_line_start) - 1)
    limit = min(len(source_lines), int(md_line_end))
    output = []
    offset = 0
    for raw_index, raw_with_ending in enumerate((raw_text or "").splitlines(keepends=True)):
        raw_line = raw_with_ending.rstrip("\r\n")
        raw_start = offset
        raw_end = raw_start + len(raw_line)
        offset += len(raw_with_ending)
        if not raw_line.strip():
            continue
        key = " ".join(raw_line.strip().lstrip("\ufeff").split())
        found = None
        for source_index in range(cursor, limit):
            source_key = " ".join(source_lines[source_index].strip().lstrip("\ufeff").split())
            if source_key == key:
                found = source_index
                break
        if found is None:
            output.append({"raw_line_index": raw_index, "raw_start_cp": raw_start,
                           "raw_end_cp": raw_end, "source_line_no": None,
                           "paragraph_start_line": None, "paragraph_end_line": None,
                           "paragraph_length": None})
            continue
        cursor = found + 1
        paragraph = paragraph_map.get(found)
        output.append({
            "raw_line_index": raw_index, "raw_start_cp": raw_start, "raw_end_cp": raw_end,
            "source_line_no": found + 1,
            "paragraph_start_line": paragraph[0] if paragraph else None,
            "paragraph_end_line": paragraph[1] if paragraph else None,
            "paragraph_length": paragraph[2] if paragraph else None,
        })
    return output


def _locate_span_in_source(
    raw_text: str, plain_text: str, start_cp: int, end_cp: int, line_map: list[dict[str, Any]],
) -> dict[str, Any]:
    """Map plain-text code-point spans to exact original Markdown lines when possible."""
    result = {"source_md_line_start": None, "source_md_line_end": None,
              "source_paragraph_start": None, "source_paragraph_end": None,
              "source_paragraph_length": None, "source_location_status": "passage_range_only"}
    if not (0 <= start_cp < end_cp <= len(plain_text)) or not line_map:
        return result
    if raw_text == plain_text:
        raw_start, raw_end = start_cp, end_cp
    else:
        quote = plain_text[start_cp:end_cp]
        if not quote:
            return result
        first = raw_text.find(quote)
        if first < 0 or raw_text.find(quote, first + 1) >= 0:
            return result
        raw_start, raw_end = first, first + len(quote)

    def line_at(offset: int) -> dict[str, Any] | None:
        for item in line_map:
            if item["source_line_no"] is None:
                continue
            if item["raw_start_cp"] <= offset < item["raw_end_cp"]:
                return item
            if offset == item["raw_end_cp"]:
                return item
        return None

    first_line = line_at(raw_start)
    last_line = line_at(max(raw_start, raw_end - 1))
    if not first_line or not last_line:
        return result
    result.update({
        "source_md_line_start": first_line["source_line_no"],
        "source_md_line_end": last_line["source_line_no"],
        "source_location_status": "exact_source_lines",
    })
    para_start = first_line["paragraph_start_line"]
    para_end = first_line["paragraph_end_line"]
    if (para_start is not None and para_start == last_line["paragraph_start_line"]
            and para_end == last_line["paragraph_end_line"]):
        result.update({
            "source_paragraph_start": para_start,
            "source_paragraph_end": para_end,
            "source_paragraph_length": first_line["paragraph_length"],
        })
    return result


MAX_PROOFREADING_POINT_CHARS = 1600


def _local_claim_components(records: list[dict[str, Any]]) -> list[list[dict[str, Any]]]:
    """Join only overlapping issue spans or claims sharing an exact trigger."""
    if not records:
        return []
    parent = list(range(len(records)))

    def find(index: int) -> int:
        while parent[index] != index:
            parent[index] = parent[parent[index]]
            index = parent[index]
        return index

    def union(left: int, right: int) -> None:
        left_root, right_root = find(left), find(right)
        if left_root != right_root:
            parent[right_root] = left_root

    trigger_owner: dict[tuple[int, int], int] = {}
    for index, record in enumerate(records):
        start, end = record.get("trigger_start_cp"), record.get("trigger_end_cp")
        if start is not None and end is not None and end > start:
            key = (int(start), int(end))
            if key in trigger_owner:
                union(index, trigger_owner[key])
            else:
                trigger_owner[key] = index

    ordered = sorted(range(len(records)), key=lambda index: (
        int(records[index]["claim_start_cp"]), int(records[index]["claim_end_cp"]), records[index]["claim_candidate_id"]
    ))
    current_index = None
    current_end = -1
    for index in ordered:
        start = int(records[index]["claim_start_cp"])
        end = int(records[index]["claim_end_cp"])
        if current_index is not None and start < current_end:
            union(index, current_index)
            current_end = max(current_end, end)
        else:
            current_index = index
            current_end = end

    components: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for index, record in enumerate(records):
        components[find(index)].append(record)
    return sorted(components.values(), key=lambda group: (
        min(int(row["claim_start_cp"]) for row in group),
        min(row["claim_candidate_id"] for row in group),
    ))


def _segment_claim_candidates(records: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], set[str]]:
    """Create machine issue points from bounded Markdown paragraphs or local spans."""
    by_passage: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for record in records:
        by_passage[record["source_passage_id"]].append(record)

    groups: list[dict[str, Any]] = []
    unsegmented: set[str] = set()
    for source_passage_id, passage_records in by_passage.items():
        paragraph_records: dict[tuple[int, int], list[dict[str, Any]]] = defaultdict(list)
        local_records: dict[tuple[int | None, int | None], list[dict[str, Any]]] = defaultdict(list)
        invalid_records = []
        for record in passage_records:
            start, end = record.get("claim_start_cp"), record.get("claim_end_cp")
            trigger_start, trigger_end = record.get("trigger_start_cp"), record.get("trigger_end_cp")
            if start is None or end is None or int(end) <= int(start) or trigger_start is None or trigger_end is None or int(trigger_end) <= int(trigger_start):
                invalid_records.append(record)
                continue
            para_start = record.get("source_paragraph_start")
            para_end = record.get("source_paragraph_end")
            para_length = record.get("source_paragraph_length")
            if para_start is not None and para_end is not None and para_length is not None and int(para_length) <= MAX_PROOFREADING_POINT_CHARS:
                paragraph_records[(int(para_start), int(para_end))].append(record)
            else:
                local_records[(int(para_start) if para_start is not None else None,
                                int(para_end) if para_end is not None else None)].append(record)
        unsegmented.update(record["claim_candidate_id"] for record in invalid_records)

        for (para_start, para_end), members in paragraph_records.items():
            groups.append({
                "source_passage_id": source_passage_id, "records": members,
                "segmentation_status": "bounded_markdown_paragraph_cluster",
                "link_method": "bounded_markdown_paragraph_cluster",
                "paragraph_start": para_start, "paragraph_end": para_end,
            })
        for (para_start, para_end), members in local_records.items():
            for component in _local_claim_components(members):
                starts = [int(row["claim_start_cp"]) for row in component]
                ends = [int(row["claim_end_cp"]) for row in component]
                if max(ends) - min(starts) > MAX_PROOFREADING_POINT_CHARS:
                    unsegmented.update(row["claim_candidate_id"] for row in component)
                    continue
                groups.append({
                    "source_passage_id": source_passage_id, "records": component,
                    "segmentation_status": "overlapping_claim_trigger_cluster",
                    "link_method": "overlapping_claim_trigger_cluster",
                    "paragraph_start": para_start, "paragraph_end": para_end,
                })
    groups.sort(key=lambda group: (
        group["source_passage_id"],
        min(int(row["claim_start_cp"]) for row in group["records"]),
        min(row["claim_candidate_id"] for row in group["records"]),
    ))
    return groups, unsegmented


def _relation_key(item: dict[str, Any]) -> tuple[Any, ...]:
    claim = item.get("claim_span") or {}
    trigger = item.get("trigger_span") or {}
    return (
        item.get("relation_type"), item.get("relation_cue"),
        item.get("left_form"), item.get("right_form"), item.get("changed_from"),
        item.get("changed_to"), item.get("author_stance"), item.get("directionality"),
        claim.get("start_cp"), claim.get("end_cp"), trigger.get("start_cp"),
        trigger.get("end_cp"), item.get("quote"),
    )


def process_passage(row: tuple[Any, ...]) -> dict[str, Any]:
    """Run all configured modules against every distinct Han target in one passage."""
    passage_id, work_key, local_ordinal, line_start, line_end, text, candidate_id = row
    text = text or ""
    # Keep the runner's established Han target domain and order.
    import re
    targets = sorted(set(re.findall(r"[\u3400-\u9fff\U00020000-\U0002FA1F]", text)))
    found: dict[tuple[Any, ...], dict[str, Any]] = {}
    parse_outputs = suppressed_outputs = abstention_count = 0
    abstention_reasons: Counter[str] = Counter()
    active_targets: set[str] = set()
    suppressed_targets: set[str] = set()
    for target in targets:
        relations, abstentions = analyze_relation_candidates(text, target, modules=DEFAULT_MODULES)
        abstention_count += len(abstentions)
        abstention_reasons.update(str(item.get("reason") or "unspecified") for item in abstentions)
        parse_outputs += len(relations)
        for relation in relations:
            key = _relation_key(relation)
            record = found.setdefault(key, dict(relation))
            record.setdefault("_targets_by_query", {})[target] = True
            record.setdefault("_target_spans_by_query", {})[target] = relation.get("target_spans") or []
            record.setdefault("_scopes_by_query", {})[target] = relation.get("relation_scope")
            if relation.get("author_stance") in {"rejected", "conditional"}:
                suppressed_outputs += 1
                suppressed_targets.add(target)
            else:
                active_targets.add(target)
    return {
        "passage_id": passage_id,
        "work_key": work_key,
        "local_ordinal": int(local_ordinal),
        "line_start": line_start,
        "line_end": line_end,
        "candidate_id": candidate_id,
        "target_count": len(targets),
        "parse_outputs": parse_outputs,
        "suppressed_outputs": suppressed_outputs,
        "abstention_count": abstention_count,
        "abstention_reasons": dict(abstention_reasons),
        "active_targets": sorted(active_targets),
        "suppressed_targets": sorted(suppressed_targets),
        "relations": [found[key] for key in sorted(found, key=repr)],
    }


def _source_passage_id(work_key: str, source_sha: str, passage_id: str, raw_sha: str) -> str:
    identity = stable_json([work_key, source_sha, passage_id, raw_sha]).encode("utf-8")
    return "sp-" + sha256_bytes(identity)[:24]


def _term_form_id(form: str) -> tuple[str, str, str]:
    normalized = unicodedata.normalize("NFKC", form)
    form_kind = "single_character" if len(normalized) == 1 else "phrase"
    identity = stable_json([NORMALIZATION_VERSION, normalized]).encode("utf-8")
    return "tf-" + sha256_bytes(identity)[:24], normalized, form_kind


def _insert_term_form(connection: sqlite3.Connection, form: str, origin: str) -> str | None:
    form = str(form or "")
    if not form:
        return None
    form_id, normalized, form_kind = _term_form_id(form)
    connection.execute(
        """INSERT OR IGNORE INTO term_forms
           (term_form_id, normalized_form, display_form, form_kind, normalization_version, origin_flags_json)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (form_id, normalized, form, form_kind, NORMALIZATION_VERSION, stable_json([origin])),
    )
    row = connection.execute("SELECT origin_flags_json FROM term_forms WHERE term_form_id=?", (form_id,)).fetchone()
    if row:
        origins = set(json.loads(row[0]))
        if origin not in origins:
            origins.add(origin)
            connection.execute("UPDATE term_forms SET origin_flags_json=? WHERE term_form_id=?", (stable_json(sorted(origins)), form_id))
    return form_id


SCHEMA = """
PRAGMA foreign_keys=ON;
CREATE TABLE metadata (key TEXT PRIMARY KEY, value_json TEXT NOT NULL);
CREATE TABLE source_versions (
  source_version_id TEXT PRIMARY KEY, source_document_id TEXT NOT NULL, work_key TEXT NOT NULL,
  source_file TEXT NOT NULL, source_file_sha256 TEXT NOT NULL, source_bytes INTEGER,
  canonical_status TEXT NOT NULL,
  UNIQUE(work_key, source_file_sha256)
);
CREATE TABLE parser_runs (
  run_id TEXT PRIMARY KEY, parser_name TEXT NOT NULL, parser_sha256 TEXT NOT NULL,
  machine_library_sha256 TEXT NOT NULL,
  input_manifest_sha256 TEXT NOT NULL, input_manifest_json TEXT NOT NULL,
  source_database_sha256 TEXT NOT NULL, term_group_database_sha256 TEXT NOT NULL,
  created_at TEXT NOT NULL, worker_count INTEGER NOT NULL, modules_json TEXT NOT NULL,
  run_status TEXT NOT NULL, content_sha256 TEXT
);
CREATE TABLE works (
  work_key TEXT PRIMARY KEY, work_title TEXT NOT NULL, source_version_id TEXT NOT NULL REFERENCES source_versions,
  source_file TEXT NOT NULL, source_file_sha256 TEXT NOT NULL,
  source_passage_count INTEGER NOT NULL DEFAULT 0, case_passage_count INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE source_passages (
  source_passage_id TEXT PRIMARY KEY, work_key TEXT NOT NULL REFERENCES works,
  passage_id TEXT NOT NULL, local_ordinal INTEGER NOT NULL, md_line_start INTEGER, md_line_end INTEGER,
  raw_text TEXT NOT NULL, plain_text TEXT NOT NULL, normalized_text TEXT NOT NULL,
  raw_text_sha256 TEXT NOT NULL, normalized_text_sha256 TEXT NOT NULL, inline_notes_json TEXT NOT NULL,
  UNIQUE(work_key, passage_id)
);
CREATE TABLE case_passages (
  run_id TEXT NOT NULL REFERENCES parser_runs, source_passage_id TEXT NOT NULL REFERENCES source_passages,
  candidate_id TEXT NOT NULL, candidate_status TEXT NOT NULL, human_status TEXT NOT NULL,
  risk_flags_json TEXT NOT NULL, selection_json TEXT NOT NULL, candidate_text TEXT NOT NULL,
  PRIMARY KEY(run_id, source_passage_id), UNIQUE(run_id, candidate_id)
);
CREATE TABLE term_forms (
  term_form_id TEXT PRIMARY KEY, normalized_form TEXT NOT NULL, display_form TEXT NOT NULL,
  form_kind TEXT NOT NULL, normalization_version TEXT NOT NULL, origin_flags_json TEXT NOT NULL,
  UNIQUE(normalization_version, normalized_form)
);
CREATE TABLE term_groups (
  term_group_id TEXT PRIMARY KEY, run_id TEXT NOT NULL REFERENCES parser_runs,
  source_version_id TEXT NOT NULL REFERENCES source_versions,
  source_passage_id TEXT REFERENCES source_passages, work_key TEXT NOT NULL REFERENCES works,
  record_id INTEGER NOT NULL, line_no INTEGER NOT NULL, heading_sha256 TEXT NOT NULL,
  payload_json TEXT NOT NULL, UNIQUE(run_id, work_key, line_no)
);
CREATE TABLE term_group_members (
  term_group_id TEXT NOT NULL REFERENCES term_groups, term_form_id TEXT NOT NULL REFERENCES term_forms,
  member_role TEXT NOT NULL, token_order INTEGER NOT NULL, span_start_cp INTEGER, span_end_cp INTEGER,
  PRIMARY KEY(term_group_id, term_form_id, member_role, token_order)
);
CREATE TABLE relation_claim_candidates (
  run_id TEXT NOT NULL REFERENCES parser_runs, claim_candidate_id TEXT NOT NULL,
  source_passage_id TEXT NOT NULL REFERENCES source_passages, candidate_id TEXT,
  relation_type TEXT NOT NULL, relation_scope TEXT NOT NULL, relation_label TEXT NOT NULL,
  relation_cue TEXT NOT NULL, left_form TEXT NOT NULL, right_form TEXT NOT NULL,
  changed_from TEXT, changed_to TEXT, directionality TEXT NOT NULL, author_stance TEXT NOT NULL,
  machine_status TEXT NOT NULL, claim_start_cp INTEGER NOT NULL, claim_end_cp INTEGER NOT NULL,
  trigger_start_cp INTEGER, trigger_end_cp INTEGER, quote TEXT NOT NULL,
  source_md_line_start INTEGER, source_md_line_end INTEGER,
  source_paragraph_start INTEGER, source_paragraph_end INTEGER, source_paragraph_length INTEGER,
  source_location_status TEXT NOT NULL,
  candidate_fingerprint TEXT NOT NULL, target_forms_json TEXT NOT NULL, query_scopes_json TEXT NOT NULL,
  payload_json TEXT NOT NULL,
  PRIMARY KEY(run_id, claim_candidate_id)
);
CREATE TABLE claim_evidence (
  run_id TEXT NOT NULL, claim_candidate_id TEXT NOT NULL, evidence_id TEXT NOT NULL,
  source_passage_id TEXT NOT NULL REFERENCES source_passages, evidence_role TEXT NOT NULL,
  start_cp INTEGER NOT NULL, end_cp INTEGER NOT NULL, quote_sha256 TEXT NOT NULL, quote TEXT NOT NULL,
  PRIMARY KEY(run_id, claim_candidate_id, evidence_id),
  FOREIGN KEY(run_id, claim_candidate_id) REFERENCES relation_claim_candidates(run_id, claim_candidate_id)
);
CREATE TABLE claim_endpoint_links (
  endpoint_link_id TEXT PRIMARY KEY, run_id TEXT NOT NULL, claim_candidate_id TEXT NOT NULL,
  term_form_id TEXT NOT NULL REFERENCES term_forms, endpoint_role TEXT NOT NULL,
  span_coordinate_space TEXT NOT NULL, span_start_cp INTEGER, span_end_cp INTEGER,
  link_method TEXT NOT NULL,
  FOREIGN KEY(run_id, claim_candidate_id) REFERENCES relation_claim_candidates(run_id, claim_candidate_id)
);
CREATE TABLE proofreading_points (
  proofreading_point_id TEXT PRIMARY KEY, run_id TEXT NOT NULL REFERENCES parser_runs,
  source_passage_id TEXT NOT NULL REFERENCES source_passages,
  source_md_line_start INTEGER, source_md_line_end INTEGER,
  source_paragraph_start INTEGER, source_paragraph_end INTEGER,
  source_location_status TEXT NOT NULL, trigger_spans_json TEXT NOT NULL,
  issue_start_cp INTEGER NOT NULL, issue_end_cp INTEGER NOT NULL, trigger_start_cp INTEGER NOT NULL,
  trigger_end_cp INTEGER NOT NULL, focus_text TEXT NOT NULL, segmentation_status TEXT NOT NULL,
  machine_status TEXT NOT NULL, human_status TEXT NOT NULL
);
CREATE TABLE claim_case_links (
  run_id TEXT NOT NULL, claim_candidate_id TEXT NOT NULL,
  proofreading_point_id TEXT NOT NULL REFERENCES proofreading_points,
  link_method TEXT NOT NULL, link_status TEXT NOT NULL,
  PRIMARY KEY(run_id, claim_candidate_id, proofreading_point_id),
  FOREIGN KEY(run_id, claim_candidate_id) REFERENCES relation_claim_candidates(run_id, claim_candidate_id)
);
CREATE TABLE relation_groups (
  run_id TEXT NOT NULL REFERENCES parser_runs, relation_group_id TEXT NOT NULL,
  relation_scope TEXT NOT NULL, relation_type TEXT NOT NULL, left_form TEXT NOT NULL,
  right_form TEXT NOT NULL, directionality TEXT NOT NULL, machine_status TEXT NOT NULL,
  relation_label TEXT NOT NULL, changed_from TEXT, changed_to TEXT,
  PRIMARY KEY(run_id, relation_group_id)
);
CREATE TABLE relation_group_claims (
  run_id TEXT NOT NULL, relation_group_id TEXT NOT NULL, claim_candidate_id TEXT NOT NULL,
  PRIMARY KEY(run_id, relation_group_id, claim_candidate_id),
  FOREIGN KEY(run_id, relation_group_id) REFERENCES relation_groups(run_id, relation_group_id),
  FOREIGN KEY(run_id, claim_candidate_id) REFERENCES relation_claim_candidates(run_id, claim_candidate_id)
);
CREATE INDEX idx_source_passages_work_ordinal ON source_passages(work_key, local_ordinal);
CREATE INDEX idx_claim_work ON relation_claim_candidates(run_id, source_passage_id, relation_type);
CREATE INDEX idx_claim_spans ON relation_claim_candidates(source_passage_id, claim_start_cp, claim_end_cp);
CREATE INDEX idx_case_links_point ON claim_case_links(run_id, proofreading_point_id);
CREATE INDEX idx_endpoint_form ON claim_endpoint_links(term_form_id);
"""


def _canonical_db_hash(connection: sqlite3.Connection) -> str:
    excluded = {"metadata"}
    digest = hashlib.sha256()
    for (table,) in connection.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"):
        if table in excluded:
            continue
        table_info = connection.execute(f"PRAGMA table_info({table})").fetchall()
        columns = [row[1] for row in table_info]
        primary_key = [row[1] for row in sorted((row for row in table_info if row[5]), key=lambda row: row[5])]
        if table == "parser_runs":
            columns = [name for name in columns if name not in {"created_at", "content_sha256"}]
        ordering = ",".join(f'"{name}"' for name in columns)
        order_by = ",".join(f'"{name}"' for name in primary_key) or "rowid"
        digest.update((table + "\n" + ",".join(columns) + "\n").encode("utf-8"))
        query = f'SELECT {ordering} FROM "{table}" ORDER BY {order_by}'
        for row in connection.execute(query):
            digest.update(stable_json(list(row)).encode("utf-8"))
            digest.update(b"\n")
    return digest.hexdigest()


def _initialize_database(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    connection.executescript(SCHEMA)
    connection.execute("PRAGMA journal_mode=DELETE")
    connection.execute("PRAGMA synchronous=FULL")
    return connection


def build_database(
    *, source_db: Path, term_db: Path, db_path: Path, log_dir: Path, workers: int,
) -> dict[str, Any]:
    started = time.perf_counter()
    source_db = source_db.resolve()
    term_db = term_db.resolve()
    db_path = db_path.resolve()
    log_dir.mkdir(parents=True, exist_ok=True)
    for path in (source_db, term_db):
        if not path.is_file():
            raise FileNotFoundError(path)
    parser_path = ROOT / "solution" / "website" / "scripts" / "relation_parser.py"
    library_path = Path(__file__).resolve()
    identity_path = ROOT / "solution" / "website" / "scripts" / "relation_identity.py"
    parser_sha = sha256_file(parser_path)
    library_sha = sha256_file(library_path)
    source_db_sha = sha256_file(source_db)
    term_db_sha = sha256_file(term_db)

    source = read_only_connection(source_db)
    source_docs = [dict(row) for row in source.execute(
        "SELECT source_document_id, work_key, source_work, source_file, source_file_sha256, canonical_status FROM source_documents ORDER BY work_key"
    )]
    passage_rows = [tuple(row) for row in source.execute(
        """SELECT sp.passage_id, sp.work_key, sp.local_ordinal, sp.md_line_start, sp.md_line_end,
                  sp.raw_text, sp.plain_text, sp.normalized_text, sp.raw_text_sha256,
                  sp.normalized_text_sha256, sp.inline_notes_json, pc.candidate_id,
                  pc.candidate_status, pc.human_status, pc.risk_flags_json, pc.rule_hits_json,
                  pc.provenance_json, pc.candidate_text
           FROM source_passages sp
           LEFT JOIN parser_case_candidates pc ON pc.passage_id=sp.passage_id
           ORDER BY sp.work_key, sp.local_ordinal, sp.passage_id"""
    )]
    source.close()
    source_md_root = BASE / "pipeline_snapshot" / "four_book_cases" / "source"
    source_lines_by_work: dict[str, list[str]] = {}
    source_paragraphs_by_work: dict[str, dict[int, tuple[int, int, int]]] = {}
    source_bytes_by_work: dict[str, int] = {}
    for doc in source_docs:
        source_path = source_md_root / doc["source_file"]
        if not source_path.is_file():
            raise FileNotFoundError(f"source Markdown missing for location mapping: {source_path}")
        actual_sha = sha256_file(source_path)
        if actual_sha != doc["source_file_sha256"]:
            raise RuntimeError(f"source Markdown SHA-256 mismatch: {doc['work_key']}")
        source_text = source_path.read_text(encoding="utf-8")
        source_lines_by_work[doc["work_key"]] = source_text.splitlines()
        source_paragraphs_by_work[doc["work_key"]] = _markdown_paragraphs(source_lines_by_work[doc["work_key"]])
        source_bytes_by_work[doc["work_key"]] = source_path.stat().st_size
    term_connection = read_only_connection(term_db)
    term_rows = term_connection.execute(
        "SELECT record_id, work_key, line_no, payload_json FROM parsed_records ORDER BY work_key, line_no, record_id"
    ).fetchall()
    term_sources = {row[0]: row[1] for row in term_connection.execute("SELECT work_key, source_sha256 FROM source_files")}
    term_connection.close()
    term_group_parser_names = sorted({
        str((json.loads(row[3]).get("parser") or "unknown")) for row in term_rows
    })
    if len(term_rows) != 2341:
        raise RuntimeError(f"expected 2,341 term groups, found {len(term_rows)}")
    counts_by_work = Counter(row[1] for row in passage_rows)
    if len(source_docs) != 4 or len(passage_rows) != 7532 or dict(counts_by_work) != EXPECTED_WORK_COUNTS:
        raise RuntimeError(f"unexpected complete source corpus: docs={len(source_docs)}, passages={len(passage_rows)}, by_work={dict(counts_by_work)}")
    if any(not row[6] for row in passage_rows):
        raise RuntimeError("empty plain_text passage found; full relation parse refused")
    source_doc_by_work = {row["work_key"]: row for row in source_docs}
    if set(source_doc_by_work) != set(WORK_ORDER):
        raise RuntimeError(f"unexpected work keys: {sorted(source_doc_by_work)}")

    source_versions = {}
    for doc in source_docs:
        version_id = "sv-" + sha256_bytes(stable_json([doc["work_key"], doc["source_file_sha256"]]).encode())[:20]
        source_versions[doc["work_key"]] = version_id
    input_manifest = {
        "schema_version": SCHEMA_VERSION,
        "source_db_path": source_db.relative_to(ROOT).as_posix() if source_db.is_relative_to(ROOT) else source_db.name,
        "source_database_sha256": source_db_sha,
        "source_documents": [{**{k: doc[k] for k in ("source_document_id", "work_key", "source_file", "source_file_sha256", "canonical_status")},
                              "source_file_bytes": source_bytes_by_work[doc["work_key"]]} for doc in source_docs],
        "source_passage_count": len(passage_rows),
        "source_passages_by_work": dict(sorted(counts_by_work.items())),
        "term_group_database_sha256": term_db_sha,
        "term_groups_source": "parsed_records from new_parser_full_four_book_full.db",
        "term_group_parser_names": term_group_parser_names,
        "term_group_count": len(term_rows),
        "term_grouping_version": "parsed_records-payload-v1",
        "parser_sha256": parser_sha,
        "machine_library_sha256": library_sha,
        "identity_sha256": sha256_file(identity_path) if identity_path.is_file() else None,
        "relation_grouping_version": "relation_identity-v1-plus-machine-status",
        "proofreading_point_segmentation_version": "bounded-markdown-paragraph-plus-local-cluster-v2",
        "source_location_mapping_version": "sequential-raw-line-to-markdown-paragraph-v1",
        "modules": sorted(DEFAULT_MODULES),
        "extraction": "all Han characters in every source passage; direct extraction, no parse cache",
        "normalization_version": NORMALIZATION_VERSION,
    }
    manifest_sha = sha256_bytes(stable_json(input_manifest).encode("utf-8"))
    run_id = "ml-" + sha256_bytes(stable_json([SCHEMA_VERSION, parser_sha, manifest_sha]).encode("utf-8"))[:20]
    worker_count = max(1, min(int(workers), 4))
    temp_path = db_path.with_name(db_path.name + f".building-{os.getpid()}")
    if temp_path.exists():
        temp_path.unlink()
    log_path = log_dir / f"machine-library-build-{run_id}.log"
    summary_path = log_dir / f"machine-library-build-{run_id}.json"
    log_path.write_text(
        f"run_id={run_id}\nsource_passages={len(passage_rows)}\nworkers={worker_count}\n"
        f"parser_sha256={parser_sha}\ninput_manifest_sha256={manifest_sha}\nmode=direct_extract_no_cache\n",
        encoding="utf-8",
    )

    connection = _initialize_database(temp_path)
    try:
        with connection:
            connection.execute("INSERT INTO parser_runs VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL)", (
                run_id, "relation_parser", parser_sha, library_sha, manifest_sha, stable_json(input_manifest),
                source_db_sha, term_db_sha, datetime.now(timezone.utc).isoformat(), worker_count,
                stable_json(sorted(DEFAULT_MODULES)), "building",
            ))
            connection.execute("INSERT INTO metadata VALUES (?, ?)", ("schema_version", stable_json(SCHEMA_VERSION)))
            connection.execute("INSERT INTO metadata VALUES (?, ?)", ("active_run_id", stable_json(run_id)))
            passage_map: dict[str, dict[str, Any]] = {}
            passage_line_maps: dict[str, list[dict[str, Any]]] = {}
            by_work_lines: dict[str, list[tuple[int | None, int | None, str]]] = defaultdict(list)
            for doc in source_docs:
                work = doc["work_key"]
                version_id = source_versions[work]
                connection.execute("INSERT INTO source_versions VALUES (?, ?, ?, ?, ?, ?, ?)", (
                    version_id, doc["source_document_id"], work, doc["source_file"], doc["source_file_sha256"],
                    source_bytes_by_work[work], doc["canonical_status"],
                ))
                connection.execute("INSERT INTO works VALUES (?, ?, ?, ?, ?, ?, ?)", (
                    work, doc["source_work"], version_id, doc["source_file"], doc["source_file_sha256"],
                    EXPECTED_WORK_COUNTS[work], 0,
                ))
            candidate_counts = Counter()
            for row in passage_rows:
                (passage_id, work_key, ordinal, line_start, line_end, raw, plain, normalized,
                 raw_sha, normalized_sha, notes_json, candidate_id, candidate_status, human_status,
                 risk_json, rule_hits_json, provenance_json, candidate_text) = row
                doc = source_doc_by_work[work_key]
                raw = raw or ""
                plain = plain or ""
                normalized = normalized or ""
                actual_raw_sha = source_sha256_text(raw)
                actual_normalized_sha = source_sha256_text(normalized)
                if raw_sha and raw_sha != actual_raw_sha:
                    raise RuntimeError(f"raw source hash mismatch: {work_key}/{passage_id}")
                if normalized_sha and normalized_sha != actual_normalized_sha:
                    raise RuntimeError(f"normalized source hash mismatch: {work_key}/{passage_id}")
                raw_sha = raw_sha or actual_raw_sha
                normalized_sha = normalized_sha or actual_normalized_sha
                spid = _source_passage_id(work_key, doc["source_file_sha256"], passage_id, raw_sha)
                passage_line_maps[passage_id] = _align_passage_lines(
                    raw, source_lines_by_work[work_key], source_paragraphs_by_work[work_key],
                    line_start, line_end,
                )
                connection.execute("INSERT INTO source_passages VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", (
                    spid, work_key, passage_id, int(ordinal), line_start, line_end, raw, plain, normalized,
                    raw_sha, normalized_sha, notes_json or "[]",
                ))
                passage = {"source_passage_id": spid, "passage_id": passage_id, "work_key": work_key,
                           "local_ordinal": int(ordinal), "md_line_start": line_start, "md_line_end": line_end,
                           "plain_text": plain, "raw_text": raw, "source_file_sha256": doc["source_file_sha256"]}
                passage_map[passage_id] = passage
                by_work_lines[work_key].append((line_start, line_end, spid))
                if candidate_id:
                    candidate_counts[work_key] += 1
                    connection.execute("INSERT INTO case_passages VALUES (?, ?, ?, ?, ?, ?, ?, ?)", (
                        run_id, spid, candidate_id, candidate_status or "candidate", human_status or "pending",
                        risk_json or "[]", stable_json({"rule_hits_json": rule_hits_json or "[]", "provenance_json": provenance_json or "{}"}),
                        candidate_text or "",
                    ))
            for work_key, count in candidate_counts.items():
                connection.execute("UPDATE works SET case_passage_count=? WHERE work_key=?", (count, work_key))

            # Import the complete four-book parser group snapshot as a separate compatibility layer.
            source_hashes = {doc["work_key"]: doc["source_file_sha256"] for doc in source_docs}
            if term_sources != source_hashes:
                raise RuntimeError("term-group source hashes do not match the four-book passage source")
            group_count = 0
            group_member_count = 0
            for record_id, work_key, line_no, payload_text in term_rows:
                payload = json.loads(payload_text)
                heading_payload = payload.get("heading") or {}
                group_identity = stable_json([run_id, work_key, int(line_no), int(record_id)]).encode("utf-8")
                group_id = "tg-" + sha256_bytes(group_identity)[:24]
                raw_line = str(heading_payload.get("raw_line") or heading_payload.get("head_prefix") or "")
                heading_sha = source_sha256_text(raw_line)
                source_passage_id = None
                containing = [item for item in by_work_lines[work_key]
                              if item[0] is not None and item[1] is not None and item[0] <= int(line_no) <= item[1]]
                if containing:
                    source_passage_id = containing[0][2]
                connection.execute("INSERT INTO term_groups VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)", (
                    group_id, run_id, source_versions[work_key], source_passage_id, work_key,
                    int(record_id), int(line_no), heading_sha, stable_json(payload),
                ))
                group_count += 1
                for member_role, key in (("head", "head_tokens"), ("phonetic", "phonetic_tokens"), ("ambiguous", "ambiguous_tokens")):
                    members = heading_payload.get(key) or []
                    for index, member in enumerate(members):
                        if not isinstance(member, dict):
                            continue
                        surface = str(member.get("surface") or "")
                        form_id = _insert_term_form(connection, surface, f"term_group:{member_role}")
                        if form_id:
                            connection.execute("INSERT OR IGNORE INTO term_group_members VALUES (?, ?, ?, ?, NULL, NULL)", (
                                group_id, form_id, member_role, int(member.get("token_index", index)),
                            ))
                            group_member_count += 1

        # Claims are extracted from every source passage, including the 598 passages
        # that do not occur in parser_case_candidates.
        relation_counts = Counter()
        relation_group_items: dict[tuple[Any, ...], list[dict[str, Any]]] = defaultdict(list)
        claim_segment_records: list[dict[str, Any]] = []
        done = 0
        with concurrent.futures.ProcessPoolExecutor(max_workers=worker_count) as executor:
            for result in executor.map(process_passage, passage_rows_for_workers(passage_rows), chunksize=8):
                done += 1
                passage = passage_map[result["passage_id"]]
                for relation in result["relations"]:
                    target_forms = sorted(relation.pop("_targets_by_query", {}).keys())
                    target_spans = relation.pop("_target_spans_by_query", {})
                    query_scopes = relation.pop("_scopes_by_query", {})
                    raw_left_form = str(relation.get("left_form") or "")
                    raw_right_form = str(relation.get("right_form") or "")
                    claim_span = relation.get("claim_span") or {}
                    trigger_span = relation.get("trigger_span") or {}
                    start = int(claim_span.get("start_cp", -1))
                    end = int(claim_span.get("end_cp", -1))
                    trigger_start = int(trigger_span.get("start_cp", -1))
                    trigger_end = int(trigger_span.get("end_cp", -1))
                    quote = str(relation.get("quote") or "")
                    exact_quote = passage["plain_text"][start:end] if 0 <= start <= end <= len(passage["plain_text"]) else None
                    if exact_quote is None or exact_quote != quote:
                        raise RuntimeError(f"quote span mismatch at {result['passage_id']}:{start}-{end}")
                    source_location = _locate_span_in_source(
                        passage["raw_text"], passage["plain_text"], start, end,
                        passage_line_maps.get(result["passage_id"], []),
                    )
                    relation_key = _relation_key(relation)
                    identity = _relation_identity(relation)
                    relation["relation_scope"] = identity[0]
                    fingerprint_payload = [passage["source_passage_id"], relation_key]
                    fingerprint = sha256_bytes(stable_json(fingerprint_payload).encode("utf-8"))
                    claim_id = "mc-" + fingerprint[:24]
                    stance = str(relation.get("author_stance") or "uncertain")
                    machine_status = "suppressed_candidate" if stance in {"rejected", "conditional"} else "pending_candidate"
                    relation_payload = dict(relation)
                    relation_payload["query_targets"] = target_forms
                    relation_payload["target_spans_by_query"] = target_spans
                    relation_payload["query_scopes_by_target"] = query_scopes
                    relation_payload["source_location"] = source_location
                    connection.execute("INSERT INTO relation_claim_candidates VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", (
                        run_id, claim_id, passage["source_passage_id"], result["candidate_id"],
                        str(relation.get("relation_type") or "unknown"), str(relation.get("relation_scope") or "unknown"),
                        str(relation.get("relation_label") or relation.get("relation_type") or ""),
                        str(relation.get("relation_cue") or ""), str(relation.get("left_form") or ""),
                        str(relation.get("right_form") or ""), relation.get("changed_from"), relation.get("changed_to"),
                        str(relation.get("directionality") or "left_to_right"), stance, machine_status,
                        start, end, trigger_start if trigger_start >= 0 else None,
                        trigger_end if trigger_end >= 0 else None, quote,
                        source_location["source_md_line_start"], source_location["source_md_line_end"],
                        source_location["source_paragraph_start"], source_location["source_paragraph_end"],
                        source_location["source_paragraph_length"], source_location["source_location_status"],
                        fingerprint,
                        stable_json(target_forms), stable_json(query_scopes), stable_json(relation_payload),
                    ))
                    evidence_id = "ev-" + sha256_bytes(stable_json([claim_id, start, end, quote]).encode("utf-8"))[:24]
                    connection.execute("INSERT INTO claim_evidence VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)", (
                        run_id, claim_id, evidence_id, passage["source_passage_id"], "claim_quote", start, end,
                        source_sha256_text(quote), quote,
                    ))
                    relation_counts["claims"] += 1
                    relation_counts[machine_status] += 1
                    relation_counts["evidence"] += 1
                    if source_location["source_location_status"] == "exact_source_lines":
                        relation_counts["claims_with_exact_source_lines"] += 1
                    claim_segment_records.append({
                        "claim_candidate_id": claim_id, "source_passage_id": passage["source_passage_id"],
                        "claim_start_cp": start, "claim_end_cp": end,
                        "trigger_start_cp": trigger_start if trigger_start >= 0 else None,
                        "trigger_end_cp": trigger_end if trigger_end >= 0 else None,
                        "machine_status": machine_status, **source_location,
                    })

                    for role, value in (("left_form", relation.get("left_form")), ("right_form", relation.get("right_form")),
                                        ("changed_from", relation.get("changed_from")), ("changed_to", relation.get("changed_to"))):
                        if value:
                            form_id = _insert_term_form(connection, str(value), f"claim:{role}")
                            if form_id:
                                endpoint_id = "el-" + sha256_bytes(stable_json([claim_id, role, form_id]).encode("utf-8"))[:24]
                                connection.execute("INSERT INTO claim_endpoint_links VALUES (?, ?, ?, ?, ?, ?, NULL, NULL, ?)", (
                                    endpoint_id, run_id, claim_id, form_id, role, "term_form", "parser_endpoint",
                                ))
                                relation_counts["endpoint_links"] += 1
                    for target in target_forms:
                        form_id = _insert_term_form(connection, target, "claim:query_target")
                        if form_id:
                            for span in target_spans.get(target, []):
                                side = str(span.get("side") or "")
                                endpoint_id = "el-" + sha256_bytes(stable_json([claim_id, "query_target", target, side, span.get("start_cp"), span.get("end_cp")]).encode("utf-8"))[:24]
                                connection.execute("INSERT OR IGNORE INTO claim_endpoint_links VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)", (
                                    endpoint_id, run_id, claim_id, form_id, "query_target", "term_form",
                                    span.get("start_cp"), span.get("end_cp"), "parser_query_target_span",
                                ))
                                relation_counts["endpoint_links"] += 1

                    group_key = (*identity, machine_status)
                    relation_group_items[group_key].append({
                        "claim_candidate_id": claim_id, "relation": relation, "status": machine_status,
                        "target_forms": target_forms,
                        "raw_left_form": raw_left_form, "raw_right_form": raw_right_form,
                    })
                if done % 250 == 0 or done == len(passage_rows):
                    with log_path.open("a", encoding="utf-8") as handle:
                        handle.write(f"progress={done}/{len(passage_rows)} elapsed_s={time.perf_counter()-started:.1f} claims={relation_counts['claims']}\n")

        point_groups, unsegmented_claim_ids = _segment_claim_candidates(claim_segment_records)
        relation_counts["unsegmented_claims"] = len(unsegmented_claim_ids)
        point_count = 0
        point_id_by_claim: dict[str, str] = {}
        with connection:
            for group in point_groups:
                spid = group["source_passage_id"]
                records = group["records"]
                claim_ids = sorted({record["claim_candidate_id"] for record in records})
                start = min(int(record["claim_start_cp"]) for record in records)
                end = max(int(record["claim_end_cp"]) for record in records)
                trigger_start = min(int(record["trigger_start_cp"]) for record in records)
                trigger_end = max(int(record["trigger_end_cp"]) for record in records)
                point_identity = [spid, claim_ids, start, end, group["segmentation_status"]]
                point_id = "pp-" + sha256_bytes(stable_json(point_identity).encode("utf-8"))[:24]
                passage = next(item for item in passage_map.values() if item["source_passage_id"] == spid)
                focus = passage["plain_text"][start:end]
                point_status = "suppressed_candidate" if all(record["machine_status"] == "suppressed_candidate" for record in records) else "pending_candidate"
                all_locations_exact = all(record["source_location_status"] == "exact_source_lines" for record in records)
                source_md_start = min(int(record["source_md_line_start"]) for record in records) if all_locations_exact else None
                source_md_end = max(int(record["source_md_line_end"]) for record in records) if all_locations_exact else None
                para_start = group["paragraph_start"]
                para_end = group["paragraph_end"]
                trigger_spans = [{"claim_id": record["claim_candidate_id"], "start_cp": record["trigger_start_cp"],
                                  "end_cp": record["trigger_end_cp"]} for record in records]
                connection.execute("INSERT INTO proofreading_points VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", (
                    point_id, run_id, spid, source_md_start, source_md_end, para_start, para_end,
                    "exact_source_lines" if all_locations_exact else "passage_range_only",
                    stable_json(trigger_spans), start, end, trigger_start, trigger_end, focus,
                    group["segmentation_status"], point_status, "unreviewed",
                ))
                for claim_id in claim_ids:
                    connection.execute("INSERT INTO claim_case_links VALUES (?, ?, ?, ?, ?)", (
                        run_id, claim_id, point_id, group["link_method"], "machine_candidate",
                    ))
                    point_id_by_claim[claim_id] = point_id
                if group["segmentation_status"] == "bounded_markdown_paragraph_cluster":
                    relation_counts["bounded_paragraph_points"] += 1
                else:
                    relation_counts["local_cluster_points"] += 1
                if all_locations_exact:
                    relation_counts["points_with_exact_source_lines"] += 1
                point_count += 1

            relation_group_count = 0
            for group_key, items in sorted(relation_group_items.items(), key=lambda pair: repr(pair[0])):
                scope, relation_type, left, right, directionality, machine_status = group_key
                relation = items[0]["relation"]
                group_id = "rg-" + sha256_bytes(stable_json(group_key).encode("utf-8"))[:24]
                connection.execute("INSERT INTO relation_groups VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", (
                    run_id, group_id, scope, relation_type, left, right, directionality, machine_status,
                    str(relation.get("relation_label") or relation_type), relation.get("changed_from"), relation.get("changed_to"),
                ))
                for item in sorted(items, key=lambda row: row["claim_candidate_id"]):
                    connection.execute("INSERT INTO relation_group_claims VALUES (?, ?, ?)", (
                        run_id, group_id, item["claim_candidate_id"],
                    ))
                relation_group_count += 1

        if sha256_file(parser_path) != parser_sha:
            raise RuntimeError("relation_parser.py changed during the full build; refusing to activate the mixed run")
        if sha256_file(library_path) != library_sha:
            raise RuntimeError("machine_library.py changed during the full build; refusing to activate the mixed run")
        if sha256_file(source_db) != source_db_sha or sha256_file(term_db) != term_db_sha:
            raise RuntimeError("an input database changed during the full build")
        if identity_path.is_file() and input_manifest["identity_sha256"] != sha256_file(identity_path):
            raise RuntimeError("relation_identity.py changed during the full build")

        connection.execute("UPDATE parser_runs SET run_status='active' WHERE run_id=?", (run_id,))
        foreign_key_errors = connection.execute("PRAGMA foreign_key_check").fetchall()
        if foreign_key_errors:
            raise RuntimeError(f"foreign-key check failed: {foreign_key_errors[:10]}")
        quote_mismatches = connection.execute(
            """SELECT count(*) FROM claim_evidence e JOIN source_passages s ON s.source_passage_id=e.source_passage_id
               WHERE substr(s.plain_text, e.start_cp+1, e.end_cp-e.start_cp) != e.quote"""
        ).fetchone()[0]
        if quote_mismatches:
            raise RuntimeError(f"quote round-trip check failed for {quote_mismatches} rows")
        passage_counts = dict(connection.execute("SELECT work_key, count(*) FROM source_passages GROUP BY work_key"))
        candidate_counts_db = dict(connection.execute(
            "SELECT s.work_key, count(*) FROM case_passages c JOIN source_passages s USING(source_passage_id) GROUP BY s.work_key"
        ))
        claim_counts_by_work = dict(connection.execute(
            "SELECT s.work_key, count(*) FROM relation_claim_candidates c JOIN source_passages s USING(source_passage_id) GROUP BY s.work_key"
        ))
        if passage_counts != EXPECTED_WORK_COUNTS or sum(passage_counts.values()) != 7532:
            raise RuntimeError(f"source coverage check failed: {passage_counts}")
        if sum(candidate_counts_db.values()) != 6934:
            raise RuntimeError(f"case-passage candidate import mismatch: {candidate_counts_db}")
        content_sha = _canonical_db_hash(connection)
        connection.execute("UPDATE parser_runs SET content_sha256=? WHERE run_id=?", (content_sha, run_id))
        connection.execute("INSERT INTO metadata VALUES (?, ?)", ("content_sha256", stable_json(content_sha)))
        connection.commit()
        connection.execute("VACUUM")
    except Exception:
        connection.close()
        if temp_path.exists():
            temp_path.unlink()
        raise
    finally:
        connection.close()

    if db_path.exists():
        backup_path = log_dir / f"machine-library-rollback-{datetime.now().strftime('%Y%m%d-%H%M%S')}.sqlite3"
        shutil.copy2(db_path, backup_path)
    else:
        backup_path = None
    db_path.parent.mkdir(parents=True, exist_ok=True)
    os.replace(temp_path, db_path)
    inspect_connection = read_only_connection(db_path)
    try:
        term_form_count = inspect_connection.execute("SELECT count(*) FROM term_forms").fetchone()[0]
        active_point_count = _count(inspect_connection, "SELECT count(*) FROM proofreading_points WHERE run_id=? AND machine_status!='suppressed_candidate'", (run_id,))
        suppressed_point_count = _count(inspect_connection, "SELECT count(*) FROM proofreading_points WHERE run_id=? AND machine_status='suppressed_candidate'", (run_id,))
        active_group_count = _count(inspect_connection, "SELECT count(*) FROM relation_groups WHERE run_id=? AND machine_status!='suppressed_candidate'", (run_id,))
        suppressed_group_count = _count(inspect_connection, "SELECT count(*) FROM relation_groups WHERE run_id=? AND machine_status='suppressed_candidate'", (run_id,))
    finally:
        inspect_connection.close()
    counts = {
        "source_documents": len(source_docs), "source_passages": len(passage_rows),
        "case_passages": sum(candidate_counts.values()), "term_groups": group_count,
        "term_group_members": group_member_count,
        "term_forms": term_form_count,
        "relation_claims": relation_counts["claims"], "active_claims": relation_counts["pending_candidate"],
        "suppressed_claims": relation_counts["suppressed_candidate"], "evidence": relation_counts["evidence"],
        "endpoint_links": relation_counts["endpoint_links"], "proofreading_points": point_count,
        "active_proofreading_points": active_point_count,
        "suppressed_proofreading_points": suppressed_point_count,
        "active_relation_groups": active_group_count,
        "suppressed_relation_groups": suppressed_group_count,
        "unsegmented_claims": relation_counts["unsegmented_claims"], "relation_groups": relation_group_count,
        "claims_with_exact_source_lines": relation_counts["claims_with_exact_source_lines"],
        "points_with_exact_source_lines": relation_counts["points_with_exact_source_lines"],
        "bounded_paragraph_points": relation_counts["bounded_paragraph_points"],
        "local_cluster_points": relation_counts["local_cluster_points"],
        "quote_mismatches": quote_mismatches, "foreign_key_errors": len(foreign_key_errors),
        "passages_by_work": passage_counts, "case_passages_by_work": candidate_counts_db,
        "claims_by_work": claim_counts_by_work,
    }
    elapsed = round(time.perf_counter() - started, 3)
    result = {
        "available": True, "run": {"id": run_id, "parser_sha256": parser_sha,
                                     "machine_library_sha256": library_sha,
                                     "input_manifest_sha256": manifest_sha, "content_sha256": content_sha},
        "db": str(db_path), "size_bytes": db_path.stat().st_size, "elapsed_seconds": elapsed,
        "worker_count": worker_count, "counts": counts,
        "rollback_backup": str(backup_path) if backup_path else None,
        "log": str(log_path),
    }
    summary_path.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    with log_path.open("a", encoding="utf-8") as handle:
        handle.write(f"complete elapsed_s={elapsed:.3f} size_bytes={result['size_bytes']} content_sha256={content_sha}\n")
    return result


def passage_rows_for_workers(passage_rows: list[tuple[Any, ...]]) -> list[tuple[Any, ...]]:
    """Project the immutable source rows into the parser runner's compact tuple shape."""
    output = []
    for row in passage_rows:
        output.append((row[0], row[1], row[2], row[3], row[4], row[6], row[11]))
    return output


def _load_run(connection: sqlite3.Connection) -> sqlite3.Row:
    connection.row_factory = sqlite3.Row
    run_id_row = connection.execute("SELECT value_json FROM metadata WHERE key='active_run_id'").fetchone()
    if not run_id_row:
        raise RuntimeError("database has no active run")
    run_id = json.loads(run_id_row[0])
    row = connection.execute("SELECT * FROM parser_runs WHERE run_id=?", (run_id,)).fetchone()
    if not row:
        raise RuntimeError(f"active run not found: {run_id}")
    if row["run_status"] != "active":
        raise RuntimeError(f"active run pointer references a non-active run: {run_id} ({row['run_status']})")
    return row


def _count(connection: sqlite3.Connection, sql: str, params: tuple[Any, ...] = ()) -> int:
    return int(connection.execute(sql, params).fetchone()[0])


def meta(db_path: Path) -> dict[str, Any]:
    if not db_path.is_file():
        return {"available": False, "run": None, "counts": {}, "works": [], "relation_types": []}
    connection = read_only_connection(db_path)
    try:
        run = _load_run(connection)
        run_payload = {
            "id": run["run_id"], "parser_sha256": run["parser_sha256"],
            "machine_library_sha256": run["machine_library_sha256"],
            "input_manifest_sha256": run["input_manifest_sha256"],
            "source_database_sha256": run["source_database_sha256"],
            "term_group_database_sha256": run["term_group_database_sha256"],
            "created_at": run["created_at"], "worker_count": run["worker_count"],
            "modules": json.loads(run["modules_json"]), "status": run["run_status"],
            "content_sha256": run["content_sha256"],
        }
        work_items = []
        for work in connection.execute(
            """SELECT w.*, v.source_document_id, v.canonical_status
               FROM works w JOIN source_versions v USING(source_version_id) ORDER BY w.work_key"""
        ):
            key = work["work_key"]
            work_items.append({
                "work_key": key, "work_title": work["work_title"], "source_document_id": work["source_document_id"],
                "canonical_status": work["canonical_status"], "source_file": work["source_file"],
                "source_sha256": work["source_file_sha256"], "source_passage_count": work["source_passage_count"],
                "case_passage_count": work["case_passage_count"],
                "relation_claim_count": _count(connection, "SELECT count(*) FROM relation_claim_candidates c JOIN source_passages s USING(source_passage_id) WHERE c.run_id=? AND s.work_key=?", (run["run_id"], key)),
                "proofreading_point_count": _count(connection, "SELECT count(*) FROM proofreading_points p JOIN source_passages s USING(source_passage_id) WHERE p.run_id=? AND s.work_key=?", (run["run_id"], key)),
            })
        relation_types = [
            {"value": row[0], "label": row[1], "count": int(row[2]), "suppressed_count": int(row[3])}
            for row in connection.execute(
                """SELECT relation_type, min(relation_label),
                          sum(CASE WHEN machine_status!='suppressed_candidate' THEN 1 ELSE 0 END),
                          sum(CASE WHEN machine_status='suppressed_candidate' THEN 1 ELSE 0 END)
                   FROM relation_claim_candidates WHERE run_id=? GROUP BY relation_type ORDER BY relation_type""",
                (run["run_id"],),
            )
        ]
        counts = {
            "source_documents": _count(connection, "SELECT count(*) FROM source_versions"),
            "source_passages": _count(connection, "SELECT count(*) FROM source_passages"),
            "case_passages": _count(connection, "SELECT count(*) FROM case_passages WHERE run_id=?", (run["run_id"],)),
            "term_groups": _count(connection, "SELECT count(*) FROM term_groups WHERE run_id=?", (run["run_id"],)),
            "term_group_members": _count(connection, "SELECT count(*) FROM term_group_members m JOIN term_groups g USING(term_group_id) WHERE g.run_id=?", (run["run_id"],)),
            "term_forms": _count(connection, "SELECT count(*) FROM term_forms"),
            "relation_claims": _count(connection, "SELECT count(*) FROM relation_claim_candidates WHERE run_id=?", (run["run_id"],)),
            "active_claims": _count(connection, "SELECT count(*) FROM relation_claim_candidates WHERE run_id=? AND machine_status='pending_candidate'", (run["run_id"],)),
            "suppressed_claims": _count(connection, "SELECT count(*) FROM relation_claim_candidates WHERE run_id=? AND machine_status='suppressed_candidate'", (run["run_id"],)),
            "evidence": _count(connection, "SELECT count(*) FROM claim_evidence WHERE run_id=?", (run["run_id"],)),
            "endpoint_links": _count(connection, "SELECT count(*) FROM claim_endpoint_links WHERE run_id=?", (run["run_id"],)),
            "claims_with_exact_source_lines": _count(connection, "SELECT count(*) FROM relation_claim_candidates WHERE run_id=? AND source_location_status='exact_source_lines'", (run["run_id"],)),
            "proofreading_points": _count(connection, "SELECT count(*) FROM proofreading_points WHERE run_id=?", (run["run_id"],)),
            "points_with_exact_source_lines": _count(connection, "SELECT count(*) FROM proofreading_points WHERE run_id=? AND source_location_status='exact_source_lines'", (run["run_id"],)),
            "bounded_paragraph_points": _count(connection, "SELECT count(*) FROM proofreading_points WHERE run_id=? AND segmentation_status='bounded_markdown_paragraph_cluster'", (run["run_id"],)),
            "local_cluster_points": _count(connection, "SELECT count(*) FROM proofreading_points WHERE run_id=? AND segmentation_status='overlapping_claim_trigger_cluster'", (run["run_id"],)),
            "active_proofreading_points": _count(connection, "SELECT count(*) FROM proofreading_points WHERE run_id=? AND machine_status!='suppressed_candidate'", (run["run_id"],)),
            "suppressed_proofreading_points": _count(connection, "SELECT count(*) FROM proofreading_points WHERE run_id=? AND machine_status='suppressed_candidate'", (run["run_id"],)),
            "unsegmented_claims": _count(connection, "SELECT count(*) FROM relation_claim_candidates WHERE run_id=? AND claim_candidate_id NOT IN (SELECT claim_candidate_id FROM claim_case_links WHERE run_id=?)", (run["run_id"], run["run_id"])),
            "unsegmented_passages": _count(connection, """SELECT count(DISTINCT source_passage_id) FROM relation_claim_candidates c
                WHERE c.run_id=? AND c.claim_candidate_id NOT IN (SELECT claim_candidate_id FROM claim_case_links WHERE run_id=?)""", (run["run_id"], run["run_id"])),
            "relation_groups": _count(connection, "SELECT count(*) FROM relation_groups WHERE run_id=?", (run["run_id"],)),
            "active_relation_groups": _count(connection, "SELECT count(*) FROM relation_groups WHERE run_id=? AND machine_status!='suppressed_candidate'", (run["run_id"],)),
            "suppressed_relation_groups": _count(connection, "SELECT count(*) FROM relation_groups WHERE run_id=? AND machine_status='suppressed_candidate'", (run["run_id"],)),
        }
        return {"available": True, "run": run_payload, "counts": counts, "works": work_items,
                "relation_types": relation_types}
    finally:
        connection.close()


def _query_tokens(q: str) -> list[str]:
    return [unicodedata.normalize("NFKC", token) for token in str(q or "").split() if token]


def _endpoint_pair(claim: sqlite3.Row) -> tuple[str, str]:
    relation = dict(claim)
    _, _, left, right, _ = _relation_identity(relation)
    return left, right


def _matches_query(claim: sqlite3.Row, tokens: list[str], match: str, position: str = "any") -> tuple[bool, str]:
    if not tokens:
        return True, "both"
    left, right = _endpoint_pair(claim)
    left_norm = unicodedata.normalize("NFKC", left)
    right_norm = unicodedata.normalize("NFKC", right)
    target_forms = set(json.loads(claim["target_forms_json"] or "[]"))

    def allowed(token: str) -> bool:
        # Single Han glyphs must have been accepted as a parser target for this
        # persisted claim. This prevents a glyph inside a phonetic annotation
        # (for example the 反 in 都奚反) from becoming a main dictionary result.
        return len(token) != 1 or token in target_forms

    def on_left(token: str) -> bool:
        return allowed(token) and token in left_norm

    def on_right(token: str) -> bool:
        return allowed(token) and token in right_norm

    def in_position(token: str) -> bool:
        # Symmetric relations have no intrinsic source/result role. Do not let
        # the canonical display order arbitrarily hide one end of a loan pair.
        if claim["directionality"] == "symmetric" or position == "any":
            return on_left(token) or on_right(token)
        return on_left(token) if position == "source" else on_right(token)

    matched = all(in_position(token) for token in tokens) if match == "all" else any(in_position(token) for token in tokens)
    if not matched:
        return False, ""
    left_ok = any(on_left(token) for token in tokens)
    right_ok = any(on_right(token) for token in tokens)
    if left_ok and right_ok:
        return True, "both"
    return True, "left" if left_ok else "right"


def _relation_group_key(claim: sqlite3.Row) -> tuple[str, str, str, str, str, str]:
    identity = _relation_identity(dict(claim))
    return (*identity, str(claim["machine_status"]))


def _group_id(key: tuple[Any, ...]) -> str:
    return "rg-" + sha256_bytes(stable_json(key).encode("utf-8"))[:24]


def _location(passage: sqlite3.Row) -> str:
    ordinal = int(passage["local_ordinal"])
    start, end = passage["md_line_start"], passage["md_line_end"]
    if start is not None and end is not None and start != end:
        return f"段 {ordinal} · 来源段范围 行 {start}-{end}"
    if start is not None:
        return f"段 {ordinal} · 来源段范围 行 {start}"
    return f"段 {ordinal}"


def _value(record: sqlite3.Row | dict[str, Any], key: str) -> Any:
    if isinstance(record, dict):
        return record.get(key)
    try:
        return record[key]
    except (IndexError, KeyError, TypeError):
        return None


def _point_location(record: sqlite3.Row | dict[str, Any]) -> str:
    if (_value(record, "source_location_status") == "exact_source_lines"
            and _value(record, "source_md_line_start") is not None
            and _value(record, "source_md_line_end") is not None):
        start, end = int(record["source_md_line_start"]), int(record["source_md_line_end"])
        ordinal = int(record["local_ordinal"])
        return f"段 {ordinal} · 原文行 {start}" if start == end else f"段 {ordinal} · 原文行 {start}-{end}"
    return _location(record)


def _claim_location(record: sqlite3.Row | dict[str, Any]) -> str:
    if (_value(record, "source_location_status") == "exact_source_lines"
            and _value(record, "source_md_line_start") is not None
            and _value(record, "source_md_line_end") is not None):
        start, end = int(record["source_md_line_start"]), int(record["source_md_line_end"])
        ordinal = int(record["local_ordinal"])
        return f"段 {ordinal} · 原文行 {start}" if start == end else f"段 {ordinal} · 原文行 {start}-{end}"
    return _location(record)


def _get_claims(connection: sqlite3.Connection, run_id: str, query: dict[str, Any]) -> list[dict[str, Any]]:
    sql = """SELECT c.*, s.passage_id, s.work_key, s.local_ordinal, s.md_line_start, s.md_line_end,
                    w.work_title, p.proofreading_point_id,
                    p.issue_start_cp, p.issue_end_cp, p.focus_text, p.segmentation_status, p.human_status,
                    p.source_md_line_start, p.source_md_line_end, p.source_paragraph_start,
                    p.source_paragraph_end, p.source_location_status
             FROM relation_claim_candidates c
             JOIN source_passages s USING(source_passage_id)
             JOIN works w USING(work_key)
             LEFT JOIN claim_case_links cl ON cl.run_id=c.run_id AND cl.claim_candidate_id=c.claim_candidate_id
             LEFT JOIN proofreading_points p ON p.proofreading_point_id=cl.proofreading_point_id
             WHERE c.run_id=?"""
    params: list[Any] = [run_id]
    work_keys = query["work_keys"]
    if work_keys == ["none"]:
        return []
    if work_keys:
        marks = ",".join("?" for _ in work_keys)
        sql += f" AND s.work_key IN ({marks})"
        params.extend(work_keys)
    if query["relation_type"]:
        sql += " AND c.relation_type=?"
        params.append(query["relation_type"])
    sql += " ORDER BY s.work_key, s.local_ordinal, c.claim_start_cp, c.claim_candidate_id"
    rows = connection.execute(sql, params).fetchall()
    tokens = _query_tokens(query["q"])
    selected = []
    for row in rows:
        matches, query_side = _matches_query(row, tokens, query["match"], query.get("position", "any"))
        if matches:
            item = dict(row)
            item["query_side"] = query_side
            selected.append(item)
    return selected


def _claim_as_row(record: dict[str, Any]) -> sqlite3.Row:
    # A tiny stand-in is not needed: matching helpers accept mapping-like key access.
    return record  # type: ignore[return-value]


def _relation_card(records: list[dict[str, Any]]) -> dict[str, Any]:
    first = records[0]
    key = _relation_group_key(first)
    left, right = key[2], key[3]
    query_sides = {record["query_side"] for record in records}
    query_side = "both" if "both" in query_sides or len(query_sides) > 1 else next(iter(query_sides), "both")
    claims = sorted({record["claim_candidate_id"] for record in records})
    cues = sorted({str(record["relation_cue"]) for record in records if record.get("relation_cue")})
    context_forms = []
    seen_contexts = set()
    claim_cues = []
    for record in sorted(records, key=lambda x: x["claim_candidate_id"]):
        raw_pair = (str(record["left_form"] or ""), str(record["right_form"] or ""))
        claim_cues.append({
            "claim_id": record["claim_candidate_id"], "relation_cue": record.get("relation_cue"),
            "left_form": raw_pair[0], "right_form": raw_pair[1],
            "directionality": record.get("directionality"), "author_stance": record.get("author_stance"),
        })
        if raw_pair not in seen_contexts and raw_pair != (left, right):
            seen_contexts.add(raw_pair)
            context_forms.append({"claim_id": record["claim_candidate_id"], "left_form": raw_pair[0], "right_form": raw_pair[1]})
    group_id = _group_id(key)
    return {
        "id": group_id, "left_form": left, "right_form": right,
        "relation_type": first["relation_type"], "relation_label": first["relation_label"],
        "directionality": first["directionality"], "query_side": query_side,
        "identity_scope": key[0], "relation_cue": cues[0] if len(cues) == 1 else None,
        "cues": cues, "relation_cues": cues, "context_forms": context_forms,
        "claim_cues": claim_cues,
        "changed_from": first["changed_from"], "changed_to": first["changed_to"],
        "author_stance": "mixed" if len({r["author_stance"] for r in records}) > 1 else first["author_stance"],
        "machine_status": first["machine_status"], "claim_ids": claims,
        "_records": records,
    }


def _case_dict_from_records(records: list[dict[str, Any]], case_id: str, *, unsegmented: bool = False) -> dict[str, Any]:
    first = records[0]
    point_start = first.get("issue_start_cp")
    point_end = first.get("issue_end_cp")
    if not unsegmented and point_start is not None and point_end is not None:
        quote = str(first.get("focus_text") or "")
        start = int(point_start)
        end = int(point_end)
    else:
        start = int(first["claim_start_cp"])
        end = int(first["claim_end_cp"])
        quote = str(first.get("quote") or "")
    return {
        "id": case_id, "work_key": first["work_key"], "work_title": first["work_title"],
        "passage_id": first["passage_id"], "source_passage_id": first["source_passage_id"],
        "location": _point_location(first), "location_status": first.get("source_location_status", "passage_range_only"),
        "source_md_line_start": first.get("source_md_line_start"),
        "source_md_line_end": first.get("source_md_line_end"), "quote": quote,
        "claim_ids": sorted({r["claim_candidate_id"] for r in records}),
        "issue_span": {"start_cp": start, "end_cp": end},
        "segmentation_status": "unsegmented_passage" if unsegmented else first["segmentation_status"],
        "human_status": "unreviewed" if unsegmented else first.get("human_status", "unreviewed"),
    }


def _unsegmented_dict(records: list[dict[str, Any]]) -> dict[str, Any]:
    first = records[0]
    snippets = []
    seen = set()
    for record in sorted(records, key=lambda x: (x["claim_start_cp"], x["claim_candidate_id"])):
        key = (record["claim_candidate_id"], record["quote"])
        if key in seen:
            continue
        seen.add(key)
        snippets.append({"claim_id": record["claim_candidate_id"], "quote": record["quote"],
                         "claim_span": {"start_cp": record["claim_start_cp"], "end_cp": record["claim_end_cp"]}})
    return {
        "id": "up-" + str(first["source_passage_id"]), "work_key": first["work_key"],
        "work_title": first["work_title"], "passage_id": first["passage_id"],
        "source_passage_id": first["source_passage_id"], "location": _location(first),
        "segmentation_status": "unsegmented_passage", "claim_ids": sorted({r["claim_candidate_id"] for r in records}),
        "claim_quotes": snippets,
    }


def _search_mentions(connection: sqlite3.Connection, query: dict[str, Any], run_id: str, matched_claim_ids: set[str]) -> dict[str, Any]:
    if not query["include_mentions"]:
        return {"total": 0, "items": []}
    tokens = _query_tokens(query["q"])
    if not tokens or query["work_keys"] == ["none"]:
        return {"total": 0, "items": []}
    sql = "SELECT s.*, w.work_title FROM source_passages s JOIN works w USING(work_key)"
    params: list[Any] = []
    if query["work_keys"]:
        marks = ",".join("?" for _ in query["work_keys"])
        sql += f" WHERE s.work_key IN ({marks})"
        params.extend(query["work_keys"])
    if query["relation_type"]:
        conjunction = " AND " if " WHERE " in sql else " WHERE "
        sql += conjunction + "EXISTS (SELECT 1 FROM relation_claim_candidates c WHERE c.run_id=? AND c.source_passage_id=s.source_passage_id AND c.relation_type=?)"
        params.extend([run_id, query["relation_type"]])
    sql += " ORDER BY s.work_key, s.local_ordinal, s.passage_id"
    items = []
    for passage in connection.execute(sql, params):
        text = passage["plain_text"] or ""
        positions = [text.find(token) for token in tokens]
        if query["match"] == "all":
            matched = all(pos >= 0 for pos in positions)
        else:
            matched = any(pos >= 0 for pos in positions)
        if not matched:
            continue
        chosen = min((pos for pos in positions if pos >= 0), default=0)
        original = passage["plain_text"] or ""
        start = max(0, chosen - 60)
        end = min(len(original), chosen + max((len(token) for token in tokens), default=1) + 60)
        main_claims = [row[0] for row in connection.execute(
            "SELECT claim_candidate_id FROM relation_claim_candidates WHERE run_id=? AND source_passage_id=?",
            (run_id, passage["source_passage_id"]),
        ) if row[0] in matched_claim_ids]
        items.append({
            "id": "mention-" + sha256_bytes(stable_json([passage["source_passage_id"], tokens, query["match"]]).encode("utf-8"))[:24],
            "work_key": passage["work_key"], "work_title": passage["work_title"],
            "passage_id": passage["passage_id"], "location": _location(passage),
            "quote": original[start:end], "mention_span": {"start_cp": start, "end_cp": end},
            "main_claim_overlap": bool(main_claims),
        })
    items.sort(key=lambda x: (x["work_key"], x["passage_id"]))
    return {"total": len(items), "items": items[:20]}


def search(db_path: Path, query_value: dict[str, Any]) -> dict[str, Any]:
    if not db_path.is_file():
        view = str(query_value.get("view") or "terms")
        page = max(1, int(query_value.get("page") or 1))
        page_size = min(10, max(1, int(query_value.get("page_size") or 10)))
        return {
            "available": False, "run": None, "query": query_value, "view": view,
            "page": page, "page_size": page_size, "total": 0, "total_pages": 0,
            "matched_claim_count": 0, "matched_claim_ids": [], "relation_group_count": 0,
            "case_count": 0, "items": [], "unsegmented_passage_count": 0,
            "unsegmented": {"total": 0, "items": []}, "suppressed_claim_count": 0,
            "suppressed": {"total": 0, "items": []}, "mentions": {"total": 0, "items": []},
        }
    view = str(query_value.get("view") or "terms")
    match = str(query_value.get("match") or "all")
    position = str(query_value.get("position") or "any")
    if view not in {"terms", "cases"}:
        raise ValueError("view must be 'terms' or 'cases'")
    if match not in {"all", "any"}:
        raise ValueError("match must be 'all' or 'any'")
    if position not in {"any", "source", "target"}:
        raise ValueError("position must be 'any', 'source' or 'target'")
    raw_work_keys = query_value.get("work_keys") or []
    if isinstance(raw_work_keys, str):
        raw_work_keys = [raw_work_keys]
    work_keys = sorted(set(str(x) for x in raw_work_keys if str(x)))
    if "none" in work_keys:
        work_keys = ["none"]
    include_mentions_value = query_value.get("include_mentions", False)
    include_mentions = include_mentions_value is True or str(include_mentions_value).lower() in {"1", "true", "yes"}
    query = {
        "q": str(query_value.get("q") or "").strip(), "view": view, "match": match, "position": position,
        "work_keys": work_keys, "relation_type": str(query_value.get("relation_type") or ""),
        "page": max(1, int(query_value.get("page") or 1)),
        "page_size": min(10, max(1, int(query_value.get("page_size") or 10))),
        "include_mentions": include_mentions,
    }
    connection = read_only_connection(db_path)
    try:
        run = _load_run(connection)
        run_payload = {"id": run["run_id"], "parser_sha256": run["parser_sha256"], "machine_library_sha256": run["machine_library_sha256"], "input_manifest_sha256": run["input_manifest_sha256"]}
        selected_all = _get_claims(connection, run["run_id"], query)
        suppressed_matches = [record for record in selected_all if record["machine_status"] == "suppressed_candidate"]
        nonsuppressed = [record for record in selected_all if record["machine_status"] != "suppressed_candidate"]
        selected = [record for record in nonsuppressed if record.get("proofreading_point_id")]
        selected_unsegmented = [record for record in nonsuppressed if not record.get("proofreading_point_id")]
        matched_claim_ids = sorted({r["claim_candidate_id"] for r in selected})
        matched_set = set(matched_claim_ids)
        grouped_relations: dict[tuple[Any, ...], list[dict[str, Any]]] = defaultdict(list)
        for record in selected:
            grouped_relations[_relation_group_key(record)].append(record)
        relation_cards = {key: _relation_card(records) for key, records in grouped_relations.items()}

        point_records: dict[str, list[dict[str, Any]]] = defaultdict(list)
        unsegmented_records: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for record in selected:
            point_records[str(record["proofreading_point_id"])].append(record)
        for record in selected_unsegmented:
            unsegmented_records[str(record["source_passage_id"])].append(record)

        if view == "terms":
            items = []
            for key in sorted(relation_cards, key=repr):
                card = relation_cards[key]
                linked_cases: dict[str, list[dict[str, Any]]] = defaultdict(list)
                for record in card.pop("_records"):
                    point_id = record.get("proofreading_point_id")
                    if point_id:
                        linked_cases[str(point_id)].append(record)
                cases = []
                for case_id, records in linked_cases.items():
                    case = _case_dict_from_records(records, case_id)
                    cases.append({k: case[k] for k in ("id", "work_key", "work_title", "passage_id", "location", "location_status", "source_md_line_start", "source_md_line_end", "quote", "claim_ids", "segmentation_status", "human_status")})
                card["cases"] = sorted(cases, key=lambda x: (x["work_key"], x["passage_id"], x["id"]))
                items.append(card)
            side_rank = {"left": 0, "both": 0, "right": 1}
            items.sort(key=lambda item: (side_rank.get(item["query_side"], 0), item["left_form"], item["right_form"], item["relation_type"], item["id"]))
            total = len(items)
        else:
            items = []
            for point_id, records in point_records.items():
                case = _case_dict_from_records(records, point_id)
                relation_list = []
                records_by_relation: dict[tuple[Any, ...], list[dict[str, Any]]] = defaultdict(list)
                for record in records:
                    records_by_relation[_relation_group_key(record)].append(record)
                for key in sorted(records_by_relation, key=repr):
                    relation = _relation_card(records_by_relation[key])
                    relation.pop("_records", None)
                    relation_list.append(relation)
                case["relations"] = relation_list
                items.append(case)
            items.sort(key=lambda x: (x["work_key"], x["passage_id"], x["issue_span"]["start_cp"], x["id"]))
            total = len(items)

        unsegmented_items = []
        for source_passage_id, records in sorted(unsegmented_records.items()):
            card = _unsegmented_dict(records)
            relation_list = []
            unsegmented_by_relation: dict[tuple[Any, ...], list[dict[str, Any]]] = defaultdict(list)
            for record in records:
                unsegmented_by_relation[_relation_group_key(record)].append(record)
            for key in sorted(unsegmented_by_relation, key=repr):
                relation = _relation_card(unsegmented_by_relation[key])
                relation.pop("_records", None)
                relation_list.append(relation)
            card["relations"] = relation_list
            unsegmented_items.append(card)

        suppressed_items = []
        for record in sorted(suppressed_matches, key=lambda r: (r["work_key"], r["passage_id"], r["claim_start_cp"], r["claim_candidate_id"])):
            display_left, display_right = _endpoint_pair(record)
            suppressed_items.append({
                "claim_id": record["claim_candidate_id"], "work_key": record["work_key"],
                "work_title": record["work_title"], "passage_id": record["passage_id"],
                "location": _claim_location(record), "quote": record["quote"],
                "relation_type": record["relation_type"], "relation_label": record["relation_label"],
                "relation_cue": record["relation_cue"], "left_form": display_left,
                "right_form": display_right, "source_left_form": record["left_form"],
                "source_right_form": record["right_form"], "directionality": record["directionality"],
                "author_stance": record["author_stance"], "machine_status": record["machine_status"],
            })

        relation_group_count = len(grouped_relations)
        case_count = len(point_records)
        page_size = query["page_size"]
        page = query["page"]
        total_pages = math.ceil(total / page_size) if total else 0
        start = (page - 1) * page_size
        paged = items[start:start + page_size]
        mentions = _search_mentions(connection, query, run["run_id"], matched_set)
        return {
            "available": True, "run": run_payload, "query": query, "view": view,
            "page": page, "page_size": page_size, "total": total, "total_pages": total_pages,
            "matched_claim_count": len(matched_claim_ids), "matched_claim_ids": matched_claim_ids,
            "unsegmented_claim_count": len({r["claim_candidate_id"] for r in selected_unsegmented}),
            "suppressed_claim_count": len(suppressed_matches),
            "relation_group_count": relation_group_count, "case_count": case_count,
            "unsegmented_passage_count": len(unsegmented_records), "unsegmented": {"total": len(unsegmented_items), "items": unsegmented_items[:10]},
            "suppressed": {"total": len(suppressed_items), "items": suppressed_items[:10]},
            "items": paged,
            "mentions": mentions,
        }
    finally:
        connection.close()


def detail(db_path: Path, object_id: str) -> dict[str, Any]:
    if not db_path.is_file():
        return {"available": False, "id": object_id}
    connection = read_only_connection(db_path)
    try:
        run = _load_run(connection)
        run_id = run["run_id"]
        if object_id.startswith("mc-"):
            row = connection.execute(
                """SELECT c.*, s.passage_id, s.work_key, s.local_ordinal, s.md_line_start, s.md_line_end,
                          s.plain_text, s.raw_text, w.work_title
                   FROM relation_claim_candidates c JOIN source_passages s USING(source_passage_id)
                   JOIN works w USING(work_key) WHERE c.run_id=? AND c.claim_candidate_id=?""",
                (run_id, object_id),
            ).fetchone()
            if not row:
                return {"available": True, "id": object_id, "found": False}
            claim = dict(row)
            point = connection.execute(
                """SELECT p.* FROM proofreading_points p JOIN claim_case_links l USING(proofreading_point_id)
                   WHERE l.run_id=? AND l.claim_candidate_id=? LIMIT 1""", (run_id, object_id),
            ).fetchone()
            evidence = [dict(x) for x in connection.execute("SELECT * FROM claim_evidence WHERE run_id=? AND claim_candidate_id=? ORDER BY start_cp", (run_id, object_id))]
            links = [dict(x) for x in connection.execute("SELECT * FROM claim_endpoint_links WHERE run_id=? AND claim_candidate_id=? ORDER BY endpoint_role, span_start_cp", (run_id, object_id))]
            start, end = int(claim["claim_start_cp"]), int(claim["claim_end_cp"])
            source = {"work_key": claim["work_key"], "work_title": claim["work_title"], "passage_id": claim["passage_id"],
                      "source_passage_id": claim["source_passage_id"], "location": _claim_location(row),
                      "raw_text": claim["raw_text"], "plain_text": claim["plain_text"]}
            plain = claim["plain_text"] or ""
            context = {"before": plain[max(0, start - 200):start], "focus": plain[start:end],
                       "after": plain[end:min(len(plain), end + 200)], "span": {"start_cp": start, "end_cp": end}}
            return {"available": True, "found": True, "id": object_id, "type": "claim", "run": {"id": run_id, "parser_sha256": run["parser_sha256"], "machine_library_sha256": run["machine_library_sha256"], "input_manifest_sha256": run["input_manifest_sha256"]}, "claim": claim, "proofreading_point": dict(point) if point else None, "source": source, "context": context, "evidence": evidence, "endpoint_links": links}
        if object_id.startswith("pp-"):
            row = connection.execute(
                """SELECT p.*, s.passage_id, s.work_key, s.local_ordinal, s.md_line_start, s.md_line_end,
                          s.plain_text, s.raw_text, w.work_title
                   FROM proofreading_points p JOIN source_passages s USING(source_passage_id)
                   JOIN works w USING(work_key) WHERE p.run_id=? AND p.proofreading_point_id=?""",
                (run_id, object_id),
            ).fetchone()
            if not row:
                return {"available": True, "found": False, "id": object_id}
            claims = [dict(x) for x in connection.execute(
                "SELECT * FROM relation_claim_candidates WHERE run_id=? AND claim_candidate_id IN (SELECT claim_candidate_id FROM claim_case_links WHERE proofreading_point_id=?) ORDER BY claim_start_cp, claim_candidate_id",
                (run_id, object_id),
            )]
            start, end = int(row["issue_start_cp"]), int(row["issue_end_cp"])
            plain = row["plain_text"] or ""
            location = _location(row)
            source = {"work_key": row["work_key"], "work_title": row["work_title"], "passage_id": row["passage_id"],
                      "source_passage_id": row["source_passage_id"], "location": _point_location(row),
                      "passage_location": location,
                      "raw_text": row["raw_text"], "plain_text": plain}
            context = {"before": plain[max(0, start - 200):start], "focus": plain[start:end],
                       "after": plain[end:min(len(plain), end + 200)], "span": {"start_cp": start, "end_cp": end}}
            return {"available": True, "found": True, "id": object_id, "type": "proofreading_point", "run": {"id": run_id, "parser_sha256": run["parser_sha256"], "machine_library_sha256": run["machine_library_sha256"], "input_manifest_sha256": run["input_manifest_sha256"]}, "proofreading_point": dict(row), "source": source, "context": context, "claims": claims}
        if object_id.startswith("rg-"):
            row = connection.execute("SELECT * FROM relation_groups WHERE run_id=? AND relation_group_id=?", (run_id, object_id)).fetchone()
            if not row:
                return {"available": True, "found": False, "id": object_id}
            claims = [dict(x) for x in connection.execute(
                "SELECT * FROM relation_claim_candidates WHERE run_id=? AND claim_candidate_id IN (SELECT claim_candidate_id FROM relation_group_claims WHERE run_id=? AND relation_group_id=?) ORDER BY claim_candidate_id",
                (run_id, run_id, object_id),
            )]
            return {"available": True, "found": True, "id": object_id, "type": "relation_group", "run": {"id": run_id, "parser_sha256": run["parser_sha256"], "machine_library_sha256": run["machine_library_sha256"], "input_manifest_sha256": run["input_manifest_sha256"]}, "relation_group": dict(row), "claims": claims}
        if object_id.startswith("up-"):
            source_passage_id = object_id[3:]
            passage = connection.execute(
                "SELECT s.*, w.work_title FROM source_passages s JOIN works w USING(work_key) WHERE s.source_passage_id=?",
                (source_passage_id,),
            ).fetchone()
            if not passage:
                return {"available": True, "found": False, "id": object_id}
            claims = [dict(x) for x in connection.execute("SELECT * FROM relation_claim_candidates WHERE run_id=? AND source_passage_id=? ORDER BY claim_start_cp", (run_id, source_passage_id))]
            return {"available": True, "found": True, "id": object_id, "type": "unsegmented_passage",
                    "run": {"id": run_id, "parser_sha256": run["parser_sha256"], "machine_library_sha256": run["machine_library_sha256"], "input_manifest_sha256": run["input_manifest_sha256"]},
                    "passage": dict(passage), "claims": claims}
        if object_id.startswith("new-parsebench-c3:"):
            passage_alias = object_id.split(":", 1)[1]
        else:
            passage_alias = object_id
        passage = connection.execute(
            """SELECT s.*, w.work_title FROM source_passages s JOIN works w USING(work_key)
               WHERE s.passage_id=?""", (passage_alias,),
        ).fetchone()
        if passage:
            points = [dict(x) for x in connection.execute(
                "SELECT * FROM proofreading_points WHERE run_id=? AND source_passage_id=? ORDER BY issue_start_cp, proofreading_point_id",
                (run_id, passage["source_passage_id"]),
            )]
            claims = [dict(x) for x in connection.execute(
                "SELECT * FROM relation_claim_candidates WHERE run_id=? AND source_passage_id=? ORDER BY claim_start_cp, claim_candidate_id",
                (run_id, passage["source_passage_id"]),
            )]
            return {"available": True, "found": True, "id": object_id, "type": "source_passage",
                    "run": {"id": run_id, "parser_sha256": run["parser_sha256"], "machine_library_sha256": run["machine_library_sha256"], "input_manifest_sha256": run["input_manifest_sha256"]},
                    "source": {**dict(passage), "location": _location(passage)},
                    "proofreading_points": points, "claims": claims}
        return {"available": True, "found": False, "id": object_id}
    finally:
        connection.close()


def _emit(value: Any) -> None:
    print(json.dumps(value, ensure_ascii=False, separators=(",", ":")))


def main() -> None:
    parser = argparse.ArgumentParser(description="Build and query the independent four-book machine library")
    sub = parser.add_subparsers(dest="command", required=True)
    build_parser = sub.add_parser("build", help="read-only source import plus complete direct relation extraction")
    build_parser.add_argument("--input-db", type=Path, default=DEFAULT_SOURCE_DB)
    build_parser.add_argument("--term-db", type=Path, default=DEFAULT_TERM_DB)
    build_parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    build_parser.add_argument("--log-dir", type=Path, default=DEFAULT_LOG_DIR)
    build_parser.add_argument("--workers", type=int, default=4)
    meta_parser = sub.add_parser("meta", help="show active machine run and per-layer counts")
    meta_parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    search_parser = sub.add_parser("search", help="search the persisted claim run in term or case view")
    search_parser.add_argument("--query-json", required=True)
    search_parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    detail_parser = sub.add_parser("detail", help="load a claim, relation group, case point, or unsegmented passage")
    detail_parser.add_argument("--id", required=True)
    detail_parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    args = parser.parse_args()
    if args.command == "build":
        _emit(build_database(source_db=args.input_db, term_db=args.term_db, db_path=args.db, log_dir=args.log_dir, workers=args.workers))
    elif args.command == "meta":
        _emit(meta(args.db))
    elif args.command == "search":
        _emit(search(args.db, json.loads(args.query_json)))
    elif args.command == "detail":
        _emit(detail(args.db, args.id))


if __name__ == "__main__":
    main()
