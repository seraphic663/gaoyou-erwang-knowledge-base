from __future__ import annotations

import json
import sqlite3
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


def _source_document_id(passages: list[dict[str, Any]]) -> str:
    if not passages:
        raise ValueError("cannot_register_empty_passages")
    first = passages[0]
    work_key = first.get("work_key") or "unknown_work"
    source_hash = first.get("source_file_sha256") or "nohash"
    return f"{work_key}:{source_hash[:16]}"


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
        "source_file_sha256": first.get("source_file_sha256"),
    }
    if metadata:
        source_metadata.update(metadata)

    connection.execute(
        """
        INSERT INTO source_documents(
            source_document_id, work_key, source_kind, source_file,
            source_file_sha256, metadata_json, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(source_document_id) DO UPDATE SET
            source_file = excluded.source_file,
            source_file_sha256 = excluded.source_file_sha256,
            metadata_json = excluded.metadata_json
        """,
        (
            source_document_id,
            first.get("work_key", ""),
            source_kind,
            first.get("source_file", ""),
            first.get("source_file_sha256", ""),
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


def _lifecycle(machine_status: str, human_status: str) -> str:
    if human_status == "approved":
        return "gold"
    if machine_status == "rejected" or human_status == "rejected":
        return "rejected"
    if human_status == "uncertain":
        return "human_review"
    return "machine_draft"


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

    source_passage_id = case.get("source_passage_id")
    if source_passage_id:
        exists = connection.execute(
            "SELECT 1 FROM passages WHERE passage_id = ?", (source_passage_id,)
        ).fetchone()
        if exists is None:
            raise ValueError(f"missing_source_passage:{source_passage_id}")

    now = _now()
    lifecycle = _lifecycle(machine_status, human_status)
    connection.execute(
        """
        INSERT INTO annotation_cases(
            case_id, schema_version, case_title, submitted_by, source_work,
            target_work, target_text, source_passage_id, origin, lifecycle,
            machine_status, human_status, review_status, machine_result_json,
            human_review_json, case_json, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(case_id) DO UPDATE SET
            schema_version = excluded.schema_version,
            case_title = excluded.case_title,
            submitted_by = excluded.submitted_by,
            source_work = excluded.source_work,
            target_work = excluded.target_work,
            target_text = excluded.target_text,
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
            case.get("target_text", ""),
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


def get_case(connection: sqlite3.Connection, case_id: str) -> dict[str, Any] | None:
    row = connection.execute(
        """
        SELECT case_id, case_title, origin, lifecycle, machine_status,
               human_status, review_status, source_passage_id
        FROM annotation_cases WHERE case_id = ?
        """,
        (case_id,),
    ).fetchone()
    return dict(row) if row else None


def database_counts(connection: sqlite3.Connection) -> dict[str, int]:
    tables = (
        "source_documents",
        "passages",
        "annotation_cases",
        "annotation_terms",
        "annotation_evidences",
        "annotation_process_steps",
        "review_events",
    )
    return {
        table: connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        for table in tables
    }
