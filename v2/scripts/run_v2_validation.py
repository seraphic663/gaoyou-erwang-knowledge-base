#!/usr/bin/env python3
"""Run the read-only, database-level acceptance checks for the V2 snapshot.

The checks are deliberately stricter than a row-count report: they verify the
canonical source-version policy, the legacy materialization boundary, quote
hashes, passage ownership, and machine/human state separation.  The script
never updates the database; it only writes a JSON validation report.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


V2_ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = V2_ROOT.parent
DEFAULT_DATABASE = V2_ROOT / "data/real_runs/annotation_v2.db"
DEFAULT_REPORT = V2_ROOT / "data/real_runs/v2_validation_report.json"

DUSHU_CANONICAL_SHA256 = (
    "1460a906825998bf8a4bf3c51d4525fe19b8b79f377fb6d25ccdad4dc698e19e"
)
DUSHU_HISTORICAL_SHA256 = (
    "1534084959961a160ddc93b5d7523ec2565bb01f0c079523f53442ef61fa37b2"
)
CANONICAL_WORKS = {
    "guangya_shuzheng",
    "jingzhuan_shici",
    "jingyi_shuwen",
    "dushu_zazhi",
}
LEGACY_ORIGIN = "legacy_dictionary_db_reprocessing"


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def connect_read_only(database_path: Path) -> sqlite3.Connection:
    uri = f"file:{database_path.resolve()}?mode=ro"
    connection = sqlite3.connect(uri, uri=True)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA query_only = ON")
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def scalar(connection: sqlite3.Connection, sql: str, params: tuple[Any, ...] = ()) -> Any:
    return connection.execute(sql, params).fetchone()[0]


def as_count(value: Any) -> int:
    return int(value or 0)


def parse_json(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    try:
        parsed = json.loads(value or "{}")
    except (TypeError, ValueError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def sha256_file(path: Path) -> str | None:
    if not path.exists() or not path.is_file():
        return None
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def table_counts(connection: sqlite3.Connection) -> dict[str, int]:
    tables = (
        "source_documents",
        "source_version_registry",
        "passages",
        "candidate_items",
        "annotation_cases",
        "annotation_terms",
        "annotation_evidences",
        "annotation_process_steps",
        "review_events",
        "external_source_registry",
        "annotation_evidence_external_sources",
        "work_registry",
        "work_aliases",
        "target_work_resolution_queue",
        "external_source_resolution_queue",
        "external_passage_resolution_queue",
        "legacy_catalog_terms",
        "legacy_catalog_works",
    )
    return {table: as_count(scalar(connection, f"SELECT COUNT(*) FROM {table}")) for table in tables}


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
        "orphan_case_target_passages": """
            SELECT COUNT(*) FROM annotation_cases ac
            LEFT JOIN passages p ON p.passage_id = ac.target_passage_id
            WHERE ac.target_passage_id IS NOT NULL AND p.passage_id IS NULL
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
        "orphan_candidate_source_documents": """
            SELECT COUNT(*) FROM candidate_items ci
            LEFT JOIN source_documents sd ON sd.source_document_id = ci.source_document_id
            WHERE ci.source_document_id IS NOT NULL AND sd.source_document_id IS NULL
        """,
        "orphan_candidate_passages": """
            SELECT COUNT(*) FROM candidate_items ci
            LEFT JOIN passages p ON p.passage_id = ci.passage_id
            WHERE ci.passage_id IS NOT NULL AND p.passage_id IS NULL
        """,
        "orphan_candidate_output_cases": """
            SELECT COUNT(*) FROM candidate_items ci
            LEFT JOIN annotation_cases ac ON ac.case_id = ci.output_case_id
            WHERE ci.output_case_id IS NOT NULL AND ac.case_id IS NULL
        """,
    }
    return {name: as_count(scalar(connection, query)) for name, query in queries.items()}


def source_policy(connection: sqlite3.Connection) -> dict[str, Any]:
    documents = [
        dict(row)
        for row in connection.execute(
            """
            SELECT work_key, source_kind, source_file, source_file_sha256,
                   canonical_status
            FROM source_documents
            ORDER BY work_key, source_file_sha256
            """
        )
    ]
    registry = [
        dict(row)
        for row in connection.execute(
            """
            SELECT work_key, source_file, source_file_sha256, canonical_status,
                   superseded_by_sha256, reason
            FROM source_version_registry
            ORDER BY work_key, canonical_status, source_file_sha256
            """
        )
    ]
    active = {
        row["work_key"]: row["source_file_sha256"]
        for row in documents
        if row["canonical_status"] == "canonical_active"
    }
    historical = [
        row
        for row in registry
        if row["source_file_sha256"] == DUSHU_HISTORICAL_SHA256
    ]
    dushu_path = next(
        (
            Path(row["source_file"])
            for row in documents
            if row["work_key"] == "dushu_zazhi"
            and row["canonical_status"] == "canonical_active"
        ),
        None,
    )
    return {
        "source_documents": documents,
        "source_version_registry": registry,
        "active_hashes": active,
        "dushu_current_file_hash": sha256_file(dushu_path) if dushu_path else None,
        "dushu_historical_registry_rows": historical,
        "active_old_dushu_document_count": as_count(
            scalar(
                connection,
                """
                SELECT COUNT(*) FROM source_documents
                WHERE work_key='dushu_zazhi' AND source_file_sha256=?
                """,
                (DUSHU_HISTORICAL_SHA256,),
            )
        ),
    }


def legacy_materialization(connection: sqlite3.Connection) -> dict[str, Any]:
    case_row = connection.execute(
        """
        SELECT COUNT(*) AS cases,
               SUM(source_passage_id IS NOT NULL) AS source_links,
               SUM(target_passage_id IS NOT NULL) AS target_links,
               SUM(process_text IS NOT NULL AND TRIM(process_text) <> '') AS process_texts
        FROM annotation_cases
        WHERE origin=?
        """,
        (LEGACY_ORIGIN,),
    ).fetchone()
    evidence_row = connection.execute(
        """
        SELECT COUNT(*) AS evidences,
               SUM(e.passage_id IS NOT NULL) AS passage_links,
               SUM(e.quote_check='unchecked') AS unchecked,
               SUM(e.quote_check IN ('passed', 'normalized_passed')) AS passed
        FROM annotation_evidences e
        JOIN annotation_cases c ON c.case_id=e.case_id
        WHERE c.origin=?
        """,
        (LEGACY_ORIGIN,),
    ).fetchone()
    evidence_resolution = [
        dict(row)
        for row in connection.execute(
            """
            SELECT e.quote_check,
                   json_extract(e.evidence_json, '$.source_resolution') AS source_resolution,
                   COUNT(*) AS count
            FROM annotation_evidences e
            JOIN annotation_cases c ON c.case_id=e.case_id
            WHERE c.origin=?
            GROUP BY e.quote_check, source_resolution
            ORDER BY e.quote_check, source_resolution
            """,
            (LEGACY_ORIGIN,),
        )
    ]
    step_fields = {
        row["field_name"]: as_count(row["count"])
        for row in connection.execute(
            """
            SELECT ps.field_name, COUNT(*) AS count
            FROM annotation_process_steps ps
            JOIN annotation_cases c ON c.case_id=ps.case_id
            WHERE c.origin=? AND ps.step_text IS NOT NULL AND TRIM(ps.step_text) <> ''
            GROUP BY ps.field_name
            """,
            (LEGACY_ORIGIN,),
        )
    }
    bad_step_case_count = as_count(
        scalar(
            connection,
            """
            SELECT COUNT(*) FROM (
                SELECT c.case_id, COUNT(ps.step_index) AS step_count
                FROM annotation_cases c
                LEFT JOIN annotation_process_steps ps ON ps.case_id=c.case_id
                WHERE c.origin=?
                GROUP BY c.case_id
                HAVING step_count <> 5
            )
            """,
            (LEGACY_ORIGIN,),
        )
    )
    passage_counts = {
        row["entry_kind"]: as_count(row["count"])
        for row in connection.execute(
            """
            SELECT p.entry_kind, COUNT(*) AS count
            FROM passages p
            JOIN source_documents sd ON sd.source_document_id=p.source_document_id
            WHERE sd.work_key IN ('legacy_guangya_shuzheng_source',
                                  'legacy_dictionary_db_evidence')
            GROUP BY p.entry_kind
            """
        )
    }
    return {
        "case_counts": {key: as_count(case_row[key]) for key in ("cases", "source_links", "target_links", "process_texts")},
        "evidence_counts": {key: as_count(evidence_row[key]) for key in ("evidences", "passage_links", "unchecked", "passed")},
        "evidence_resolution": evidence_resolution,
        "process_field_counts": step_fields,
        "bad_step_case_count": bad_step_case_count,
        "passage_counts_by_entry_kind": passage_counts,
    }


def quote_validation(connection: sqlite3.Connection) -> dict[str, Any]:
    hash_mismatches: list[dict[str, Any]] = []
    for row in connection.execute(
        "SELECT case_id, evidence_index, quote, quote_sha256 FROM annotation_evidences"
    ):
        expected = hashlib.sha256((row["quote"] or "").encode("utf-8")).hexdigest()
        if row["quote_sha256"] and expected.lower() != str(row["quote_sha256"]).lower():
            if len(hash_mismatches) < 20:
                hash_mismatches.append(
                    {"case_id": row["case_id"], "evidence_index": row["evidence_index"]}
                )

    passed_violations: list[dict[str, Any]] = []
    passed_count = 0
    for row in connection.execute(
        """
        SELECT e.case_id, e.evidence_index, e.quote, e.quote_check,
               e.evidence_json, p.raw_text, p.plain_text, p.normalized_text,
               sd.canonical_status, p.passage_id
        FROM annotation_evidences e
        LEFT JOIN passages p ON p.passage_id=e.passage_id
        LEFT JOIN source_documents sd ON sd.source_document_id=p.source_document_id
        WHERE e.quote_check IN ('passed', 'normalized_passed')
        """
    ):
        passed_count += 1
        evidence = parse_json(row["evidence_json"])
        quote = row["quote"] or ""
        in_passage = any(
            quote in (row[column] or "")
            for column in ("raw_text", "plain_text", "normalized_text")
        )
        valid = (
            evidence.get("source_resolution") == "canonical_source_passage"
            and row["canonical_status"] == "canonical_active"
            and in_passage
        )
        if not valid and len(passed_violations) < 20:
            passed_violations.append(
                {
                    "case_id": row["case_id"],
                    "evidence_index": row["evidence_index"],
                    "source_resolution": evidence.get("source_resolution"),
                    "canonical_status": row["canonical_status"],
                    "passage_id": row["passage_id"],
                    "in_passage": in_passage,
                }
            )
    return {
        "quote_hash_mismatch_count": len(hash_mismatches),
        "quote_hash_mismatch_examples": hash_mismatches,
        "canonical_passed_count": passed_count,
        "canonical_passed_violations": passed_violations,
    }


def work_identity_validation(connection: sqlite3.Connection) -> dict[str, Any]:
    canonical_keys = {
        "guangya_shuzheng",
        "jingzhuan_shici",
        "jingyi_shuwen",
        "dushu_zazhi",
    }
    canonical_rows = {
        row["work_key"]: row["identity_status"]
        for row in connection.execute(
            "SELECT work_key, identity_status FROM work_registry WHERE work_key IN (?, ?, ?, ?)",
            tuple(sorted(canonical_keys)),
        )
    }
    orphan_aliases = as_count(
        scalar(
            connection,
            """
            SELECT COUNT(*) FROM work_aliases wa
            LEFT JOIN work_registry wr ON wr.work_key=wa.work_key
            WHERE wr.work_key IS NULL
            """,
        )
    )
    empty_aliases = as_count(
        scalar(
            connection,
            """
            SELECT COUNT(*) FROM work_aliases
            WHERE TRIM(raw_label)='' OR TRIM(normalized_label)=''
            """,
        )
    )
    external_count = as_count(scalar(connection, "SELECT COUNT(*) FROM external_source_registry"))
    external_alias_count = as_count(
        scalar(
            connection,
            """
            SELECT COUNT(DISTINCT source_record_id) FROM work_aliases
            WHERE source_file='external_source_registry'
            """,
        )
    )
    return {
        "canonical_rows": canonical_rows,
        "orphan_alias_count": orphan_aliases,
        "empty_alias_count": empty_aliases,
        "external_source_count": external_count,
        "external_alias_source_record_count": external_alias_count,
        "valid": (
            canonical_rows == {key: "canonical_active" for key in canonical_keys}
            and orphan_aliases == 0
            and empty_aliases == 0
            and external_alias_count == external_count
        ),
    }


def work_queue_validation(connection: sqlite3.Connection) -> dict[str, Any]:
    orphan_target = as_count(
        scalar(
            connection,
            """
            SELECT COUNT(*) FROM target_work_resolution_queue q
            LEFT JOIN annotation_cases c ON c.case_id=q.case_id
            WHERE c.case_id IS NULL
            """,
        )
    )
    orphan_external_source = as_count(
        scalar(
            connection,
            """
            SELECT COUNT(*) FROM external_source_resolution_queue q
            LEFT JOIN external_source_registry s ON s.external_source_id=q.external_source_id
            WHERE s.external_source_id IS NULL
            """,
        )
    )
    orphan_external_passage = as_count(
        scalar(
            connection,
            """
            SELECT COUNT(*) FROM external_passage_resolution_queue q
            LEFT JOIN annotation_evidences e
              ON e.case_id=q.case_id AND e.evidence_index=q.evidence_index
            WHERE e.case_id IS NULL
            """,
        )
    )
    target_pending_case_count = as_count(
        scalar(
            connection,
            """
            SELECT COUNT(DISTINCT case_id) FROM target_work_resolution_queue
            WHERE queue_status IN ('pending', 'needs_context')
            """,
        )
    )
    human_queue_count = as_count(
        scalar(
            connection,
            "SELECT COUNT(*) FROM annotation_cases WHERE human_status IN ('pending','uncertain')",
        )
    )
    review_columns = {
        row[1] for row in connection.execute("PRAGMA table_info(review_events)")
    }
    review_operation_index = as_count(
        scalar(
            connection,
            """
            SELECT COUNT(*) FROM sqlite_master
            WHERE type='index' AND name='idx_review_events_operation_id'
            """,
        )
    )
    review_boundary_valid = {
        "operation_id", "event_kind", "from_lifecycle", "from_human_status", "to_lifecycle"
    }.issubset(review_columns) and review_operation_index == 1
    return {
        "target_queue_count": as_count(scalar(connection, "SELECT COUNT(*) FROM target_work_resolution_queue")),
        "external_source_queue_count": as_count(scalar(connection, "SELECT COUNT(*) FROM external_source_resolution_queue")),
        "external_passage_queue_count": as_count(scalar(connection, "SELECT COUNT(*) FROM external_passage_resolution_queue")),
        "target_pending_case_count": target_pending_case_count,
        "human_review_queue_count": human_queue_count,
        "orphan_target_count": orphan_target,
        "orphan_external_source_count": orphan_external_source,
        "orphan_external_passage_count": orphan_external_passage,
        "review_events_count": as_count(scalar(connection, "SELECT COUNT(*) FROM review_events")),
        "review_boundary_columns": sorted(review_columns),
        "review_operation_index_count": review_operation_index,
        "review_boundary_valid": review_boundary_valid,
        "valid": (
            orphan_target == 0
            and orphan_external_source == 0
            and orphan_external_passage == 0
            and human_queue_count == 936
            and target_pending_case_count == 932
            and review_boundary_valid
        ),
    }


def build_report(database_path: Path) -> dict[str, Any]:
    connection = connect_read_only(database_path)
    try:
        counts = table_counts(connection)
        source = source_policy(connection)
        legacy = legacy_materialization(connection)
        quote = quote_validation(connection)
        work_identity = work_identity_validation(connection)
        work_queues = work_queue_validation(connection)
        orphans = orphan_counts(connection)
        integrity = str(scalar(connection, "PRAGMA integrity_check"))
        foreign_keys = [dict(row) for row in connection.execute("PRAGMA foreign_key_check")]
        lifecycle = {
            str(row["value"]): as_count(row["count"])
            for row in connection.execute(
                "SELECT lifecycle AS value, COUNT(*) AS count FROM annotation_cases GROUP BY lifecycle"
            )
        }
        machine_status = {
            str(row["value"]): as_count(row["count"])
            for row in connection.execute(
                "SELECT machine_status AS value, COUNT(*) AS count FROM annotation_cases GROUP BY machine_status"
            )
        }
        human_status = {
            str(row["value"]): as_count(row["count"])
            for row in connection.execute(
                "SELECT human_status AS value, COUNT(*) AS count FROM annotation_cases GROUP BY human_status"
            )
        }
        external_status = {
            str(row["value"]): as_count(row["count"])
            for row in connection.execute(
                "SELECT status AS value, COUNT(*) AS count FROM external_source_registry GROUP BY status"
            )
        }
    finally:
        connection.close()

    active_hashes = source["active_hashes"]
    historical_rows = source["dushu_historical_registry_rows"]
    dushu_historical_ok = any(
        row["canonical_status"] == "historical_superseded"
        and row["superseded_by_sha256"] == DUSHU_CANONICAL_SHA256
        for row in historical_rows
    )
    process_fields_ok = all(
        legacy["process_field_counts"].get(field) == 815
        for field in (
            "problem_discovery",
            "research_question",
            "evidence_collection",
            "reasoning",
            "conclusion",
        )
    )
    checks = {
        "integrity_check": integrity == "ok",
        "foreign_key_check": not foreign_keys,
        "snapshot_counts": counts == {
            "source_documents": 6,
            "source_version_registry": 7,
            "passages": 15467,
            "candidate_items": 6749,
            "annotation_cases": 936,
            "annotation_terms": 6778,
            "annotation_evidences": 7345,
            "annotation_process_steps": 4680,
            "review_events": 0,
            "external_source_registry": 100,
            "annotation_evidence_external_sources": 121,
            "work_registry": 120,
            "work_aliases": 962,
            "target_work_resolution_queue": 1317,
            "external_source_resolution_queue": 100,
            "external_passage_resolution_queue": 121,
            "legacy_catalog_terms": 14,
            "legacy_catalog_works": 12,
        },
        "canonical_documents": (
            len([row for row in source["source_documents"] if row["canonical_status"] == "canonical_active"]) == 4
            and set(active_hashes) == CANONICAL_WORKS
        ),
        "dushu_canonical_hash": active_hashes.get("dushu_zazhi") == DUSHU_CANONICAL_SHA256,
        "dushu_current_file_hash": source["dushu_current_file_hash"] == DUSHU_CANONICAL_SHA256,
        "dushu_historical_hash_policy": (
            dushu_historical_ok and source["active_old_dushu_document_count"] == 0
        ),
        "legacy_case_materialization": legacy["case_counts"] == {
            "cases": 815,
            "source_links": 815,
            "target_links": 815,
            "process_texts": 815,
        },
        "legacy_passage_materialization": legacy["passage_counts_by_entry_kind"] == {
            "legacy_source_case": 815,
            "legacy_derived_quote": 7120,
        },
        "legacy_process_fields": process_fields_ok and legacy["bad_step_case_count"] == 0,
        "legacy_evidence_boundary": legacy["evidence_counts"] == {
            "evidences": 7120,
            "passage_links": 7120,
            "unchecked": 7120,
            "passed": 0,
        }
        and legacy["evidence_resolution"] == [
            {
                "quote_check": "unchecked",
                "source_resolution": "legacy_derived_passage",
                "count": 7120,
            }
        ],
        "quote_hashes": quote["quote_hash_mismatch_count"] == 0,
        "canonical_quote_boundary": not quote["canonical_passed_violations"],
        "orphan_references": not any(orphans.values()),
        "catalog_only_coverage": (
            counts["legacy_catalog_terms"] == 14 and counts["legacy_catalog_works"] == 12
        ),
        "machine_human_state_separation": (
            human_status == {"pending": 936}
            and lifecycle.get("gold", 0) == 0
            and machine_status == {"draft": 936}
        ),
        "work_identity_registry": work_identity["valid"],
        "work_queues": work_queues["valid"],
    }
    warnings = {
        "external_canonical_files": {
            "registered_external_sources": 100,
            "registry_status_counts": external_status,
            "canonical_file_registered_count": 0,
        },
        "pending_target_work_count": 932,
        "human_review_performed": False,
    }
    return {
        "report_version": "v2-validation.v1",
        "generated_at": now(),
        "database": str(database_path.resolve().relative_to(PROJECT_ROOT)),
        "status": "passed" if all(checks.values()) else "failed",
        "checks": checks,
        "counts": counts,
        "integrity_check": integrity,
        "foreign_key_violations": foreign_keys,
        "orphan_counts": orphans,
        "lifecycle_counts": lifecycle,
        "machine_status_counts": machine_status,
        "human_status_counts": human_status,
        "source_policy": source,
        "legacy_materialization": legacy,
        "quote_validation": quote,
        "work_identity_validation": work_identity,
        "work_queue_validation": work_queues,
        "warnings": warnings,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, default=DEFAULT_DATABASE)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    args = parser.parse_args()
    report = build_report(args.db.resolve())
    args.report.resolve().parent.mkdir(parents=True, exist_ok=True)
    args.report.resolve().write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
