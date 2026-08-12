from __future__ import annotations

import hashlib
import json
import sqlite3
import unicodedata
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable


MACHINE_STATUSES = {"pending", "draft", "approved", "rejected"}
HUMAN_STATUSES = {"pending", "approved", "rejected", "uncertain"}
PROCESS_FIELDS = (
    "problem_discovery",
    "research_question",
    "evidence_collection",
    "reasoning",
    "conclusion",
)
DEFAULT_SCHEMA_PATH = Path(__file__).resolve().parents[2] / "schemas/annotation_v2.sql"


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _normalize_work_label(value: str | None) -> str:
    text = unicodedata.normalize("NFKC", value or "").strip().strip("《》")
    return " ".join(text.split())


def _ensure_schema_extensions(connection: sqlite3.Connection) -> None:
    """Apply additive columns to a database created by an earlier V2 build."""

    table_additions = {
        "source_documents": {
            "canonical_status": "TEXT NOT NULL DEFAULT 'unknown'",
            "supersedes_source_document_id": "TEXT",
        },
        "annotation_cases": {
            "target_works_json": "TEXT NOT NULL DEFAULT '[]'",
            "target_scope_json": "TEXT NOT NULL DEFAULT '{}'",
            "target_passage_id": "TEXT",
            "target_location_json": "TEXT NOT NULL DEFAULT '{}'",
            "process_text": "TEXT NOT NULL DEFAULT ''",
            "evidence_state": "TEXT NOT NULL DEFAULT 'present'",
        },
        "review_events": {
            "operation_id": "TEXT",
            "event_kind": "TEXT NOT NULL DEFAULT 'human_review'",
            "from_lifecycle": "TEXT",
            "from_human_status": "TEXT",
            "to_lifecycle": "TEXT",
        },
    }
    for table, additions in table_additions.items():
        columns = {
            row[1] for row in connection.execute(f"PRAGMA table_info({table})")
        }
        for name, definition in additions.items():
            if name not in columns:
                connection.execute(
                    f"ALTER TABLE {table} ADD COLUMN {name} {definition}"
                )
    connection.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS idx_review_events_operation_id
        ON review_events(operation_id)
        WHERE operation_id IS NOT NULL
        """
    )


def _source_document_id(passages: list[dict[str, Any]]) -> str:
    if not passages:
        raise ValueError("cannot_register_empty_passages")
    first = passages[0]
    work_key = first.get("work_key") or "unknown_work"
    source_hash = first.get("source_file_sha256") or "nohash"
    return f"{work_key}:{source_hash[:16]}"


def register_source_version(
    connection: sqlite3.Connection,
    *,
    work_key: str,
    source_file: str,
    source_file_sha256: str,
    canonical_status: str,
    reason: str,
    superseded_by_sha256: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> str:
    """Record source-version lineage separately from loaded passage rows.

    A historical or rejected version may be registered without loading its
    text.  This makes the canonical decision auditable while preventing an
    inactive hash from silently becoming a passage source.
    """

    source_version_id = f"{work_key}:{source_file_sha256}"
    now = _now()
    connection.execute(
        """
        INSERT INTO source_version_registry(
            source_version_id, work_key, source_file, source_file_sha256,
            canonical_status, superseded_by_sha256, reason, metadata_json,
            recorded_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(source_version_id) DO UPDATE SET
            source_file = excluded.source_file,
            canonical_status = excluded.canonical_status,
            superseded_by_sha256 = excluded.superseded_by_sha256,
            reason = excluded.reason,
            metadata_json = excluded.metadata_json,
            recorded_at = excluded.recorded_at
        """,
        (
            source_version_id,
            work_key,
            source_file,
            source_file_sha256,
            canonical_status,
            superseded_by_sha256,
            reason,
            _json(metadata or {}),
            now,
        ),
    )
    return source_version_id


def open_database(
    database_path: str | Path,
    schema_path: str | Path = DEFAULT_SCHEMA_PATH,
) -> sqlite3.Connection:
    path = Path(database_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    connection.executescript(Path(schema_path).read_text(encoding="utf-8"))
    _ensure_schema_extensions(connection)
    return connection


def ingest_passages(
    connection: sqlite3.Connection,
    passages: Iterable[dict[str, Any]],
    *,
    source_kind: str = "markdown",
    metadata: dict[str, Any] | None = None,
) -> str:
    passage_list = list(passages)
    source_document_id = _source_document_id(passage_list)
    first = passage_list[0]
    conflicting_source = connection.execute(
        """
        SELECT source_document_id, source_file_sha256
        FROM source_documents
        WHERE work_key = ? AND source_file = ? AND source_file_sha256 <> ?
        """,
        (
            first.get("work_key", ""),
            first.get("source_file", ""),
            first.get("source_file_sha256", ""),
        ),
    ).fetchone()
    if conflicting_source is not None:
        raise ValueError(
            "source_version_conflict:"
            f"{conflicting_source['source_document_id']}"
        )
    source_metadata = {
        "source_file": first.get("source_file"),
        "source_file_sha256": first.get("source_file_sha256"),
    }
    if metadata:
        source_metadata.update(metadata)
    canonical_status = source_metadata.get("canonical_status")
    if not canonical_status:
        canonical_status = (
            "canonical_active"
            if source_kind in {"markdown", "markdown_core", "original_markdown"}
            else "legacy_unverified"
            if source_kind.startswith("legacy")
            else "unknown"
        )
    supersedes_source_document_id = source_metadata.get(
        "supersedes_source_document_id"
    )

    connection.execute(
        """
        INSERT INTO source_documents(
            source_document_id, work_key, source_kind, source_file,
            source_file_sha256, canonical_status, supersedes_source_document_id,
            metadata_json, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(source_document_id) DO UPDATE SET
            source_file = excluded.source_file,
            source_file_sha256 = excluded.source_file_sha256,
            canonical_status = excluded.canonical_status,
            supersedes_source_document_id = excluded.supersedes_source_document_id,
            metadata_json = excluded.metadata_json
        """,
        (
            source_document_id,
            first.get("work_key", ""),
            source_kind,
            first.get("source_file", ""),
            first.get("source_file_sha256", ""),
            canonical_status,
            supersedes_source_document_id,
            _json(source_metadata),
            _now(),
        ),
    )
    register_source_version(
        connection,
        work_key=first.get("work_key", ""),
        source_file=first.get("source_file", ""),
        source_file_sha256=first.get("source_file_sha256", ""),
        canonical_status=canonical_status,
        reason=source_metadata.get(
            "source_version_reason",
            "loaded source version registered by V2 passage ingestion",
        ),
        superseded_by_sha256=source_metadata.get("superseded_by_sha256"),
        metadata={
            "source_document_id": source_document_id,
            "source_kind": source_kind,
            "source_role": source_metadata.get("source_role"),
        },
    )

    for passage in passage_list:
        connection.execute(
            """
            INSERT INTO passages(
                passage_id, source_document_id, work_key, document_title,
                section_title, entry_title, entry_kind, local_ordinal,
                md_line_start, md_line_end, raw_text, plain_text,
                normalized_text, raw_text_sha256, normalized_text_sha256,
                inline_notes_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(passage_id) DO UPDATE SET
                source_document_id = excluded.source_document_id,
                work_key = excluded.work_key,
                document_title = excluded.document_title,
                section_title = excluded.section_title,
                entry_title = excluded.entry_title,
                entry_kind = excluded.entry_kind,
                local_ordinal = excluded.local_ordinal,
                md_line_start = excluded.md_line_start,
                md_line_end = excluded.md_line_end,
                raw_text = excluded.raw_text,
                plain_text = excluded.plain_text,
                normalized_text = excluded.normalized_text,
                raw_text_sha256 = excluded.raw_text_sha256,
                normalized_text_sha256 = excluded.normalized_text_sha256,
                inline_notes_json = excluded.inline_notes_json
            """,
            (
                passage["passage_id"],
                source_document_id,
                passage.get("work_key", ""),
                passage.get("document_title"),
                passage.get("section_title"),
                passage.get("entry_title"),
                passage.get("entry_kind"),
                passage.get("local_ordinal"),
                passage.get("md_line_start"),
                passage.get("md_line_end"),
                passage.get("raw_text", ""),
                passage.get("plain_text", ""),
                passage.get("normalized_text", ""),
                passage.get("raw_text_sha256"),
                passage.get("normalized_text_sha256"),
                _json(passage.get("inline_notes", [])),
            ),
        )
    return source_document_id


def ingest_candidate_items(
    connection: sqlite3.Connection,
    candidates: Iterable[dict[str, Any]],
    *,
    source_document_id: str,
    origin: str,
) -> int:
    """Store machine candidate records separately from annotation cases."""

    candidate_list = list(candidates)
    now = _now()
    for candidate in candidate_list:
        candidate_id = str(candidate.get("candidate_id") or "").strip()
        passage_id = str(candidate.get("passage_id") or "").strip()
        if not candidate_id or not passage_id:
            raise ValueError("candidate_id_and_passage_id_required")
        connection.execute(
            """
            INSERT INTO candidate_items(
                candidate_id, source_document_id, passage_id, work_key,
                source_work, candidate_text, rule_hits_json, risk_flags_json,
                candidate_status, origin, output_case_id, provenance_json,
                created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(candidate_id) DO UPDATE SET
                source_document_id = excluded.source_document_id,
                passage_id = excluded.passage_id,
                work_key = excluded.work_key,
                source_work = excluded.source_work,
                candidate_text = excluded.candidate_text,
                rule_hits_json = excluded.rule_hits_json,
                risk_flags_json = excluded.risk_flags_json,
                candidate_status = excluded.candidate_status,
                origin = excluded.origin,
                output_case_id = excluded.output_case_id,
                provenance_json = excluded.provenance_json,
                updated_at = excluded.updated_at
            """,
            (
                candidate_id,
                source_document_id,
                passage_id,
                candidate.get("work_key", ""),
                candidate.get("source_work", ""),
                candidate.get("candidate_text", candidate.get("text", "")),
                _json(candidate.get("rule_hits", [])),
                _json(candidate.get("risk_flags", [])),
                candidate.get("candidate_status", "pending"),
                origin,
                candidate.get("output_case_id"),
                _json(candidate.get("provenance", {})),
                now,
                now,
            ),
        )
    return len(candidate_list)


def _lifecycle(machine_status: str, human_status: str) -> str:
    if human_status == "approved":
        return "gold"
    if machine_status == "rejected" or human_status == "rejected":
        return "rejected"
    if human_status == "uncertain":
        return "human_review"
    return "machine_draft"


def _register_external_sources(
    connection: sqlite3.Connection, case: dict[str, Any]
) -> list[tuple[int, str]]:
    """Register cited works that are not represented by a canonical passage."""

    links: list[tuple[int, str]] = []
    for index, evidence in enumerate(case.get("evidences", [])):
        if evidence.get("cited_work_match_status") != "external_source_pending":
            continue
        cited_work = str(evidence.get("source_work") or "").strip()
        normalized_work = _normalize_work_label(cited_work)
        if not normalized_work:
            continue
        external_source_id = "external:" + hashlib.sha256(
            normalized_work.encode("utf-8")
        ).hexdigest()[:16]
        now = _now()
        connection.execute(
            """
            INSERT INTO external_source_registry(
                external_source_id, cited_work, normalized_work, source_kind,
                status, metadata_json, created_at, updated_at
            ) VALUES (?, ?, ?, 'external_citation', 'pending', '{}', ?, ?)
            ON CONFLICT(normalized_work) DO UPDATE SET
                cited_work = excluded.cited_work,
                updated_at = excluded.updated_at
            """,
            (
                external_source_id,
                cited_work,
                normalized_work,
                now,
                now,
            ),
        )
        evidence["external_source_id"] = external_source_id
        links.append((index, external_source_id))
    return links


def ingest_case(
    connection: sqlite3.Connection,
    case: dict[str, Any],
    *,
    origin: str,
) -> dict[str, Any]:
    """Insert a machine case into the unified work DB without gold promotion."""

    case_id = case.get("case_id")
    if not case_id:
        raise ValueError("case_id_required_for_database_ingest")
    machine_result = case.get("machine_result") or {"status": "pending"}
    human_review = case.get("human_review") or {"status": "pending"}
    machine_status = machine_result.get("status", "pending")
    human_status = human_review.get("status", "pending")
    if machine_status not in MACHINE_STATUSES:
        raise ValueError(f"invalid_machine_status:{machine_status}")
    if human_status not in HUMAN_STATUSES:
        raise ValueError(f"invalid_human_status:{human_status}")

    target_works = case.get("target_works") or []
    target_scope = case.get("target_scope") or {}
    evidence_state = case.get("evidence_state", "present")
    if not isinstance(target_works, list):
        raise ValueError("target_works_must_be_list")
    if evidence_state not in {"present", "source_no_citation"}:
        raise ValueError(f"invalid_evidence_state:{evidence_state}")

    source_passage_id = case.get("source_passage_id")
    if source_passage_id:
        exists = connection.execute(
            "SELECT 1 FROM passages WHERE passage_id = ?", (source_passage_id,)
        ).fetchone()
        if exists is None:
            raise ValueError(f"missing_source_passage:{source_passage_id}")
    target_passage_id = case.get("target_passage_id")
    if target_passage_id:
        exists = connection.execute(
            "SELECT 1 FROM passages WHERE passage_id = ?", (target_passage_id,)
        ).fetchone()
        if exists is None:
            raise ValueError(f"missing_target_passage:{target_passage_id}")
    target_location = case.get("target_location") or {}
    if not isinstance(target_location, dict):
        raise ValueError("target_location_must_be_object_or_null")

    external_links = _register_external_sources(connection, case)
    now = _now()
    lifecycle = _lifecycle(machine_status, human_status)
    connection.execute(
        """
        INSERT INTO annotation_cases(
            case_id, schema_version, case_title, submitted_by, source_work,
            target_work, target_works_json, target_scope_json, target_text,
            target_passage_id, target_location_json, process_text,
            evidence_state, source_passage_id, origin, lifecycle,
            machine_status, human_status, review_status, machine_result_json,
            human_review_json, case_json, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(case_id) DO UPDATE SET
            schema_version = excluded.schema_version,
            case_title = excluded.case_title,
            submitted_by = excluded.submitted_by,
            source_work = excluded.source_work,
            target_work = excluded.target_work,
            target_works_json = excluded.target_works_json,
            target_scope_json = excluded.target_scope_json,
            target_text = excluded.target_text,
            target_passage_id = excluded.target_passage_id,
            target_location_json = excluded.target_location_json,
            process_text = excluded.process_text,
            evidence_state = excluded.evidence_state,
            source_passage_id = excluded.source_passage_id,
            origin = excluded.origin,
            lifecycle = excluded.lifecycle,
            machine_status = excluded.machine_status,
            human_status = excluded.human_status,
            review_status = excluded.review_status,
            machine_result_json = excluded.machine_result_json,
            human_review_json = excluded.human_review_json,
            case_json = excluded.case_json,
            updated_at = excluded.updated_at
        """,
        (
            case_id,
            case.get("schema_version", "annotation_case.v1"),
            case.get("case_title", ""),
            case.get("submitted_by", ""),
            case.get("source_work", ""),
            case.get("target_work", ""),
            _json(target_works),
            _json(target_scope),
            case.get("target_text", ""),
            target_passage_id,
            _json(target_location),
            case.get("process_text", ""),
            evidence_state,
            source_passage_id,
            origin,
            lifecycle,
            machine_status,
            human_status,
            human_status,
            _json(machine_result),
            _json(human_review),
            _json(case),
            now,
            now,
        ),
    )

    connection.execute("DELETE FROM annotation_terms WHERE case_id = ?", (case_id,))
    for index, term in enumerate(case.get("term_relations", [])):
        connection.execute(
            """
            INSERT INTO annotation_terms(
                case_id, term_index, source_term, target_term, relation_type,
                relation_subtype, relation_note, term_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                case_id,
                index,
                term.get("source_term", ""),
                term.get("target_term", ""),
                term.get("relation_type"),
                term.get("relation_subtype"),
                term.get("relation_note"),
                _json(term),
            ),
        )

    connection.execute("DELETE FROM annotation_evidences WHERE case_id = ?", (case_id,))
    for index, evidence in enumerate(case.get("evidences", [])):
        connection.execute(
            """
            INSERT INTO annotation_evidences(
                case_id, evidence_index, passage_id, source_work, quote,
                quote_sha256, quote_check, evidence_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                case_id,
                index,
                evidence.get("passage_id"),
                evidence.get("source_work"),
                evidence.get("quote", ""),
                evidence.get("quote_sha256"),
                evidence.get("quote_check"),
                _json(evidence),
            ),
        )

    connection.execute(
        "DELETE FROM annotation_evidence_external_sources WHERE case_id = ?",
        (case_id,),
    )
    for evidence_index, external_source_id in external_links:
        connection.execute(
            """
            INSERT INTO annotation_evidence_external_sources(
                case_id, evidence_index, external_source_id
            ) VALUES (?, ?, ?)
            """,
            (case_id, evidence_index, external_source_id),
        )

    connection.execute("DELETE FROM annotation_process_steps WHERE case_id = ?", (case_id,))
    for index, field_name in enumerate(PROCESS_FIELDS):
        connection.execute(
            """
            INSERT INTO annotation_process_steps(
                case_id, step_index, field_name, step_text, step_json
            ) VALUES (?, ?, ?, ?, ?)
            """,
            (
                case_id,
                index,
                field_name,
                case.get(field_name),
                _json({"field_name": field_name, "text": case.get(field_name)}),
            ),
        )
    return get_case(connection, case_id) or {}


def _parse_json_object(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    try:
        parsed = json.loads(value or "{}")
    except (TypeError, ValueError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _review_approval_errors(
    connection: sqlite3.Connection,
    case_row: sqlite3.Row,
    review: dict[str, Any],
) -> list[str]:
    """Return the explicit gates required before a case can become gold."""

    errors: list[str] = []
    if not str(case_row["target_work"] or "").strip():
        errors.append("target_work_not_resolved")
    if not case_row["target_passage_id"]:
        errors.append("target_passage_not_bound")

    field_decisions = review.get("field_decisions")
    required_fields = (
        "source_passage",
        "target_work",
        "target_passage",
        "evidence",
        "process",
        "conclusion",
    )
    if not isinstance(field_decisions, dict):
        errors.append("field_decisions_required")
    else:
        for field in required_fields:
            if field_decisions.get(field) != "approved":
                errors.append(f"field_not_approved:{field}")

    evidence_rows = connection.execute(
        """
        SELECT evidence_index, quote_check
        FROM annotation_evidences
        WHERE case_id = ?
        ORDER BY evidence_index
        """,
        (case_row["case_id"],),
    ).fetchall()
    evidence_decisions = review.get("evidence_decisions")
    if not isinstance(evidence_decisions, list):
        evidence_decisions = []
    decision_by_index = {
        int(item["evidence_index"]): item
        for item in evidence_decisions
        if isinstance(item, dict) and str(item.get("evidence_index", "")).isdigit()
    }
    for evidence in evidence_rows:
        index = int(evidence["evidence_index"])
        decision = decision_by_index.get(index)
        if not decision or decision.get("status") != "approved":
            errors.append(f"evidence_not_approved:{index}")
        if evidence["quote_check"] not in {"passed", "normalized_passed"}:
            errors.append(f"evidence_quote_not_passed:{index}")
    if len(decision_by_index) != len(evidence_rows):
        errors.append("evidence_decisions_incomplete")
    return errors


def apply_review_event(
    connection: sqlite3.Connection,
    case_id: str,
    *,
    reviewer: str,
    review_status: str,
    operation_id: str,
    review_note: str = "",
    review: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Apply one idempotent human-review command in a single DB transaction.

    This function is the write boundary for a future review UI.  It never
    treats machine validation, legacy labels, or an existing machine status as
    human approval.  Approval additionally requires explicit field decisions,
    resolved target links, complete evidence decisions, and passed quote checks.
    ``operation_id`` is mandatory so a retried request cannot create a second
    review event or perform a second promotion.
    """

    if review_status not in HUMAN_STATUSES:
        raise ValueError(f"invalid_review_status:{review_status}")
    if not str(operation_id or "").strip():
        raise ValueError("operation_id_required")
    if review_status in {"approved", "rejected", "uncertain"} and not str(reviewer or "").strip():
        raise ValueError("reviewer_required_for_decision")
    review_payload = dict(review or {})
    started_transaction = not connection.in_transaction
    if started_transaction:
        connection.execute("BEGIN IMMEDIATE")
    try:
        existing_event = connection.execute(
            """
            SELECT review_event_id, case_id, review_status, to_lifecycle,
                   operation_id, review_json
            FROM review_events
            WHERE operation_id = ?
            """,
            (operation_id,),
        ).fetchone()
        if existing_event is not None:
            if existing_event["case_id"] != case_id:
                raise ValueError("operation_id_already_used_for_other_case")
            result = dict(existing_event)
            result["idempotent"] = True
            if started_transaction:
                connection.commit()
            return result

        case_row = connection.execute(
            """
            SELECT case_id, machine_status, human_status, lifecycle,
                   target_work, target_passage_id, human_review_json
            FROM annotation_cases
            WHERE case_id = ?
            """,
            (case_id,),
        ).fetchone()
        if case_row is None:
            raise ValueError(f"case_not_found:{case_id}")
        if case_row["lifecycle"] == "gold" and review_status != "approved":
            raise ValueError("gold_case_is_immutable")

        if review_status == "approved":
            approval_errors = _review_approval_errors(connection, case_row, review_payload)
            if approval_errors:
                raise ValueError("approval_gate_failed:" + ",".join(approval_errors))

        to_lifecycle = _lifecycle(case_row["machine_status"], review_status)
        human_review = _parse_json_object(case_row["human_review_json"])
        human_review.update(
            {
                "status": review_status,
                "reviewer": reviewer or None,
                "review_note": review_note,
                "operation_id": operation_id,
                "review_contract": "human_review_transaction.v1",
                "field_decisions": review_payload.get("field_decisions", {}),
                "evidence_decisions": review_payload.get("evidence_decisions", []),
            }
        )
        timestamp = _now()
        connection.execute(
            """
            INSERT INTO review_events(
                case_id, reviewer, operation_id, event_kind,
                from_lifecycle, from_human_status, to_lifecycle,
                review_status, review_note, review_json, created_at
            ) VALUES (?, ?, ?, 'human_review', ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                case_id,
                reviewer or None,
                operation_id,
                case_row["lifecycle"],
                case_row["human_status"],
                to_lifecycle,
                review_status,
                review_note,
                _json(review_payload),
                timestamp,
            ),
        )
        connection.execute(
            """
            UPDATE annotation_cases
            SET lifecycle = ?, human_status = ?, review_status = ?,
                human_review_json = ?, updated_at = ?
            WHERE case_id = ?
            """,
            (
                to_lifecycle,
                review_status,
                review_status,
                _json(human_review),
                timestamp,
                case_id,
            ),
        )
        event_id = connection.execute("SELECT last_insert_rowid()").fetchone()[0]
        if started_transaction:
            connection.commit()
        return {
            "review_event_id": event_id,
            "case_id": case_id,
            "review_status": review_status,
            "to_lifecycle": to_lifecycle,
            "operation_id": operation_id,
            "idempotent": False,
        }
    except Exception:
        if started_transaction:
            connection.rollback()
        raise


def ingest_legacy_catalog(
    connection: sqlite3.Connection,
    *,
    terms: Iterable[dict[str, Any]],
    works: Iterable[dict[str, Any]],
    source_file: str,
    source_file_sha256: str,
) -> dict[str, int]:
    """Persist unreferenced legacy terms/works as explicit catalog-only rows.

    These rows are inventory relationships, not annotation cases.  They carry
    no fabricated evidence and remain available for later source registration
    or manual review.
    """

    now = _now()
    term_rows = list(terms)
    work_rows = list(works)
    for term in term_rows:
        legacy_id = int(term["id"])
        connection.execute(
            """
            INSERT INTO legacy_catalog_terms(
                catalog_term_id, legacy_term_id, term, term_type, category,
                aliases_json, notes, core_meaning, catalog_status,
                evidence_state, reason, source_file, source_file_sha256,
                metadata_json, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'catalog_only', 'unreferenced', ?, ?, ?, ?, ?, ?)
            ON CONFLICT(catalog_term_id) DO UPDATE SET
                term = excluded.term,
                term_type = excluded.term_type,
                category = excluded.category,
                aliases_json = excluded.aliases_json,
                notes = excluded.notes,
                core_meaning = excluded.core_meaning,
                reason = excluded.reason,
                source_file = excluded.source_file,
                source_file_sha256 = excluded.source_file_sha256,
                metadata_json = excluded.metadata_json,
                updated_at = excluded.updated_at
            """,
            (
                f"legacy-term:{legacy_id}",
                legacy_id,
                term.get("term") or "未定",
                term.get("term_type"),
                term.get("category"),
                _json(term.get("aliases") or []),
                term.get("notes"),
                term.get("core_meaning"),
                "legacy terms table has no case_ids/evidence relationship",
                source_file,
                source_file_sha256,
                _json({"legacy_row": term}),
                now,
                now,
            ),
        )
    for work in work_rows:
        legacy_id = int(work["id"])
        connection.execute(
            """
            INSERT INTO legacy_catalog_works(
                catalog_work_id, legacy_work_id, title, author, work_type,
                dynasty, time_note, notes, catalog_status, evidence_state,
                reason, source_file, source_file_sha256, metadata_json,
                created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'catalog_only', 'unreferenced', ?, ?, ?, ?, ?, ?)
            ON CONFLICT(catalog_work_id) DO UPDATE SET
                title = excluded.title,
                author = excluded.author,
                work_type = excluded.work_type,
                dynasty = excluded.dynasty,
                time_note = excluded.time_note,
                notes = excluded.notes,
                reason = excluded.reason,
                source_file = excluded.source_file,
                source_file_sha256 = excluded.source_file_sha256,
                metadata_json = excluded.metadata_json,
                updated_at = excluded.updated_at
            """,
            (
                f"legacy-work:{legacy_id}",
                legacy_id,
                work.get("title") or "未定",
                work.get("author"),
                work.get("work_type"),
                work.get("dynasty"),
                work.get("time_note"),
                work.get("notes"),
                "legacy works row has no evidence reference",
                source_file,
                source_file_sha256,
                _json({"legacy_row": work}),
                now,
                now,
            ),
        )
    return {"catalog_only_terms": len(term_rows), "catalog_only_works": len(work_rows)}


def get_case(connection: sqlite3.Connection, case_id: str) -> dict[str, Any] | None:
    row = connection.execute(
        """
        SELECT case_id, case_title, origin, lifecycle, machine_status,
               human_status, review_status, source_passage_id,
               target_passage_id, target_location_json, process_text
        FROM annotation_cases WHERE case_id = ?
        """,
        (case_id,),
    ).fetchone()
    return dict(row) if row else None


def database_counts(connection: sqlite3.Connection) -> dict[str, int]:
    tables = (
        "source_documents",
        "passages",
        "candidate_items",
        "annotation_cases",
        "annotation_terms",
        "annotation_evidences",
        "annotation_process_steps",
        "review_events",
        "external_source_registry",
        "annotation_evidence_external_sources",
        "source_version_registry",
        "work_registry",
        "work_aliases",
        "target_work_resolution_queue",
        "external_source_resolution_queue",
        "external_passage_resolution_queue",
        "legacy_catalog_terms",
        "legacy_catalog_works",
    )
    return {
        table: connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        for table in tables
    }
