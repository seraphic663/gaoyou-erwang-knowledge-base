#!/usr/bin/env python3
"""Materialize the three next-step work queues from the V2 work database.

This command is a queue/index build, not a verification pass.  It preserves
machine candidates, public-source candidates, and review decisions as
separate states and never promotes a case, source, or quote to gold.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


V2_ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = V2_ROOT.parent
DEFAULT_DATABASE = V2_ROOT / "data/real_runs/annotation_v2.db"
DEFAULT_MANIFEST = V2_ROOT / "data/real_runs/external_public_candidate_manifest.json"
DEFAULT_OUTPUT_DIR = V2_ROOT / "data/real_runs/queues"
DEFAULT_REPORT = V2_ROOT / "data/real_runs/work_queues_report.json"

sys.path.insert(0, str(V2_ROOT / "scripts"))
sys.path.insert(0, str(V2_ROOT / "src"))
from build_work_registry import normalize_label  # noqa: E402
from erwang_v2.database import open_database  # noqa: E402


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def relative_path(value: str | Path | None) -> str | None:
    if value is None:
        return None
    path = Path(value)
    try:
        return path.resolve().relative_to(PROJECT_ROOT.resolve()).as_posix()
    except ValueError:
        return str(path)


def parse_json(value: Any, fallback: Any) -> Any:
    if isinstance(value, (dict, list)):
        return value
    try:
        return json.loads(value or "")
    except (TypeError, ValueError):
        return fallback


def candidate_ref_key(ref: dict[str, Any]) -> tuple[str, ...]:
    """Return a stable identity for a frozen public candidate reference."""

    raw_file = str(ref.get("raw_file") or "")
    if raw_file:
        return ("raw", raw_file)
    pageid = str(ref.get("pageid") or "")
    revid = str(ref.get("revid") or "")
    if pageid and revid:
        return ("revision", pageid, revid)
    if raw_file and revid:
        return ("file_revision", raw_file, revid)
    page_url = str(ref.get("page_url") or "")
    if page_url:
        return ("url", page_url)
    return ("json", json.dumps(ref, ensure_ascii=False, sort_keys=True))


def merge_candidate_refs(
    current_refs: list[dict[str, Any]],
    previous_refs: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Keep prior machine candidates when a later public search is unstable.

    The current manifest is authoritative for newly observed fields, while a
    prior frozen candidate (including a linked candidate passage id) remains
    available for review if the public search ranking or API response changes.
    """

    merged: dict[tuple[str, ...], dict[str, Any]] = {}
    order: list[tuple[str, ...]] = []
    for ref in [*current_refs, *previous_refs]:
        if not isinstance(ref, dict):
            continue
        key = candidate_ref_key(ref)
        if key not in merged:
            merged[key] = dict(ref)
            order.append(key)
            continue
        for field, value in ref.items():
            if value not in (None, "") and merged[key].get(field) in (None, ""):
                merged[key][field] = value
    return [merged[key] for key in order]


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n")


def load_manifest(path: Path) -> tuple[dict[str, Any], dict[tuple[str, int], dict[str, Any]]]:
    if not path.exists():
        return {}, {}
    manifest = json.loads(path.read_text(encoding="utf-8"))
    entries = {
        (entry.get("case_id"), int(entry.get("evidence_index", -1))): entry
        for entry in manifest.get("entries", [])
    }
    return manifest, entries


def candidate_work_key(connection: sqlite3.Connection, raw_label: str) -> str | None:
    normalized = normalize_label(raw_label)
    if not normalized:
        return None
    row = connection.execute(
        """
        SELECT work_key
        FROM work_aliases
        WHERE normalized_label = ? AND mapping_status IN ('canonical', 'candidate')
        ORDER BY CASE mapping_status WHEN 'canonical' THEN 0 ELSE 1 END, work_key
        LIMIT 1
        """,
        (normalized,),
    ).fetchone()
    return row["work_key"] if row else None


def build_target_work_queue(connection: sqlite3.Connection) -> list[dict[str, Any]]:
    rows = connection.execute(
        """
        SELECT case_id, case_title, origin, source_work, source_passage_id,
               target_work, target_works_json, target_scope_json,
               machine_status, human_status, lifecycle
        FROM annotation_cases
        WHERE TRIM(target_work) = ''
           OR json_extract(target_scope_json, '$.status') <> 'resolved'
        ORDER BY case_id
        """
    ).fetchall()
    output: list[dict[str, Any]] = []
    timestamp = now()
    for row in rows:
        scope = parse_json(row["target_scope_json"], {})
        labels = parse_json(row["target_works_json"], [])
        if not isinstance(labels, list) or not labels:
            labels = scope.get("candidate_works") or scope.get("target_works") or []
        labels = [str(label).strip() for label in labels if str(label).strip()]
        if not labels:
            labels = [""]
        evidence_indexes = scope.get("evidence_indexes") or []
        for raw_label in dict.fromkeys(labels):
            normalized = normalize_label(raw_label)
            status = "machine_inferred" if raw_label else "unresolved"
            queue_status = "pending" if raw_label else "needs_context"
            priority = 55 if raw_label else 90
            if len(labels) > 1:
                priority -= 10
            queue_item_id = f"target-work:{row['case_id']}:{raw_label or '<empty>'}"
            context = {
                "case_id": row["case_id"],
                "case_title": row["case_title"],
                "origin": row["origin"],
                "source_work": row["source_work"],
                "source_passage_id": row["source_passage_id"],
                "machine_status": row["machine_status"],
                "human_status": row["human_status"],
                "lifecycle": row["lifecycle"],
                "target_scope": scope,
                "candidate_labels_for_case": labels,
                "resolution_boundary": "machine label/citation is a candidate only; human must resolve work identity and edition/passage scope",
            }
            candidate_key = candidate_work_key(connection, raw_label)
            connection.execute(
                """
                INSERT INTO target_work_resolution_queue(
                    queue_item_id, case_id, raw_label, normalized_label,
                    machine_candidate_work_key, machine_inference_status,
                    queue_status, evidence_indexes_json, context_json,
                    priority, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(case_id, raw_label) DO UPDATE SET
                    normalized_label=excluded.normalized_label,
                    machine_candidate_work_key=excluded.machine_candidate_work_key,
                    machine_inference_status=excluded.machine_inference_status,
                    evidence_indexes_json=excluded.evidence_indexes_json,
                    context_json=excluded.context_json,
                    priority=excluded.priority,
                    updated_at=excluded.updated_at
                """,
                (
                    queue_item_id,
                    row["case_id"],
                    raw_label,
                    normalized,
                    candidate_key,
                    status,
                    queue_status,
                    json.dumps(evidence_indexes, ensure_ascii=False),
                    json.dumps(context, ensure_ascii=False, sort_keys=True),
                    priority,
                    timestamp,
                    timestamp,
                ),
            )
            output.append(
                {
                    "queue_schema": "target_work_resolution_queue.v1",
                    "queue_item_id": queue_item_id,
                    "case_id": row["case_id"],
                    "raw_label": raw_label,
                    "normalized_label": normalized,
                    "machine_candidate_work_key": candidate_key,
                    "machine_inference_status": status,
                    "queue_status": queue_status,
                    "evidence_indexes": evidence_indexes,
                    "priority": priority,
                    "context": context,
                }
            )
    return output


def build_external_queues(
    connection: sqlite3.Connection,
    manifest: dict[str, Any],
    manifest_entries: dict[tuple[str, int], dict[str, Any]],
    manifest_path: Path,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    evidence_rows = connection.execute(
        """
        SELECT link.external_source_id, es.cited_work, es.status AS registry_status,
               es.source_file, es.edition,
               ae.case_id, ae.evidence_index, ae.source_work, ae.quote,
               ae.quote_check, ae.evidence_json
        FROM annotation_evidence_external_sources link
        JOIN external_source_registry es
          ON es.external_source_id=link.external_source_id
        JOIN annotation_evidences ae
          ON ae.case_id=link.case_id AND ae.evidence_index=link.evidence_index
        ORDER BY es.external_source_id, ae.case_id, ae.evidence_index
        """
    ).fetchall()
    by_source: dict[str, list[dict[str, Any]]] = defaultdict(list)
    passage_rows: list[dict[str, Any]] = []
    timestamp = now()
    for row in evidence_rows:
        entry = manifest_entries.get((row["case_id"], int(row["evidence_index"])), {})
        status = entry.get("status")
        candidates = entry.get("candidates") or []
        if status == "candidate_found" and candidates:
            queue_status = "candidate_available"
            edition_status = "candidate_registered" if row["registry_status"] != "verified" else "verified"
            passage_status = "candidate_match"
        elif status == "search_hit_only":
            queue_status = "pending"
            edition_status = "candidate_registered" if row["registry_status"] == "registered" else "missing"
            passage_status = "search_hit_only"
        elif status == "no_public_match":
            queue_status = "no_public_match"
            edition_status = "candidate_registered" if row["registry_status"] == "registered" else "missing"
            passage_status = "missing"
        else:
            queue_status = "pending"
            edition_status = "verified" if row["registry_status"] == "verified" else (
                "candidate_registered" if row["registry_status"] == "registered" else "missing"
            )
            passage_status = "missing"
        queue_item_id = f"external-passage:{row['case_id']}:{row['evidence_index']}"
        existing_queue = connection.execute(
            "SELECT queue_status, edition_status, passage_status, "
            "candidate_refs_json, candidate_passage_ids_json, context_json "
            "FROM external_passage_resolution_queue WHERE queue_item_id = ?",
            (queue_item_id,),
        ).fetchone()
        previous_candidate_refs = parse_json(
            existing_queue["candidate_refs_json"] if existing_queue is not None else None,
            [],
        )
        if not isinstance(previous_candidate_refs, list):
            previous_candidate_refs = []
        previous_candidate_passage_ids = parse_json(
            existing_queue["candidate_passage_ids_json"] if existing_queue is not None else None,
            [],
        )
        if not isinstance(previous_candidate_passage_ids, list):
            previous_candidate_passage_ids = []
        previous_candidate_passage_ids = sorted(
            set(str(value) for value in previous_candidate_passage_ids if str(value).strip())
        )
        previous_candidate_available = bool(
            existing_queue is not None
            and (
                existing_queue["queue_status"] == "candidate_available"
                or previous_candidate_passage_ids
                or any(
                    isinstance(ref, dict)
                    and (
                        ref.get("candidate_passage_id")
                        or ref.get("offline_match_mode") == "normalized_contiguous"
                    )
                    for ref in previous_candidate_refs
                )
            )
        )
        has_human_resolution = connection.execute(
            "SELECT 1 FROM resolution_events "
            "WHERE resolution_kind = 'external_passage_resolution' AND queue_item_id = ? LIMIT 1",
            (queue_item_id,),
        ).fetchone() is not None
        if has_human_resolution and existing_queue is not None:
            # Rebuilding machine indexes must not erase an explicit human
            # resolution merely because a later manifest/search pass changes.
            queue_status = existing_queue["queue_status"]
            edition_status = existing_queue["edition_status"]
            passage_status = existing_queue["passage_status"]
        candidate_refs = [
            {
                key: candidate.get(key)
                for key in (
                    "page_title", "pageid", "revid", "timestamp", "raw_file",
                    "page_url", "api_url",
                    "match_mode", "start_char", "end_char",
                    "offline_match_mode", "offline_start_char", "offline_end_char",
                    "candidate_passage_id",
                )
                if key in candidate
            }
            for candidate in candidates
        ]
        candidate_refs = merge_candidate_refs(candidate_refs, previous_candidate_refs)
        if previous_candidate_available and not has_human_resolution and queue_status != "candidate_available":
            # Public search is a discovery lane, not a destructive refresh.  A
            # later run may omit a previously found page because search ranking
            # and API results are not stable; retain that machine candidate for
            # review instead of silently downgrading it to no-match/pending.
            queue_status = "candidate_available"
            edition_status = "candidate_registered" if row["registry_status"] != "verified" else "verified"
            passage_status = "candidate_match"
        context = {
            "source_work_raw": row["source_work"],
            "evidence_json": parse_json(row["evidence_json"], {}),
            "registry_source_file": row["source_file"],
            "registry_edition": row["edition"],
            "manifest_status": status,
            "manifest_boundary": manifest.get("source_policy", {}).get("version_rule"),
            "prior_candidate_preserved": bool(previous_candidate_refs),
        }
        if has_human_resolution and existing_queue is not None:
            existing_context = parse_json(existing_queue["context_json"], {})
            if isinstance(existing_context, dict) and existing_context.get("human_resolution"):
                context["human_resolution"] = existing_context["human_resolution"]
        connection.execute(
            """
            INSERT INTO external_passage_resolution_queue(
                queue_item_id, external_source_id, case_id, evidence_index,
                cited_work, quote, source_resolution, quote_check, queue_status,
                edition_status, passage_status, candidate_manifest_path,
                candidate_refs_json, context_json,
                created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(case_id, evidence_index) DO UPDATE SET
                external_source_id=excluded.external_source_id,
                cited_work=excluded.cited_work,
                quote=excluded.quote,
                source_resolution=excluded.source_resolution,
                quote_check=excluded.quote_check,
                queue_status=excluded.queue_status,
                edition_status=excluded.edition_status,
                passage_status=excluded.passage_status,
                candidate_manifest_path=excluded.candidate_manifest_path,
                candidate_refs_json=excluded.candidate_refs_json,
                context_json=excluded.context_json,
                updated_at=excluded.updated_at
            """,
            (
                queue_item_id,
                row["external_source_id"],
                row["case_id"],
                row["evidence_index"],
                row["cited_work"],
                row["quote"],
                parse_json(row["evidence_json"], {}).get("source_resolution", ""),
                row["quote_check"],
                queue_status,
                edition_status,
                passage_status,
                relative_path(manifest_path),
                json.dumps(candidate_refs, ensure_ascii=False, sort_keys=True),
                json.dumps(context, ensure_ascii=False, sort_keys=True),
                timestamp,
                timestamp,
            ),
        )
        stored_candidate_passage_ids = previous_candidate_passage_ids
        record = {
            "queue_schema": "external_passage_resolution_queue.v1",
            "queue_item_id": queue_item_id,
            "external_source_id": row["external_source_id"],
            "case_id": row["case_id"],
            "evidence_index": row["evidence_index"],
            "cited_work": row["cited_work"],
            "quote": row["quote"],
            "source_resolution": context["evidence_json"].get("source_resolution"),
            "quote_check": row["quote_check"],
            "queue_status": queue_status,
            "edition_status": edition_status,
            "passage_status": passage_status,
            "candidate_manifest_path": relative_path(manifest_path),
            "candidate_refs": candidate_refs,
            "candidate_passage_ids": stored_candidate_passage_ids,
            "context": context,
        }
        passage_rows.append(record)
        by_source[row["external_source_id"]].append(record)

    source_rows: list[dict[str, Any]] = []
    for row in connection.execute(
        "SELECT * FROM external_source_registry ORDER BY external_source_id"
    ).fetchall():
        records = by_source.get(row["external_source_id"], [])
        candidate_count = sum(item["passage_status"] == "candidate_match" for item in records)
        no_match_count = sum(item["passage_status"] == "missing" for item in records)
        if row["status"] == "verified":
            queue_status = "verified"
            edition_status = "verified"
        elif candidate_count:
            queue_status = "candidate_available"
            edition_status = "candidate_registered"
        elif records and no_match_count == len(records):
            queue_status = "no_public_match"
            edition_status = "candidate_registered" if row["status"] == "registered" else "missing"
        else:
            queue_status = "pending"
            edition_status = "candidate_registered" if row["status"] == "registered" else "missing"
        queue_item_id = f"external-source:{row['external_source_id']}"
        existing_queue = connection.execute(
            "SELECT queue_status, edition_status, registry_status, context_json "
            "FROM external_source_resolution_queue WHERE queue_item_id = ?",
            (queue_item_id,),
        ).fetchone()
        has_human_resolution = connection.execute(
            "SELECT 1 FROM resolution_events "
            "WHERE resolution_kind = 'external_source_resolution' AND queue_item_id = ? LIMIT 1",
            (queue_item_id,),
        ).fetchone() is not None
        registry_status = row["status"]
        if has_human_resolution and existing_queue is not None:
            # Keep an explicit edition/source decision stable across machine
            # queue rebuilds.  The next human event, not a new manifest, owns
            # this state transition.
            queue_status = existing_queue["queue_status"]
            edition_status = existing_queue["edition_status"]
            registry_status = existing_queue["registry_status"]
        context = {
            "normalized_work": row["normalized_work"],
            "source_file": row["source_file"],
            "edition": row["edition"],
            "metadata": parse_json(row["metadata_json"], {}),
            "manifest_path": relative_path(manifest_path),
            "verification_boundary": "public transcription candidate is not an edition-verified canonical source",
        }
        if has_human_resolution and existing_queue is not None:
            existing_context = parse_json(existing_queue["context_json"], {})
            if isinstance(existing_context, dict) and existing_context.get("human_resolution"):
                context["human_resolution"] = existing_context["human_resolution"]
        connection.execute(
            """
            INSERT INTO external_source_resolution_queue(
                queue_item_id, external_source_id, cited_work, registry_status,
                queue_status, edition_status, evidence_count,
                pending_evidence_count, candidate_evidence_count, context_json,
                created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(external_source_id) DO UPDATE SET
                cited_work=excluded.cited_work,
                registry_status=excluded.registry_status,
                queue_status=excluded.queue_status,
                edition_status=excluded.edition_status,
                evidence_count=excluded.evidence_count,
                pending_evidence_count=excluded.pending_evidence_count,
                candidate_evidence_count=excluded.candidate_evidence_count,
                context_json=excluded.context_json,
                updated_at=excluded.updated_at
            """,
            (
                queue_item_id,
                row["external_source_id"],
                row["cited_work"],
                registry_status,
                queue_status,
                edition_status,
                len(records),
                sum(item["quote_check"] not in {"passed", "normalized_passed"} for item in records),
                candidate_count,
                json.dumps(context, ensure_ascii=False, sort_keys=True),
                timestamp,
                timestamp,
            ),
        )
        source_rows.append(
            {
                "queue_schema": "external_source_resolution_queue.v1",
                "queue_item_id": queue_item_id,
                "external_source_id": row["external_source_id"],
                "cited_work": row["cited_work"],
                "registry_status": registry_status,
                "queue_status": queue_status,
                "edition_status": edition_status,
                "evidence_count": len(records),
                "pending_evidence_count": sum(item["quote_check"] not in {"passed", "normalized_passed"} for item in records),
                "candidate_evidence_count": candidate_count,
                "context": context,
            }
        )
    return source_rows, passage_rows


def build_review_queue(connection: sqlite3.Connection) -> list[dict[str, Any]]:
    rows = connection.execute(
        """
        SELECT case_id, case_title, origin, source_work, target_work,
               source_passage_id, target_passage_id, target_scope_json,
               evidence_state, machine_status, human_status, lifecycle,
               updated_at
        FROM annotation_cases
        WHERE human_status IN ('pending', 'uncertain')
        ORDER BY case_id
        """
    ).fetchall()
    output = []
    for row in rows:
        scope = parse_json(row["target_scope_json"], {})
        output.append(
            {
                "queue_schema": "human_review_queue.v1",
                "case_id": row["case_id"],
                "case_title": row["case_title"],
                "origin": row["origin"],
                "source_work": row["source_work"],
                "target_work": row["target_work"],
                "source_passage_id": row["source_passage_id"],
                "target_passage_id": row["target_passage_id"],
                "target_scope_status": scope.get("status"),
                "evidence_state": row["evidence_state"],
                "machine_status": row["machine_status"],
                "human_status": row["human_status"],
                "lifecycle": row["lifecycle"],
                "review_contract": {
                    "operation_id_required": True,
                    "reviewer_required_for_decision": True,
                    "approval_requires_field_decisions": [
                        "source_passage", "target_work", "target_passage",
                        "evidence", "process", "conclusion",
                    ],
                    "approval_requires_complete_evidence_decisions": True,
                    "approval_never_comes_from_machine_status": True,
                },
                "updated_at": row["updated_at"],
            }
        )
    return output


def build_queues(
    *,
    database_path: Path = DEFAULT_DATABASE,
    manifest_path: Path = DEFAULT_MANIFEST,
    output_dir: Path = DEFAULT_OUTPUT_DIR,
    report_path: Path = DEFAULT_REPORT,
) -> dict[str, Any]:
    manifest, manifest_entries = load_manifest(manifest_path)
    with open_database(database_path) as connection:
        target_rows = build_target_work_queue(connection)
        external_source_rows, external_passage_rows = build_external_queues(
            connection, manifest, manifest_entries, manifest_path
        )
        review_rows = build_review_queue(connection)
        connection.commit()
        counts = {
            "target_work_queue": len(target_rows),
            "external_source_queue": len(external_source_rows),
            "external_passage_queue": len(external_passage_rows),
            "human_review_queue": len(review_rows),
            "review_events": connection.execute("SELECT COUNT(*) FROM review_events").fetchone()[0],
        }
        target_statuses = {
            row["queue_status"]: row["count"]
            for row in connection.execute(
                "SELECT queue_status, COUNT(*) AS count FROM target_work_resolution_queue GROUP BY queue_status"
            )
        }
        external_source_statuses = {
            row["queue_status"]: row["count"]
            for row in connection.execute(
                "SELECT queue_status, COUNT(*) AS count FROM external_source_resolution_queue GROUP BY queue_status"
            )
        }
        external_passage_statuses = {
            row["queue_status"]: row["count"]
            for row in connection.execute(
                "SELECT queue_status, COUNT(*) AS count FROM external_passage_resolution_queue GROUP BY queue_status"
            )
        }
        review_by_origin = {
            row["origin"]: row["count"]
            for row in connection.execute(
                "SELECT origin, COUNT(*) AS count FROM annotation_cases WHERE human_status IN ('pending','uncertain') GROUP BY origin"
            )
        }

    output_dir.mkdir(parents=True, exist_ok=True)
    target_path = output_dir / "target_work_resolution_queue.target_work.v1.jsonl"
    source_path = output_dir / "external_source_resolution_queue.edition.v1.jsonl"
    passage_path = output_dir / "external_passage_resolution_queue.passage.v1.jsonl"
    review_path = output_dir / "human_review_queue.review.v1.jsonl"
    write_jsonl(target_path, target_rows)
    write_jsonl(source_path, external_source_rows)
    write_jsonl(passage_path, external_passage_rows)
    write_jsonl(review_path, review_rows)
    report = {
        "report_version": "v2-work-queues.v1",
        "generated_at": now(),
        "database": relative_path(database_path),
        "manifest": relative_path(manifest_path),
        "policy": {
            "target_work_resolution_is_human_pending": True,
            "external_public_candidates_are_not_canonical": True,
            "review_events_are_write_boundary_only": True,
            "queue_build_promotes_nothing": True,
        },
        "counts": counts,
        "target_work_queue_statuses": target_statuses,
        "external_source_queue_statuses": external_source_statuses,
        "external_passage_queue_statuses": external_passage_statuses,
        "human_review_by_origin": review_by_origin,
        "outputs": {
            "target_work": relative_path(target_path),
            "external_source": relative_path(source_path),
            "external_passage": relative_path(passage_path),
            "human_review": relative_path(review_path),
        },
    }
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", type=Path, default=DEFAULT_DATABASE)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    args = parser.parse_args()
    report = build_queues(
        database_path=args.database,
        manifest_path=args.manifest,
        output_dir=args.output_dir,
        report_path=args.report,
    )
    print(json.dumps(report["counts"], ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
