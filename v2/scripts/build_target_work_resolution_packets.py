#!/usr/bin/env python3
"""Build queue-bound, machine-only packets for target-work resolution.

The target-work queue contains machine labels and unresolved context, not
resolved target works.  This command reads the V2 database in SQLite
read-only mode and materializes one packet for every pending queue row.  A
packet joins the case snapshot, source passage, evidence and their passage
links, work-registry/alias context, original candidate target locations, and
external-resolution references.

The artifact is deliberately below the human-review boundary.  It never
updates ``annotation_cases.target_work``, ``target_passage_id``, review state,
quote state, resolution events, or gold state.  A canonical work identity or
an exact machine passage candidate is still only a candidate for a human
edition/location decision.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
import unicodedata
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable


V2_ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = V2_ROOT.parent
DEFAULT_DATABASE = V2_ROOT / "data/real_runs/annotation_v2.db"
DEFAULT_PACKET = V2_ROOT / "data/real_runs/target_work_resolution_packets.v1.jsonl"
DEFAULT_REPORT = V2_ROOT / "data/real_runs/target_work_resolution_packets_report.json"
QUEUE_STATUSES = ("pending", "needs_context", "uncertain")


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


def normalize_label(value: Any) -> str:
    text = unicodedata.normalize("NFKC", str(value or "")).strip()
    text = text.strip("《》")
    return " ".join(text.split())


def connect_read_only(database_path: Path) -> sqlite3.Connection:
    if not database_path.is_file():
        raise FileNotFoundError(f"v2_database_not_found:{database_path}")
    uri = f"file:{database_path.resolve()}?mode=ro"
    connection = sqlite3.connect(uri, uri=True)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA query_only = ON")
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def chunked(values: Iterable[str], size: int = 800) -> Iterable[list[str]]:
    chunk: list[str] = []
    for value in values:
        chunk.append(str(value))
        if len(chunk) >= size:
            yield chunk
            chunk = []
    if chunk:
        yield chunk


def select_in(
    connection: sqlite3.Connection,
    sql_prefix: str,
    values: Iterable[str],
    sql_suffix: str = "",
) -> list[sqlite3.Row]:
    values = [str(value) for value in values if value]
    rows: list[sqlite3.Row] = []
    for part in chunked(values):
        placeholders = ",".join("?" for _ in part)
        rows.extend(connection.execute(
            f"{sql_prefix} ({placeholders}) {sql_suffix}", tuple(part)
        ).fetchall())
    return rows


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _compact_counter(counter: Counter[str]) -> dict[str, int]:
    return {str(key): int(value) for key, value in sorted(counter.items())}


def _passage_payload(
    connection: sqlite3.Connection,
    passage_id: str | None,
    cache: dict[str, dict[str, Any] | None],
) -> dict[str, Any] | None:
    if not passage_id:
        return None
    passage_id = str(passage_id)
    if passage_id in cache:
        return cache[passage_id]
    row = connection.execute(
        """
        SELECT p.passage_id, p.source_document_id, p.work_key,
               p.document_title, p.section_title, p.entry_title,
               p.entry_kind, p.local_ordinal, p.md_line_start, p.md_line_end,
               p.raw_text, p.plain_text, p.normalized_text,
               p.raw_text_sha256, p.normalized_text_sha256,
               p.inline_notes_json,
               sd.source_kind, sd.source_file, sd.source_file_sha256,
               sd.canonical_status AS source_canonical_status,
               sd.metadata_json AS source_metadata_json,
               sd.supersedes_source_document_id
        FROM passages p
        JOIN source_documents sd
          ON sd.source_document_id = p.source_document_id
        WHERE p.passage_id = ?
        """,
        (passage_id,),
    ).fetchone()
    if row is None:
        cache[passage_id] = None
        return None
    payload = dict(row)
    payload["inline_notes"] = parse_json(payload.pop("inline_notes_json"), [])
    payload["source_metadata"] = parse_json(payload.pop("source_metadata_json"), {})
    payload["canonical_boundary"] = {
        "source_kind": payload["source_kind"],
        "source_canonical_status": payload["source_canonical_status"],
        "is_canonical_active": payload["source_canonical_status"] == "canonical_active",
        "is_legacy_or_machine_only": payload["source_canonical_status"] != "canonical_active",
    }
    cache[passage_id] = payload
    return payload


def _source_version_context(
    connection: sqlite3.Connection,
    work_key: str,
) -> dict[str, Any]:
    documents = [
        dict(row)
        for row in connection.execute(
            """
            SELECT source_document_id, work_key, source_kind, source_file,
                   source_file_sha256, canonical_status, supersedes_source_document_id,
                   metadata_json
            FROM source_documents WHERE work_key = ?
            ORDER BY canonical_status, source_file_sha256
            """,
            (work_key,),
        ).fetchall()
    ]
    for row in documents:
        row["metadata"] = parse_json(row.pop("metadata_json"), {})
    registry = [
        dict(row)
        for row in connection.execute(
            """
            SELECT source_version_id, work_key, source_file, source_file_sha256,
                   canonical_status, superseded_by_sha256, reason, metadata_json,
                   recorded_at
            FROM source_version_registry WHERE work_key = ?
            ORDER BY canonical_status, source_file_sha256
            """,
            (work_key,),
        ).fetchall()
    ]
    for row in registry:
        row["metadata"] = parse_json(row.pop("metadata_json"), {})
    return {
        "work_key": work_key,
        "source_documents": documents,
        "source_version_registry": registry,
        "canonical_active_hashes": sorted({
            str(row["source_file_sha256"])
            for row in documents
            if row["canonical_status"] == "canonical_active"
        }),
    }


def _alias_context(
    aliases_by_label: dict[str, list[dict[str, Any]]],
    normalized_label: str,
) -> dict[str, Any]:
    rows = aliases_by_label.get(normalized_label, [])
    mapping_status = Counter(str(row["mapping_status"]) for row in rows)
    confidence = Counter(str(row["confidence"]) for row in rows)
    methods = Counter(str(row["mapping_method"]) for row in rows)
    work_keys = Counter(str(row["work_key"]) for row in rows)
    source_records = sorted({
        str(row["source_record_id"])
        for row in rows
        if str(row["source_record_id"] or "").strip()
    })
    # A large canonical alias group (for example repeated legacy source-work
    # mappings) is represented by a complete count and deterministic sample;
    # the database table remains the complete source of record.
    sample = [
        {
            "work_key": row["work_key"],
            "raw_label": row["raw_label"],
            "mapping_status": row["mapping_status"],
            "mapping_method": row["mapping_method"],
            "confidence": row["confidence"],
            "source_file": row["source_file"],
            "source_record_id": row["source_record_id"],
            "metadata": row["metadata"],
        }
        for row in rows[:100]
    ]
    return {
        "normalized_label": normalized_label,
        "match_count": len(rows),
        "mapping_status_counts": _compact_counter(mapping_status),
        "confidence_counts": _compact_counter(confidence),
        "mapping_method_counts": _compact_counter(methods),
        "work_key_counts": _compact_counter(work_keys),
        "source_record_count": len(source_records),
        "source_record_ids_sha256": hashlib.sha256(
            "\n".join(source_records).encode("utf-8")
        ).hexdigest() if source_records else None,
        "source_record_id_sample": source_records[:100],
        "sample_limit": 100,
        "matches_sample": sample,
        "complete_source": {
            "database_table": "work_aliases",
            "query": "SELECT * FROM work_aliases WHERE normalized_label = ? ORDER BY work_alias_id",
            "parameter": normalized_label,
            "sample_is_not_complete": len(rows) > len(sample),
        },
    }


def _row_with_json(row: sqlite3.Row, json_fields: Iterable[str]) -> dict[str, Any]:
    result = dict(row)
    for field in json_fields:
        if field in result:
            result[field.removesuffix("_json")] = parse_json(result.pop(field), {})
    return result


def _case_snapshot(
    row: dict[str, Any],
    process_steps: list[dict[str, Any]],
) -> dict[str, Any]:
    case_data = parse_json(row.get("case_json"), {})
    migration = case_data.get("_migration") if isinstance(case_data, dict) else {}
    if not isinstance(migration, dict):
        migration = {}
    return {
        "case_id": row["case_id"],
        "schema_version": row["schema_version"],
        "case_title": row["case_title"],
        "submitted_by": row["submitted_by"],
        "source_work": row["source_work"],
        "target_work": row["target_work"],
        "target_text": row["target_text"],
        "source_passage_id": row["source_passage_id"],
        "origin": row["origin"],
        "lifecycle": row["lifecycle"],
        "machine_status": row["machine_status"],
        "human_status": row["human_status"],
        "review_status": row["review_status"],
        "target_works": row["target_works"],
        "target_scope": row["target_scope"],
        "evidence_state": row["evidence_state"],
        "target_passage_id": row["target_passage_id"],
        "target_location": row["target_location"],
        "process_text": row["process_text"],
        "process_steps": process_steps,
        "machine_result": row["machine_result"],
        "human_review": row["human_review"],
        "migration_provenance": migration.get("provenance", {}),
        "migration_target_work_inference": migration.get("target_work_inference", {}),
        "migration_transformation": {
            "source_format": migration.get("source_format"),
            "source_layer": migration.get("source_layer"),
            "transformation_kind": migration.get("transformation_kind"),
            "transformation_description": migration.get("transformation_description"),
        },
    }


def _machine_assessment(
    queue: dict[str, Any],
    case: dict[str, Any],
    registry: dict[str, Any] | None,
    evidence_rows: list[dict[str, Any]],
    location_rows: list[dict[str, Any]],
) -> dict[str, Any]:
    blockers: list[str] = []
    if not str(queue.get("raw_label") or "").strip():
        blockers.append("target_work_label_missing")
    if not queue.get("machine_candidate_work_key"):
        blockers.append("machine_work_identity_not_mapped")
    elif not registry:
        blockers.append("machine_work_key_not_in_work_registry")
    elif registry.get("identity_status") != "canonical_active":
        blockers.append("work_identity_is_candidate_or_unknown")
    if not str(case.get("target_passage_id") or "").strip():
        blockers.append("target_passage_not_bound")
    if not location_rows:
        blockers.append("no_original_candidate_target_location_for_case")
    elif not any(row.get("target_passage_candidate_id") for row in location_rows):
        blockers.append("candidate_locations_have_no_target_passage_candidate")
    return {
        "status": "machine_candidate_only",
        "queue_status": queue["queue_status"],
        "machine_inference_status": queue["machine_inference_status"],
        "machine_candidate_work_key": queue["machine_candidate_work_key"],
        "registry_identity_status": registry.get("identity_status") if registry else None,
        "evidence_source_resolution_counts": _compact_counter(
            Counter(str(row.get("source_resolution") or "unknown") for row in evidence_rows)
        ),
        "original_candidate_location_count": len(location_rows),
        "blockers": blockers,
        "automated_target_work_resolution_allowed": False,
        "automated_target_passage_resolution_allowed": False,
        "reason": "The packet assembles locating context only; a human must choose the target work identity, edition, and target passage.",
    }


def build_packets(
    *,
    database_path: Path = DEFAULT_DATABASE,
    packet_path: Path = DEFAULT_PACKET,
    report_path: Path = DEFAULT_REPORT,
) -> dict[str, Any]:
    generated_at = now()
    database_path = Path(database_path).resolve()
    packet_path = Path(packet_path).resolve()
    report_path = Path(report_path).resolve()

    with connect_read_only(database_path) as connection:
        queue_rows = [
            dict(row)
            for row in connection.execute(
                """
                SELECT queue_item_id, case_id, raw_label, normalized_label,
                       machine_candidate_work_key, machine_inference_status,
                       queue_status, evidence_indexes_json, context_json, priority,
                       created_at, updated_at
                FROM target_work_resolution_queue
                WHERE queue_status IN ('pending', 'needs_context', 'uncertain')
                ORDER BY priority DESC, queue_item_id
                """
            ).fetchall()
        ]
        for row in queue_rows:
            row["evidence_indexes"] = parse_json(row.pop("evidence_indexes_json"), [])
            row["context"] = parse_json(row.pop("context_json"), {})

        case_ids = sorted({str(row["case_id"]) for row in queue_rows})
        case_rows = {
            str(row["case_id"]): {
                **dict(row),
                "target_works": parse_json(row["target_works_json"], []),
                "target_scope": parse_json(row["target_scope_json"], {}),
                "target_location": parse_json(row["target_location_json"], {}),
                "machine_result": parse_json(row["machine_result_json"], {}),
                "human_review": parse_json(row["human_review_json"], {}),
            }
            for row in select_in(
                connection,
                """
                SELECT case_id, schema_version, case_title, submitted_by,
                       source_work, target_work, target_text, source_passage_id,
                       origin, lifecycle, machine_status, human_status,
                       review_status, machine_result_json, human_review_json,
                       case_json, target_works_json, target_scope_json,
                       evidence_state, target_passage_id, target_location_json,
                       process_text, updated_at
                FROM annotation_cases WHERE case_id IN
                """,
                case_ids,
            )
        }

        process_by_case: dict[str, list[dict[str, Any]]] = defaultdict(list)
        if case_ids:
            for row in select_in(
                connection,
                """
                SELECT case_id, step_index, field_name, step_text, step_json
                FROM annotation_process_steps WHERE case_id IN
                """,
                case_ids,
                "ORDER BY case_id, step_index",
            ):
                item = dict(row)
                item["step_data"] = parse_json(item.pop("step_json"), {})
                process_by_case[str(row["case_id"])].append(item)

        evidence_by_case: dict[str, list[dict[str, Any]]] = defaultdict(list)
        if case_ids:
            for row in select_in(
                connection,
                """
                SELECT case_id, evidence_index, passage_id, source_work,
                       quote, quote_sha256, quote_check, evidence_json
                FROM annotation_evidences WHERE case_id IN
                """,
                case_ids,
                "ORDER BY case_id, evidence_index",
            ):
                item = dict(row)
                item["evidence"] = parse_json(item.pop("evidence_json"), {})
                item["source_resolution"] = item["evidence"].get("source_resolution") or "unknown"
                item["external_source_id"] = item["evidence"].get("external_source_id")
                item["source_location"] = item["evidence"].get("source_location")
                evidence_by_case[str(row["case_id"])].append(item)

        location_by_case: dict[str, list[dict[str, Any]]] = defaultdict(list)
        location_rows = connection.execute(
            """
            SELECT candidate_target_id, candidate_id, case_id, raw_label,
                   normalized_label, candidate_work_key, work_identity_status,
                   label_start_char, label_end_char, label_match,
                   source_passage_id, target_passage_candidate_id,
                   target_passage_match_status, target_passage_candidate_count,
                   evidence_indexes_json, machine_status, human_status,
                   provenance_json, created_at, updated_at
            FROM candidate_target_locations
            ORDER BY case_id, candidate_target_id
            """
        ).fetchall()
        location_candidate_ids: set[str] = set()
        for row in location_rows:
            item = _row_with_json(row, ("evidence_indexes_json", "provenance_json"))
            case_id = str(item["case_id"])
            location_by_case[case_id].append(item)
            location_candidate_ids.add(str(item["candidate_id"]))

        candidate_items_by_id: dict[str, dict[str, Any]] = {}
        if location_candidate_ids:
            for row in select_in(
                connection,
                """
                SELECT candidate_id, source_document_id, passage_id, work_key,
                       source_work, candidate_text, rule_hits_json, risk_flags_json,
                       candidate_status, origin, output_case_id, provenance_json,
                       created_at, updated_at
                FROM candidate_items WHERE candidate_id IN
                """,
                sorted(location_candidate_ids),
            ):
                item = dict(row)
                for field in ("rule_hits_json", "risk_flags_json", "provenance_json"):
                    item[field.removesuffix("_json")] = parse_json(item.pop(field), {})
                candidate_items_by_id[str(item["candidate_id"])] = item

        registry_rows = [dict(row) for row in connection.execute(
            "SELECT work_key, canonical_title, author, work_type, identity_status, metadata_json, created_at, updated_at FROM work_registry ORDER BY work_key"
        ).fetchall()]
        work_registry = {}
        for row in registry_rows:
            row["metadata"] = parse_json(row.pop("metadata_json"), {})
            work_registry[str(row["work_key"])] = row

        aliases_by_label: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for row in connection.execute(
            """
            SELECT work_alias_id, work_key, raw_label, normalized_label,
                   mapping_status, mapping_method, confidence, source_file,
                   source_record_id, metadata_json
            FROM work_aliases ORDER BY normalized_label, work_alias_id
            """
        ).fetchall():
            item = dict(row)
            item["metadata"] = parse_json(item.pop("metadata_json"), {})
            aliases_by_label[str(item["normalized_label"])].append(item)

        external_registry = {
            str(row["external_source_id"]): dict(row)
            for row in connection.execute("SELECT * FROM external_source_registry").fetchall()
        }
        external_source_queue = {
            str(row["external_source_id"]): _row_with_json(row, ("context_json",))
            for row in connection.execute("SELECT * FROM external_source_resolution_queue").fetchall()
        }
        external_passage_queue: dict[tuple[str, int], dict[str, Any]] = {}
        for row in connection.execute("SELECT * FROM external_passage_resolution_queue").fetchall():
            item = _row_with_json(row, ("candidate_refs_json", "context_json", "candidate_passage_ids_json"))
            external_passage_queue[(str(item["case_id"]), int(item["evidence_index"]))] = item

        passage_cache: dict[str, dict[str, Any] | None] = {}
        packet_rows: list[dict[str, Any]] = []
        queue_status_counts: Counter[str] = Counter()
        inference_status_counts: Counter[str] = Counter()
        origin_counts: Counter[str] = Counter()
        registry_status_counts: Counter[str] = Counter()
        total_evidence_rows = 0
        total_location_rows = 0
        packets_with_source_passage = 0
        packets_with_work_key = 0
        packets_with_registry = 0

        for queue in queue_rows:
            case_id = str(queue["case_id"])
            case = case_rows.get(case_id)
            if case is None:
                raise ValueError(f"target_work_queue_case_missing:{case_id}")
            evidence_rows = evidence_by_case.get(case_id, [])
            locations = location_by_case.get(case_id, [])
            target_key = queue.get("machine_candidate_work_key")
            registry = work_registry.get(str(target_key)) if target_key else None
            queue_status_counts[str(queue["queue_status"])] += 1
            inference_status_counts[str(queue["machine_inference_status"])] += 1
            origin_counts[str(case["origin"])] += 1
            registry_status_counts[str(registry["identity_status"] if registry else "missing")] += 1
            total_evidence_rows += len(evidence_rows)
            total_location_rows += len(locations)
            if case.get("source_passage_id"):
                packets_with_source_passage += 1
            if target_key:
                packets_with_work_key += 1
            if registry:
                packets_with_registry += 1

            referenced_passage_ids: set[str] = set()
            for value in (
                case.get("source_passage_id"),
                case.get("target_passage_id"),
            ):
                if value:
                    referenced_passage_ids.add(str(value))
            for evidence in evidence_rows:
                if evidence.get("passage_id"):
                    referenced_passage_ids.add(str(evidence["passage_id"]))
                source_location = evidence.get("source_location") or {}
                if isinstance(source_location, dict) and source_location.get("passage_id"):
                    referenced_passage_ids.add(str(source_location["passage_id"]))
            for location in locations:
                for field in ("source_passage_id", "target_passage_candidate_id"):
                    if location.get(field):
                        referenced_passage_ids.add(str(location[field]))

            passage_context: dict[str, dict[str, Any]] = {}
            missing_passage_ids: list[str] = []
            for passage_id in sorted(referenced_passage_ids):
                payload = _passage_payload(connection, passage_id, passage_cache)
                if payload is None:
                    missing_passage_ids.append(passage_id)
                else:
                    passage_context[passage_id] = payload

            evidence_context: list[dict[str, Any]] = []
            for evidence in evidence_rows:
                evidence_item = {
                    "case_id": evidence["case_id"],
                    "evidence_index": evidence["evidence_index"],
                    "passage_id": evidence["passage_id"],
                    "source_work": evidence["source_work"],
                    "quote": evidence["quote"],
                    "quote_sha256": evidence["quote_sha256"],
                    "quote_check": evidence["quote_check"],
                    "source_resolution": evidence["source_resolution"],
                    "source_location": evidence["source_location"],
                    "evidence": evidence["evidence"],
                }
                external_id = evidence.get("external_source_id")
                if external_id:
                    external_queue = external_source_queue.get(str(external_id))
                    external_passage = external_passage_queue.get(
                        (case_id, int(evidence["evidence_index"]))
                    )
                    evidence_item["external_resolution"] = {
                        "external_source_id": external_id,
                        "registry": external_registry.get(str(external_id)),
                        "source_queue": external_queue,
                        "passage_queue": external_passage,
                        "evidence_packet_ref": {
                            "path": "v2/data/real_runs/external_evidence_packets.v1.jsonl",
                            "packet_id": f"external-evidence-packet:{external_id}",
                            "queue_item_id": f"external-passage:{case_id}:{evidence['evidence_index']}",
                        },
                    }
                evidence_context.append(evidence_item)

            location_context = {
                "count": len(locations),
                "status_counts": _compact_counter(Counter(
                    f"{row['work_identity_status']}:{row['target_passage_match_status']}"
                    for row in locations
                )),
                "rows": locations,
                "candidate_items": [
                    candidate_items_by_id[candidate_id]
                    for candidate_id in sorted({
                        str(row["candidate_id"]) for row in locations
                        if str(row["candidate_id"]) in candidate_items_by_id
                    })
                ],
                "resolution_boundary": "candidate_target_locations are machine locating candidates; they do not write target_work or target_passage_id",
            }
            work_context = {
                "requested_label": queue["raw_label"],
                "normalized_label": queue["normalized_label"] or normalize_label(queue["raw_label"]),
                "machine_candidate_work_key": target_key,
                "registry": registry,
                "alias_context": _alias_context(
                    aliases_by_label,
                    str(queue["normalized_label"] or normalize_label(queue["raw_label"])),
                ),
                "source_version_context": _source_version_context(connection, str(target_key)) if target_key in work_registry else None,
                "external_registry_label_candidates": [
                    dict(value)
                    for value in external_registry.values()
                    if normalize_label(value.get("normalized_work")) == normalize_label(queue["normalized_label"] or queue["raw_label"])
                    or normalize_label(value.get("cited_work")) == normalize_label(queue["normalized_label"] or queue["raw_label"])
                ],
                "identity_boundary": "work_registry identity is a machine candidate; it does not establish a target edition or target passage",
            }
            packet_rows.append(
                {
                    "packet_version": "target-work-resolution-packet.v1",
                    "packet_id": f"target-work-resolution-packet:{queue['queue_item_id']}",
                    "generated_at": generated_at,
                    "queue_item": queue,
                    "case_snapshot": _case_snapshot(case, process_by_case.get(case_id, [])),
                    "source_passage_ref": {
                        "passage_id": case.get("source_passage_id"),
                        "available": bool(case.get("source_passage_id") in passage_context),
                    },
                    "evidence_context": {
                        "count": len(evidence_context),
                        "requested_evidence_indexes": queue.get("evidence_indexes", []),
                        "rows": evidence_context,
                    },
                    "work_resolution": work_context,
                    "candidate_target_location_context": location_context,
                    "passage_context": {
                        "count": len(passage_context),
                        "passages": passage_context,
                        "referenced_passage_ids": sorted(referenced_passage_ids),
                        "missing_passage_ids": missing_passage_ids,
                    },
                    "machine_assessment": _machine_assessment(
                        queue, case, registry, evidence_rows, locations
                    ),
                    "decision_contract": {
                        "allowed_human_statuses": ["resolved", "uncertain", "rejected"],
                        "human_must_confirm": [
                            "target_work_identity",
                            "target_edition_or_source_version",
                            "target_passage",
                            "target_location",
                        ],
                        "machine_candidate_is_not_resolution": True,
                        "canonical_work_identity_is_not_target_passage": True,
                        "candidate_target_location_is_not_target_passage": True,
                        "promotes_to_gold": False,
                        "database_submission": "erwang_v2.database.apply_target_work_resolution",
                    },
                    "detail_ref": {
                        "case_id": case_id,
                        "api_path": f"/api/v2/case?id={case_id}",
                        "database_tables": [
                            "annotation_cases",
                            "annotation_evidences",
                            "passages",
                            "work_registry",
                            "work_aliases",
                            "candidate_target_locations",
                            "target_work_resolution_queue",
                        ],
                    },
                    "machine_only_boundary": {
                        "database_write_performed": False,
                        "target_work_mutated": False,
                        "target_passage_mutated": False,
                        "quote_check_mutated": False,
                        "human_status_mutated": False,
                        "gold_promotion_performed": False,
                        "canonical_semantic_truth_asserted": False,
                        "human_review_required": True,
                    },
                }
            )

    packet_path.parent.mkdir(parents=True, exist_ok=True)
    with packet_path.open("w", encoding="utf-8") as handle:
        for packet in packet_rows:
            handle.write(json.dumps(packet, ensure_ascii=False, separators=(",", ":")) + "\n")

    expected_ids = {str(row["queue_item_id"]) for row in queue_rows}
    actual_ids = {str(row["queue_item"]["queue_item_id"]) for row in packet_rows}
    report = {
        "report_version": "target-work-resolution-packets-report.v1",
        "generated_at": generated_at,
        "database": relative_path(database_path),
        "packet_file": relative_path(packet_path),
        "packet_sha256": sha256_file(packet_path),
        "policy": {
            "database_write_performed": False,
            "target_work_mutated": False,
            "target_passage_mutated": False,
            "quote_check_mutated": False,
            "human_status_mutated": False,
            "gold_promotion_performed": False,
            "machine_candidate_is_not_resolution": True,
            "candidate_target_locations_remain_candidate_only": True,
            "canonical_passage_match_is_not_target_resolution": True,
            "queue_is_source_of_truth": True,
        },
        "counts": {
            "queue_count": len(queue_rows),
            "packet_count": len(packet_rows),
            "queue_case_count": len(case_ids),
            "packet_case_count": len({str(row['queue_item']['case_id']) for row in packet_rows}),
            "missing_packet_count": len(expected_ids - actual_ids),
            "orphan_packet_count": len(actual_ids - expected_ids),
            "evidence_rows_embedded": total_evidence_rows,
            "candidate_target_location_rows_embedded": total_location_rows,
            "packets_with_source_passage": packets_with_source_passage,
            "packets_with_machine_work_key": packets_with_work_key,
            "packets_with_work_registry_row": packets_with_registry,
            "packets_with_missing_passage_context": sum(
                bool(row["passage_context"]["missing_passage_ids"])
                for row in packet_rows
            ),
        },
        "queue_status_counts": _compact_counter(queue_status_counts),
        "machine_inference_status_counts": _compact_counter(inference_status_counts),
        "case_origin_counts": _compact_counter(origin_counts),
        "registry_identity_status_counts": _compact_counter(registry_status_counts),
        "coverage": {
            "queue_fully_packetized": expected_ids == actual_ids,
            "one_packet_per_queue_item": len(packet_rows) == len(actual_ids),
            "all_packets_machine_only": all(
                row["machine_only_boundary"]["database_write_performed"] is False
                and row["machine_only_boundary"]["target_work_mutated"] is False
                and row["machine_only_boundary"]["target_passage_mutated"] is False
                and row["machine_only_boundary"]["human_status_mutated"] is False
                and row["machine_only_boundary"]["gold_promotion_performed"] is False
                for row in packet_rows
            ),
        },
        "source_chain": {
            "case_to_source_passage": "annotation_cases.source_passage_id -> passages -> source_documents",
            "evidence_to_passage": "annotation_evidences.passage_id -> passages -> source_documents",
            "target_candidate_chain": "candidate_target_locations -> candidate_items -> passages/source_documents",
            "work_identity_chain": "target_work_resolution_queue -> work_registry/work_aliases",
            "external_chain": "annotation_evidences.evidence_json.external_source_id -> external_source_registry/external_*_resolution_queue",
        },
        "review_boundary": "This packet is readying machine context for human review. It does not decide target_work, target_passage, canonical status, quote correctness, or gold status.",
    }
    report["valid"] = bool(
        all(report["coverage"].values())
        and report["counts"]["missing_packet_count"] == 0
        and report["counts"]["orphan_packet_count"] == 0
    )
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return report


def validate_target_work_resolution_packets(
    *,
    database_path: Path = DEFAULT_DATABASE,
    report_path: Path = DEFAULT_REPORT,
    packet_path: Path | None = None,
) -> dict[str, Any]:
    """Reconcile packet rows with pending target-work queue rows."""

    errors: list[str] = []
    database_path = Path(database_path).resolve()
    report_path = Path(report_path).resolve()
    if not report_path.is_file():
        return {"valid": False, "errors": ["packet_report_missing"], "counts": {}}
    try:
        report = json.loads(report_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        return {"valid": False, "errors": [f"packet_report_invalid:{type(error).__name__}"], "counts": {}}
    packet_path = Path(packet_path or (PROJECT_ROOT / str(report.get("packet_file") or ""))).resolve()
    if not packet_path.is_file():
        return {"valid": False, "errors": ["packet_file_missing"], "counts": {}}
    actual_hash = sha256_file(packet_path)
    if actual_hash != report.get("packet_sha256"):
        errors.append("packet_sha256_mismatch")

    packets: list[dict[str, Any]] = []
    try:
        for line_number, line in enumerate(packet_path.read_text(encoding="utf-8").splitlines(), start=1):
            value = json.loads(line)
            if not isinstance(value, dict):
                errors.append(f"packet_row_not_object:{line_number}")
            else:
                packets.append(value)
    except (OSError, ValueError) as error:
        errors.append(f"packet_file_invalid:{type(error).__name__}")

    with connect_read_only(database_path) as connection:
        expected_rows = connection.execute(
            """
            SELECT queue_item_id, case_id, queue_status
            FROM target_work_resolution_queue
            WHERE queue_status IN ('pending', 'needs_context', 'uncertain')
            ORDER BY queue_item_id
            """
        ).fetchall()
        expected_ids = {str(row["queue_item_id"]) for row in expected_rows}
        evidence_counts = {
            str(row["case_id"]): int(row["count"])
            for row in connection.execute(
                "SELECT case_id, COUNT(*) AS count FROM annotation_evidences GROUP BY case_id"
            ).fetchall()
        }
        location_counts = {
            str(row["case_id"]): int(row["count"])
            for row in connection.execute(
                "SELECT case_id, COUNT(*) AS count FROM candidate_target_locations GROUP BY case_id"
            ).fetchall()
        }
        case_ids = {
            str(row["case_id"])
            for row in connection.execute("SELECT case_id FROM annotation_cases").fetchall()
        }

    actual_ids: list[str] = []
    for packet in packets:
        queue = packet.get("queue_item") or {}
        queue_id = str(queue.get("queue_item_id") or "")
        actual_ids.append(queue_id)
        if not queue_id:
            errors.append("packet_queue_item_id_missing")
        if packet.get("packet_id") != f"target-work-resolution-packet:{queue_id}":
            errors.append(f"packet_id_mismatch:{queue_id}")
        if queue_id not in expected_ids:
            errors.append(f"packet_queue_item_not_pending:{queue_id}")
        case_id = str(queue.get("case_id") or "")
        if case_id not in case_ids:
            errors.append(f"packet_case_missing:{queue_id}")
        case_snapshot = packet.get("case_snapshot") or {}
        evidence_context = packet.get("evidence_context") or {}
        locations = packet.get("candidate_target_location_context") or {}
        if int(evidence_context.get("count") or 0) != evidence_counts.get(case_id, 0):
            errors.append(f"packet_evidence_count_mismatch:{queue_id}")
        if int(locations.get("count") or 0) != location_counts.get(case_id, 0):
            errors.append(f"packet_location_count_mismatch:{queue_id}")
        boundary = packet.get("machine_only_boundary") or {}
        for field in (
            "database_write_performed",
            "target_work_mutated",
            "target_passage_mutated",
            "quote_check_mutated",
            "human_status_mutated",
            "gold_promotion_performed",
            "canonical_semantic_truth_asserted",
        ):
            if boundary.get(field) is not False:
                errors.append(f"machine_boundary_breach:{queue_id}:{field}")
        assessment = packet.get("machine_assessment") or {}
        if assessment.get("automated_target_work_resolution_allowed") is not False:
            errors.append(f"automated_target_work_boundary_breach:{queue_id}")
        if assessment.get("automated_target_passage_resolution_allowed") is not False:
            errors.append(f"automated_target_passage_boundary_breach:{queue_id}")
        decision_contract = packet.get("decision_contract") or {}
        if decision_contract.get("promotes_to_gold") is not False:
            errors.append(f"gold_boundary_breach:{queue_id}")
        if case_snapshot.get("case_id") != case_id:
            errors.append(f"case_snapshot_mismatch:{queue_id}")
        missing_passages = (packet.get("passage_context") or {}).get("missing_passage_ids") or []
        if missing_passages:
            errors.append(f"missing_passage_context:{queue_id}:{len(missing_passages)}")

    actual_set = set(actual_ids)
    if len(actual_ids) != len(actual_set):
        errors.append("duplicate_packet_queue_item_id")
    if expected_ids - actual_set:
        errors.append(f"packets_missing:{len(expected_ids - actual_set)}")
    if actual_set - expected_ids:
        errors.append(f"packets_orphan:{len(actual_set - expected_ids)}")
    report_counts = report.get("counts") or {}
    if int(report_counts.get("queue_count") or 0) != len(expected_ids):
        errors.append("report_queue_count_mismatch")
    if int(report_counts.get("packet_count") or 0) != len(packets):
        errors.append("report_packet_count_mismatch")
    if not (report.get("policy") or {}).get("machine_candidate_is_not_resolution"):
        errors.append("report_policy_machine_boundary_missing")

    return {
        "valid": not errors,
        "errors": errors,
        "database": relative_path(database_path),
        "packet_file": relative_path(packet_path),
        "report_file": relative_path(report_path),
        "counts": {
            "expected_queue_count": len(expected_ids),
            "packet_count": len(packets),
            "unique_packet_queue_item_count": len(actual_set),
            "expected_case_count": len({str(row["case_id"]) for row in expected_rows}),
        },
        "policy": report.get("policy", {}),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", type=Path, default=DEFAULT_DATABASE)
    parser.add_argument("--packet", type=Path, default=DEFAULT_PACKET)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--validate", action="store_true")
    args = parser.parse_args()
    if args.validate:
        result = validate_target_work_resolution_packets(
            database_path=args.database,
            report_path=args.report,
            packet_path=args.packet,
        )
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0 if result["valid"] else 1
    result = build_packets(
        database_path=args.database,
        packet_path=args.packet,
        report_path=args.report,
    )
    print(json.dumps({"valid": result["valid"], "counts": result["counts"]}, ensure_ascii=False, indent=2))
    return 0 if result["valid"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
