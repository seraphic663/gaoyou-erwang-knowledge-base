from __future__ import annotations

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


class ClosingConnection(sqlite3.Connection):
    """Commit or roll back, then release the database handle on context exit."""

    def __exit__(self, exc_type, exc_value, traceback):
        try:
            return super().__exit__(exc_type, exc_value, traceback)
        finally:
            self.close()


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
        "external_passage_resolution_queue": {
            "selected_passage_id": "TEXT",
            "candidate_passage_ids_json": "TEXT NOT NULL DEFAULT '[]'",
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
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS resolution_events (
            resolution_event_id INTEGER PRIMARY KEY AUTOINCREMENT,
            resolution_kind TEXT NOT NULL CHECK(resolution_kind IN (
                'external_source_resolution', 'external_passage_resolution'
            )),
            queue_item_id TEXT NOT NULL,
            external_source_id TEXT,
            case_id TEXT,
            evidence_index INTEGER,
            reviewer TEXT NOT NULL,
            operation_id TEXT NOT NULL UNIQUE,
            from_queue_status TEXT,
            to_queue_status TEXT NOT NULL,
            resolution_note TEXT,
            resolution_json TEXT NOT NULL DEFAULT '{}',
            created_at TEXT NOT NULL,
            FOREIGN KEY(external_source_id) REFERENCES external_source_registry(external_source_id),
            FOREIGN KEY(case_id, evidence_index)
                REFERENCES annotation_evidences(case_id, evidence_index)
                ON DELETE CASCADE
        )
        """
    )
    connection.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_resolution_events_queue_item
        ON resolution_events(resolution_kind, queue_item_id, created_at)
        """
    )
    connection.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_external_passage_queue_selected_passage
        ON external_passage_resolution_queue(selected_passage_id)
        """
    )


def _source_document_id(passages: list[dict[str, Any]]) -> str:
    if not passages:
        raise ValueError("cannot_register_empty_passages")
    first = passages[0]
    work_key = first.get("work_key") or "unknown_work"
    source_file = str(first.get("source_file") or "source")
    source_name = Path(source_file).stem or "source"
    return f"{work_key}:{source_name}"


def open_database(
    database_path: str | Path,
    schema_path: str | Path = DEFAULT_SCHEMA_PATH,
) -> sqlite3.Connection:
    path = Path(database_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path, factory=ClosingConnection)
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
    source_metadata = {
        "source_file": first.get("source_file"),
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
            canonical_status, supersedes_source_document_id,
            metadata_json, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(source_document_id) DO UPDATE SET
            source_file = excluded.source_file,
            canonical_status = excluded.canonical_status,
            supersedes_source_document_id = excluded.supersedes_source_document_id,
            metadata_json = excluded.metadata_json
        """,
        (
            source_document_id,
            first.get("work_key", ""),
            source_kind,
            first.get("source_file", ""),
            canonical_status,
            supersedes_source_document_id,
            _json(source_metadata),
            _now(),
        ),
    )
    for passage in passage_list:
        connection.execute(
            """
            INSERT INTO passages(
                passage_id, source_document_id, work_key, document_title,
                section_title, entry_title, entry_kind, local_ordinal,
                md_line_start, md_line_end, raw_text, plain_text,
                normalized_text, inline_notes_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                output_case_id = COALESCE(excluded.output_case_id, candidate_items.output_case_id),
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
        external_source_id = f"external:{normalized_work}"
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
                quote_check, evidence_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                case_id,
                index,
                evidence.get("passage_id"),
                evidence.get("source_work"),
                evidence.get("quote", ""),
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


def _parse_json_list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    try:
        parsed = json.loads(value or "[]")
    except (TypeError, ValueError):
        return []
    return parsed if isinstance(parsed, list) else []


def _passage_source_status(
    connection: sqlite3.Connection, passage_id: str | None
) -> str | None:
    if not passage_id:
        return None
    row = connection.execute(
        """
        SELECT sd.canonical_status
        FROM passages p
        JOIN source_documents sd ON sd.source_document_id = p.source_document_id
        WHERE p.passage_id = ?
        """,
        (passage_id,),
    ).fetchone()
    return row["canonical_status"] if row else None


def _require_passage(
    connection: sqlite3.Connection,
    passage_id: str,
    *,
    require_canonical: bool = False,
    field_name: str,
) -> None:
    status = _passage_source_status(connection, passage_id)
    if status is None:
        raise ValueError(f"{field_name}_missing:{passage_id}")
    if require_canonical and status != "canonical_active":
        raise ValueError(f"{field_name}_not_canonical:{passage_id}")


def _process_values(
    connection: sqlite3.Connection,
    case_id: str,
    case_data: dict[str, Any],
) -> dict[str, Any]:
    existing_rows = connection.execute(
        """
        SELECT field_name, step_text
        FROM annotation_process_steps
        WHERE case_id = ? ORDER BY step_index
        """,
        (case_id,),
    ).fetchall()
    existing = {row["field_name"]: row["step_text"] for row in existing_rows}
    values = {
        field: case_data.get(field) or existing.get(field, "") or ""
        for field in PROCESS_FIELDS
    }
    return values


def _replace_process_steps(
    connection: sqlite3.Connection,
    case_id: str,
    values: dict[str, Any],
) -> None:
    connection.execute("DELETE FROM annotation_process_steps WHERE case_id = ?", (case_id,))
    for index, field_name in enumerate(PROCESS_FIELDS):
        text = str(values.get(field_name) or "")
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
                text,
                _json({"field_name": field_name, "text": text}),
            ),
        )


def _apply_evidence_decisions(
    connection: sqlite3.Connection,
    case_id: str,
    decisions: Any,
    case_data: dict[str, Any],
) -> None:
    if decisions is None:
        return
    if not isinstance(decisions, list):
        raise ValueError("evidence_decisions_must_be_list")

    evidence_data_by_index = {
        index: evidence
        for index, evidence in enumerate(case_data.get("evidences", []))
        if isinstance(evidence, dict)
    }
    for decision in decisions:
        if not isinstance(decision, dict):
            raise ValueError("evidence_decision_must_be_object")
        raw_index = decision.get("evidence_index")
        try:
            evidence_index = int(raw_index)
        except (TypeError, ValueError):
            raise ValueError("evidence_index_required") from None
        row = connection.execute(
            """
            SELECT passage_id, source_work, quote, quote_check, evidence_json
            FROM annotation_evidences
            WHERE case_id = ? AND evidence_index = ?
            """,
            (case_id, evidence_index),
        ).fetchone()
        if row is None:
            raise ValueError(f"evidence_not_found:{evidence_index}")

        evidence = _parse_json_object(row["evidence_json"])
        evidence.update(evidence_data_by_index.get(evidence_index, {}))
        field_values = {
            "passage_id": row["passage_id"],
            "source_work": row["source_work"],
            "quote": row["quote"],
            "quote_check": row["quote_check"],
        }
        for field in field_values:
            if field in decision:
                field_values[field] = decision[field]
        passage_id = field_values["passage_id"]
        if passage_id:
            _require_passage(
                connection,
                str(passage_id),
                field_name="evidence_passage",
            )
        quote_check = field_values["quote_check"]
        if quote_check not in {None, "unchecked", "passed", "failed", "normalized_passed"}:
            raise ValueError(f"invalid_quote_check:{evidence_index}:{quote_check}")
        quote = str(field_values["quote"] or "")
        if not quote:
            raise ValueError(f"empty_evidence_quote:{evidence_index}")
        for field in ("source_resolution", "cited_work_match_status", "external_source_id"):
            if field in decision:
                evidence[field] = decision[field]
        if quote_check in {"passed", "normalized_passed"}:
            if evidence.get("source_resolution") != "canonical_source_passage":
                raise ValueError(f"noncanonical_quote_cannot_pass:{evidence_index}")
            if not passage_id or _passage_source_status(connection, str(passage_id)) != "canonical_active":
                raise ValueError(f"noncanonical_evidence_passage_cannot_pass:{evidence_index}")
            passage_row = connection.execute(
                "SELECT raw_text, plain_text, normalized_text FROM passages WHERE passage_id = ?",
                (passage_id,),
            ).fetchone()
            matched = passage_row is not None and any(
                quote in (passage_row[column] or "")
                for column in ("raw_text", "plain_text", "normalized_text")
            )
            if not matched:
                raise ValueError(f"evidence_quote_not_in_passage:{evidence_index}")
        evidence.update(
            {
                "passage_id": passage_id,
                "source_work": field_values["source_work"],
                "quote": quote,
                "quote_check": quote_check,
            }
        )
        connection.execute(
            """
            UPDATE annotation_evidences
            SET passage_id = ?, source_work = ?, quote = ?, quote_check = ?,
                evidence_json = ?
            WHERE case_id = ? AND evidence_index = ?
            """,
            (
                passage_id,
                field_values["source_work"],
                quote,
                quote_check,
                _json(evidence),
                case_id,
                evidence_index,
            ),
        )
        while len(case_data.setdefault("evidences", [])) <= evidence_index:
            case_data["evidences"].append({})
        case_data["evidences"][evidence_index] = evidence


def _apply_case_patch(
    connection: sqlite3.Connection,
    case_id: str,
    case_patch: dict[str, Any] | None,
    evidence_decisions: Any,
) -> None:
    """Apply only an explicit review patch before the lifecycle gate.

    This is intentionally a narrow write surface.  It updates the structured
    annotation fields and their derived process/evidence rows, but it never
    decides whether a machine result is academically correct.
    """

    patch = dict(case_patch or {})
    allowed_fields = {
        "source_passage_id",
        "target_work",
        "target_works",
        "target_scope",
        "target_text",
        "target_passage_id",
        "target_location",
        "process_text",
        *PROCESS_FIELDS,
    }
    unknown_fields = sorted(set(patch) - allowed_fields)
    if unknown_fields:
        raise ValueError("unsupported_case_patch_fields:" + ",".join(unknown_fields))

    row = connection.execute(
        """
        SELECT case_json, source_passage_id, target_work, target_works_json,
               target_scope_json, target_text, target_passage_id,
               target_location_json, process_text
        FROM annotation_cases WHERE case_id = ?
        """,
        (case_id,),
    ).fetchone()
    if row is None:
        raise ValueError(f"case_not_found:{case_id}")
    case_data = _parse_json_object(row["case_json"])

    values: dict[str, Any] = {
        "source_passage_id": row["source_passage_id"],
        "target_work": row["target_work"],
        "target_works": _parse_json_list(row["target_works_json"]),
        "target_scope": _parse_json_object(row["target_scope_json"]),
        "target_text": row["target_text"],
        "target_passage_id": row["target_passage_id"],
        "target_location": _parse_json_object(row["target_location_json"]),
        "process_text": row["process_text"],
    }
    values.update({field: case_data.get(field, "") for field in PROCESS_FIELDS})
    values.update({key: patch[key] for key in patch})

    if values["source_passage_id"]:
        _require_passage(
            connection,
            str(values["source_passage_id"]),
            field_name="source_passage",
        )
    if values["target_passage_id"]:
        _require_passage(
            connection,
            str(values["target_passage_id"]),
            field_name="target_passage",
        )
    if not isinstance(values["target_works"], list):
        raise ValueError("target_works_must_be_list")
    if not isinstance(values["target_scope"], dict):
        raise ValueError("target_scope_must_be_object")
    if not isinstance(values["target_location"], dict):
        raise ValueError("target_location_must_be_object")

    values["target_works"] = [str(item).strip() for item in values["target_works"] if str(item).strip()]
    if "target_work" in patch and str(values["target_work"] or "").strip() and "target_works" not in patch:
        values["target_works"] = [str(values["target_work"]).strip()]
    values["target_work"] = str(values["target_work"] or "")
    process = _process_values(connection, case_id, {**case_data, **values})
    values["process_text"] = patch.get(
        "process_text",
        "\n".join(f"{field}: {process[field]}" for field in PROCESS_FIELDS),
    )

    case_data.update(
        {
            "source_passage_id": values["source_passage_id"],
            "target_work": values["target_work"],
            "target_works": values["target_works"],
            "target_scope": values["target_scope"],
            "target_text": values["target_text"],
            "target_passage_id": values["target_passage_id"],
            "target_location": values["target_location"],
            "process_text": values["process_text"],
            **process,
        }
    )
    _apply_evidence_decisions(connection, case_id, evidence_decisions, case_data)

    connection.execute(
        """
        UPDATE annotation_cases
        SET source_passage_id = ?, target_work = ?, target_works_json = ?,
            target_scope_json = ?, target_text = ?, target_passage_id = ?,
            target_location_json = ?, process_text = ?, case_json = ?,
            updated_at = ?
        WHERE case_id = ?
        """,
        (
            values["source_passage_id"],
            values["target_work"],
            _json(values["target_works"]),
            _json(values["target_scope"]),
            values["target_text"],
            values["target_passage_id"],
            _json(values["target_location"]),
            values["process_text"],
            _json(case_data),
            _now(),
            case_id,
        ),
    )
    _replace_process_steps(connection, case_id, process)


def _review_approval_errors(
    connection: sqlite3.Connection,
    case_row: sqlite3.Row,
    review: dict[str, Any],
) -> list[str]:
    """Return the explicit gates required before a case can become gold."""

    errors: list[str] = []
    if not case_row["source_passage_id"]:
        errors.append("source_passage_not_bound")
    if not str(case_row["target_work"] or "").strip():
        errors.append("target_work_not_resolved")
    if not case_row["target_passage_id"]:
        errors.append("target_passage_not_bound")

    process_rows = connection.execute(
        """
        SELECT field_name, step_text
        FROM annotation_process_steps
        WHERE case_id = ?
        """,
        (case_row["case_id"],),
    ).fetchall()
    process_by_field = {row["field_name"]: row["step_text"] for row in process_rows}
    for field in PROCESS_FIELDS:
        if not str(process_by_field.get(field) or "").strip():
            errors.append(f"process_field_missing:{field}")

    source_source_status = connection.execute(
        """
        SELECT sd.canonical_status
        FROM passages p
        JOIN source_documents sd ON sd.source_document_id = p.source_document_id
        WHERE p.passage_id = ?
        """,
        (case_row["source_passage_id"],),
    ).fetchone()
    if source_source_status is None:
        errors.append("source_passage_missing")
    elif source_source_status["canonical_status"] != "canonical_active":
        errors.append("source_passage_not_canonical")

    target_source_status = connection.execute(
        """
        SELECT sd.canonical_status
        FROM passages p
        JOIN source_documents sd ON sd.source_document_id = p.source_document_id
        WHERE p.passage_id = ?
        """,
        (case_row["target_passage_id"],),
    ).fetchone()
    if target_source_status is None:
        errors.append("target_passage_missing")
    elif target_source_status["canonical_status"] != "canonical_active":
        errors.append("target_passage_not_canonical")

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
        SELECT e.evidence_index, e.quote, e.quote_check, e.passage_id,
               e.evidence_json, p.raw_text, p.plain_text, p.normalized_text,
               sd.canonical_status
        FROM annotation_evidences e
        LEFT JOIN passages p ON p.passage_id = e.passage_id
        LEFT JOIN source_documents sd ON sd.source_document_id = p.source_document_id
        WHERE e.case_id = ?
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
        evidence_data = _parse_json_object(evidence["evidence_json"])
        quote = str(evidence["quote"] or "")
        in_passage = any(
            quote in (evidence[column] or "")
            for column in ("raw_text", "plain_text", "normalized_text")
        )
        if evidence_data.get("source_resolution") != "canonical_source_passage":
            errors.append(f"evidence_source_not_canonical:{index}")
        if evidence["canonical_status"] != "canonical_active":
            errors.append(f"evidence_passage_not_canonical:{index}")
        if not in_passage:
            errors.append(f"evidence_quote_not_in_passage:{index}")
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
    event_kind: str = "human_review",
    update_case_state: bool = True,
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
                   source_passage_id, target_work, target_passage_id,
                   human_review_json
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

        to_lifecycle = (
            _lifecycle(case_row["machine_status"], review_status)
            if update_case_state
            else case_row["lifecycle"]
        )
        timestamp = _now()
        connection.execute(
            """
            INSERT INTO review_events(
                case_id, reviewer, operation_id, event_kind,
                from_lifecycle, from_human_status, to_lifecycle,
                review_status, review_note, review_json, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                case_id,
                reviewer or None,
                operation_id,
                event_kind,
                case_row["lifecycle"],
                case_row["human_status"],
                to_lifecycle,
                review_status,
                review_note,
                _json(review_payload),
                timestamp,
            ),
        )
        if update_case_state:
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


def apply_case_review_submission(
    connection: sqlite3.Connection,
    case_id: str,
    *,
    reviewer: str,
    review_status: str,
    operation_id: str,
    review_note: str = "",
    case_patch: dict[str, Any] | None = None,
    review: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Apply an explicit case patch and its human review event atomically.

    The patch is deliberately applied before the approval gate is evaluated so
    a reviewer can fill missing target/process/evidence fields in one request.
    A retry identified by the same ``operation_id`` returns the original event
    without applying the patch a second time.
    """

    review_payload = dict(review or {})
    started_transaction = not connection.in_transaction
    if started_transaction:
        connection.execute("BEGIN IMMEDIATE")
    try:
        existing_event = connection.execute(
            """
            SELECT review_event_id, case_id, review_status, to_lifecycle,
                   operation_id, review_json
            FROM review_events WHERE operation_id = ?
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

        _apply_case_patch(
            connection,
            case_id,
            case_patch,
            review_payload.get("evidence_decisions"),
        )
        result = apply_review_event(
            connection,
            case_id,
            reviewer=reviewer,
            review_status=review_status,
            operation_id=operation_id,
            review_note=review_note,
            review=review_payload,
            event_kind="case_review",
        )
        if started_transaction:
            connection.commit()
        return result
    except Exception:
        if started_transaction:
            connection.rollback()
        raise


def apply_target_work_resolution(
    connection: sqlite3.Connection,
    queue_item_id: str,
    *,
    reviewer: str,
    operation_id: str,
    target_work: str | None,
    target_passage_id: str | None,
    target_scope: dict[str, Any],
    resolution_status: str,
    review_note: str = "",
) -> dict[str, Any]:
    """Record a target-work decision without promoting the annotation case.

    Resolving a target is an auxiliary review task.  It may populate target
    fields, but the case remains machine-draft/human-pending until a separate
    case review submission passes the complete human approval contract.
    """

    allowed_statuses = {"resolved", "uncertain", "rejected"}
    if resolution_status not in allowed_statuses:
        raise ValueError(f"invalid_target_resolution_status:{resolution_status}")
    if not str(operation_id or "").strip():
        raise ValueError("operation_id_required")
    if not str(reviewer or "").strip():
        raise ValueError("reviewer_required_for_decision")
    if not isinstance(target_scope, dict):
        raise ValueError("target_scope_must_be_object")
    target_work_value = str(target_work or "").strip()

    started_transaction = not connection.in_transaction
    if started_transaction:
        connection.execute("BEGIN IMMEDIATE")
    try:
        queue_row = connection.execute(
            """
            SELECT queue_item_id, case_id, context_json
            FROM target_work_resolution_queue
            WHERE queue_item_id = ?
            """,
            (queue_item_id,),
        ).fetchone()
        if queue_row is None:
            raise ValueError(f"target_resolution_queue_item_not_found:{queue_item_id}")
        case_id = queue_row["case_id"]

        existing_event = connection.execute(
            """
            SELECT review_event_id, case_id, review_status, to_lifecycle,
                   operation_id, review_json
            FROM review_events WHERE operation_id = ?
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

        if resolution_status == "resolved":
            if not target_work_value:
                raise ValueError("resolved_target_work_required")
            if not target_passage_id:
                raise ValueError("resolved_target_passage_required")
            if target_scope.get("status") != "resolved":
                raise ValueError("resolved_target_scope_required")
            _require_passage(
                connection,
                str(target_passage_id),
                require_canonical=True,
                field_name="target_passage",
            )
        elif target_passage_id:
            _require_passage(connection, str(target_passage_id), field_name="target_passage")

        case_row = connection.execute(
            """
            SELECT case_id, lifecycle, target_work, target_works_json,
                   target_scope_json, target_passage_id, target_location_json,
                   case_json
            FROM annotation_cases WHERE case_id = ?
            """,
            (case_id,),
        ).fetchone()
        if case_row is None:
            raise ValueError(f"case_not_found:{case_id}")
        if case_row["lifecycle"] == "gold":
            raise ValueError("gold_case_is_immutable")

        existing_works = _parse_json_list(case_row["target_works_json"])
        target_works = [str(item).strip() for item in existing_works if str(item).strip()]
        if target_work_value and target_work_value not in target_works:
            target_works = [target_work_value]
        elif not target_work_value:
            target_work_value = str(case_row["target_work"] or "")
        if not target_works and target_work_value:
            target_works = [target_work_value]
        if resolution_status != "resolved":
            target_scope = {
                **_parse_json_object(case_row["target_scope_json"]),
                **target_scope,
            }
            target_scope["status"] = resolution_status
        if resolution_status != "resolved" and not target_passage_id:
            target_passage_id = case_row["target_passage_id"]
        target_location = _parse_json_object(case_row["target_location_json"])
        if target_passage_id:
            passage = connection.execute(
                """
                SELECT p.passage_id, p.source_document_id, p.work_key,
                       p.document_title, p.section_title, p.entry_title,
                       p.entry_kind, p.local_ordinal, p.md_line_start, p.md_line_end
                FROM passages p WHERE p.passage_id = ?
                """,
                (target_passage_id,),
            ).fetchone()
            if passage is None:
                raise ValueError(f"target_passage_missing:{target_passage_id}")
            target_location = dict(passage)

        case_data = _parse_json_object(case_row["case_json"])
        case_data.update(
            {
                "target_work": target_work_value,
                "target_works": target_works,
                "target_scope": target_scope,
                "target_passage_id": target_passage_id,
                "target_location": target_location,
            }
        )
        timestamp = _now()
        connection.execute(
            """
            UPDATE annotation_cases
            SET target_work = ?, target_works_json = ?, target_scope_json = ?,
                target_passage_id = ?, target_location_json = ?, case_json = ?,
                updated_at = ?
            WHERE case_id = ?
            """,
            (
                target_work_value,
                _json(target_works),
                _json(target_scope),
                target_passage_id,
                _json(target_location),
                _json(case_data),
                timestamp,
                case_id,
            ),
        )
        context = _parse_json_object(queue_row["context_json"])
        context["human_resolution"] = {
            "status": resolution_status,
            "target_work": target_work_value,
            "target_passage_id": target_passage_id,
            "target_scope": target_scope,
            "reviewer": reviewer,
            "operation_id": operation_id,
        }
        connection.execute(
            """
            UPDATE target_work_resolution_queue
            SET queue_status = ?, context_json = ?, updated_at = ?
            WHERE queue_item_id = ?
            """,
            (
                resolution_status,
                _json(context),
                timestamp,
                queue_item_id,
            ),
        )
        result = apply_review_event(
            connection,
            case_id,
            reviewer=reviewer,
            review_status="pending",
            operation_id=operation_id,
            review_note=review_note,
            review={
                "queue_item_id": queue_item_id,
                "resolution_status": resolution_status,
                "target_work": target_work_value,
                "target_passage_id": target_passage_id,
                "target_scope": target_scope,
            },
            event_kind="target_work_resolution",
            update_case_state=False,
        )
        if started_transaction:
            connection.commit()
        return result
    except Exception:
        if started_transaction:
            connection.rollback()
        raise


def _existing_resolution_event(
    connection: sqlite3.Connection, operation_id: str
) -> sqlite3.Row | None:
    return connection.execute(
        """
        SELECT resolution_event_id, resolution_kind, queue_item_id,
               external_source_id, case_id, evidence_index, reviewer,
               operation_id, from_queue_status, to_queue_status,
               resolution_note, resolution_json, created_at
        FROM resolution_events WHERE operation_id = ?
        """,
        (operation_id,),
    ).fetchone()


def _insert_resolution_event(
    connection: sqlite3.Connection,
    *,
    resolution_kind: str,
    queue_item_id: str,
    external_source_id: str | None,
    case_id: str | None,
    evidence_index: int | None,
    reviewer: str,
    operation_id: str,
    from_queue_status: str,
    to_queue_status: str,
    resolution_note: str,
    resolution: dict[str, Any],
) -> dict[str, Any]:
    timestamp = _now()
    cursor = connection.execute(
        """
        INSERT INTO resolution_events(
            resolution_kind, queue_item_id, external_source_id, case_id,
            evidence_index, reviewer, operation_id, from_queue_status,
            to_queue_status, resolution_note, resolution_json, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            resolution_kind,
            queue_item_id,
            external_source_id,
            case_id,
            evidence_index,
            reviewer,
            operation_id,
            from_queue_status,
            to_queue_status,
            resolution_note,
            _json(resolution),
            timestamp,
        ),
    )
    return {
        "resolution_event_id": cursor.lastrowid,
        "resolution_kind": resolution_kind,
        "queue_item_id": queue_item_id,
        "operation_id": operation_id,
        "to_queue_status": to_queue_status,
        "idempotent": False,
    }


def apply_external_source_resolution(
    connection: sqlite3.Connection,
    queue_item_id: str,
    *,
    reviewer: str,
    operation_id: str,
    resolution_status: str,
    source_file: str | None = None,
    edition: str | None = None,
    location_note: str | None = None,
    resolution_note: str = "",
) -> dict[str, Any]:
    """Record an external edition decision without making it canonical.

    verified is allowed only when an edition and readable file are supplied.
    The caller still has to register a canonical passage separately. The event itself never
    changes annotation evidence quote status.
    """

    allowed_statuses = {"candidate_available", "no_public_match", "verified", "rejected"}
    if resolution_status not in allowed_statuses:
        raise ValueError(f"invalid_external_source_resolution_status:{resolution_status}")
    if not str(reviewer or "").strip():
        raise ValueError("reviewer_required_for_decision")
    if not str(operation_id or "").strip():
        raise ValueError("operation_id_required")
    if resolution_status == "verified":
        if not str(source_file or "").strip():
            raise ValueError("verified_external_source_file_required")
        if not str(edition or "").strip():
            raise ValueError("verified_external_source_edition_required")

    started_transaction = not connection.in_transaction
    if started_transaction:
        connection.execute("BEGIN IMMEDIATE")
    try:
        queue_row = connection.execute(
            """
            SELECT q.queue_item_id, q.external_source_id, q.queue_status,
                   q.edition_status, r.source_file, r.edition, r.location_note
            FROM external_source_resolution_queue q
            JOIN external_source_registry r
              ON r.external_source_id = q.external_source_id
            WHERE q.queue_item_id = ?
            """,
            (queue_item_id,),
        ).fetchone()
        if queue_row is None:
            raise ValueError(f"external_source_queue_item_not_found:{queue_item_id}")
        existing = _existing_resolution_event(connection, operation_id)
        if existing is not None:
            if existing["queue_item_id"] != queue_item_id:
                raise ValueError("operation_id_already_used_for_other_resolution")
            result = dict(existing)
            result["idempotent"] = True
            if started_transaction:
                connection.commit()
            return result

        if resolution_status == "verified":
            verified_source_file = str(source_file).strip()
            if not Path(verified_source_file).is_file():
                raise ValueError("verified_external_source_file_not_found")
            edition_status = "verified"
            resolved_source_file = verified_source_file
            resolved_edition = str(edition).strip()
            resolved_location_note = location_note
        elif resolution_status == "candidate_available":
            resolved_source_file = source_file if source_file is not None else queue_row["source_file"]
            resolved_edition = edition if edition is not None else queue_row["edition"]
            resolved_location_note = location_note if location_note is not None else queue_row["location_note"]
            edition_status = "candidate_registered" if resolved_source_file else "missing"
        else:
            edition_status = "rejected" if resolution_status == "rejected" else (
                "candidate_registered" if queue_row["source_file"] else "missing"
            )
            resolved_source_file = source_file if source_file is not None else queue_row["source_file"]
            resolved_edition = edition if edition is not None else queue_row["edition"]
            resolved_location_note = location_note if location_note is not None else queue_row["location_note"]

        connection.execute(
            """
            UPDATE external_source_registry
            SET status = ?, source_file = ?, edition = ?,
                location_note = ?, updated_at = ?
            WHERE external_source_id = ?
            """,
            (
                "verified" if resolution_status == "verified" else (
                    "registered" if resolved_source_file else "pending"
                ),
                resolved_source_file,
                resolved_edition,
                resolved_location_note,
                _now(),
                queue_row["external_source_id"],
            ),
        )
        connection.execute(
            """
            UPDATE external_source_resolution_queue
            SET queue_status = ?, edition_status = ?, registry_status = ?,
                context_json = json_set(
                    context_json, '$.human_resolution', json(?)), updated_at = ?
            WHERE queue_item_id = ?
            """,
            (
                resolution_status,
                edition_status,
                "verified" if resolution_status == "verified" else (
                    "registered" if resolved_source_file else "pending"
                ),
                _json(
                    {
                        "status": resolution_status,
                        "reviewer": reviewer,
                        "operation_id": operation_id,
                        "source_file": resolved_source_file,
                        "edition": resolved_edition,
                    }
                ),
                _now(),
                queue_item_id,
            ),
        )
        result = _insert_resolution_event(
            connection,
            resolution_kind="external_source_resolution",
            queue_item_id=queue_item_id,
            external_source_id=queue_row["external_source_id"],
            case_id=None,
            evidence_index=None,
            reviewer=reviewer,
            operation_id=operation_id,
            from_queue_status=queue_row["queue_status"],
            to_queue_status=resolution_status,
            resolution_note=resolution_note,
            resolution={
                "source_file": resolved_source_file,
                "edition": resolved_edition,
                "location_note": resolved_location_note,
            },
        )
        if started_transaction:
            connection.commit()
        return result
    except Exception:
        if started_transaction:
            connection.rollback()
        raise


def apply_external_passage_resolution(
    connection: sqlite3.Connection,
    queue_item_id: str,
    *,
    reviewer: str,
    operation_id: str,
    resolution_status: str,
    selected_passage_id: str | None = None,
    resolution_note: str = "",
) -> dict[str, Any]:
    """Record an external quote/passage decision without auto-passing it.

    A selected passage must be from a canonical-active source and contain the
    quote.  The function records the selection and leaves ``annotation_evidences``
    unchanged; quote_check/source_resolution change only in a later explicit
    case-review patch after the evidence boundary is re-evaluated.
    """

    allowed_statuses = {"verified", "candidate_available", "no_public_match", "rejected"}
    if resolution_status not in allowed_statuses:
        raise ValueError(f"invalid_external_passage_resolution_status:{resolution_status}")
    if not str(reviewer or "").strip():
        raise ValueError("reviewer_required_for_decision")
    if not str(operation_id or "").strip():
        raise ValueError("operation_id_required")

    started_transaction = not connection.in_transaction
    if started_transaction:
        connection.execute("BEGIN IMMEDIATE")
    try:
        queue_row = connection.execute(
            """
            SELECT queue_item_id, external_source_id, case_id, evidence_index,
                   quote, queue_status, edition_status, passage_status
            FROM external_passage_resolution_queue
            WHERE queue_item_id = ?
            """,
            (queue_item_id,),
        ).fetchone()
        if queue_row is None:
            raise ValueError(f"external_passage_queue_item_not_found:{queue_item_id}")
        existing = _existing_resolution_event(connection, operation_id)
        if existing is not None:
            if existing["queue_item_id"] != queue_item_id:
                raise ValueError("operation_id_already_used_for_other_resolution")
            result = dict(existing)
            result["idempotent"] = True
            if started_transaction:
                connection.commit()
            return result

        if resolution_status == "verified":
            if not selected_passage_id:
                raise ValueError("verified_external_passage_required")
            source_queue = connection.execute(
                """
                SELECT q.edition_status, r.status
                FROM external_source_resolution_queue q
                JOIN external_source_registry r
                  ON r.external_source_id = q.external_source_id
                WHERE q.external_source_id = ?
                """,
                (queue_row["external_source_id"],),
            ).fetchone()
            if source_queue is None or source_queue["edition_status"] != "verified" or source_queue["status"] != "verified":
                raise ValueError("verified_external_source_edition_required")
            _require_passage(
                connection,
                selected_passage_id,
                require_canonical=True,
                field_name="external_selected_passage",
            )
            passage_row = connection.execute(
                """
                SELECT p.raw_text, p.plain_text, p.normalized_text,
                       sd.source_file, r.source_file AS registry_source_file
                FROM passages p
                JOIN source_documents sd ON sd.source_document_id = p.source_document_id
                JOIN external_source_registry r
                  ON r.external_source_id = ?
                WHERE p.passage_id = ?
                """,
                (queue_row["external_source_id"], selected_passage_id),
            ).fetchone()
            quote = str(queue_row["quote"] or "")
            if passage_row is None:
                raise ValueError("verified_external_passage_missing")
            if (
                not passage_row["registry_source_file"]
                or passage_row["source_file"] != passage_row["registry_source_file"]
            ):
                raise ValueError("verified_external_passage_source_mismatch")
            if not any(
                quote in (passage_row[column] or "")
                for column in ("raw_text", "plain_text", "normalized_text")
            ):
                raise ValueError("verified_external_quote_not_in_passage")
            passage_status = "verified"
            edition_status = "verified"
        elif resolution_status == "candidate_available":
            passage_status = "candidate_match" if selected_passage_id else "search_hit_only"
            edition_status = "selected_pending" if selected_passage_id else queue_row["edition_status"]
        elif resolution_status == "no_public_match":
            passage_status = "missing"
            edition_status = queue_row["edition_status"]
            selected_passage_id = None
        else:
            passage_status = "rejected"
            edition_status = "rejected"
            selected_passage_id = None

        connection.execute(
            """
            UPDATE external_passage_resolution_queue
            SET queue_status = ?, edition_status = ?, passage_status = ?,
                selected_passage_id = ?,
                context_json = json_set(
                    context_json, '$.human_resolution', json(?)), updated_at = ?
            WHERE queue_item_id = ?
            """,
            (
                resolution_status,
                edition_status,
                passage_status,
                selected_passage_id,
                _json(
                    {
                        "status": resolution_status,
                        "reviewer": reviewer,
                        "operation_id": operation_id,
                        "selected_passage_id": selected_passage_id,
                    }
                ),
                _now(),
                queue_item_id,
            ),
        )
        result = _insert_resolution_event(
            connection,
            resolution_kind="external_passage_resolution",
            queue_item_id=queue_item_id,
            external_source_id=queue_row["external_source_id"],
            case_id=queue_row["case_id"],
            evidence_index=queue_row["evidence_index"],
            reviewer=reviewer,
            operation_id=operation_id,
            from_queue_status=queue_row["queue_status"],
            to_queue_status=resolution_status,
            resolution_note=resolution_note,
            resolution={"selected_passage_id": selected_passage_id},
        )
        if started_transaction:
            connection.commit()
        return result
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
                evidence_state, reason, source_file,
                metadata_json, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'catalog_only', 'unreferenced', ?, ?, ?, ?, ?)
            ON CONFLICT(catalog_term_id) DO UPDATE SET
                term = excluded.term,
                term_type = excluded.term_type,
                category = excluded.category,
                aliases_json = excluded.aliases_json,
                notes = excluded.notes,
                core_meaning = excluded.core_meaning,
                reason = excluded.reason,
                source_file = excluded.source_file,
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
                reason, source_file, metadata_json,
                created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'catalog_only', 'unreferenced', ?, ?, ?, ?, ?)
            ON CONFLICT(catalog_work_id) DO UPDATE SET
                title = excluded.title,
                author = excluded.author,
                work_type = excluded.work_type,
                dynasty = excluded.dynasty,
                time_note = excluded.time_note,
                notes = excluded.notes,
                reason = excluded.reason,
                source_file = excluded.source_file,
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
                _json({"legacy_row": work}),
                now,
                now,
            ),
        )
    return {"catalog_only_terms": len(term_rows), "catalog_only_works": len(work_rows)}


def ingest_legacy_dictionary_inventory(
    connection: sqlite3.Connection,
    *,
    terms: Iterable[dict[str, Any]],
    works: Iterable[dict[str, Any]],
    cases: Iterable[dict[str, Any]],
    source_file: str,
) -> dict[str, int]:
    """Persist the complete legacy term/work inventory and its relationships.

    ``legacy_catalog_*`` is intentionally limited to unreferenced rows.  This
    companion layer keeps *all* old rows and the old relationship fields so the
    V2 database can use the legacy dictionary as migration material without
    confusing inventory metadata with canonical evidence or human review.
    """

    now = _now()
    term_rows = [dict(row) for row in terms]
    work_rows = [dict(row) for row in works]
    case_rows = [dict(row) for row in cases]
    terms_by_id = {int(row["id"]): row for row in term_rows}
    works_by_id = {int(row["id"]): row for row in work_rows}
    term_case_ids: dict[int, list[int]] = {term_id: [] for term_id in terms_by_id}
    term_case_positions: dict[tuple[int, int], list[int]] = {}
    case_by_legacy_id: dict[int, str] = {}
    for case in case_rows:
        migration_provenance = (
            case.get("_migration", {}).get("provenance", {})
            if isinstance(case.get("_migration"), dict)
            else {}
        )
        legacy_case_value = case.get("legacy_case_id") or migration_provenance.get("legacy_case_id")
        if legacy_case_value is None:
            case_id_text = str(case.get("case_id") or "")
            legacy_case_value = case_id_text.rsplit(":", 1)[-1]
        legacy_case_id = int(legacy_case_value)
        v2_case_id = str(case["case_id"])
        case_by_legacy_id[legacy_case_id] = v2_case_id
        raw_term_ids = case.get("legacy_term_ids") or migration_provenance.get("legacy_term_ids") or []
        if isinstance(raw_term_ids, str):
            try:
                raw_term_ids = json.loads(raw_term_ids)
            except (TypeError, ValueError):
                raw_term_ids = []
        for position, raw_term_id in enumerate(raw_term_ids):
            try:
                term_id = int(raw_term_id)
            except (TypeError, ValueError):
                continue
            if term_id not in terms_by_id:
                continue
            term_case_ids[term_id].append(legacy_case_id)
            term_case_positions.setdefault((term_id, legacy_case_id), []).append(position)

    evidence_rows: list[dict[str, Any]] = []
    for case in case_rows:
        migration_provenance = (
            case.get("_migration", {}).get("provenance", {})
            if isinstance(case.get("_migration"), dict)
            else {}
        )
        legacy_case_value = case.get("legacy_case_id") or migration_provenance.get("legacy_case_id")
        if legacy_case_value is None:
            legacy_case_value = str(case.get("case_id") or "").rsplit(":", 1)[-1]
        for evidence_index, evidence in enumerate(case.get("evidences") or []):
            evidence_rows.append(
                {
                    "legacy_evidence_id": int(evidence["legacy_evidence_id"]),
                    "legacy_case_id": int(legacy_case_value),
                    "v2_case_id": str(case["case_id"]),
                    "v2_evidence_index": evidence_index,
                    "legacy_work_id": evidence.get("legacy_work_id"),
                    "legacy_term_id": evidence.get("legacy_term_id"),
                    "evidence_type": evidence.get("legacy_evidence_type"),
                }
            )
    work_evidence_counts: dict[int, int] = {work_id: 0 for work_id in works_by_id}
    work_case_ids: dict[int, list[int]] = {work_id: [] for work_id in works_by_id}
    term_evidence_counts: dict[int, int] = {term_id: 0 for term_id in terms_by_id}
    for evidence in evidence_rows:
        try:
            work_id = int(evidence["legacy_work_id"])
        except (TypeError, ValueError):
            work_id = None
        if work_id in work_evidence_counts:
            work_evidence_counts[work_id] += 1
            work_case_ids[work_id].append(evidence["legacy_case_id"])
        try:
            term_id = int(evidence["legacy_term_id"])
        except (TypeError, ValueError):
            term_id = None
        if term_id in term_evidence_counts:
            term_evidence_counts[term_id] += 1

    for term_id, row in terms_by_id.items():
        case_ids = sorted(set(term_case_ids[term_id]))
        connection.execute(
            """
            INSERT INTO legacy_dictionary_terms(
                legacy_term_id, term, term_type, category, aliases_json, notes,
                core_meaning, legacy_case_ids_json, usage_status,
                case_reference_count, evidence_reference_count, source_file,
                metadata_json, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(legacy_term_id) DO UPDATE SET
                term=excluded.term, term_type=excluded.term_type,
                category=excluded.category, aliases_json=excluded.aliases_json,
                notes=excluded.notes, core_meaning=excluded.core_meaning,
                legacy_case_ids_json=excluded.legacy_case_ids_json,
                usage_status=excluded.usage_status,
                case_reference_count=excluded.case_reference_count,
                evidence_reference_count=excluded.evidence_reference_count,
                source_file=excluded.source_file,
                metadata_json=excluded.metadata_json, updated_at=excluded.updated_at
            """,
            (
                term_id,
                row.get("term") or "未定",
                row.get("term_type"),
                row.get("category"),
                _json(row.get("aliases") or []),
                row.get("notes"),
                row.get("core_meaning"),
                _json(case_ids),
                "referenced" if case_ids else "catalog_only",
                len(case_ids),
                term_evidence_counts[term_id],
                source_file,
                _json({"legacy_row": row, "catalog_only": not bool(case_ids)}),
                now,
                now,
            ),
        )

    for work_id, row in works_by_id.items():
        case_ids = sorted(set(work_case_ids[work_id]))
        connection.execute(
            """
            INSERT INTO legacy_dictionary_works(
                legacy_work_id, title, author, work_type, dynasty, time_note,
                notes, legacy_case_ids_json, usage_status, case_reference_count,
                evidence_reference_count, source_file,
                metadata_json, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(legacy_work_id) DO UPDATE SET
                title=excluded.title, author=excluded.author,
                work_type=excluded.work_type, dynasty=excluded.dynasty,
                time_note=excluded.time_note, notes=excluded.notes,
                legacy_case_ids_json=excluded.legacy_case_ids_json,
                usage_status=excluded.usage_status,
                case_reference_count=excluded.case_reference_count,
                evidence_reference_count=excluded.evidence_reference_count,
                source_file=excluded.source_file,
                metadata_json=excluded.metadata_json, updated_at=excluded.updated_at
            """,
            (
                work_id,
                row.get("title") or "未定",
                row.get("author"),
                row.get("work_type"),
                row.get("dynasty"),
                row.get("time_note"),
                row.get("notes"),
                _json(case_ids),
                "referenced" if work_evidence_counts[work_id] else "catalog_only",
                len(case_ids),
                work_evidence_counts[work_id],
                source_file,
                _json({"legacy_row": row, "catalog_only": not bool(work_evidence_counts[work_id])}),
                now,
                now,
            ),
        )

    connection.execute(
        "DELETE FROM legacy_term_case_links WHERE v2_case_id IN (SELECT case_id FROM annotation_cases WHERE origin='legacy_dictionary_db_reprocessing')"
    )
    for (term_id, legacy_case_id), positions in term_case_positions.items():
        v2_case_id = case_by_legacy_id.get(legacy_case_id)
        if not v2_case_id:
            continue
        for position in positions:
            connection.execute(
                """
                INSERT INTO legacy_term_case_links(
                    legacy_term_id, legacy_case_id, v2_case_id, term_position,
                    source_field, metadata_json
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (term_id, legacy_case_id, v2_case_id, position, "cases.term_ids", "{}"),
            )

    connection.execute(
        "DELETE FROM legacy_work_evidence_links WHERE v2_case_id IN (SELECT case_id FROM annotation_cases WHERE origin='legacy_dictionary_db_reprocessing')"
    )
    for evidence in evidence_rows:
        try:
            work_id = int(evidence["legacy_work_id"])
        except (TypeError, ValueError):
            continue
        term_id = evidence.get("legacy_term_id")
        try:
            term_id = int(term_id) if term_id is not None else None
        except (TypeError, ValueError):
            term_id = None
        connection.execute(
            """
            INSERT INTO legacy_work_evidence_links(
                legacy_work_id, legacy_evidence_id, legacy_case_id, v2_case_id,
                v2_evidence_index, legacy_term_id, evidence_type,
                source_field, metadata_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                work_id,
                evidence["legacy_evidence_id"],
                evidence["legacy_case_id"],
                evidence["v2_case_id"],
                evidence["v2_evidence_index"],
                term_id,
                evidence.get("evidence_type"),
                "evidences.work_id",
                "{}",
            ),
        )
    return {
        "legacy_dictionary_terms": len(term_rows),
        "legacy_dictionary_works": len(work_rows),
        "legacy_term_case_links": sum(len(positions) for positions in term_case_positions.values()),
        "legacy_work_evidence_links": len(evidence_rows),
        "referenced_terms": sum(bool(term_case_ids[term_id]) for term_id in terms_by_id),
        "catalog_only_terms": sum(not bool(term_case_ids[term_id]) for term_id in terms_by_id),
        "referenced_works": sum(bool(work_evidence_counts[work_id]) for work_id in works_by_id),
        "catalog_only_works": sum(not bool(work_evidence_counts[work_id]) for work_id in works_by_id),
    }


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
        "candidate_target_locations",
        "annotation_cases",
        "annotation_terms",
        "annotation_evidences",
        "annotation_process_steps",
        "review_events",
        "resolution_events",
        "external_source_registry",
        "annotation_evidence_external_sources",
        "work_registry",
        "work_aliases",
        "target_work_resolution_queue",
        "external_source_resolution_queue",
        "external_passage_resolution_queue",
        "legacy_catalog_terms",
        "legacy_catalog_works",
        "legacy_dictionary_terms",
        "legacy_dictionary_works",
        "legacy_term_case_links",
        "legacy_work_evidence_links",
    )
    return {
        table: connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        for table in tables
    }
