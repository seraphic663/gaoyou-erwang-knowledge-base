#!/usr/bin/env python3
"""Read-only API bridge for the V2/VR acceptance page.

The website intentionally does not import the V2 writer.  Every command opens
annotation_v2.db with SQLite's read-only URI and query_only enabled, then
prints one JSON response for the Node server.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
from collections import Counter
from pathlib import Path
from typing import Any


WORKSPACE_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DB = WORKSPACE_ROOT / "v2" / "data" / "real_runs" / "annotation_v2.db"
REPORT_FILE = WORKSPACE_ROOT / "v2" / "data" / "real_runs" / "batch_migration_report.json"


def parse_json(value: Any, fallback: Any) -> Any:
    if value is None or value == "":
        return fallback
    if isinstance(value, (dict, list)):
        return value
    try:
        return json.loads(value)
    except (TypeError, ValueError):
        return fallback


def row_dict(row: sqlite3.Row | None) -> dict[str, Any] | None:
    return dict(row) if row is not None else None


def rows_dict(rows: list[sqlite3.Row]) -> list[dict[str, Any]]:
    return [dict(row) for row in rows]


def connect(db_path: Path) -> sqlite3.Connection:
    if not db_path.exists():
        raise FileNotFoundError(f"V2 database not found: {db_path}")
    uri = f"file:{db_path.resolve()}?mode=ro"
    connection = sqlite3.connect(uri, uri=True)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA query_only = ON")
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def load_report() -> dict[str, Any]:
    if not REPORT_FILE.exists():
        return {}
    try:
        return json.loads(REPORT_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def grouped_count(connection: sqlite3.Connection, column: str) -> dict[str, int]:
    allowed = {"lifecycle", "machine_status", "human_status", "review_status"}
    if column not in allowed:
        raise ValueError(f"Unsupported grouped column: {column}")
    rows = connection.execute(
        f"SELECT {column} AS value, COUNT(*) AS count FROM annotation_cases GROUP BY {column}"
    ).fetchall()
    return {str(row["value"]): int(row["count"]) for row in rows}


def evidence_counters(connection: sqlite3.Connection) -> dict[str, dict[str, int]]:
    resolution = Counter()
    cited_match = Counter()
    quote_check = Counter()
    context_check = Counter()
    rows = connection.execute(
        "SELECT evidence_json, quote_check FROM annotation_evidences"
    ).fetchall()
    for row in rows:
        evidence = parse_json(row["evidence_json"], {})
        source_resolution = evidence.get("source_resolution") or "unknown"
        cited_work_match = evidence.get("cited_work_match_status") or "unknown"
        resolution[str(source_resolution)] += 1
        cited_match[str(cited_work_match)] += 1
        quote_check[str(row["quote_check"] or evidence.get("quote_check") or "unknown")] += 1
        context_check[str(evidence.get("annotation_context_check") or "unknown")] += 1
    return {
        "source_resolution": dict(resolution),
        "cited_work_match": dict(cited_match),
        "quote_check": dict(quote_check),
        "annotation_context_check": dict(context_check),
    }


def source_rows(connection: sqlite3.Connection) -> list[dict[str, Any]]:
    rows = connection.execute(
        """
        SELECT sd.*,
               (SELECT COUNT(*) FROM passages p WHERE p.source_document_id = sd.source_document_id) AS passage_count,
               (SELECT COUNT(*) FROM annotation_cases ac
                JOIN passages p ON p.passage_id = ac.source_passage_id
                WHERE p.source_document_id = sd.source_document_id) AS case_count
        FROM source_documents sd
        ORDER BY sd.work_key
        """
    ).fetchall()
    result = []
    for row in rows:
        item = dict(row)
        item["metadata"] = parse_json(item.pop("metadata_json", "{}"), {})
        item["source_file_sha256_short"] = item["source_file_sha256"][:16]
        result.append(item)
    return result


def source_conflicts(connection: sqlite3.Connection) -> list[dict[str, Any]]:
    rows = connection.execute(
        """
        SELECT work_key, source_file, COUNT(DISTINCT source_file_sha256) AS hash_count,
               GROUP_CONCAT(DISTINCT source_file_sha256) AS hashes
        FROM source_documents
        GROUP BY work_key, source_file
        HAVING COUNT(DISTINCT source_file_sha256) > 1
        ORDER BY work_key, source_file
        """
    ).fetchall()
    return [
        {
            "work_key": row["work_key"],
            "source_file": row["source_file"],
            "hash_count": int(row["hash_count"]),
            "hashes": str(row["hashes"] or "").split(","),
        }
        for row in rows
    ]


def orphan_counts(connection: sqlite3.Connection) -> dict[str, int]:
    queries = {
        "orphan_passages": """
            SELECT COUNT(*) FROM passages p
            LEFT JOIN source_documents sd ON sd.source_document_id = p.source_document_id
            WHERE sd.source_document_id IS NULL
        """,
        "orphan_case_source_passages": """
            SELECT COUNT(*) FROM annotation_cases ac
            LEFT JOIN passages p ON p.passage_id = ac.source_passage_id
            WHERE ac.source_passage_id IS NOT NULL AND p.passage_id IS NULL
        """,
        "orphan_evidence_passages": """
            SELECT COUNT(*) FROM annotation_evidences ae
            LEFT JOIN passages p ON p.passage_id = ae.passage_id
            WHERE ae.passage_id IS NOT NULL AND p.passage_id IS NULL
        """,
        "orphan_external_links": """
            SELECT COUNT(*) FROM annotation_evidence_external_sources link
            LEFT JOIN external_source_registry es ON es.external_source_id = link.external_source_id
            WHERE es.external_source_id IS NULL
        """,
    }
    return {
        name: int(connection.execute(query).fetchone()[0])
        for name, query in queries.items()
    }


def acceptance_check(key: str, label: str, status: str, value: str, detail: str) -> dict[str, str]:
    return {
        "key": key,
        "label": label,
        "status": status,
        "value": value,
        "detail": detail,
    }


def build_summary(connection: sqlite3.Connection, db_path: Path) -> dict[str, Any]:
    report = load_report()
    report_summary = report.get("summary") or {}
    counts = {}
    for table in (
        "source_documents",
        "passages",
        "annotation_cases",
        "annotation_terms",
        "annotation_evidences",
        "annotation_process_steps",
        "review_events",
        "external_source_registry",
        "annotation_evidence_external_sources",
    ):
        counts[table] = int(connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])

    lifecycle_counts = grouped_count(connection, "lifecycle")
    machine_counts = grouped_count(connection, "machine_status")
    human_counts = grouped_count(connection, "human_status")
    review_counts = grouped_count(connection, "review_status")
    evidence_counts = evidence_counters(connection)
    sources = source_rows(connection)
    conflicts = source_conflicts(connection)
    orphans = orphan_counts(connection)
    integrity = str(connection.execute("PRAGMA integrity_check").fetchone()[0])
    foreign_key_rows = connection.execute("PRAGMA foreign_key_check").fetchall()
    expected_cases = int((report.get("inputs") or {}).get("expected_case_count") or counts["annotation_cases"])
    unresolved_targets = int(connection.execute(
        """
        SELECT COUNT(*) FROM annotation_cases
        WHERE target_work = '' OR json_extract(target_scope_json, '$.status') = 'unresolved'
        """
    ).fetchone()[0])
    no_citation_cases = int(connection.execute(
        "SELECT COUNT(*) FROM annotation_cases WHERE evidence_state = 'source_no_citation'"
    ).fetchone()[0])
    gold_count = lifecycle_counts.get("gold", 0)
    external_pending = evidence_counts["source_resolution"].get("external_source_pending", 0)
    canonical_count = evidence_counts["source_resolution"].get("canonical_source_passage", 0)
    secondary_count = evidence_counts["source_resolution"].get("secondary_citation_match", 0)
    pending_human = human_counts.get("pending", 0)
    orphan_total = sum(orphans.values())
    fk_status = "pass" if not foreign_key_rows else "fail"
    integrity_status = "pass" if integrity == "ok" else "fail"
    expected_status = "pass" if counts["annotation_cases"] == expected_cases else "fail"
    separation_status = "pass" if gold_count == 0 and pending_human == counts["annotation_cases"] else "warn"
    source_status = "pass" if not conflicts else "fail"
    orphan_status = "pass" if orphan_total == 0 else "fail"

    checks = [
        acceptance_check(
            "integrity",
            "数据库完整性",
            integrity_status,
            integrity,
            "SQLite integrity_check；只读验收接口不会写入数据库。",
        ),
        acceptance_check(
            "foreign_keys",
            "外键完整性",
            fk_status,
            "0 个违规" if not foreign_key_rows else f"{len(foreign_key_rows)} 个违规",
            "案例、段落、证据与外部来源的引用关系。",
        ),
        acceptance_check(
            "canonical_source",
            "原典版本唯一",
            source_status,
            f"{len(sources)} 个来源版本" if not conflicts else f"{len(conflicts)} 个冲突",
            "同一 work_key + source_file 不得混入多个 hash；当前读书杂志只保留 1460…版本。",
        ),
        acceptance_check(
            "no_orphans",
            "引用无孤儿",
            orphan_status,
            f"{orphan_total} 个孤儿引用",
            "source_passage、evidence passage 和 external source link 都必须能回指。",
        ),
        acceptance_check(
            "stored_cases",
            "案例入库数量",
            expected_status,
            f"{counts['annotation_cases']} / {expected_cases}",
            "与本轮批量迁移清单中的预期案例数对照。",
        ),
        acceptance_check(
            "machine_human_separation",
            "机器与人工状态分离",
            separation_status,
            f"machine draft {machine_counts.get('draft', 0)}；rejected {machine_counts.get('rejected', 0)}；human pending {pending_human}",
            "机器入库不等于人工通过；当前没有 gold。",
        ),
        acceptance_check(
            "canonical_evidence",
            "原典引文核验",
            "pass" if external_pending == 0 and canonical_count == counts["annotation_evidences"] else "warn",
            f"canonical {canonical_count}；secondary {secondary_count}；external pending {external_pending}",
            "secondary citation match 仍是王氏正文中的二次引文命中，不是被引原典核验通过。",
        ),
        acceptance_check(
            "target_work",
            "target_work 完整度",
            "pass" if unresolved_targets == 0 else "warn",
            f"{unresolved_targets} 条待补",
            "target_work 缺失的案例保持 rejected，不伪造目标典籍。",
        ),
        acceptance_check(
            "no_citation",
            "无引文状态",
            "pass" if no_citation_cases == 0 else "warn",
            f"{no_citation_cases} 条 source_no_citation",
            "原典明确无引文时保留状态，不制造 evidence 占位记录。",
        ),
    ]
    overall = "fail" if any(item["status"] == "fail" for item in checks) else (
        "pass_with_warnings" if any(item["status"] == "warn" for item in checks) else "pass"
    )

    schema_version_row = connection.execute(
        "SELECT meta_value FROM schema_meta WHERE meta_key = 'schema_version'"
    ).fetchone()
    return {
        "ok": True,
        "overall_status": overall,
        "database": {
            "path": str(db_path),
            "display_path": "v2/data/real_runs/annotation_v2.db",
            "schema_version": schema_version_row[0] if schema_version_row else "unknown",
            "read_only": True,
        },
        "counts": counts,
        "lifecycle_counts": lifecycle_counts,
        "machine_status_counts": machine_counts,
        "human_status_counts": human_counts,
        "review_status_counts": review_counts,
        "evidence_counts": evidence_counts,
        "sources": sources,
        "source_version_conflicts": conflicts,
        "orphans": orphans,
        "checks": checks,
        "report_context": {
            "report_version": report.get("report_version"),
            "run_status": report.get("run_status"),
            "full_json_context_counts": report_summary.get("full_json_context_counts", {}),
            "source_file_count": report_summary.get("source_file_count"),
        },
    }


def passage_payload(row: sqlite3.Row | None) -> dict[str, Any] | None:
    if row is None:
        return None
    item = dict(row)
    item["inline_notes"] = parse_json(item.pop("inline_notes_json", "[]"), [])
    return item


def list_cases(connection: sqlite3.Connection) -> list[dict[str, Any]]:
    rows = connection.execute(
        """
        SELECT ac.*,
               p.document_title AS source_document_title,
               p.section_title AS source_section_title,
               p.entry_title AS source_entry_title,
               p.md_line_start AS source_md_line_start,
               p.md_line_end AS source_md_line_end,
               (SELECT COUNT(*) FROM annotation_terms t WHERE t.case_id = ac.case_id) AS term_count,
               (SELECT COUNT(*) FROM annotation_evidences e WHERE e.case_id = ac.case_id) AS evidence_count,
               (SELECT COUNT(*) FROM annotation_process_steps ps WHERE ps.case_id = ac.case_id) AS process_step_count
        FROM annotation_cases ac
        LEFT JOIN passages p ON p.passage_id = ac.source_passage_id
        ORDER BY CASE ac.source_work WHEN '读书杂志' THEN 1 WHEN '广雅疏证' THEN 2 ELSE 3 END,
                 ac.case_id
        """
    ).fetchall()
    result = []
    for row in rows:
        item = dict(row)
        item["target_works"] = parse_json(item.pop("target_works_json", "[]"), [])
        item["target_scope"] = parse_json(item.pop("target_scope_json", "{}"), {})
        item["machine_result"] = parse_json(item.pop("machine_result_json", "{}"), {})
        item["human_review"] = parse_json(item.pop("human_review_json", "{}"), {})
        item.pop("case_json", None)
        item["evidence_summary"] = {}
        evidence_rows = connection.execute(
            "SELECT evidence_json FROM annotation_evidences WHERE case_id = ?",
            (item["case_id"],),
        ).fetchall()
        for evidence_row in evidence_rows:
            evidence = parse_json(evidence_row["evidence_json"], {})
            key = evidence.get("source_resolution") or "unknown"
            item["evidence_summary"][key] = item["evidence_summary"].get(key, 0) + 1
        result.append(item)
    return result


def get_case(connection: sqlite3.Connection, case_id: str) -> dict[str, Any] | None:
    row = connection.execute(
        "SELECT * FROM annotation_cases WHERE case_id = ?",
        (case_id,),
    ).fetchone()
    if row is None:
        return None
    item = dict(row)
    item["target_works"] = parse_json(item.pop("target_works_json", "[]"), [])
    item["target_scope"] = parse_json(item.pop("target_scope_json", "{}"), {})
    item["machine_result"] = parse_json(item.pop("machine_result_json", "{}"), {})
    item["human_review"] = parse_json(item.pop("human_review_json", "{}"), {})
    item["case_data"] = parse_json(item.pop("case_json", "{}"), {})

    source_passage = connection.execute(
        "SELECT * FROM passages WHERE passage_id = ?",
        (item.get("source_passage_id"),),
    ).fetchone() if item.get("source_passage_id") else None
    item["source_passage"] = passage_payload(source_passage)

    term_rows = connection.execute(
        """
        SELECT case_id, term_index, source_term, target_term, relation_type,
               relation_subtype, relation_note, term_json
        FROM annotation_terms WHERE case_id = ? ORDER BY term_index
        """,
        (case_id,),
    ).fetchall()
    terms = []
    for term_row in term_rows:
        term = dict(term_row)
        term["data"] = parse_json(term.pop("term_json", "{}"), {})
        terms.append(term)
    item["terms"] = terms

    evidence_rows = connection.execute(
        """
        SELECT e.*, link.external_source_id,
               es.cited_work AS external_cited_work,
               es.status AS external_status,
               es.source_file AS external_source_file,
               es.edition AS external_edition,
               es.location_note AS external_location_note
        FROM annotation_evidences e
        LEFT JOIN annotation_evidence_external_sources link
          ON link.case_id = e.case_id AND link.evidence_index = e.evidence_index
        LEFT JOIN external_source_registry es
          ON es.external_source_id = link.external_source_id
        WHERE e.case_id = ?
        ORDER BY e.evidence_index
        """,
        (case_id,),
    ).fetchall()
    evidences = []
    for evidence_row in evidence_rows:
        evidence = dict(evidence_row)
        evidence["data"] = parse_json(evidence.pop("evidence_json", "{}"), {})
        evidence["source_passage"] = passage_payload(
            connection.execute(
                "SELECT * FROM passages WHERE passage_id = ?",
                (evidence.get("passage_id"),),
            ).fetchone() if evidence.get("passage_id") else None
        )
        evidences.append(evidence)
    item["evidences"] = evidences

    steps = connection.execute(
        """
        SELECT step_index, field_name, step_text, step_json
        FROM annotation_process_steps WHERE case_id = ? ORDER BY step_index
        """,
        (case_id,),
    ).fetchall()
    item["process_steps"] = [
        {
            **dict(step),
            "data": parse_json(step["step_json"], {}),
        }
        for step in steps
    ]
    item["review_events"] = rows_dict(connection.execute(
        """
        SELECT review_event_id, reviewer, review_status, review_note,
               review_json, created_at
        FROM review_events WHERE case_id = ? ORDER BY review_event_id
        """,
        (case_id,),
    ).fetchall())
    for review in item["review_events"]:
        review["data"] = parse_json(review.pop("review_json", "{}"), {})
    return item


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("summary", "cases", "case"))
    parser.add_argument("case_id", nargs="?")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    args = parser.parse_args()

    try:
        connection = connect(args.db)
        try:
            if args.command == "summary":
                payload = build_summary(connection, args.db)
            elif args.command == "cases":
                payload = {"ok": True, "items": list_cases(connection)}
            else:
                payload = get_case(connection, args.case_id or "")
                if payload is None:
                    payload = {"ok": False, "message": "V2 case not found"}
                else:
                    payload["ok"] = True
        finally:
            connection.close()
        print(json.dumps(payload, ensure_ascii=False))
        return 0
    except Exception as error:
        print(json.dumps({"ok": False, "message": str(error)}, ensure_ascii=False))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
