#!/usr/bin/env python3
"""Build a read-only, source-bound evidence packet for every external queue row.

The public-search manifest is intentionally narrower than the V2 external
resolution queues: it currently covers the 80 ``external_source_pending``
records that were sent to the public search lane, while the database carries
121 external passage tasks and 100 unique external sources.  This script
closes that *accounting* gap without pretending that an unsearched record is
verified.

The output is one JSON object per external source.  Each object contains the
source queue row, registry boundary, every linked passage queue row, frozen
candidate metadata, recomputed local file/hash/match checks, and an explicit
machine-only assessment.  It never updates SQLite, never changes evidence
``passage_id`` or ``quote_check``, and never changes canonical status.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable


V2_ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = V2_ROOT.parent
DEFAULT_DATABASE = V2_ROOT / "data/real_runs/annotation_v2.db"
DEFAULT_MANIFEST = V2_ROOT / "data/real_runs/external_public_candidate_manifest.json"
DEFAULT_EDITION_MANIFEST = V2_ROOT / "data/real_runs/external_edition_candidate_manifest.v1.json"
DEFAULT_PACKET = V2_ROOT / "data/real_runs/external_evidence_packets.v1.jsonl"
DEFAULT_REPORT = V2_ROOT / "data/real_runs/external_evidence_packets_report.json"


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def relative_path(path: Path) -> str:
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


def sha256_file(path: Path) -> str | None:
    if not path.is_file():
        return None
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def connect_read_only(database_path: Path) -> sqlite3.Connection:
    if not database_path.is_file():
        raise FileNotFoundError(f"v2_database_not_found:{database_path}")
    uri = f"file:{database_path.resolve()}?mode=ro"
    connection = sqlite3.connect(uri, uri=True)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA query_only = ON")
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def load_manifest(manifest_path: Path) -> tuple[dict[str, Any], str]:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if not isinstance(manifest, dict):
        raise ValueError("external_candidate_manifest_must_be_object")
    manifest_hash = hashlib.sha256(manifest_path.read_bytes()).hexdigest()
    return manifest, manifest_hash


def load_edition_manifest(
    manifest_path: Path,
) -> tuple[dict[str, Any], str | None]:
    """Load the optional downloaded-edition candidate layer."""

    if not manifest_path.is_file():
        return {}, None
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if not isinstance(manifest, dict):
        raise ValueError("external_edition_candidate_manifest_must_be_object")
    if manifest.get("schema_version") != "external_edition_candidate_manifest.v1":
        raise ValueError("unexpected_external_edition_candidate_manifest_schema")
    return manifest, hashlib.sha256(manifest_path.read_bytes()).hexdigest()


def edition_candidate_summary(candidate: dict[str, Any]) -> dict[str, Any]:
    """Keep packet references useful without duplicating raw OCR/PDF bytes."""

    items: list[dict[str, Any]] = []
    for item in candidate.get("items") or []:
        files: list[dict[str, Any]] = []
        for file_record in item.get("files") or []:
            files.append(
                {
                    key: file_record.get(key)
                    for key in (
                        "role", "name", "path", "status", "http_status", "size_bytes",
                        "metadata_size", "sha256", "url", "download_reason", "error",
                    )
                    if key in file_record
                }
            )
        items.append(
            {
                key: item.get(key)
                for key in (
                    "identifier", "volume_label", "item_url", "metadata_url",
                    "metadata_status", "metadata_raw_sha256", "metadata_file",
                    "metadata_title", "metadata_creator", "metadata_date",
                    "metadata_collection", "metadata_contributor", "metadata_volume",
                    "availability_status", "quote_matches",
                )
                if key in item
            }
            | {"files": files}
        )
    return {
        "candidate_id": candidate.get("candidate_id"),
        "edition": candidate.get("edition"),
        "text_layer": candidate.get("text_layer"),
        "provider": candidate.get("provider"),
        "source_url": candidate.get("source_url"),
        "metadata_url": candidate.get("metadata_url"),
        "availability_status": candidate.get("availability_status"),
        "linked_evidence_count": candidate.get("linked_evidence_count", 0),
        "quote_match_count": candidate.get("quote_match_count", 0),
        "canonical_status": "unknown",
        "items": items,
        "boundary": "downloaded public candidate only; edition/image/passage/human verification remains pending",
    }


def validate_external_edition_candidate_manifest(
    manifest_path: Path = DEFAULT_EDITION_MANIFEST,
) -> dict[str, Any]:
    """Validate the frozen edition-candidate files without touching SQLite."""

    errors: list[str] = []
    if not manifest_path.is_file():
        return {
            "valid": False,
            "errors": ["edition_candidate_manifest_missing"],
            "manifest_file": relative_path(manifest_path),
            "counts": {},
        }
    try:
        manifest, manifest_hash = load_edition_manifest(manifest_path)
    except (OSError, ValueError, json.JSONDecodeError) as error:
        return {
            "valid": False,
            "errors": [f"edition_candidate_manifest_invalid:{type(error).__name__}:{error}"],
            "manifest_file": relative_path(manifest_path),
            "counts": {},
        }

    candidates = manifest.get("candidates") or []
    if not isinstance(candidates, list):
        errors.append("edition_candidate_candidates_not_list")
        candidates = []
    item_count = 0
    complete_file_count = 0
    missing_file_count = 0
    hash_mismatch_count = 0
    size_mismatch_count = 0
    unsafe_path_count = 0
    candidate_status_counts: Counter[str] = Counter()
    for candidate in candidates:
        if not isinstance(candidate, dict):
            errors.append("edition_candidate_not_object")
            continue
        candidate_status = str(candidate.get("availability_status") or "missing_status")
        candidate_status_counts[candidate_status] += 1
        if candidate.get("canonical_status") in {"canonical_active", "verified", "gold"}:
            errors.append(f"edition_candidate_canonical_status_breach:{candidate.get('candidate_id')}")
        for item in candidate.get("items") or []:
            if not isinstance(item, dict):
                errors.append(f"edition_candidate_item_not_object:{candidate.get('candidate_id')}")
                continue
            item_count += 1
            for file_record in item.get("files") or []:
                if not isinstance(file_record, dict):
                    errors.append(f"edition_candidate_file_not_object:{candidate.get('candidate_id')}")
                    continue
                status = str(file_record.get("status") or "")
                if status not in {"downloaded", "reused"}:
                    continue
                complete_file_count += 1
                raw_path = file_record.get("path")
                if not raw_path:
                    missing_file_count += 1
                    continue
                file_path = (PROJECT_ROOT / str(raw_path)).resolve()
                try:
                    file_path.relative_to(PROJECT_ROOT.resolve())
                except ValueError:
                    unsafe_path_count += 1
                    continue
                if not file_path.is_file():
                    missing_file_count += 1
                    continue
                actual_size = file_path.stat().st_size
                expected_size = file_record.get("size_bytes")
                if expected_size is not None and int(expected_size) != actual_size:
                    size_mismatch_count += 1
                expected_hash = str(file_record.get("sha256") or "")
                actual_hash = sha256_file(file_path)
                if not expected_hash or actual_hash != expected_hash:
                    hash_mismatch_count += 1

    expected_summary = manifest.get("summary") or {}
    if expected_summary.get("candidate_count") != len(candidates):
        errors.append("edition_candidate_summary_candidate_count_mismatch")
    if expected_summary.get("item_count") != item_count:
        errors.append("edition_candidate_summary_item_count_mismatch")
    if expected_summary.get("downloaded_file_count") != complete_file_count:
        errors.append("edition_candidate_summary_file_count_mismatch")
    if expected_summary.get("database_rows_changed") != 0:
        errors.append("edition_candidate_database_mutation_claim")
    if missing_file_count:
        errors.append(f"edition_candidate_file_missing:{missing_file_count}")
    if hash_mismatch_count:
        errors.append(f"edition_candidate_file_hash_mismatch:{hash_mismatch_count}")
    if size_mismatch_count:
        errors.append(f"edition_candidate_file_size_mismatch:{size_mismatch_count}")
    if unsafe_path_count:
        errors.append(f"edition_candidate_unsafe_path:{unsafe_path_count}")
    return {
        "valid": not errors,
        "errors": errors,
        "manifest_file": relative_path(manifest_path),
        "manifest_sha256": manifest_hash,
        "counts": {
            "candidate_count": len(candidates),
            "item_count": item_count,
            "complete_file_count": complete_file_count,
            "missing_file_count": missing_file_count,
            "hash_mismatch_count": hash_mismatch_count,
            "size_mismatch_count": size_mismatch_count,
            "unsafe_path_count": unsafe_path_count,
        },
        "candidate_status_counts": dict(candidate_status_counts),
        "database_rows_changed": 0,
    }


def _relative_candidate_path(raw_file: Any) -> Path | None:
    if not raw_file:
        return None
    path = (PROJECT_ROOT / str(raw_file)).resolve()
    try:
        path.relative_to(PROJECT_ROOT.resolve())
    except ValueError:
        return None
    return path


def recompute_candidate(
    candidate: dict[str, Any],
    *,
    quote: str,
) -> dict[str, Any]:
    """Recheck the frozen file without trusting manifest match fields alone."""

    raw_file = _relative_candidate_path(candidate.get("raw_file"))
    actual_hash = sha256_file(raw_file) if raw_file else None
    expected_hash = str(
        candidate.get("raw_sha256") or candidate.get("content_sha256") or ""
    ) or None
    hash_matches = bool(actual_hash and expected_hash and actual_hash == expected_hash)
    result: dict[str, Any] = {
        "raw_file": candidate.get("raw_file"),
        "raw_file_exists": bool(raw_file and raw_file.is_file()),
        "raw_sha256_expected": expected_hash,
        "raw_sha256_actual": actual_hash,
        "raw_hash_matches": hash_matches,
        "manifest_match_mode": candidate.get("offline_match_mode") or candidate.get("match_mode"),
        "manifest_start_char": candidate.get("offline_start_char"),
        "manifest_end_char": candidate.get("offline_end_char"),
        "recomputed_match_mode": "not_checked",
        "recomputed_start_char": None,
        "recomputed_end_char": None,
    }
    if not raw_file or not raw_file.is_file() or not hash_matches:
        result["recomputed_match_mode"] = "file_or_hash_unverified"
        return result

    # Use the same conservative normalizer as the fetch/reconcile lane.  The
    # import is local so read-only packet generation remains usable as a
    # standalone script from the repository root.
    import sys

    scripts_root = str(V2_ROOT / "scripts")
    if scripts_root not in sys.path:
        sys.path.insert(0, scripts_root)
    from external_text_normalization import normalized_contiguous_match  # noqa: PLC0415

    raw_text = raw_file.read_text(encoding="utf-8")
    matched, start, end = normalized_contiguous_match(raw_text, quote)
    if matched:
        result["recomputed_match_mode"] = "normalized_contiguous"
        result["recomputed_start_char"] = start
        result["recomputed_end_char"] = end
    else:
        result["recomputed_match_mode"] = "not_found"
    return result


def _candidate_passage_rows(
    connection: sqlite3.Connection,
    passage_ids: Iterable[str],
) -> dict[str, dict[str, Any]]:
    ids = [str(value) for value in passage_ids if value]
    if not ids:
        return {}
    placeholders = ",".join("?" for _ in ids)
    rows = connection.execute(
        f"""
        SELECT p.passage_id, p.source_document_id, p.work_key,
               sd.source_file_sha256, sd.source_kind, sd.source_file,
               sd.canonical_status
        FROM passages p
        JOIN source_documents sd ON sd.source_document_id = p.source_document_id
        WHERE p.passage_id IN ({placeholders})
        """,
        tuple(ids),
    ).fetchall()
    return {str(row["passage_id"]): dict(row) for row in rows}


def _manifest_entries(manifest: dict[str, Any]) -> dict[tuple[str, int, str], dict[str, Any]]:
    entries: dict[tuple[str, int, str], dict[str, Any]] = {}
    for entry in manifest.get("entries") or []:
        try:
            key = (
                str(entry["case_id"]),
                int(entry["evidence_index"]),
                str(entry["external_source_id"]),
            )
        except (KeyError, TypeError, ValueError):
            continue
        entries[key] = entry
    return entries


def _candidate_index(entry: dict[str, Any] | None) -> dict[tuple[str, str], dict[str, Any]]:
    result: dict[tuple[str, str], dict[str, Any]] = {}
    if not entry:
        return result
    for candidate in entry.get("candidates") or []:
        if not isinstance(candidate, dict):
            continue
        result[
            (
                str(candidate.get("raw_file") or ""),
                str(candidate.get("raw_sha256") or candidate.get("content_sha256") or ""),
            )
        ] = candidate
    return result


def _candidate_summary(
    *,
    entry: dict[str, Any] | None,
    queue_refs: list[dict[str, Any]],
    quote: str,
    passage_rows: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    manifest_candidates = _candidate_index(entry)
    candidates: list[dict[str, Any]] = []
    refs = list(queue_refs)
    for ref in refs:
        if not isinstance(ref, dict):
            continue
        key = (
            str(ref.get("raw_file") or ""),
            str(ref.get("raw_sha256") or ref.get("content_sha256") or ""),
        )
        candidate = dict(manifest_candidates.get(key) or {})
        candidate.update({key: value for key, value in ref.items() if value is not None})
        recheck = recompute_candidate(candidate, quote=quote)
        candidate_passage_ids = [
            str(value) for value in (candidate.get("candidate_passage_ids") or []) if value
        ]
        candidate["candidate_passages"] = [
            passage_rows[passage_id]
            for passage_id in candidate_passage_ids
            if passage_id in passage_rows
        ]
        candidate["candidate_passage_ids"] = candidate_passage_ids
        candidate["recheck"] = recheck
        candidates.append(candidate)

    # The manifest may have a frozen page candidate even when the queue has
    # not yet copied its reference into candidate_refs_json.
    for key, candidate in manifest_candidates.items():
        if any(
            str(item.get("raw_file") or "") == key[0]
            and str(item.get("raw_sha256") or item.get("content_sha256") or "") == key[1]
            for item in candidates
        ):
            continue
        item = dict(candidate)
        item["candidate_passages"] = []
        item["candidate_passage_ids"] = []
        item["recheck"] = recompute_candidate(item, quote=quote)
        item["queue_ref_present"] = False
        candidates.append(item)
    return candidates


def _machine_assessment(
    *,
    entry: dict[str, Any] | None,
    candidates: list[dict[str, Any]],
) -> dict[str, Any]:
    if entry is None:
        return {
            "status": "not_in_public_search_scope",
            "reason": "no manifest entry; this queue row was not in the public-search input lane",
            "canonical_verified": False,
            "quote_check_mutated": False,
        }
    matched = [
        candidate
        for candidate in candidates
        if candidate.get("recheck", {}).get("recomputed_match_mode") == "normalized_contiguous"
    ]
    if matched:
        status = "frozen_public_candidate_quote_match"
    elif candidates:
        status = "search_hit_without_verified_quote_match"
    elif entry.get("status") == "no_public_match":
        status = "no_public_match_in_search_lane"
    else:
        status = "search_lane_candidate_without_recomputed_match"
    return {
        "status": status,
        "manifest_status": entry.get("status"),
        "candidate_count": len(candidates),
        "recomputed_contiguous_match_count": len(matched),
        "canonical_verified": False,
        "quote_check_mutated": False,
        "reason": "public transcription/page revision is locating evidence only; edition/image/canonical verification remains pending",
    }


def build_packets(
    *,
    database_path: Path = DEFAULT_DATABASE,
    manifest_path: Path = DEFAULT_MANIFEST,
    edition_manifest_path: Path = DEFAULT_EDITION_MANIFEST,
    packet_path: Path = DEFAULT_PACKET,
    report_path: Path = DEFAULT_REPORT,
) -> dict[str, Any]:
    manifest, manifest_hash = load_manifest(manifest_path)
    edition_manifest, edition_manifest_hash = load_edition_manifest(edition_manifest_path)
    edition_candidate_validation = validate_external_edition_candidate_manifest(
        edition_manifest_path
    )
    entries = _manifest_entries(manifest)
    edition_candidates_by_source: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for candidate in edition_manifest.get("candidates") or []:
        summary = edition_candidate_summary(candidate)
        for source_id in candidate.get("linked_external_source_ids") or []:
            edition_candidates_by_source[str(source_id)].append(summary)
    with connect_read_only(database_path) as connection:
        source_rows = connection.execute(
            """
            SELECT q.queue_item_id, q.external_source_id, q.cited_work,
                   q.registry_status, q.queue_status, q.edition_status,
                   q.evidence_count, q.pending_evidence_count,
                   q.candidate_evidence_count, q.context_json, q.updated_at,
                   r.status AS registry_current_status, r.source_file,
                   r.source_file_sha256, r.edition, r.location_note,
                   r.metadata_json
            FROM external_source_resolution_queue q
            JOIN external_source_registry r
              ON r.external_source_id = q.external_source_id
            ORDER BY q.external_source_id
            """
        ).fetchall()
        passage_rows = connection.execute(
            """
            SELECT queue_item_id, external_source_id, case_id,
                   evidence_index, cited_work, quote, source_resolution,
                   quote_check, queue_status, edition_status, passage_status,
                   candidate_manifest_path, candidate_manifest_sha256,
                   selected_passage_id, candidate_passage_ids_json,
                   candidate_refs_json, context_json, updated_at
            FROM external_passage_resolution_queue
            ORDER BY external_source_id, case_id, evidence_index
            """
        ).fetchall()
        all_candidate_passage_ids = [
            passage_id
            for row in passage_rows
            for passage_id in parse_json(row["candidate_passage_ids_json"], [])
        ]
        candidate_passage_map = _candidate_passage_rows(
            connection, all_candidate_passage_ids
        )

    passage_by_source: dict[str, list[sqlite3.Row]] = defaultdict(list)
    for row in passage_rows:
        passage_by_source[str(row["external_source_id"])].append(row)

    packets: list[dict[str, Any]] = []
    evidence_assessments: Counter[str] = Counter()
    source_assessments: Counter[str] = Counter()
    file_checks = Counter()
    packet_evidence_ids: set[str] = set()
    packet_source_ids: set[str] = set()

    for source_row in source_rows:
        source_id = str(source_row["external_source_id"])
        packet_source_ids.add(source_id)
        evidence_packets: list[dict[str, Any]] = []
        source_entry_count = 0
        for passage_row in passage_by_source.get(source_id, []):
            case_id = str(passage_row["case_id"])
            evidence_index = int(passage_row["evidence_index"])
            packet_evidence_ids.add(str(passage_row["queue_item_id"]))
            key = (case_id, evidence_index, source_id)
            entry = entries.get(key)
            if entry is not None:
                source_entry_count += 1
            queue_refs = parse_json(passage_row["candidate_refs_json"], [])
            if not isinstance(queue_refs, list):
                queue_refs = []
            candidate_list = _candidate_summary(
                entry=entry,
                queue_refs=queue_refs,
                quote=str(passage_row["quote"] or ""),
                passage_rows=candidate_passage_map,
            )
            assessment = _machine_assessment(entry=entry, candidates=candidate_list)
            evidence_assessments[assessment["status"]] += 1
            for candidate in candidate_list:
                recheck = candidate.get("recheck") or {}
                if not recheck.get("raw_file_exists"):
                    file_checks["candidate_file_missing"] += 1
                elif not recheck.get("raw_hash_matches"):
                    file_checks["candidate_file_hash_mismatch"] += 1
                else:
                    file_checks["candidate_file_hash_pass"] += 1
            evidence_packets.append(
                {
                    "queue_item_id": str(passage_row["queue_item_id"]),
                    "case_id": case_id,
                    "evidence_index": evidence_index,
                    "cited_work": passage_row["cited_work"],
                    "quote": passage_row["quote"],
                    "source_resolution": passage_row["source_resolution"],
                    "quote_check": passage_row["quote_check"],
                    "queue_state": {
                        "queue_status": passage_row["queue_status"],
                        "edition_status": passage_row["edition_status"],
                        "passage_status": passage_row["passage_status"],
                        "selected_passage_id": passage_row["selected_passage_id"],
                    },
                    "candidate_manifest": {
                        "path": passage_row["candidate_manifest_path"],
                        "sha256": passage_row["candidate_manifest_sha256"],
                        "entry_present": entry is not None,
                        "entry_status": entry.get("status") if entry else None,
                    },
                    "candidates": candidate_list,
                    "edition_candidates": edition_candidates_by_source.get(source_id, []),
                    "machine_assessment": assessment,
                    "boundary": {
                        "candidate_is_not_canonical": True,
                        "quote_check_is_not_changed": True,
                        "human_resolution_required": True,
                    },
                }
            )

        source_assessment = (
            "public_search_manifest_covered"
            if source_entry_count
            else "not_in_public_search_manifest"
        )
        source_assessments[source_assessment] += 1
        packets.append(
            {
                "packet_version": "external-evidence-packet.v1",
                "packet_id": f"external-evidence-packet:{source_id}",
                "generated_at": now(),
                "external_source_id": source_id,
                "cited_work": source_row["cited_work"],
                "source_queue": {
                    "queue_item_id": source_row["queue_item_id"],
                    "registry_status": source_row["registry_status"],
                    "queue_status": source_row["queue_status"],
                    "edition_status": source_row["edition_status"],
                    "evidence_count": source_row["evidence_count"],
                    "pending_evidence_count": source_row["pending_evidence_count"],
                    "candidate_evidence_count": source_row["candidate_evidence_count"],
                    "updated_at": source_row["updated_at"],
                },
                "registry": {
                    "status": source_row["registry_current_status"],
                    "source_file": source_row["source_file"],
                    "source_file_sha256": source_row["source_file_sha256"],
                    "edition": source_row["edition"],
                    "location_note": source_row["location_note"],
                    "metadata": parse_json(source_row["metadata_json"], {}),
                },
                "edition_candidates": edition_candidates_by_source.get(source_id, []),
                "search_scope": {
                    "manifest_path": relative_path(manifest_path),
                    "manifest_sha256": manifest_hash,
                    "source_entry_count": source_entry_count,
                    "status": source_assessment,
                },
                "evidence_packets": evidence_packets,
                "machine_only_boundary": "This packet records locating and matching evidence. It is not an edition decision, canonical passage, quote_check pass, human review event, or gold promotion.",
            }
        )

    packet_path.parent.mkdir(parents=True, exist_ok=True)
    with packet_path.open("w", encoding="utf-8") as handle:
        for packet in packets:
            handle.write(json.dumps(packet, ensure_ascii=False, separators=(",", ":")) + "\n")

    expected_source_ids = {str(row["external_source_id"]) for row in source_rows}
    expected_passage_ids = {str(row["queue_item_id"]) for row in passage_rows}
    report = {
        "report_version": "external-evidence-packets-report.v1",
        "generated_at": now(),
        "database": relative_path(database_path),
        "manifest": {
            "path": relative_path(manifest_path),
            "sha256": manifest_hash,
            "entry_count": len(manifest.get("entries") or []),
            "unique_source_count": len({str(entry.get("external_source_id")) for entry in manifest.get("entries") or []}),
        },
        "edition_candidate_manifest": {
            "path": relative_path(edition_manifest_path) if edition_manifest_hash else None,
            "sha256": edition_manifest_hash,
            "candidate_count": len(edition_manifest.get("candidates") or []),
            "linked_source_count": len(edition_candidates_by_source),
            "present": edition_manifest_hash is not None,
        },
        "edition_candidate_manifest_validation": edition_candidate_validation,
        "packet_file": relative_path(packet_path),
        "policy": {
            "database_write_performed": False,
            "canonical_status_mutated": False,
            "annotation_evidence_mutated": False,
            "quote_check_mutated": False,
            "queue_source_of_truth": True,
            "public_transcription_is_not_canonical": True,
            "downloaded_edition_candidate_is_not_canonical": True,
            "downloaded_edition_candidate_does_not_change_quote_check": True,
            "edition_candidate_manifest_files_valid": edition_candidate_validation["valid"],
        },
        "counts": {
            "source_queue_count": len(source_rows),
            "source_packet_count": len(packets),
            "source_packet_missing_count": len(expected_source_ids - packet_source_ids),
            "passage_queue_count": len(passage_rows),
            "passage_packet_count": len(packet_evidence_ids),
            "passage_packet_missing_count": len(expected_passage_ids - packet_evidence_ids),
            "manifest_entry_count": len(entries),
            "manifest_entry_matched_to_queue_count": sum(
                1
                for entry in entries.values()
                if f"external-passage:{entry.get('case_id')}:{entry.get('evidence_index')}" in packet_evidence_ids
            ),
            "candidate_file_hash_pass_count": file_checks["candidate_file_hash_pass"],
            "candidate_file_missing_count": file_checks["candidate_file_missing"],
            "candidate_file_hash_mismatch_count": file_checks["candidate_file_hash_mismatch"],
            "edition_candidate_source_reference_count": len(edition_candidates_by_source),
            "edition_candidate_evidence_reference_count": sum(
                len(edition_candidates_by_source.get(str(packet["external_source_id"]), []))
                for packet in packets
            ),
        },
        "source_assessment_counts": dict(source_assessments),
        "evidence_assessment_counts": dict(evidence_assessments),
        "coverage": {
            "source_queue_fully_packetized": expected_source_ids == packet_source_ids,
            "passage_queue_fully_packetized": expected_passage_ids == packet_evidence_ids,
            "manifest_entries_are_queue_bound": all(
                f"external-passage:{entry.get('case_id')}:{entry.get('evidence_index')}" in packet_evidence_ids
                for entry in entries.values()
            ),
        },
        "boundary": {
            "all_candidates_remain_unknown": all(
                candidate.get("canonical_status") != "canonical_active"
                for packet in packets
                for evidence in packet["evidence_packets"]
                for candidate in evidence["candidates"]
            ),
            "all_evidence_quote_checks_remain_unchecked_or_existing": all(
                evidence["quote_check"] in {"unchecked", "passed", "normalized_passed"}
                for packet in packets
                for evidence in packet["evidence_packets"]
            ),
        },
    }
    report["valid"] = bool(
        all(report["coverage"].values())
        and report["counts"]["candidate_file_missing_count"] == 0
        and report["counts"]["candidate_file_hash_mismatch_count"] == 0
        and edition_candidate_validation["valid"]
        and report["boundary"]["all_candidates_remain_unknown"]
        and report["boundary"]["all_evidence_quote_checks_remain_unchecked_or_existing"]
    )
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return report


def validate_external_evidence_packets(
    *,
    database_path: Path = DEFAULT_DATABASE,
    report_path: Path = DEFAULT_REPORT,
    packet_path: Path | None = None,
) -> dict[str, Any]:
    """Validate packet coverage against the current read-only queue."""

    errors: list[str] = []
    if not report_path.is_file():
        return {"valid": False, "errors": ["packet_report_missing"], "counts": {}}
    try:
        report = json.loads(report_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        return {"valid": False, "errors": [f"packet_report_invalid:{type(error).__name__}"], "counts": {}}
    edition_report = report.get("edition_candidate_manifest") or {}
    edition_manifest_path = (
        PROJECT_ROOT / str(edition_report.get("path"))
        if edition_report.get("path")
        else DEFAULT_EDITION_MANIFEST
    )
    edition_validation = validate_external_edition_candidate_manifest(edition_manifest_path)
    if not edition_validation["valid"]:
        errors.extend(edition_validation.get("errors") or ["edition_candidate_manifest_invalid"])
    if edition_report.get("sha256") and edition_report.get("sha256") != edition_validation.get("manifest_sha256"):
        errors.append("edition_candidate_manifest_report_hash_mismatch")
    if not edition_report:
        errors.append("edition_candidate_manifest_report_missing")
    packet_path = packet_path or (PROJECT_ROOT / str(report.get("packet_file") or ""))
    if not packet_path.is_file():
        return {"valid": False, "errors": ["packet_file_missing"], "counts": {}}
    packets: list[dict[str, Any]] = []
    try:
        for line_number, line in enumerate(packet_path.read_text(encoding="utf-8").splitlines(), start=1):
            row = json.loads(line)
            if not isinstance(row, dict):
                errors.append(f"packet_row_not_object:{line_number}")
            else:
                packets.append(row)
    except (OSError, ValueError) as error:
        errors.append(f"packet_file_invalid:{type(error).__name__}")

    with connect_read_only(database_path) as connection:
        expected_sources = {
            str(row["external_source_id"])
            for row in connection.execute("SELECT external_source_id FROM external_source_resolution_queue")
        }
        expected_passages = {
            str(row["queue_item_id"])
            for row in connection.execute("SELECT queue_item_id FROM external_passage_resolution_queue")
        }
    actual_sources = {str(packet.get("external_source_id")) for packet in packets}
    actual_passages = {
        str(evidence.get("queue_item_id"))
        for packet in packets
        for evidence in packet.get("evidence_packets") or []
    }
    source_duplicates = len(actual_sources) != len(packets)
    if source_duplicates:
        errors.append("duplicate_source_packet")
    if expected_sources - actual_sources:
        errors.append(f"source_packets_missing:{len(expected_sources - actual_sources)}")
    if actual_sources - expected_sources:
        errors.append(f"source_packets_orphan:{len(actual_sources - expected_sources)}")
    if expected_passages - actual_passages:
        errors.append(f"passage_packets_missing:{len(expected_passages - actual_passages)}")
    if actual_passages - expected_passages:
        errors.append(f"passage_packets_orphan:{len(actual_passages - expected_passages)}")
    report_counts = report.get("counts") or {}
    if report_counts.get("candidate_file_missing_count", 0):
        errors.append("candidate_file_missing")
    if report_counts.get("candidate_file_hash_mismatch_count", 0):
        errors.append("candidate_file_hash_mismatch")
    for packet in packets:
        for candidate in packet.get("edition_candidates") or []:
            if candidate.get("canonical_status") in {"canonical_active", "verified", "gold"}:
                errors.append(f"edition_candidate_canonical_boundary_breach:{packet.get('external_source_id')}")
        for evidence in packet.get("evidence_packets") or []:
            for candidate in evidence.get("edition_candidates") or []:
                if candidate.get("canonical_status") in {"canonical_active", "verified", "gold"}:
                    errors.append(f"edition_candidate_evidence_boundary_breach:{evidence.get('queue_item_id')}")
            if evidence.get("machine_assessment", {}).get("canonical_verified"):
                errors.append(f"canonical_boundary_breach:{evidence.get('queue_item_id')}")
            if evidence.get("machine_assessment", {}).get("quote_check_mutated"):
                errors.append(f"quote_check_boundary_breach:{evidence.get('queue_item_id')}")

    return {
        "valid": not errors,
        "errors": errors,
        "packet_file": relative_path(packet_path),
        "report_file": relative_path(report_path),
        "counts": {
            "expected_source_queue_count": len(expected_sources),
            "packet_source_count": len(actual_sources),
            "expected_passage_queue_count": len(expected_passages),
            "packet_passage_count": len(actual_passages),
            "manifest_entry_count": report.get("manifest", {}).get("entry_count", 0),
            "edition_candidate_count": edition_validation.get("counts", {}).get("candidate_count", 0),
            "edition_candidate_item_count": edition_validation.get("counts", {}).get("item_count", 0),
            "edition_candidate_file_count": edition_validation.get("counts", {}).get("complete_file_count", 0),
        },
        "edition_candidate_manifest_validation": edition_validation,
        "policy": report.get("policy", {}),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", type=Path, default=DEFAULT_DATABASE)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--edition-manifest", type=Path, default=DEFAULT_EDITION_MANIFEST)
    parser.add_argument("--packet", type=Path, default=DEFAULT_PACKET)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    args = parser.parse_args()
    report = build_packets(
        database_path=args.database,
        manifest_path=args.manifest,
        edition_manifest_path=args.edition_manifest,
        packet_path=args.packet,
        report_path=args.report,
    )
    print(json.dumps({"valid": report["valid"], "counts": report["counts"]}, ensure_ascii=False, indent=2))
    return 0 if report["valid"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
