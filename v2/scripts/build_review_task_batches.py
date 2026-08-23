#!/usr/bin/env python3
"""Build bounded, read-only review task artifacts from the V2 work database.

The V2 database remains the source of truth.  This command only reads the
database and writes a compact task manifest plus four JSONL streams:

* case review;
* target-work/target-scope resolution;
* external source/edition resolution; and
* external passage/quote resolution.

Each task has a stable task id and a deterministic batch id.  The artifact is
an input to human review, not a review decision and not a second database.
Nothing in this script changes target_work, target_passage_id, quote_check,
human_status, lifecycle, or gold state.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable


V2_ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = V2_ROOT.parent
DEFAULT_DATABASE = V2_ROOT / "data/real_runs/annotation_v2.db"
DEFAULT_OUTPUT_DIR = V2_ROOT / "data/real_runs/review_tasks"
DEFAULT_MANIFEST = "review_task_manifest.review.v1.json"
EXTERNAL_EVIDENCE_PACKET_PATH = "v2/data/real_runs/external_evidence_packets.v1.jsonl"
TARGET_WORK_RESOLUTION_PACKET_PATH = "v2/data/real_runs/target_work_resolution_packets.v1.jsonl"
TARGET_WORK_RESOLUTION_PROPOSAL_PATH = "v2/data/real_runs/target_work_resolution_proposals.v1.jsonl"

STREAMS = (
    "case_review",
    "target_work_resolution",
    "external_source_resolution",
    "external_passage_resolution",
)

REVIEW_SEQUENCE = (
    {
        "phase": 1,
        "stream": "external_source_resolution",
        "label": "外部来源 / 底本",
        "reason": "先确定被引典籍和可用底本；这一步不会直接把引文升级为 canonical。",
    },
    {
        "phase": 2,
        "stream": "external_passage_resolution",
        "label": "外部 passage / 引文",
        "reason": "底本登记后再核对 quote 与 passage；机器候选仍不能替代人工核验。",
    },
    {
        "phase": 3,
        "stream": "target_work_resolution",
        "label": "目标典籍消歧",
        "reason": "先处理有显式目标标签的可操作任务，无上下文候选壳留到最后。",
    },
    {
        "phase": 4,
        "stream": "case_review",
        "label": "案例字段审校",
        "reason": "目标范围和证据边界明确后，再逐案例决定字段与是否允许 approved。",
    },
)

REVIEW_CONTRACT = {
    "operation_id_required": True,
    "reviewer_required_for_decision": True,
    "approval_requires_field_decisions": [
        "source_passage",
        "target_work",
        "target_passage",
        "evidence",
        "process",
        "conclusion",
    ],
    "approval_requires_complete_evidence_decisions": True,
    "approval_never_comes_from_machine_status": True,
}


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def parse_json(value: Any, fallback: Any) -> Any:
    if isinstance(value, (dict, list)):
        return value
    try:
        return json.loads(value or "")
    except (TypeError, ValueError):
        return fallback


def relative_path(value: str | Path) -> str:
    path = Path(value)
    try:
        return path.resolve().relative_to(PROJECT_ROOT.resolve()).as_posix()
    except ValueError:
        return path.as_posix()


def connect_read_only(database_path: Path) -> sqlite3.Connection:
    if not database_path.exists():
        raise FileNotFoundError(f"V2 database not found: {database_path}")
    uri = f"file:{database_path.resolve()}?mode=ro"
    connection = sqlite3.connect(uri, uri=True)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA query_only = ON")
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def _passage_location(connection: sqlite3.Connection, passage_id: str | None) -> dict[str, Any] | None:
    if not passage_id:
        return None
    row = connection.execute(
        """
        SELECT passage_id, source_document_id, work_key, document_title,
               section_title, entry_title, entry_kind, md_line_start,
               md_line_end, local_ordinal
        FROM passages WHERE passage_id = ?
        """,
        (passage_id,),
    ).fetchone()
    return dict(row) if row else None


def _case_evidence_summary(connection: sqlite3.Connection, case_id: str) -> dict[str, Any]:
    rows = connection.execute(
        """
        SELECT evidence_index, source_work, quote, quote_check, passage_id,
               evidence_json
        FROM annotation_evidences
        WHERE case_id = ? ORDER BY evidence_index
        """,
        (case_id,),
    ).fetchall()
    resolutions: Counter[str] = Counter()
    quote_checks: Counter[str] = Counter()
    evidence_refs: list[dict[str, Any]] = []
    for row in rows:
        data = parse_json(row["evidence_json"], {})
        resolution = str(data.get("source_resolution") or "unknown")
        quote_check = str(row["quote_check"] or data.get("quote_check") or "unknown")
        resolutions[resolution] += 1
        quote_checks[quote_check] += 1
        evidence_refs.append(
            {
                "evidence_index": int(row["evidence_index"]),
                "source_work": row["source_work"],
                "quote": row["quote"],
                "quote_check": row["quote_check"],
                "passage_id": row["passage_id"],
                "source_resolution": resolution,
                "external_source_id": data.get("external_source_id"),
                "cited_work_match_status": data.get("cited_work_match_status"),
                "secondary_citation_passage_id": data.get("secondary_citation_passage_id"),
            }
        )
    return {
        "count": len(evidence_refs),
        "source_resolution_counts": dict(resolutions),
        "quote_check_counts": dict(quote_checks),
        "evidence_refs": evidence_refs,
    }


def _case_location_summary(connection: sqlite3.Connection, case_id: str) -> dict[str, Any]:
    rows = connection.execute(
        """
        SELECT work_identity_status, target_passage_match_status,
               COUNT(*) AS count
        FROM candidate_target_locations
        WHERE case_id = ?
        GROUP BY work_identity_status, target_passage_match_status
        """,
        (case_id,),
    ).fetchall()
    total = 0
    canonical = 0
    passage_candidates = 0
    statuses: Counter[str] = Counter()
    for row in rows:
        count = int(row["count"])
        total += count
        if row["work_identity_status"] == "canonical":
            canonical += count
        if row["target_passage_match_status"] == "candidate_match":
            passage_candidates += count
        statuses[
            f"{row['work_identity_status']}:{row['target_passage_match_status']}"
        ] += count
    return {
        "count": total,
        "canonical_identity_count": canonical,
        "passage_candidate_count": passage_candidates,
        "status_counts": dict(statuses),
    }


def build_case_review_tasks(connection: sqlite3.Connection) -> list[dict[str, Any]]:
    rows = connection.execute(
        """
        SELECT case_id, case_title, origin, source_work, target_work,
               target_works_json, target_scope_json, target_text,
               target_passage_id, target_location_json, process_text,
               evidence_state, source_passage_id, lifecycle, machine_status,
               human_status, review_status, updated_at
        FROM annotation_cases
        WHERE human_status IN ('pending', 'uncertain')
        ORDER BY case_id
        """
    ).fetchall()
    tasks = []
    for row in rows:
        case_id = row["case_id"]
        step_rows = connection.execute(
            """
            SELECT field_name, step_text
            FROM annotation_process_steps
            WHERE case_id = ? ORDER BY step_index
            """,
            (case_id,),
        ).fetchall()
        process = {
            step["field_name"]: step["step_text"]
            for step in step_rows
        }
        tasks.append(
            {
                "task_id": f"case-review:{case_id}",
                "task_type": "case_review",
                "case_id": case_id,
                "case_title": row["case_title"],
                "origin": row["origin"],
                "source_work": row["source_work"],
                "source_passage_id": row["source_passage_id"],
                "source_location": _passage_location(connection, row["source_passage_id"]),
                "target_work": row["target_work"],
                "target_works": parse_json(row["target_works_json"], []),
                "target_scope": parse_json(row["target_scope_json"], {}),
                "target_text": row["target_text"],
                "target_passage_id": row["target_passage_id"],
                "target_passage_location": _passage_location(connection, row["target_passage_id"]),
                "target_location_summary": _case_location_summary(connection, case_id),
                "target_location_json": parse_json(row["target_location_json"], {}),
                "evidence_state": row["evidence_state"],
                "evidence_summary": _case_evidence_summary(connection, case_id),
                "process_summary": {
                    "field_count": len(process),
                    "required_field_count": 5,
                    "missing_fields": [
                        field for field in (
                            "problem_discovery",
                            "research_question",
                            "evidence_collection",
                            "reasoning",
                            "conclusion",
                        ) if not str(process.get(field) or "").strip()
                    ],
                },
                "status": {
                    "lifecycle": row["lifecycle"],
                    "machine_status": row["machine_status"],
                    "human_status": row["human_status"],
                    "review_status": row["review_status"],
                },
                "review_contract": REVIEW_CONTRACT,
                "write_boundary": {
                    "submission": "erwang_v2.database.apply_case_review_submission",
                    "promotes_to_gold_only_after_explicit_approval_gate": True,
                },
                "detail_ref": {
                    "case_id": case_id,
                    "api_path": f"/api/v2/case?id={case_id}",
                    "database_table": "annotation_cases",
                },
                "updated_at": row["updated_at"],
            }
        )
    return tasks


def build_target_work_tasks(connection: sqlite3.Connection) -> list[dict[str, Any]]:
    rows = connection.execute(
        """
        SELECT queue_item_id, case_id, raw_label, normalized_label,
               machine_candidate_work_key, machine_inference_status,
               queue_status, evidence_indexes_json, context_json, priority,
               updated_at
        FROM target_work_resolution_queue
        WHERE queue_status IN ('pending', 'needs_context', 'uncertain')
        ORDER BY CASE queue_status
                   WHEN 'pending' THEN 0
                   WHEN 'uncertain' THEN 1
                   WHEN 'needs_context' THEN 2
                   ELSE 3
                 END,
                 CASE WHEN LENGTH(TRIM(raw_label)) > 0 THEN 0 ELSE 1 END,
                 priority DESC,
                 queue_item_id
        """
    ).fetchall()
    tasks = []
    for row in rows:
        context = parse_json(row["context_json"], {})
        tasks.append(
            {
                "task_id": row["queue_item_id"],
                "task_type": "target_work_resolution",
                "queue_item_id": row["queue_item_id"],
                "case_id": row["case_id"],
                "raw_label": row["raw_label"],
                "normalized_label": row["normalized_label"],
                "machine_candidate_work_key": row["machine_candidate_work_key"],
                "machine_inference_status": row["machine_inference_status"],
                "queue_status": row["queue_status"],
                "review_stage": (
                    "actionable_target_label"
                    if str(row["raw_label"] or "").strip()
                    else "needs_context"
                ),
                "evidence_indexes": parse_json(row["evidence_indexes_json"], []),
                "priority": row["priority"],
                "case_context": {
                    "case_title": context.get("case_title"),
                    "origin": context.get("origin"),
                    "source_work": context.get("source_work"),
                    "source_passage_id": context.get("source_passage_id"),
                    "target_scope": context.get("target_scope", {}),
                    "candidate_labels_for_case": context.get("candidate_labels_for_case", []),
                },
                "resolution_boundary": context.get(
                    "resolution_boundary",
                    "human must confirm work identity and target edition/passage; machine candidate is not a resolved target",
                ),
                "decision_contract": {
                    "allowed_statuses": ["resolved", "uncertain", "rejected"],
                    "writes_target_work": True,
                    "writes_target_passage": True,
                    "promotes_to_gold": False,
                    "resolution_event_kind": "target_work_resolution",
                    "submission": "erwang_v2.database.apply_target_work_resolution",
                },
                "target_resolution_packet_ref": {
                    "path": TARGET_WORK_RESOLUTION_PACKET_PATH,
                    "packet_id": f"target-work-resolution-packet:{row['queue_item_id']}",
                    "lookup_key": row["queue_item_id"],
                    "packet_scope": "case source/evidence/work-registry/candidate-location context for this queue item",
                    "machine_only": True,
                },
                "target_resolution_proposal_ref": {
                    "path": TARGET_WORK_RESOLUTION_PROPOSAL_PATH,
                    "proposal_id_prefix": "target-work-proposal:",
                    "lookup_key": row["queue_item_id"],
                    "proposal_scope": "compact machine-only target identity and passage-candidate review index",
                    "machine_only": True,
                },
                "detail_ref": {
                    "case_id": row["case_id"],
                    "api_path": f"/api/v2/case?id={row['case_id']}",
                },
                "updated_at": row["updated_at"],
            }
        )
    return tasks


def build_external_source_tasks(connection: sqlite3.Connection) -> list[dict[str, Any]]:
    rows = connection.execute(
        """
        SELECT q.queue_item_id, q.external_source_id, q.cited_work,
               q.registry_status, q.queue_status, q.edition_status,
               q.evidence_count, q.pending_evidence_count,
               q.candidate_evidence_count, q.context_json, q.updated_at,
               r.source_file, r.source_file_sha256, r.edition,
               r.location_note, r.metadata_json
        FROM external_source_resolution_queue q
        JOIN external_source_registry r
          ON r.external_source_id = q.external_source_id
        WHERE q.queue_status IN ('pending', 'candidate_available', 'no_public_match')
        ORDER BY CASE q.queue_status
                   WHEN 'candidate_available' THEN 0
                   WHEN 'pending' THEN 1
                   ELSE 2
                 END,
                 q.cited_work, q.external_source_id
        """
    ).fetchall()
    tasks = []
    for row in rows:
        evidence_refs = [
            dict(evidence)
            for evidence in connection.execute(
                """
                SELECT queue_item_id, case_id, evidence_index, quote,
                       queue_status, edition_status, passage_status,
                       candidate_refs_json, candidate_passage_ids_json
                FROM external_passage_resolution_queue
                WHERE external_source_id = ?
                ORDER BY case_id, evidence_index
                """,
                (row["external_source_id"],),
            ).fetchall()
        ]
        for evidence in evidence_refs:
            evidence["candidate_refs"] = parse_json(evidence.pop("candidate_refs_json"), [])
            evidence["candidate_passage_ids"] = parse_json(
                evidence.pop("candidate_passage_ids_json"), []
            )
        tasks.append(
            {
                "task_id": row["queue_item_id"],
                "task_type": "external_source_resolution",
                "queue_item_id": row["queue_item_id"],
                "external_source_id": row["external_source_id"],
                "cited_work": row["cited_work"],
                "registry_status": row["registry_status"],
                "queue_status": row["queue_status"],
                "edition_status": row["edition_status"],
                "evidence_count": row["evidence_count"],
                "pending_evidence_count": row["pending_evidence_count"],
                "candidate_evidence_count": row["candidate_evidence_count"],
                "registered_source": {
                    "source_file": row["source_file"],
                    "source_file_sha256": row["source_file_sha256"],
                    "edition": row["edition"],
                    "location_note": row["location_note"],
                },
                "registry_metadata": parse_json(row["metadata_json"], {}),
                "queue_context": parse_json(row["context_json"], {}),
                "evidence_refs": evidence_refs,
                "decision_contract": {
                    "allowed_statuses": ["verified", "candidate_available", "no_public_match", "rejected"],
                    "canonical_requires_edition_and_version_record": True,
                    "public_transcription_is_not_canonical": True,
                    "promotes_quote_check": False,
                    "resolution_event_kind": "external_source_resolution",
                    "submission": "erwang_v2.database.apply_external_source_resolution",
                    "does_not_register_passage": True,
                },
                "evidence_packet_ref": {
                    "path": EXTERNAL_EVIDENCE_PACKET_PATH,
                    "packet_id": f"external-evidence-packet:{row['external_source_id']}",
                    "lookup_key": row["external_source_id"],
                    "packet_scope": "all linked evidence rows for this external source",
                },
                "updated_at": row["updated_at"],
            }
        )
    return tasks


def build_external_passage_tasks(connection: sqlite3.Connection) -> list[dict[str, Any]]:
    rows = connection.execute(
        """
        SELECT queue_item_id, external_source_id, case_id, evidence_index,
               cited_work, quote, source_resolution, quote_check,
               queue_status, edition_status, passage_status,
               candidate_manifest_path, candidate_manifest_sha256,
               selected_passage_id, candidate_passage_ids_json,
               candidate_refs_json, context_json, updated_at
        FROM external_passage_resolution_queue
        WHERE queue_status IN ('pending', 'candidate_available', 'no_public_match')
        ORDER BY CASE queue_status
                   WHEN 'candidate_available' THEN 0
                   WHEN 'pending' THEN 1
                   ELSE 2
                 END,
                 cited_work, case_id, evidence_index
        """
    ).fetchall()
    tasks = []
    for row in rows:
        tasks.append(
            {
                "task_id": row["queue_item_id"],
                "task_type": "external_passage_resolution",
                "queue_item_id": row["queue_item_id"],
                "external_source_id": row["external_source_id"],
                "case_id": row["case_id"],
                "evidence_index": row["evidence_index"],
                "cited_work": row["cited_work"],
                "quote": row["quote"],
                "source_resolution": row["source_resolution"],
                "quote_check": row["quote_check"],
                "queue_status": row["queue_status"],
                "edition_status": row["edition_status"],
                "passage_status": row["passage_status"],
                "candidate_manifest": {
                    "path": row["candidate_manifest_path"],
                    "sha256": row["candidate_manifest_sha256"],
                    "refs": parse_json(row["candidate_refs_json"], []),
                    "passage_ids": parse_json(row["candidate_passage_ids_json"], []),
                },
                "selected_passage_id": row["selected_passage_id"],
                "context": parse_json(row["context_json"], {}),
                "decision_contract": {
                    "allowed_statuses": ["verified", "candidate_available", "no_public_match", "rejected"],
                    "quote_pass_requires_quote_in_selected_canonical_passage": True,
                    "secondary_citation_is_not_external_verification": True,
                    "hash_confirms_version_not_semantic_truth": True,
                    "promotes_case_to_gold": False,
                    "resolution_event_kind": "external_passage_resolution",
                    "submission": "erwang_v2.database.apply_external_passage_resolution",
                    "does_not_mutate_annotation_evidence": True,
                },
                "evidence_packet_ref": {
                    "path": EXTERNAL_EVIDENCE_PACKET_PATH,
                    "packet_id": f"external-evidence-packet:{row['external_source_id']}",
                    "lookup_key": row["external_source_id"],
                    "queue_item_id": row["queue_item_id"],
                    "packet_scope": "select this evidence row inside the source packet",
                },
                "detail_ref": {
                    "case_id": row["case_id"],
                    "evidence_index": row["evidence_index"],
                    "api_path": f"/api/v2/case?id={row['case_id']}",
                },
                "updated_at": row["updated_at"],
            }
        )
    return tasks


def _task_id_set(tasks: Iterable[dict[str, Any]]) -> set[str]:
    return {str(task["task_id"]) for task in tasks}


def _task_id_digest(task_ids: Iterable[str]) -> str:
    payload = "\n".join(sorted(str(task_id) for task_id in task_ids)).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _manifest_digest(manifest: dict[str, Any]) -> str:
    payload = dict(manifest)
    payload.pop("manifest_sha256", None)
    encoded = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _write_stream(path: Path, tasks: list[dict[str, Any]], batch_size: int) -> list[dict[str, Any]]:
    batches: list[dict[str, Any]] = []
    with path.open("w", encoding="utf-8") as handle:
        for offset in range(0, len(tasks), batch_size):
            batch = tasks[offset : offset + batch_size]
            batch_number = (offset // batch_size) + 1
            batch_id = f"{path.stem}.batch-{batch_number:04d}"
            for position, task in enumerate(batch, start=1):
                item = dict(task)
                item["batch_id"] = batch_id
                item["batch_number"] = batch_number
                item["batch_position"] = position
                item["batch_size"] = len(batch)
                item["batch_size_limit"] = batch_size
                handle.write(json.dumps(item, ensure_ascii=False, separators=(",", ":")) + "\n")
            batches.append(
                {
                    "batch_id": batch_id,
                    "batch_number": batch_number,
                    "task_count": len(batch),
                    "first_task_id": batch[0]["task_id"],
                    "last_task_id": batch[-1]["task_id"],
                }
            )
    return batches


def _validate_stream(tasks: list[dict[str, Any]], batches: list[dict[str, Any]], batch_size: int) -> dict[str, Any]:
    task_ids = [str(task["task_id"]) for task in tasks]
    duplicate_ids = sorted({task_id for task_id in task_ids if task_ids.count(task_id) > 1})
    invalid_batches = [
        batch["batch_id"]
        for batch in batches
        if int(batch["task_count"]) > batch_size
    ]
    return {
        "task_count": len(tasks),
        "batch_count": len(batches),
        "duplicate_task_id_count": len(duplicate_ids),
        "duplicate_task_id_examples": duplicate_ids[:10],
        "invalid_batch_count": len(invalid_batches),
        "valid": not duplicate_ids and not invalid_batches,
    }


def build_review_task_artifacts(
    *,
    database_path: Path = DEFAULT_DATABASE,
    output_dir: Path = DEFAULT_OUTPUT_DIR,
    batch_size: int = 100,
    manifest_path: Path | None = None,
) -> dict[str, Any]:
    if batch_size <= 0:
        raise ValueError("batch_size_must_be_positive")
    database_path = Path(database_path).resolve()
    output_dir = Path(output_dir).resolve()
    manifest_path = Path(manifest_path or (output_dir / DEFAULT_MANIFEST)).resolve()
    if manifest_path.name == "external_public_candidate_manifest.json":
        raise ValueError(
            "review_manifest_path_must_not_be_external_candidate_manifest; "
            "omit --manifest or pass review_task_manifest.review.v1.json"
        )
    output_dir.mkdir(parents=True, exist_ok=True)

    with connect_read_only(database_path) as connection:
        task_map = {
            "case_review": build_case_review_tasks(connection),
            "target_work_resolution": build_target_work_tasks(connection),
            "external_source_resolution": build_external_source_tasks(connection),
            "external_passage_resolution": build_external_passage_tasks(connection),
        }

    outputs: dict[str, dict[str, Any]] = {}
    stream_validation: dict[str, dict[str, Any]] = {}
    for stream in STREAMS:
        filename = f"{stream}.review_task.v1.jsonl"
        path = output_dir / filename
        batches = _write_stream(path, task_map[stream], batch_size)
        outputs[stream] = {
            "path": filename,
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            "task_count": len(task_map[stream]),
            "batch_count": len(batches),
            "task_id_sha256": _task_id_digest(
                task["task_id"] for task in task_map[stream]
            ),
            "batches": batches,
        }
        stream_validation[stream] = _validate_stream(
            task_map[stream], batches, batch_size
        )

    counts = {stream: len(task_map[stream]) for stream in STREAMS}
    coverage = {
        "all_pending_tasks_linked": all(
            stream_validation[stream]["task_count"] == counts[stream]
            and stream_validation[stream]["valid"]
            for stream in STREAMS
        ),
        "stream_validation": stream_validation,
        "task_id_examples": {
            stream: {
                "first": [task["task_id"] for task in task_map[stream][:3]],
                "last": [task["task_id"] for task in task_map[stream][-3:]],
            }
            for stream in STREAMS
        },
    }
    manifest = {
        "report_version": "v2-review-task-manifest.v1",
        "generated_at": now(),
        "database": relative_path(database_path),
        "output_directory": relative_path(output_dir),
        "batch_size": batch_size,
        "streams": list(STREAMS),
        "review_sequence": list(REVIEW_SEQUENCE),
        "counts": counts,
        "policy": {
            "database_write_performed": False,
            "source_database_read_mode": "sqlite_read_only_query_only",
            "machine_status_is_not_human_decision": True,
            "public_transcription_is_not_canonical": True,
            "task_artifacts_are_not_review_events": True,
            "task_build_promotes_nothing": True,
            "external_evidence_packet_is_machine_only": True,
            "target_work_resolution_packet_is_machine_only": True,
            "review_event_write_boundary": [
                "erwang_v2.database.apply_case_review_submission",
                "erwang_v2.database.apply_target_work_resolution",
                "erwang_v2.database.apply_external_source_resolution",
                "erwang_v2.database.apply_external_passage_resolution",
            ],
        },
        "coverage": coverage,
        "outputs": outputs,
    }
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest["manifest_sha256"] = _manifest_digest(manifest)
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    manifest_path.with_suffix(manifest_path.suffix + ".sha256").write_text(
        f"{manifest['manifest_sha256']}  {manifest_path.name}\n",
        encoding="utf-8",
    )
    return {
        "manifest": relative_path(manifest_path),
        "manifest_sha256": manifest["manifest_sha256"],
        "review_sequence": list(REVIEW_SEQUENCE),
        "counts": counts,
        "batch_counts": {
            stream: outputs[stream]["batch_count"] for stream in STREAMS
        },
        "coverage": coverage,
        "policy": manifest["policy"],
        "validation": {
            "valid": bool(coverage["all_pending_tasks_linked"]),
            "stream_validation": stream_validation,
        },
    }


def validate_review_task_artifacts(
    *,
    database_path: Path = DEFAULT_DATABASE,
    manifest_path: Path,
) -> dict[str, Any]:
    """Reconcile persisted task streams with the current pending DB queues."""

    database_path = Path(database_path).resolve()
    manifest_path = Path(manifest_path).resolve()
    errors: list[str] = []
    if not manifest_path.exists():
        return {
            "valid": False,
            "errors": [f"manifest_missing:{relative_path(manifest_path)}"],
            "stream_counts": {},
        }
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        return {
            "valid": False,
            "errors": [f"manifest_invalid:{type(error).__name__}"],
            "stream_counts": {},
        }

    expected_manifest_hash = manifest.get("manifest_sha256")
    if expected_manifest_hash != _manifest_digest(manifest):
        errors.append("manifest_sha256_mismatch")
    batch_size = int(manifest.get("batch_size") or 0)
    if batch_size <= 0:
        errors.append("invalid_batch_size")
    if tuple(manifest.get("streams") or ()) != STREAMS:
        errors.append("stream_list_mismatch")
    if tuple(
        item.get("stream") for item in (manifest.get("review_sequence") or ())
    ) != tuple(item["stream"] for item in REVIEW_SEQUENCE):
        errors.append("review_sequence_mismatch")

    output_dir = manifest_path.parent
    actual_ids: dict[str, set[str]] = {}
    stream_counts: dict[str, Any] = {}
    for stream in STREAMS:
        output = (manifest.get("outputs") or {}).get(stream) or {}
        relative_output = output.get("path")
        if not relative_output:
            errors.append(f"output_path_missing:{stream}")
            actual_ids[stream] = set()
            continue
        path = output_dir / relative_output
        if not path.exists():
            errors.append(f"output_missing:{stream}")
            actual_ids[stream] = set()
            continue
        actual_hash = hashlib.sha256(path.read_bytes()).hexdigest()
        if actual_hash != output.get("sha256"):
            errors.append(f"output_sha256_mismatch:{stream}")
        ids: list[str] = []
        invalid_batch_rows = 0
        parse_errors = 0
        for line in path.read_text(encoding="utf-8").splitlines():
            try:
                row = json.loads(line)
            except ValueError:
                parse_errors += 1
                continue
            task_id = str(row.get("task_id") or "")
            if not task_id:
                errors.append(f"task_id_missing:{stream}")
            ids.append(task_id)
            if int(row.get("batch_size") or 0) > batch_size:
                invalid_batch_rows += 1
        actual_ids[stream] = set(ids)
        if len(ids) != len(set(ids)):
            errors.append(f"duplicate_task_id:{stream}")
        if parse_errors:
            errors.append(f"json_parse_errors:{stream}:{parse_errors}")
        if invalid_batch_rows:
            errors.append(f"batch_size_exceeded:{stream}:{invalid_batch_rows}")
        if len(ids) != int(output.get("task_count") or 0):
            errors.append(f"task_count_mismatch:{stream}")
        if _task_id_digest(ids) != output.get("task_id_sha256"):
            errors.append(f"task_id_sha256_mismatch:{stream}")
        stream_counts[stream] = {
            "artifact_count": len(ids),
            "manifest_count": int(output.get("task_count") or 0),
            "batch_count": int(output.get("batch_count") or 0),
        }

    expected_ids: dict[str, set[str]] = {}
    with connect_read_only(database_path) as connection:
        expected_ids["case_review"] = {
            f"case-review:{row['case_id']}"
            for row in connection.execute(
                "SELECT case_id FROM annotation_cases WHERE human_status IN ('pending', 'uncertain')"
            )
        }
        expected_ids["target_work_resolution"] = {
            row["queue_item_id"]
            for row in connection.execute(
                """
                SELECT queue_item_id FROM target_work_resolution_queue
                WHERE queue_status IN ('pending', 'needs_context', 'uncertain')
                """
            )
        }
        expected_ids["external_source_resolution"] = {
            row["queue_item_id"]
            for row in connection.execute(
                """
                SELECT queue_item_id FROM external_source_resolution_queue
                WHERE queue_status IN ('pending', 'candidate_available', 'no_public_match')
                """
            )
        }
        expected_ids["external_passage_resolution"] = {
            row["queue_item_id"]
            for row in connection.execute(
                """
                SELECT queue_item_id FROM external_passage_resolution_queue
                WHERE queue_status IN ('pending', 'candidate_available', 'no_public_match')
                """
            )
        }

    coverage: dict[str, Any] = {}
    for stream in STREAMS:
        missing = sorted(expected_ids[stream] - actual_ids.get(stream, set()))
        stale = sorted(actual_ids.get(stream, set()) - expected_ids[stream])
        coverage[stream] = {
            "expected_count": len(expected_ids[stream]),
            "artifact_count": len(actual_ids.get(stream, set())),
            "missing_count": len(missing),
            "stale_count": len(stale),
            "missing_examples": missing[:10],
            "stale_examples": stale[:10],
            "covered": not missing and not stale,
        }
        if missing:
            errors.append(f"pending_tasks_missing:{stream}:{len(missing)}")
        if stale:
            errors.append(f"stale_tasks_present:{stream}:{len(stale)}")

    return {
        "valid": not errors,
        "errors": errors,
        "manifest": relative_path(manifest_path),
        "database": relative_path(database_path),
        "batch_size": batch_size,
        "stream_counts": stream_counts,
        "coverage": coverage,
        "policy": {
            "database_write_performed": False,
            "task_artifacts_are_not_review_events": True,
            "pending_queue_is_source_of_truth": True,
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", type=Path, default=DEFAULT_DATABASE)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--batch-size", type=int, default=100)
    parser.add_argument("--manifest", type=Path, default=None)
    args = parser.parse_args()
    report = build_review_task_artifacts(
        database_path=args.database,
        output_dir=args.output_dir,
        batch_size=args.batch_size,
        manifest_path=args.manifest,
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["validation"]["valid"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
