#!/usr/bin/env python3
"""Build compact, machine-only target-work resolution proposals.

The full target-work packet is intentionally exhaustive and large.  This
artifact is the bounded review index: one row per pending queue item, with the
machine identity candidate, target-passage candidate summary, and the exact
reason a human still has to decide.  It never writes annotation case fields or
resolution events.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


V2_ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = V2_ROOT.parent
DEFAULT_DATABASE = V2_ROOT / "data/real_runs/annotation_v2.db"
DEFAULT_OUTPUT = V2_ROOT / "data/real_runs/target_work_resolution_proposals.v1.jsonl"
DEFAULT_REPORT = V2_ROOT / "data/real_runs/target_work_resolution_proposals_report.json"


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
        return json.loads(value or "")
    except (TypeError, ValueError):
        return fallback


def connect_read_only(database_path: Path) -> sqlite3.Connection:
    connection = sqlite3.connect(f"file:{database_path.resolve()}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA query_only = ON")
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:24]


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n")


def _target_passage_context(connection: sqlite3.Connection, passage_id: str | None) -> dict[str, Any] | None:
    if not passage_id:
        return None
    row = connection.execute(
        """
        SELECT p.passage_id, p.work_key, p.document_title, p.section_title,
               p.entry_title, p.entry_kind, p.local_ordinal, p.md_line_start,
               p.md_line_end, sd.source_document_id, sd.source_kind,
               sd.canonical_status, sd.source_file, sd.source_file_sha256
        FROM passages p
        JOIN source_documents sd USING(source_document_id)
        WHERE p.passage_id = ?
        """,
        (passage_id,),
    ).fetchone()
    return dict(row) if row else None


def _identity_context(connection: sqlite3.Connection, work_key: str | None, normalized_label: str) -> dict[str, Any]:
    if not work_key:
        return {
            "work_key": None,
            "canonical_title": None,
            "work_type": None,
            "identity_status": None,
            "alias_mapping_status": None,
            "alias_confidence": None,
            "alias_count": 0,
        }
    registry = connection.execute(
        """
        SELECT work_key, canonical_title, work_type, identity_status, metadata_json
        FROM work_registry WHERE work_key = ?
        """,
        (work_key,),
    ).fetchone()
    alias_rows = connection.execute(
        """
        SELECT mapping_status, confidence
        FROM work_aliases
        WHERE work_key = ? AND normalized_label = ?
        ORDER BY CASE mapping_status WHEN 'canonical' THEN 0 WHEN 'candidate' THEN 1 ELSE 2 END,
                 CASE confidence WHEN 'high' THEN 0 WHEN 'medium' THEN 1 ELSE 2 END
        """,
        (work_key, normalized_label),
    ).fetchall()
    if registry is None:
        return {
            "work_key": work_key,
            "canonical_title": None,
            "work_type": None,
            "identity_status": None,
            "alias_mapping_status": alias_rows[0]["mapping_status"] if alias_rows else None,
            "alias_confidence": alias_rows[0]["confidence"] if alias_rows else None,
            "alias_count": len(alias_rows),
        }
    return {
        "work_key": registry["work_key"],
        "canonical_title": registry["canonical_title"],
        "work_type": registry["work_type"],
        "identity_status": registry["identity_status"],
        "alias_mapping_status": alias_rows[0]["mapping_status"] if alias_rows else None,
        "alias_confidence": alias_rows[0]["confidence"] if alias_rows else None,
        "alias_count": len(alias_rows),
    }


def _location_summary(connection: sqlite3.Connection, case_id: str) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    rows = connection.execute(
        """
        SELECT ctl.candidate_target_id, ctl.raw_label, ctl.normalized_label,
               ctl.candidate_work_key, ctl.work_identity_status,
               ctl.target_passage_candidate_id, ctl.target_passage_match_status,
               ctl.target_passage_candidate_count, ctl.machine_status,
               p.document_title, p.section_title, p.entry_title, p.local_ordinal,
               sd.source_kind, sd.canonical_status, sd.source_file,
               sd.source_file_sha256
        FROM candidate_target_locations ctl
        LEFT JOIN passages p ON p.passage_id=ctl.target_passage_candidate_id
        LEFT JOIN source_documents sd ON sd.source_document_id=p.source_document_id
        WHERE ctl.case_id = ?
        ORDER BY ctl.candidate_target_id
        """,
        (case_id,),
    ).fetchall()
    statuses: Counter[str] = Counter()
    candidate_passages: list[dict[str, Any]] = []
    for row in rows:
        statuses[f"{row['work_identity_status']}:{row['target_passage_match_status']}"] += 1
        if not row["target_passage_candidate_id"]:
            continue
        candidate_passages.append(
            {
                "candidate_target_id": row["candidate_target_id"],
                "raw_label": row["raw_label"],
                "normalized_label": row["normalized_label"],
                "candidate_work_key": row["candidate_work_key"],
                "work_identity_status": row["work_identity_status"],
                "target_passage_candidate_id": row["target_passage_candidate_id"],
                "target_passage_match_status": row["target_passage_match_status"],
                "target_passage_candidate_count": row["target_passage_candidate_count"],
                "passage_location": {
                    "document_title": row["document_title"],
                    "section_title": row["section_title"],
                    "entry_title": row["entry_title"],
                    "local_ordinal": row["local_ordinal"],
                    "source_kind": row["source_kind"],
                    "canonical_status": row["canonical_status"],
                    "source_file": row["source_file"],
                    "source_file_sha256": row["source_file_sha256"],
                },
            }
        )
    summary = {
        "location_count": len(rows),
        "canonical_identity_count": sum(
            1 for row in rows if row["work_identity_status"] == "canonical"
        ),
        "candidate_passage_count": len(candidate_passages),
        "singleton_candidate_passage_count": sum(
            1 for row in candidate_passages if row["target_passage_candidate_count"] == 1
        ),
        "ambiguous_candidate_passage_count": sum(
            1 for row in candidate_passages if (row["target_passage_candidate_count"] or 0) > 1
        ),
        "status_counts": dict(statuses),
    }
    return summary, candidate_passages


def _recommendation(identity: dict[str, Any], target_passage: dict[str, Any] | None, location: dict[str, Any]) -> tuple[str, str]:
    identity_status = identity.get("identity_status")
    if identity_status == "canonical_active":
        if target_passage and target_passage.get("canonical_status") != "canonical_active":
            return (
                "canonical_work_but_legacy_target_passage",
                "确认目标典籍身份后，仍须从 canonical passage 重新选择目标位置；现有 target passage 不能直接升级。",
            )
        if location["singleton_candidate_passage_count"] == 1:
            return (
                "review_singleton_canonical_passage_candidate",
                "机器找到唯一 canonical passage 候选，但仍需人工确认版本、篇章和语义范围。",
            )
        return (
            "review_canonical_work_and_target_passage",
            "目标著作标签可映射到 active registry，但目标 passage/版本仍需人工确认。",
        )
    if identity_status == "external_pending":
        return (
            "resolve_external_edition_then_target_passage",
            "先解决外部典籍版本和底本，再选择 canonical target passage；当前只保留外部候选。",
        )
    if identity_status == "unknown":
        return (
            "disambiguate_work_identity_and_edition",
            "机器只找到未知/候选身份，需人工消歧著作、注家或版本。",
        )
    return (
        "identify_target_work_from_context",
        "当前没有可用书名标签，需根据案例和 evidence context 确认目标典籍。",
    )


def build_proposals(
    *,
    database_path: Path = DEFAULT_DATABASE,
    output_path: Path = DEFAULT_OUTPUT,
    report_path: Path = DEFAULT_REPORT,
) -> dict[str, Any]:
    database_path = Path(database_path).resolve()
    rows_out: list[dict[str, Any]] = []
    recommendation_counts: Counter[str] = Counter()
    identity_counts: Counter[str] = Counter()
    location_candidate_count = 0
    with connect_read_only(database_path) as connection:
        queue_rows = connection.execute(
            """
            SELECT q.queue_item_id, q.case_id, q.raw_label, q.normalized_label,
                   q.machine_candidate_work_key, q.machine_inference_status,
                   q.queue_status, q.evidence_indexes_json, q.context_json,
                   q.priority, q.updated_at,
                   ac.case_title, ac.origin, ac.source_work, ac.source_passage_id,
                   ac.target_work, ac.target_passage_id, ac.target_scope_json,
                   ac.human_status, ac.machine_status, ac.lifecycle
            FROM target_work_resolution_queue q
            JOIN annotation_cases ac ON ac.case_id=q.case_id
            WHERE q.queue_status IN ('pending','needs_context','uncertain')
            ORDER BY q.priority DESC, q.queue_item_id
            """
        ).fetchall()
        for row in queue_rows:
            identity = _identity_context(
                connection, row["machine_candidate_work_key"], row["normalized_label"]
            )
            target_passage = _target_passage_context(connection, row["target_passage_id"])
            location, candidate_passages = _location_summary(connection, row["case_id"])
            recommendation, reason = _recommendation(identity, target_passage, location)
            identity_counts[str(identity.get("identity_status") or "missing")] += 1
            recommendation_counts[recommendation] += 1
            location_candidate_count += location["candidate_passage_count"]
            rows_out.append(
                {
                    "proposal_schema": "target_work_resolution_proposal.v1",
                    "proposal_id": "target-work-proposal:" + digest(str(row["queue_item_id"])),
                    "queue_item_id": row["queue_item_id"],
                    "case_id": row["case_id"],
                    "case_snapshot": {
                        "case_title": row["case_title"],
                        "origin": row["origin"],
                        "source_work": row["source_work"],
                        "source_passage_id": row["source_passage_id"],
                        "target_work": row["target_work"],
                        "target_passage_id": row["target_passage_id"],
                        "target_scope": parse_json(row["target_scope_json"], {}),
                        "machine_status": row["machine_status"],
                        "human_status": row["human_status"],
                        "lifecycle": row["lifecycle"],
                    },
                    "machine_input": {
                        "raw_label": row["raw_label"],
                        "normalized_label": row["normalized_label"],
                        "machine_candidate_work_key": row["machine_candidate_work_key"],
                        "machine_inference_status": row["machine_inference_status"],
                        "queue_status": row["queue_status"],
                        "priority": row["priority"],
                        "evidence_indexes": parse_json(row["evidence_indexes_json"], []),
                    },
                    "machine_identity_candidate": identity,
                    "existing_target_passage": target_passage,
                    "candidate_location_summary": location,
                    "candidate_passages": candidate_passages,
                    "recommendation": {
                        "kind": recommendation,
                        "reason": reason,
                    },
                    "machine_only_boundary": {
                        "database_write_performed": False,
                        "target_work_written": False,
                        "target_passage_written": False,
                        "queue_status_written": False,
                        "resolution_event_written": False,
                        "human_status_written": False,
                        "gold_promotion_performed": False,
                        "candidate_identity_is_not_resolved": True,
                        "legacy_or_external_passage_is_not_canonical": True,
                    },
                    "review_ref": {
                        "task_type": "target_work_resolution",
                        "target_resolution_queue_item": row["queue_item_id"],
                        "full_packet_path": "v2/data/real_runs/target_work_resolution_packets.v1.jsonl",
                        "full_packet_id": f"target-work-resolution-packet:{row['queue_item_id']}",
                    },
                    "updated_at": row["updated_at"],
                }
            )
    report = {
        "report_version": "target-work-resolution-proposals.v1",
        "generated_at": now(),
        "database": relative_path(database_path),
        "proposal_file": relative_path(output_path),
        "counts": {
            "pending_queue_count": len(rows_out),
            "unique_queue_item_count": len({row["queue_item_id"] for row in rows_out}),
            "identity_status_counts": dict(identity_counts),
            "recommendation_counts": dict(recommendation_counts),
            "candidate_passage_refs_embedded": location_candidate_count,
        },
        "policy": {
            "read_only_database": True,
            "proposal_is_not_resolution": True,
            "human_reviewer_required": True,
            "canonical_target_passage_required_for_resolved": True,
            "legacy_target_passage_cannot_be_promoted": True,
            "external_edition_required_before_target_resolution": True,
        },
        "valid": all(row["machine_only_boundary"]["database_write_performed"] is False for row in rows_out),
    }
    write_jsonl(Path(output_path), rows_out)
    Path(report_path).parent.mkdir(parents=True, exist_ok=True)
    Path(report_path).write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return report


def validate_proposals(
    *,
    database_path: Path = DEFAULT_DATABASE,
    output_path: Path = DEFAULT_OUTPUT,
    report_path: Path = DEFAULT_REPORT,
) -> dict[str, Any]:
    database_path = Path(database_path).resolve()
    output_path = Path(output_path).resolve()
    errors: list[str] = []
    proposal_rows: list[dict[str, Any]] = []
    if not output_path.is_file():
        errors.append("proposal_file_missing")
    else:
        with output_path.open(encoding="utf-8") as handle:
            for line_number, line in enumerate(handle, start=1):
                try:
                    row = json.loads(line)
                except ValueError as exc:
                    errors.append(f"invalid_json_line:{line_number}:{exc}")
                    continue
                if not isinstance(row, dict):
                    errors.append(f"proposal_not_object:{line_number}")
                    continue
                proposal_rows.append(row)
    with connect_read_only(database_path) as connection:
        expected = {
            row["queue_item_id"]
            for row in connection.execute(
                """
                SELECT queue_item_id FROM target_work_resolution_queue
                WHERE queue_status IN ('pending','needs_context','uncertain')
                """
            )
        }
        actual = [str(row.get("queue_item_id")) for row in proposal_rows]
        actual_set = set(actual)
        if len(actual) != len(actual_set):
            errors.append("duplicate_queue_item_ids")
        if actual_set != expected:
            errors.append(
                f"queue_coverage_mismatch:missing={len(expected-actual_set)}:orphan={len(actual_set-expected)}"
            )
        for row in proposal_rows:
            boundary = row.get("machine_only_boundary") or {}
            for field in (
                "database_write_performed",
                "target_work_written",
                "target_passage_written",
                "queue_status_written",
                "resolution_event_written",
                "human_status_written",
                "gold_promotion_performed",
            ):
                if boundary.get(field) is not False:
                    errors.append(f"boundary_breach:{row.get('queue_item_id')}:{field}")
            if boundary.get("candidate_identity_is_not_resolved") is not True:
                errors.append(f"identity_boundary_breach:{row.get('queue_item_id')}")
    report = {
        "report_version": "target-work-resolution-proposals-validation.v1",
        "generated_at": now(),
        "database": relative_path(database_path),
        "proposal_file": relative_path(output_path),
        "proposal_report": relative_path(report_path),
        "counts": {
            "expected_queue_count": len(expected),
            "proposal_count": len(proposal_rows),
            "unique_proposal_queue_item_count": len(set(actual)),
        },
        "errors": errors,
        "policy": {
            "database_write_performed": False,
            "proposal_is_not_resolution": True,
            "queue_is_source_of_truth": True,
        },
        "valid": not errors,
    }
    return report


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--database", type=Path, default=DEFAULT_DATABASE)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--validate", action="store_true")
    args = parser.parse_args()
    report = build_proposals(
        database_path=args.database,
        output_path=args.output,
        report_path=args.report,
    )
    validation = validate_proposals(
        database_path=args.database,
        output_path=args.output,
        report_path=args.report,
    )
    validation_path = args.report.with_name(args.report.stem + ".validation.json")
    validation_path.write_text(json.dumps(validation, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                "ok": bool(report["valid"] and validation["valid"]),
                "proposal_report": relative_path(args.report),
                "validation_report": relative_path(validation_path),
                "counts": validation["counts"],
            },
            ensure_ascii=False,
        )
    )
    return 0 if report["valid"] and validation["valid"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
