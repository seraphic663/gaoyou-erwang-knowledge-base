"""Append-only storage for human-reviewed five-step V2 audit cards."""

from __future__ import annotations

import argparse
import base64
import binascii
import json
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


V2_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATABASE = V2_ROOT / "data/real_runs/annotation_v2.db"
ALLOWED_MODELS = {"deepseek-flash", "deepseek-v4-pro"}
ALLOWED_EFFORTS = {"none", "low", "high", "max"}
RECORD_STATES = {"active", "superseded", "deleted"}
STEP_FIELDS = (
    "problem_discovery",
    "research_question",
    "evidence_collection",
    "reasoning",
    "conclusion",
)


def now_utc() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def connect_database(database_path: Path) -> sqlite3.Connection:
    if not database_path.is_file():
        raise FileNotFoundError(f"v2_database_not_found:{database_path}")
    connection = sqlite3.connect(database_path, timeout=60)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute("PRAGMA busy_timeout = 60000")
    return connection


def ensure_audit_table(connection: sqlite3.Connection) -> None:
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS five_step_audit_records (
            audit_id TEXT PRIMARY KEY,
            case_id TEXT NOT NULL,
            reviewer TEXT NOT NULL,
            operation_id TEXT NOT NULL UNIQUE,
            model_requested TEXT NOT NULL CHECK(model_requested IN ('deepseek-flash', 'deepseek-v4-pro')),
            model_returned TEXT NOT NULL,
            reasoning_effort TEXT NOT NULL CHECK(reasoning_effort IN ('none', 'low', 'high', 'max')),
            prompt_version TEXT NOT NULL,
            case_fingerprint TEXT NOT NULL,
            generated_at TEXT NOT NULL,
            submitted_at TEXT NOT NULL,
            audit_json TEXT NOT NULL,
            record_version INTEGER NOT NULL DEFAULT 1,
            supersedes_audit_id TEXT,
            superseded_by_audit_id TEXT,
            record_state TEXT NOT NULL DEFAULT 'active'
                CHECK(record_state IN ('active', 'superseded', 'deleted')),
            deleted_from_state TEXT,
            deleted_at TEXT,
            deleted_by TEXT,
            delete_reason TEXT,
            delete_operation_id TEXT,
            restored_at TEXT,
            restored_by TEXT,
            restore_operation_id TEXT,
            FOREIGN KEY(case_id) REFERENCES annotation_cases(case_id) ON DELETE RESTRICT
        )
        """
    )
    connection.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_five_step_audit_records_case
        ON five_step_audit_records(case_id, submitted_at DESC)
        """
    )
    existing_columns = {
        row["name"] for row in connection.execute("PRAGMA table_info(five_step_audit_records)").fetchall()
    }
    migrations = {
        "record_version": "INTEGER NOT NULL DEFAULT 1",
        "supersedes_audit_id": "TEXT",
        "superseded_by_audit_id": "TEXT",
        "record_state": "TEXT NOT NULL DEFAULT 'active'",
        "deleted_from_state": "TEXT",
        "deleted_at": "TEXT",
        "deleted_by": "TEXT",
        "delete_reason": "TEXT",
        "delete_operation_id": "TEXT",
        "restored_at": "TEXT",
        "restored_by": "TEXT",
        "restore_operation_id": "TEXT",
    }
    for column, definition in migrations.items():
        if column not in existing_columns:
            connection.execute(f"ALTER TABLE five_step_audit_records ADD COLUMN {column} {definition}")
    connection.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS idx_five_step_audit_records_delete_operation
        ON five_step_audit_records(delete_operation_id)
        WHERE delete_operation_id IS NOT NULL
        """
    )
    connection.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS idx_five_step_audit_records_restore_operation
        ON five_step_audit_records(restore_operation_id)
        WHERE restore_operation_id IS NOT NULL
        """
    )


def parse_payload(encoded: str) -> dict[str, Any]:
    try:
        raw = base64.b64decode(encoded, validate=True)
        payload = json.loads(raw.decode("utf-8"))
    except (binascii.Error, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError(f"payload_base64_json_invalid:{error}") from error
    if not isinstance(payload, dict):
        raise ValueError("payload_must_be_object")
    return payload


def validate_reviewed_steps(steps: Any) -> None:
    if not isinstance(steps, list) or len(steps) != len(STEP_FIELDS):
        raise ValueError("reviewed_steps_must_contain_five_steps")
    if [item.get("field") if isinstance(item, dict) else None for item in steps] != list(STEP_FIELDS):
        raise ValueError("reviewed_steps_must_contain_all_five_steps_in_order")
    for step in steps:
        if not str(step.get("text") or "").strip():
            raise ValueError("reviewed_step_text_required")
        if step.get("status") not in {"accepted", "edited", "question"}:
            raise ValueError("reviewed_step_decision_invalid")
        if step.get("status") in {"edited", "question"} and not str(step.get("comment") or "").strip():
            raise ValueError("reviewed_step_comment_required_for_edit_or_question")


def validate_overall_decision(value: Any) -> None:
    if value not in {"reviewed", "needs_revision", "uncertain"}:
        raise ValueError("overall_decision_invalid")


def validate_payload(payload: dict[str, Any]) -> None:
    required = (
        "case_id",
        "reviewer",
        "operation_id",
        "model_requested",
        "model_returned",
        "reasoning_effort",
        "prompt_version",
        "case_fingerprint",
        "generated_at",
        "audit_json",
    )
    missing = [field for field in required if not str(payload.get(field) or "").strip()]
    if missing:
        raise ValueError(f"required_fields_missing:{','.join(missing)}")
    if payload["model_requested"] not in ALLOWED_MODELS:
        raise ValueError("model_not_allowed")
    if payload["reasoning_effort"] not in ALLOWED_EFFORTS:
        raise ValueError("reasoning_effort_not_allowed")
    if len(str(payload["case_fingerprint"])) != 64:
        raise ValueError("case_fingerprint_invalid")
    if str(payload["prompt_version"]) != "v2-five-step-audit.v1":
        raise ValueError("prompt_version_not_supported")

    audit = payload["audit_json"]
    if not isinstance(audit, dict):
        raise ValueError("audit_json_must_be_object")
    for key in ("ai_draft", "reviewed_steps"):
        steps = audit.get(key)
        if not isinstance(steps, list) or len(steps) != len(STEP_FIELDS) or any(not isinstance(item, dict) for item in steps):
            raise ValueError(f"{key}_must_contain_all_five_steps_in_order")
        if [item.get("field") for item in steps] != list(STEP_FIELDS):
            raise ValueError(f"{key}_must_contain_all_five_steps_in_order")
    validate_overall_decision(audit.get("overall_decision"))
    validate_reviewed_steps(audit["reviewed_steps"])
    if any(
        not str(step.get("text") or "").strip()
        or not isinstance(step.get("evidence_refs"), list)
        or not isinstance(step.get("review_questions"), list)
        for step in audit["ai_draft"]
    ):
        raise ValueError("ai_draft_step_schema_invalid")


def public_record(row: sqlite3.Row) -> dict[str, Any]:
    result = dict(row)
    result["audit"] = json.loads(result.pop("audit_json"))
    return result


def list_records(database_path: Path, case_id: str) -> dict[str, Any]:
    if not case_id.strip():
        raise ValueError("case_id_required")
    connection = connect_database(database_path)
    try:
        case = connection.execute(
            "SELECT case_id FROM annotation_cases WHERE case_id = ?",
            (case_id,),
        ).fetchone()
        if case is None:
            raise ValueError(f"case_not_found:{case_id}")
        exists = connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='five_step_audit_records'"
        ).fetchone()
        if exists is None:
            return {"ok": True, "case_id": case_id, "records": []}
        ensure_audit_table(connection)
        connection.commit()
        rows = connection.execute(
            """
            SELECT audit_id, case_id, reviewer, operation_id, model_requested,
                   model_returned, reasoning_effort, prompt_version,
                   case_fingerprint, generated_at, submitted_at, audit_json,
                   record_version, supersedes_audit_id, superseded_by_audit_id,
                   record_state, deleted_from_state, deleted_at, deleted_by,
                   delete_reason, delete_operation_id, restored_at, restored_by,
                   restore_operation_id
            FROM five_step_audit_records
            WHERE case_id = ?
            ORDER BY submitted_at DESC, audit_id DESC
            LIMIT 50
            """,
            (case_id,),
        ).fetchall()
        return {"ok": True, "case_id": case_id, "records": [public_record(row) for row in rows]}
    finally:
        connection.close()


def get_record(database_path: Path, audit_id: str) -> dict[str, Any]:
    audit_id = str(audit_id or "").strip()
    if not audit_id:
        raise ValueError("audit_id_required")
    connection = connect_database(database_path)
    try:
        exists = connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='five_step_audit_records'"
        ).fetchone()
        if exists is None:
            raise ValueError(f"audit_record_not_found:{audit_id}")
        ensure_audit_table(connection)
        connection.commit()
        row = connection.execute(
            """
            SELECT audit_id, case_id, reviewer, operation_id, model_requested,
                   model_returned, reasoning_effort, prompt_version,
                   case_fingerprint, generated_at, submitted_at, audit_json,
                   record_version, supersedes_audit_id, superseded_by_audit_id,
                   record_state, deleted_from_state, deleted_at, deleted_by,
                   delete_reason, delete_operation_id, restored_at, restored_by,
                   restore_operation_id
            FROM five_step_audit_records WHERE audit_id = ?
            """,
            (audit_id,),
        ).fetchone()
        if row is None:
            raise ValueError(f"audit_record_not_found:{audit_id}")
        return {"ok": True, "record": public_record(row)}
    finally:
        connection.close()


def save_record(database_path: Path, payload: dict[str, Any]) -> dict[str, Any]:
    validate_payload(payload)
    case_id = str(payload["case_id"]).strip()
    operation_id = str(payload["operation_id"]).strip()
    connection = connect_database(database_path)
    try:
        connection.execute("BEGIN IMMEDIATE")
        ensure_audit_table(connection)
        existing = connection.execute(
            """
            SELECT audit_id, case_id, reviewer, operation_id, model_requested,
                   model_returned, reasoning_effort, prompt_version,
                   case_fingerprint, generated_at, submitted_at, audit_json,
                   record_version, supersedes_audit_id, superseded_by_audit_id,
                   record_state, deleted_from_state, deleted_at, deleted_by,
                   delete_reason, delete_operation_id, restored_at, restored_by,
                   restore_operation_id
            FROM five_step_audit_records WHERE operation_id = ?
            """,
            (operation_id,),
        ).fetchone()
        if existing is not None:
            if existing["case_id"] != case_id:
                raise ValueError("operation_id_already_used_for_other_case")
            connection.commit()
            result = public_record(existing)
            result["idempotent"] = True
            return result

        case = connection.execute(
            "SELECT case_id FROM annotation_cases WHERE case_id = ?",
            (case_id,),
        ).fetchone()
        if case is None:
            raise ValueError(f"case_not_found:{case_id}")
        evidence_indexes = {
            int(row["evidence_index"])
            for row in connection.execute(
                "SELECT evidence_index FROM annotation_evidences WHERE case_id = ?",
                (case_id,),
            ).fetchall()
        }
        if any(
            not isinstance(index, int) or index not in evidence_indexes
            for step in payload["audit_json"]["ai_draft"]
            for index in step["evidence_refs"]
        ):
            raise ValueError("ai_draft_references_unknown_v2_evidence")
        audit_id = f"audit:{uuid.uuid4().hex}"
        submitted_at = now_utc()
        audit_json = dict(payload["audit_json"])
        audit_json["submitted_at"] = submitted_at
        connection.execute(
            """
            INSERT INTO five_step_audit_records(
                audit_id, case_id, reviewer, operation_id, model_requested,
                model_returned, reasoning_effort, prompt_version,
                case_fingerprint, generated_at, submitted_at, audit_json,
                record_version, record_state
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, 'active')
            """,
            (
                audit_id,
                case_id,
                str(payload["reviewer"]).strip(),
                operation_id,
                payload["model_requested"],
                str(payload["model_returned"]).strip(),
                payload["reasoning_effort"],
                str(payload["prompt_version"]).strip(),
                str(payload["case_fingerprint"]).strip(),
                str(payload["generated_at"]).strip(),
                submitted_at,
                json.dumps(audit_json, ensure_ascii=False, sort_keys=True),
            ),
        )
        row = connection.execute(
            """
            SELECT audit_id, case_id, reviewer, operation_id, model_requested,
                   model_returned, reasoning_effort, prompt_version,
                   case_fingerprint, generated_at, submitted_at, audit_json,
                   record_version, supersedes_audit_id, superseded_by_audit_id,
                   record_state, deleted_from_state, deleted_at, deleted_by,
                   delete_reason, delete_operation_id, restored_at, restored_by,
                   restore_operation_id
            FROM five_step_audit_records WHERE audit_id = ?
            """,
            (audit_id,),
        ).fetchone()
        connection.commit()
        return public_record(row)
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def _operation_record(connection: sqlite3.Connection, operation_id: str) -> sqlite3.Row | None:
    return connection.execute(
        """
        SELECT audit_id, case_id, reviewer, operation_id, model_requested,
               model_returned, reasoning_effort, prompt_version,
               case_fingerprint, generated_at, submitted_at, audit_json,
               record_version, supersedes_audit_id, superseded_by_audit_id,
               record_state, deleted_from_state, deleted_at, deleted_by,
               delete_reason, delete_operation_id, restored_at, restored_by,
               restore_operation_id
        FROM five_step_audit_records
        WHERE operation_id = ? OR delete_operation_id = ? OR restore_operation_id = ?
        ORDER BY submitted_at DESC, audit_id DESC LIMIT 1
        """,
        (operation_id, operation_id, operation_id),
    ).fetchone()


def _record_row(connection: sqlite3.Connection, audit_id: str) -> sqlite3.Row | None:
    return connection.execute(
        """
        SELECT audit_id, case_id, reviewer, operation_id, model_requested,
               model_returned, reasoning_effort, prompt_version,
               case_fingerprint, generated_at, submitted_at, audit_json,
               record_version, supersedes_audit_id, superseded_by_audit_id,
               record_state, deleted_from_state, deleted_at, deleted_by,
               delete_reason, delete_operation_id, restored_at, restored_by,
               restore_operation_id
        FROM five_step_audit_records WHERE audit_id = ?
        """,
        (audit_id,),
    ).fetchone()


def save_revision(database_path: Path, payload: dict[str, Any]) -> dict[str, Any]:
    required = ("source_audit_id", "case_id", "reviewer", "operation_id", "case_fingerprint", "reviewed_steps", "overall_decision")
    missing = [field for field in required if not str(payload.get(field) or "").strip()]
    if missing:
        raise ValueError(f"required_fields_missing:{','.join(missing)}")
    validate_reviewed_steps(payload["reviewed_steps"])
    validate_overall_decision(payload["overall_decision"])
    case_id = str(payload["case_id"]).strip()
    source_audit_id = str(payload["source_audit_id"]).strip()
    operation_id = str(payload["operation_id"]).strip()
    case_fingerprint = str(payload["case_fingerprint"]).strip()
    if len(case_fingerprint) != 64:
        raise ValueError("case_fingerprint_invalid")

    connection = connect_database(database_path)
    try:
        connection.execute("BEGIN IMMEDIATE")
        ensure_audit_table(connection)
        existing = _operation_record(connection, operation_id)
        if existing is not None:
            if existing["case_id"] != case_id:
                raise ValueError("operation_id_already_used_for_other_case")
            connection.commit()
            result = public_record(existing)
            result["idempotent"] = True
            return result
        source = _record_row(connection, source_audit_id)
        if source is None:
            raise ValueError(f"audit_record_not_found:{source_audit_id}")
        if source["case_id"] != case_id:
            raise ValueError("audit_record_case_mismatch")
        if source["record_state"] != "active":
            raise ValueError(f"audit_record_not_active:{source['record_state']}")
        if source["case_fingerprint"] != case_fingerprint:
            raise ValueError("audit_record_case_fingerprint_mismatch")
        audit_json = json.loads(source["audit_json"])
        audit_json["reviewed_steps"] = payload["reviewed_steps"]
        audit_json["overall_decision"] = payload["overall_decision"]
        audit_json["overall_note"] = str(payload.get("overall_note") or "")
        audit_json["revision_of"] = source_audit_id
        audit_json["edited_by"] = str(payload["reviewer"]).strip()
        audit_json["edited_at"] = now_utc()
        audit_id = f"audit:{uuid.uuid4().hex}"
        submitted_at = now_utc()
        connection.execute(
            """
            INSERT INTO five_step_audit_records(
                audit_id, case_id, reviewer, operation_id, model_requested,
                model_returned, reasoning_effort, prompt_version,
                case_fingerprint, generated_at, submitted_at, audit_json,
                record_version, supersedes_audit_id, record_state
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'active')
            """,
            (
                audit_id,
                case_id,
                str(payload["reviewer"]).strip(),
                operation_id,
                source["model_requested"],
                source["model_returned"],
                source["reasoning_effort"],
                source["prompt_version"],
                source["case_fingerprint"],
                source["generated_at"],
                submitted_at,
                json.dumps(audit_json, ensure_ascii=False, sort_keys=True),
                int(source["record_version"] or 1) + 1,
                source_audit_id,
            ),
        )
        connection.execute(
            """
            UPDATE five_step_audit_records
            SET record_state = 'superseded', superseded_by_audit_id = ?
            WHERE audit_id = ?
            """,
            (audit_id, source_audit_id),
        )
        row = _record_row(connection, audit_id)
        connection.commit()
        return public_record(row)
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def delete_record(database_path: Path, payload: dict[str, Any]) -> dict[str, Any]:
    audit_id = str(payload.get("audit_id") or "").strip()
    deleted_by = str(payload.get("deleted_by") or "").strip()
    operation_id = str(payload.get("operation_id") or "").strip()
    if not audit_id or not deleted_by or not operation_id:
        raise ValueError("audit_id_deleted_by_operation_id_required")
    connection = connect_database(database_path)
    try:
        connection.execute("BEGIN IMMEDIATE")
        ensure_audit_table(connection)
        existing_operation = _operation_record(connection, operation_id)
        if existing_operation is not None:
            if existing_operation["audit_id"] != audit_id:
                raise ValueError("operation_id_already_used_for_other_audit_record")
            connection.commit()
            result = public_record(existing_operation)
            result["idempotent"] = True
            return result
        row = _record_row(connection, audit_id)
        if row is None:
            raise ValueError(f"audit_record_not_found:{audit_id}")
        if row["record_state"] == "deleted":
            raise ValueError("audit_record_already_deleted")
        deleted_at = now_utc()
        connection.execute(
            """
            UPDATE five_step_audit_records
            SET record_state = 'deleted', deleted_from_state = ?, deleted_at = ?,
                deleted_by = ?, delete_reason = ?, delete_operation_id = ?
            WHERE audit_id = ?
            """,
            (
                row["record_state"] if row["record_state"] in {"active", "superseded"} else "active",
                deleted_at,
                deleted_by,
                str(payload.get("delete_reason") or ""),
                operation_id,
                audit_id,
            ),
        )
        row = _record_row(connection, audit_id)
        connection.commit()
        return public_record(row)
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def restore_record(database_path: Path, payload: dict[str, Any]) -> dict[str, Any]:
    audit_id = str(payload.get("audit_id") or "").strip()
    restored_by = str(payload.get("restored_by") or "").strip()
    operation_id = str(payload.get("operation_id") or "").strip()
    if not audit_id or not restored_by or not operation_id:
        raise ValueError("audit_id_restored_by_operation_id_required")
    connection = connect_database(database_path)
    try:
        connection.execute("BEGIN IMMEDIATE")
        ensure_audit_table(connection)
        existing_operation = _operation_record(connection, operation_id)
        if existing_operation is not None:
            if existing_operation["audit_id"] != audit_id:
                raise ValueError("operation_id_already_used_for_other_audit_record")
            connection.commit()
            result = public_record(existing_operation)
            result["idempotent"] = True
            return result
        row = _record_row(connection, audit_id)
        if row is None:
            raise ValueError(f"audit_record_not_found:{audit_id}")
        if row["record_state"] != "deleted":
            raise ValueError("audit_record_is_not_deleted")
        restored_at = now_utc()
        connection.execute(
            """
            UPDATE five_step_audit_records
            SET record_state = COALESCE(NULLIF(deleted_from_state, ''), 'active'),
                restored_at = ?, restored_by = ?, restore_operation_id = ?
            WHERE audit_id = ?
            """,
            (restored_at, restored_by, operation_id, audit_id),
        )
        row = _record_row(connection, audit_id)
        connection.commit()
        return public_record(row)
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("list", "get", "save", "revision", "delete", "restore"))
    parser.add_argument("--db", type=Path, default=DEFAULT_DATABASE)
    parser.add_argument("--case-id", default="")
    parser.add_argument("--audit-id", default="")
    parser.add_argument("--payload-base64", default="")
    args = parser.parse_args()
    try:
        if args.command == "list":
            result = list_records(args.db.resolve(), args.case_id)
        elif args.command == "get":
            result = get_record(args.db.resolve(), args.audit_id)
        else:
            payload = parse_payload(args.payload_base64)
            if args.command == "save":
                result = save_record(args.db.resolve(), payload)
            elif args.command == "revision":
                result = save_revision(args.db.resolve(), payload)
            elif args.command == "delete":
                result = delete_record(args.db.resolve(), payload)
            else:
                result = restore_record(args.db.resolve(), payload)
        print(json.dumps(result, ensure_ascii=False))
        return 0
    except Exception as error:
        print(json.dumps({"ok": False, "message": str(error)}, ensure_ascii=False))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
