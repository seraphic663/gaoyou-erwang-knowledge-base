#!/usr/bin/env python3
"""Audit which legacy dictionary.db fields and rows are represented in V2.

This is a read-only audit.  It does not rebuild either database and does not
interpret legacy machine status or certainty as human review.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
from collections import Counter
from pathlib import Path
from typing import Any, Iterable


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_MAIN_DB = PROJECT_ROOT / "02-数据库" / "data" / "dictionary.db"
DEFAULT_V2_DB = PROJECT_ROOT / "v2" / "data" / "real_runs" / "annotation_v2.db"
DEFAULT_OUTPUT = PROJECT_ROOT / "v2" / "data" / "real_runs" / "legacy_dictionary_field_audit.json"


def open_read_only(path: Path) -> sqlite3.Connection:
    connection = sqlite3.connect(f"file:{path.resolve()}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    return connection


def rows(connection: sqlite3.Connection, query: str, parameters: Iterable[Any] = ()) -> list[dict[str, Any]]:
    return [dict(row) for row in connection.execute(query, tuple(parameters)).fetchall()]


def parse_json(value: Any, default: Any) -> Any:
    if value is None or value == "":
        return default
    if isinstance(value, (list, dict)):
        return value
    try:
        return json.loads(value)
    except (TypeError, ValueError):
        return default


def count_filled(records: list[dict[str, Any]], field: str) -> int:
    return sum(bool(str(record.get(field) or "").strip()) for record in records)


def field_population(records: list[dict[str, Any]], fields: list[str]) -> dict[str, dict[str, Any]]:
    total = len(records)
    return {
        field: {
            "filled": count_filled(records, field),
            "empty": total - count_filled(records, field),
            "total": total,
        }
        for field in fields
    }


def main_report(connection: sqlite3.Connection) -> dict[str, Any]:
    works = rows(connection, "SELECT * FROM works ORDER BY id")
    terms = rows(connection, "SELECT * FROM terms ORDER BY id")
    cases = rows(connection, "SELECT * FROM cases ORDER BY id")
    evidences = rows(connection, "SELECT * FROM evidences ORDER BY id")

    used_term_ids: set[int] = set()
    legacy_case_term_relations: set[tuple[int, int]] = set()
    for case in cases:
        for term_id in parse_json(case.get("term_ids"), []):
            if str(term_id).isdigit():
                used_term_ids.add(int(term_id))
                legacy_case_term_relations.add((int(case["id"]), int(term_id)))
    used_term_ids.update(
        int(evidence["term_id"])
        for evidence in evidences
        if evidence.get("term_id") is not None
    )

    work_titles = {int(work["id"]): str(work.get("title") or "") for work in works}
    cited_work_counts = Counter(
        work_titles.get(int(evidence["work_id"]), f"work_id:{evidence['work_id']}")
        for evidence in evidences
        if evidence.get("work_id") is not None
    )
    used_work_ids = {
        int(evidence["work_id"])
        for evidence in evidences
        if evidence.get("work_id") is not None
    }

    return {
        "database_type": "SQLite",
        "counts": {
            "works": len(works),
            "passages": int(connection.execute("SELECT COUNT(*) FROM passages").fetchone()[0]),
            "terms": len(terms),
            "cases": len(cases),
            "evidences": len(evidences),
        },
        "field_population": {
            "terms": field_population(
                terms,
                ["term", "term_type", "category", "aliases", "notes", "core_meaning", "case_ids"],
            ),
            "cases": field_population(
                cases,
                [
                    "title",
                    "section_title",
                    "volume_title",
                    "term_ids",
                    "erwang_passage_id",
                    "target_passage_id",
                    "problem",
                    "method",
                    "process_text",
                    "conclusion",
                    "certainty",
                    "status",
                ],
            ),
            "evidences": field_population(
                evidences,
                [
                    "case_id",
                    "term_id",
                    "source_passage_id",
                    "work_id",
                    "evidence_type",
                    "quote_text",
                    "core_snippet",
                    "note",
                ],
            ),
        },
        "controlled_values": {
            "term_type": dict(Counter(term.get("term_type") for term in terms)),
            "term_category": dict(Counter(term.get("category") for term in terms)),
            "evidence_type": dict(Counter(evidence.get("evidence_type") for evidence in evidences)),
            "case_certainty": dict(Counter(case.get("certainty") for case in cases)),
            "case_status": dict(Counter(case.get("status") for case in cases)),
        },
        "row_usage": {
            "terms_used_by_case_or_evidence": len(used_term_ids),
            "case_term_relation_count": len(legacy_case_term_relations),
            "terms_unused": len(terms) - len(used_term_ids),
            "unused_term_ids": [
                {"id": term["id"], "term": term.get("term")}
                for term in terms
                if int(term["id"]) not in used_term_ids
            ],
            "works_used_by_evidence": len(used_work_ids),
            "works_unreferenced": len(works) - len(used_work_ids),
            "unreferenced_works": [
                {"id": work["id"], "title": work.get("title")}
                for work in works
                if int(work["id"]) not in used_work_ids
            ],
        },
        "domain_signals": {
            "方言_evidence_count": cited_work_counts.get("方言", 0),
            "声训_evidence_count": sum(evidence.get("evidence_type") == "声训" for evidence in evidences),
            "异文_evidence_count": sum(evidence.get("evidence_type") == "异文" for evidence in evidences),
            "同义实词_term_count": sum(term.get("category") == "同义实词" for term in terms),
            "方言俗语_term_count": sum(term.get("category") == "方言俗语" for term in terms),
            "音训·通假字_term_count": sum(term.get("category") == "音训·通假字" for term in terms),
            "top_cited_works": [
                {"title": title, "evidence_count": count}
                for title, count in cited_work_counts.most_common(20)
            ],
        },
    }


def v2_report(connection: sqlite3.Connection) -> dict[str, Any]:
    table_names = [
        "source_documents",
        "source_version_registry",
        "passages",
        "candidate_items",
        "annotation_cases",
        "annotation_terms",
        "annotation_evidences",
        "annotation_process_steps",
        "external_source_registry",
        "legacy_catalog_terms",
        "legacy_catalog_works",
    ]
    term_ids: set[int] = set()
    legacy_case_term_relations: set[tuple[int, int]] = set()
    term_categories = Counter()
    for row in rows(connection, "SELECT term_json FROM annotation_terms"):
        data = parse_json(row.get("term_json"), {})
        if data.get("legacy_term_id") is not None:
            term_ids.add(int(data["legacy_term_id"]))
        if data.get("legacy_term_category"):
            term_categories[str(data["legacy_term_category"])] += 1

    for row in rows(
        connection,
        "SELECT case_id, term_json FROM annotation_terms WHERE case_id LIKE 'legacy-dictionary:%'",
    ):
        data = parse_json(row.get("term_json"), {})
        if data.get("legacy_term_id") is not None:
            legacy_case_term_relations.add((int(row["case_id"].split(":")[-1]), int(data["legacy_term_id"])))

    return {
        "counts": {
            table: int(connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])
            for table in table_names
        },
        "source_documents_by_work": [
            dict(row)
            for row in connection.execute(
                "SELECT work_key, source_kind, canonical_status, COUNT(*) AS count "
                "FROM source_documents GROUP BY work_key, source_kind, canonical_status ORDER BY work_key"
            ).fetchall()
        ],
        "passages_by_work": [
            dict(row)
            for row in connection.execute(
                "SELECT work_key, COUNT(*) AS count FROM passages GROUP BY work_key ORDER BY work_key"
            ).fetchall()
        ],
        "candidates_by_origin": [
            dict(row)
            for row in connection.execute(
                "SELECT origin, COUNT(*) AS count FROM candidate_items GROUP BY origin ORDER BY origin"
            ).fetchall()
        ],
        "cases_by_origin": [
            dict(row)
            for row in connection.execute(
                "SELECT origin, source_work, COUNT(*) AS count "
                "FROM annotation_cases GROUP BY origin, source_work ORDER BY origin, source_work"
            ).fetchall()
        ],
        "legacy_term_mapping": {
            "unique_legacy_term_ids_in_annotation_terms": len(term_ids),
            "legacy_case_term_relation_count": len(legacy_case_term_relations),
            "categories_seen_in_term_json": dict(term_categories),
        },
        "case_field_completion": {
            field: int(connection.execute(
                "SELECT COUNT(*) FROM annotation_cases "
                f"WHERE {field} IS NOT NULL AND TRIM(CAST({field} AS TEXT)) <> ''"
            ).fetchone()[0])
            for field in ("source_passage_id", "target_passage_id", "process_text", "target_work", "target_text")
        },
        "evidence_resolution": [
            dict(row)
            for row in connection.execute(
                "SELECT json_extract(evidence_json, '$.source_resolution') AS source_resolution, "
                "quote_check, COUNT(*) AS count "
                "FROM annotation_evidences GROUP BY source_resolution, quote_check "
                "ORDER BY source_resolution, quote_check"
            ).fetchall()
        ],
        "source_versions": [
            dict(row)
            for row in connection.execute(
                "SELECT work_key, source_file, source_file_sha256, canonical_status, "
                "superseded_by_sha256 FROM source_version_registry ORDER BY work_key, canonical_status"
            ).fetchall()
        ],
    }


def build_report(main_db: Path, v2_db: Path) -> dict[str, Any]:
    with open_read_only(main_db) as main_connection, open_read_only(v2_db) as v2_connection:
        return {
            "report_version": "legacy_dictionary_field_audit.v1",
            "scope": {
                "main_database": str(main_db.relative_to(PROJECT_ROOT)),
                "v2_database": str(v2_db.relative_to(PROJECT_ROOT)),
                "read_only": True,
            },
            "main_dictionary": main_report(main_connection),
            "v2_representation": v2_report(v2_connection),
            "interpretation": {
                "fully_ingested_rows": [
                    "旧 dictionary.db 的 815 cases",
                    "旧 dictionary.db 的 7,120 evidences",
                    "被 cases/evidences 使用的 3,371 terms",
                    "被 evidences 使用的 37 works",
                    "四部王氏 Markdown 抽取的 6,749 candidate_items",
                ],
                "catalog_only_rows": [
                    "14 个未被旧案例/证据使用的 terms",
                    "12 个未被旧证据引用的 works",
                ],
                "not_semantic_canonicalization": [
                    "旧 source.txt、dictionary.db 派生文本进入 legacy passage，不是 canonical 原典 passage",
                    "旧 certainty/status 只保留为迁移元数据，未升级 human review 或 gold",
                    "四部原典的 6,749 candidates 尚未全部生成 annotation_case；当前只有 4 条 original_markdown_ai 代表案例",
                ],
                "known_main_database_gaps": [
                    "main dictionary.db 的 passages 表为空",
                    "main cases 的 erwang_passage_id、target_passage_id、process_text 全部为空",
                    "main evidences 的 source_passage_id 全部为空",
                ],
            },
        }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--main-db", type=Path, default=DEFAULT_MAIN_DB)
    parser.add_argument("--v2-db", type=Path, default=DEFAULT_V2_DB)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()

    report = build_report(args.main_db.resolve(), args.v2_db.resolve())
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"ok": True, "output": str(args.output), "report_version": report["report_version"]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
