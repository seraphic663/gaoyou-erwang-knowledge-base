#!/usr/bin/env python3
"""Build a read-only accounting report for the remaining V2 automation gap.

The report separates work that is already machine-materialized from work that
still needs an edition, semantic target decision, or human approval.  It is
an audit artifact, not a status mutator and not a shortcut to canonical or
gold state.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


V2_ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = V2_ROOT.parent
DEFAULT_DATABASE = V2_ROOT / "data/real_runs/annotation_v2.db"
DEFAULT_OUTPUT = V2_ROOT / "data/real_runs/automation_gap_report.v1.json"
DEFAULT_VALIDATION = V2_ROOT / "data/real_runs/v2_validation_report.json"
DEFAULT_TARGET_PACKET_REPORT = V2_ROOT / "data/real_runs/target_work_resolution_packets_report.json"
DEFAULT_EXTERNAL_PACKET_REPORT = V2_ROOT / "data/real_runs/external_evidence_packets_report.json"
DEFAULT_EDITION_CANDIDATE_MANIFEST = V2_ROOT / "data/real_runs/external_edition_candidate_manifest.v1.json"
DEFAULT_LEGACY_AUDIT = V2_ROOT / "data/real_runs/legacy_dictionary_field_audit.json"
DEFAULT_SOURCE_INVENTORY = V2_ROOT / "data/real_runs/source_inventory.v1.json"


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def relative_path(value: str | Path) -> str:
    path = Path(value)
    try:
        return path.resolve().relative_to(PROJECT_ROOT.resolve()).as_posix()
    except ValueError:
        return path.as_posix()


def parse_json(value: Any, fallback: Any) -> Any:
    if isinstance(value, (dict, list)):
        return value
    try:
        parsed = json.loads(value or "")
    except (TypeError, ValueError):
        return fallback
    return parsed


def load_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return value if isinstance(value, dict) else {}


def connect_read_only(database_path: Path) -> sqlite3.Connection:
    uri = f"file:{database_path.resolve()}?mode=ro"
    connection = sqlite3.connect(uri, uri=True)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA query_only = ON")
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def grouped(connection: sqlite3.Connection, query: str) -> dict[str, int]:
    return {
        str(row["value"] if row["value"] is not None else "<null>"): int(row["count"])
        for row in connection.execute(query)
    }


def build_report(
    *,
    database_path: Path = DEFAULT_DATABASE,
    validation_path: Path = DEFAULT_VALIDATION,
    target_packet_report_path: Path = DEFAULT_TARGET_PACKET_REPORT,
    external_packet_report_path: Path = DEFAULT_EXTERNAL_PACKET_REPORT,
    edition_candidate_manifest_path: Path = DEFAULT_EDITION_CANDIDATE_MANIFEST,
    legacy_audit_path: Path = DEFAULT_LEGACY_AUDIT,
    source_inventory_path: Path = DEFAULT_SOURCE_INVENTORY,
) -> dict[str, Any]:
    database_path = Path(database_path).resolve()
    with connect_read_only(database_path) as connection:
        target_queue = {
            "total": int(connection.execute("SELECT COUNT(*) FROM target_work_resolution_queue").fetchone()[0]),
            "pending_case_count": int(connection.execute(
                "SELECT COUNT(DISTINCT case_id) FROM target_work_resolution_queue WHERE queue_status IN ('pending','needs_context','uncertain')"
            ).fetchone()[0]),
            "status_counts": grouped(connection, "SELECT queue_status AS value, COUNT(*) AS count FROM target_work_resolution_queue GROUP BY queue_status"),
            "inference_status_counts": grouped(connection, "SELECT machine_inference_status AS value, COUNT(*) AS count FROM target_work_resolution_queue GROUP BY machine_inference_status"),
            "origin_counts": grouped(connection, """
                SELECT ac.origin AS value, COUNT(*) AS count
                FROM target_work_resolution_queue q
                JOIN annotation_cases ac ON ac.case_id=q.case_id
                GROUP BY ac.origin
            """),
            "raw_label_counts": grouped(connection, """
                SELECT CASE WHEN TRIM(raw_label)='' THEN '<empty>' ELSE 'nonempty' END AS value,
                       COUNT(*) AS count
                FROM target_work_resolution_queue GROUP BY value
            """),
            "registry_identity_counts": grouped(connection, """
                SELECT COALESCE(wr.identity_status, '<missing>') AS value, COUNT(*) AS count
                FROM target_work_resolution_queue q
                LEFT JOIN work_registry wr ON wr.work_key=q.machine_candidate_work_key
                GROUP BY value
            """),
            "work_key_count": int(connection.execute(
                "SELECT COUNT(*) FROM target_work_resolution_queue WHERE machine_candidate_work_key IS NOT NULL"
            ).fetchone()[0]),
            "blank_target_work_case_count": int(connection.execute(
                "SELECT COUNT(*) FROM annotation_cases WHERE TRIM(target_work)=''"
            ).fetchone()[0]),
            "blank_target_passage_case_count": int(connection.execute(
                "SELECT COUNT(*) FROM annotation_cases WHERE TRIM(target_work)='' AND target_passage_id IS NULL"
            ).fetchone()[0]),
            "target_passage_source_kind_counts": grouped(connection, """
                SELECT COALESCE(sd.source_kind, '<missing>') AS value, COUNT(*) AS count
                FROM annotation_cases ac
                LEFT JOIN passages p ON p.passage_id=ac.target_passage_id
                LEFT JOIN source_documents sd ON sd.source_document_id=p.source_document_id
                WHERE TRIM(ac.target_work)='' AND ac.target_passage_id IS NOT NULL
                GROUP BY value
            """),
            "target_passage_canonical_status_counts": grouped(connection, """
                SELECT COALESCE(sd.canonical_status, '<missing>') AS value, COUNT(*) AS count
                FROM annotation_cases ac
                LEFT JOIN passages p ON p.passage_id=ac.target_passage_id
                LEFT JOIN source_documents sd ON sd.source_document_id=p.source_document_id
                WHERE TRIM(ac.target_work)='' AND ac.target_passage_id IS NOT NULL
                GROUP BY value
            """),
        }

        target_locations = {
            "total": int(connection.execute("SELECT COUNT(*) FROM candidate_target_locations").fetchone()[0]),
            "case_count": int(connection.execute("SELECT COUNT(DISTINCT case_id) FROM candidate_target_locations").fetchone()[0]),
            "identity_counts": grouped(connection, "SELECT work_identity_status AS value, COUNT(*) AS count FROM candidate_target_locations GROUP BY work_identity_status"),
            "passage_match_counts": grouped(connection, "SELECT target_passage_match_status AS value, COUNT(*) AS count FROM candidate_target_locations GROUP BY target_passage_match_status"),
            "candidate_passage_id_count": int(connection.execute(
                "SELECT COUNT(*) FROM candidate_target_locations WHERE target_passage_candidate_id IS NOT NULL"
            ).fetchone()[0]),
            "automatic_promotion_count": int(connection.execute(
                "SELECT COUNT(*) FROM candidate_target_locations WHERE machine_status <> 'candidate_only' OR human_status <> 'pending'"
            ).fetchone()[0]),
        }

        evidence = {
            "total": int(connection.execute("SELECT COUNT(*) FROM annotation_evidences").fetchone()[0]),
            "source_resolution_counts": grouped(connection, """
                SELECT COALESCE(json_extract(evidence_json,'$.source_resolution'), '<null>') AS value,
                       COUNT(*) AS count
                FROM annotation_evidences GROUP BY value
            """),
            "quote_check_counts": grouped(connection, "SELECT COALESCE(quote_check,'<null>') AS value, COUNT(*) AS count FROM annotation_evidences GROUP BY value"),
            "external_source_pending_count": int(connection.execute(
                "SELECT COUNT(*) FROM annotation_evidences WHERE json_extract(evidence_json,'$.source_resolution')='external_source_pending'"
            ).fetchone()[0]),
            "secondary_citation_match_count": int(connection.execute(
                "SELECT COUNT(*) FROM annotation_evidences WHERE json_extract(evidence_json,'$.source_resolution')='secondary_citation_match'"
            ).fetchone()[0]),
        }

        external = {
            "source_queue_count": int(connection.execute("SELECT COUNT(*) FROM external_source_resolution_queue").fetchone()[0]),
            "source_queue_status_counts": grouped(connection, "SELECT queue_status AS value, COUNT(*) AS count FROM external_source_resolution_queue GROUP BY queue_status"),
            "source_registry_status_counts": grouped(connection, "SELECT status AS value, COUNT(*) AS count FROM external_source_registry GROUP BY status"),
            "passage_queue_count": int(connection.execute("SELECT COUNT(*) FROM external_passage_resolution_queue").fetchone()[0]),
            "passage_queue_status_counts": grouped(connection, "SELECT queue_status AS value, COUNT(*) AS count FROM external_passage_resolution_queue GROUP BY queue_status"),
            "passage_status_counts": grouped(connection, "SELECT passage_status AS value, COUNT(*) AS count FROM external_passage_resolution_queue GROUP BY passage_status"),
            "candidate_passage_count": int(connection.execute(
                "SELECT COUNT(*) FROM passages p JOIN source_documents sd ON sd.source_document_id=p.source_document_id WHERE sd.source_kind='external_public_candidate'"
            ).fetchone()[0]),
        }

        states = {
            "case_count": int(connection.execute("SELECT COUNT(*) FROM annotation_cases").fetchone()[0]),
            "source_passage_case_count": int(connection.execute("SELECT COUNT(*) FROM annotation_cases WHERE source_passage_id IS NOT NULL").fetchone()[0]),
            "machine_status_counts": grouped(connection, "SELECT machine_status AS value, COUNT(*) AS count FROM annotation_cases GROUP BY machine_status"),
            "human_status_counts": grouped(connection, "SELECT human_status AS value, COUNT(*) AS count FROM annotation_cases GROUP BY human_status"),
            "lifecycle_counts": grouped(connection, "SELECT lifecycle AS value, COUNT(*) AS count FROM annotation_cases GROUP BY lifecycle"),
            "review_event_count": int(connection.execute("SELECT COUNT(*) FROM review_events").fetchone()[0]),
            "resolution_event_count": int(connection.execute("SELECT COUNT(*) FROM resolution_events").fetchone()[0]),
            "process_step_count": int(connection.execute("SELECT COUNT(*) FROM annotation_process_steps").fetchone()[0]),
            "five_step_case_count": int(connection.execute("""
                SELECT COUNT(*) FROM (
                    SELECT case_id FROM annotation_process_steps
                    WHERE field_name IN ('problem_discovery','research_question','evidence_collection','reasoning','conclusion')
                    GROUP BY case_id HAVING COUNT(DISTINCT field_name)=5
                )
            """).fetchone()[0]),
        }

        source_policy = [dict(row) for row in connection.execute(
            """
            SELECT work_key, source_file, source_file_sha256, canonical_status
            FROM source_documents WHERE canonical_status='canonical_active'
            ORDER BY work_key
            """
        ).fetchall()]

    validation = load_json(Path(validation_path))
    target_packet = load_json(Path(target_packet_report_path))
    external_packet = load_json(Path(external_packet_report_path))
    edition_candidates = load_json(Path(edition_candidate_manifest_path))
    legacy = load_json(Path(legacy_audit_path))
    source_inventory = load_json(Path(source_inventory_path))
    legacy_inventory = ((legacy.get("v2_representation") or {}).get("legacy_inventory_coverage") or {})
    main_usage = legacy.get("main_dictionary") or {}

    report = {
        "report_version": "automation-gap-report.v1",
        "generated_at": now(),
        "database": relative_path(database_path),
        "purpose": "Separate machine-materialized context from unresolved edition/semantic/human decisions; no state promotion is inferred.",
        "source_policy": {
            "active_canonical_documents": source_policy,
            "dushu_active_sha256": next((row["source_file_sha256"] for row in source_policy if row["work_key"] == "dushu_zazhi"), None),
            "mysql10_snapshot_status": ((source_inventory.get("mysql10_snapshot_search") or {}).get("status")),
            "legacy_machine_route": "02-数据库/data/dictionary.db -> 02-数据库/main/source.txt/parser.py/importer.py -> legacy_* V2 materialization",
        },
        "machine_materialized": {
            "legacy_dictionary_inventory": legacy_inventory,
            "legacy_main_field_population": main_usage.get("field_population"),
            "source_passage_cases": states["source_passage_case_count"],
            "process_fields": {
                "five_step_case_count": states["five_step_case_count"],
                "process_step_count": states["process_step_count"],
            },
            "candidate_target_locations": target_locations,
            "target_work_packets": {
                "valid": target_packet.get("valid"),
                "counts": target_packet.get("counts"),
                "coverage": target_packet.get("coverage"),
                "packet_file": target_packet.get("packet_file"),
            },
            "external_evidence_packets": {
                "valid": external_packet.get("valid"),
                "counts": external_packet.get("counts"),
                "coverage": external_packet.get("coverage"),
                "packet_file": external_packet.get("packet_file"),
            },
            "external_edition_candidates": {
                "manifest_file": relative_path(edition_candidate_manifest_path),
                "summary": edition_candidates.get("summary", {}),
                "conclusion": edition_candidates.get("conclusion"),
                "candidate_status_counts": {
                    key: sum(
                        1 for candidate in edition_candidates.get("candidates", [])
                        if candidate.get("availability_status") == key
                    )
                    for key in sorted({
                        candidate.get("availability_status")
                        for candidate in edition_candidates.get("candidates", [])
                        if candidate.get("availability_status")
                    })
                },
            },
        },
        "remaining_automation_gap": {
            "target_work_queue": target_queue,
            "evidence": evidence,
            "external_resolution": external,
            "external_edition_candidates": {
                "manifest_file": relative_path(edition_candidate_manifest_path),
                "summary": edition_candidates.get("summary", {}),
                "machine_only": True,
                "canonical_file_registered_count": 0,
                "quote_match_count": edition_candidates.get("summary", {}).get("quote_match_count", 0),
            },
            "human_and_gold_boundary": states,
            "unresolved_machine_tasks": [
                {
                    "name": "candidate_shell_target_identification",
                    "count": target_queue["origin_counts"].get("original_markdown_candidate_shell", 0),
                    "boundary": "Most candidate shells have no target label; candidate_target_locations are locating candidates only and require target-work/edition/passage decision.",
                },
                {
                    "name": "legacy_machine_or_ai_target_edition_resolution",
                    "count": target_queue["inference_status_counts"].get("machine_inferred", 0),
                    "boundary": "Explicit source-work labels and public candidates do not establish an external canonical edition or target passage.",
                },
                {
                    "name": "external_source_and_passage_resolution",
                    "count": external["source_queue_count"] + external["passage_queue_count"],
                    "boundary": "A public transcription/hash match is locating evidence; human must confirm edition, version and passage before canonical use.",
                },
                {
                    "name": "case_review_and_gold_gate",
                    "count": states["case_count"],
                    "boundary": "All cases remain machine draft/human pending; no review event or gold promotion has occurred.",
                },
            ],
        },
        "next_automated_actions": [
            "Keep rebuilding target packets, external packets, review tasks and validation after any queue or source change.",
            "If an independent external edition/bottom is supplied, bind it through the external source/passage resolution seam and rerun quote/hash validation; do not promote from public candidates alone.",
            "If human target-work or source decisions arrive, apply them through the transaction seams, then rebuild queues/tasks and rerun the full validation.",
            "Do not turn the 14 catalog-only terms or 12 catalog-only works into fabricated cases or evidence.",
        ],
        "boundary": {
            "database_write_performed": False,
            "human_review_performed": False,
            "gold_promotion_performed": False,
            "canonical_semantic_truth_asserted": False,
        },
    }
    report["valid"] = bool(
        report["boundary"]["database_write_performed"] is False
        and report["boundary"]["human_review_performed"] is False
        and report["boundary"]["gold_promotion_performed"] is False
        and report["machine_materialized"]["target_work_packets"]["valid"] is True
        and report["machine_materialized"]["external_evidence_packets"]["valid"] is True
    )
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", type=Path, default=DEFAULT_DATABASE)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    report = build_report(database_path=args.database)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"valid": report["valid"], "database": report["database"], "target_queue": report["remaining_automation_gap"]["target_work_queue"]}, ensure_ascii=False, indent=2))
    return 0 if report["valid"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
