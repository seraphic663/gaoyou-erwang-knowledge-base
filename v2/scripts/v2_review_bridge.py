#!/usr/bin/env python3
"""Read review-task batches and apply explicit human decisions.

Read commands consume the persisted review_task.v1 artifacts.  The submit
command is the only write path exposed to the local review UI and delegates to
the transaction seams in ``erwang_v2.database``.  This bridge never infers a
decision, never treats a task view as a decision, and never promotes a case
from a target/source/passage resolution alone.
"""

from __future__ import annotations

import argparse
import base64
import binascii
import json
import sqlite3
import sys
from pathlib import Path
from typing import Any


V2_ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = V2_ROOT.parent
SRC_ROOT = V2_ROOT / "src"
DEFAULT_DATABASE = V2_ROOT / "data/real_runs/annotation_v2.db"
DEFAULT_MANIFEST = V2_ROOT / "data/real_runs/review_tasks/review_task_manifest.review.v1.json"
STREAMS = (
    "case_review",
    "target_work_resolution",
    "external_source_resolution",
    "external_passage_resolution",
)

# The local Node service launches this file from ``03-项目网站``.  Keep the
# bridge self-contained so the write command can import the existing database
# writer seam without requiring the caller to preconfigure PYTHONPATH.
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))


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


def load_manifest(manifest_path: Path) -> dict[str, Any]:
    if not manifest_path.is_file():
        raise FileNotFoundError(f"review_task_manifest_not_found:{manifest_path}")
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise ValueError(f"review_task_manifest_invalid:{type(error).__name__}") from error
    if not isinstance(manifest, dict):
        raise ValueError("review_task_manifest_must_be_object")
    if tuple(manifest.get("streams") or ()) != STREAMS:
        raise ValueError("review_task_manifest_streams_invalid")
    return manifest


def stream_path(manifest_path: Path, manifest: dict[str, Any], stream: str) -> Path:
    if stream not in STREAMS:
        raise ValueError(f"review_task_stream_invalid:{stream}")
    relative_output = ((manifest.get("outputs") or {}).get(stream) or {}).get("path")
    if not relative_output:
        raise ValueError(f"review_task_stream_output_missing:{stream}")
    path = (manifest_path.parent / str(relative_output)).resolve()
    output_root = manifest_path.parent.resolve()
    if path != output_root and output_root not in path.parents:
        raise ValueError("review_task_output_path_outside_manifest_directory")
    if not path.is_file():
        raise FileNotFoundError(f"review_task_stream_file_not_found:{path}")
    return path


def read_stream(manifest_path: Path, manifest: dict[str, Any], stream: str) -> list[dict[str, Any]]:
    path = stream_path(manifest_path, manifest, stream)
    tasks: list[dict[str, Any]] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        try:
            value = json.loads(line)
        except ValueError as error:
            raise ValueError(f"review_task_json_invalid:{stream}:{line_number}") from error
        if not isinstance(value, dict) or not value.get("task_id"):
            raise ValueError(f"review_task_row_invalid:{stream}:{line_number}")
        tasks.append(value)
    return tasks


def task_batches(manifest_path: Path, manifest: dict[str, Any], stream: str) -> list[dict[str, Any]]:
    return list(((manifest.get("outputs") or {}).get(stream) or {}).get("batches") or [])


def read_tasks(
    *,
    manifest_path: Path = DEFAULT_MANIFEST,
    stream: str = "case_review",
    batch_number: int | None = None,
) -> dict[str, Any]:
    manifest_path = Path(manifest_path).resolve()
    manifest = load_manifest(manifest_path)
    tasks = read_stream(manifest_path, manifest, stream)
    batches = task_batches(manifest_path, manifest, stream)
    if batch_number is None:
        batch_number = 1 if batches else 0
    if batch_number < 1 or batch_number > len(batches):
        raise ValueError(f"review_task_batch_invalid:{stream}:{batch_number}")
    selected = [task for task in tasks if int(task.get("batch_number") or 0) == batch_number]
    batch = batches[batch_number - 1]
    return {
        "ok": True,
        "manifest": relative_path(manifest_path),
        "generated_at": manifest.get("generated_at"),
        "stream": stream,
        "batch_number": batch_number,
        "batch_count": len(batches),
        "batch": batch,
        "batch_size_limit": manifest.get("batch_size"),
        "task_count": len(selected),
        "total_task_count": len(tasks),
        "tasks": selected,
        "policy": manifest.get("policy") or {},
    }


def find_task(
    *,
    manifest_path: Path = DEFAULT_MANIFEST,
    task_id: str,
    stream: str | None = None,
) -> dict[str, Any]:
    if not str(task_id or "").strip():
        raise ValueError("review_task_id_required")
    manifest_path = Path(manifest_path).resolve()
    manifest = load_manifest(manifest_path)
    streams = (stream,) if stream else STREAMS
    for stream_name in streams:
        if stream_name not in STREAMS:
            raise ValueError(f"review_task_stream_invalid:{stream_name}")
        tasks = read_stream(manifest_path, manifest, stream_name)
        for task in tasks:
            if str(task.get("task_id")) == str(task_id):
                return {
                    "ok": True,
                    "manifest": relative_path(manifest_path),
                    "generated_at": manifest.get("generated_at"),
                    "stream": stream_name,
                    "task": task,
                    "policy": manifest.get("policy") or {},
                }
    raise ValueError(f"review_task_not_found:{task_id}")


def open_writable_database(database_path: Path) -> sqlite3.Connection:
    if not database_path.is_file():
        raise FileNotFoundError(f"v2_database_not_found:{database_path}")
    connection = sqlite3.connect(database_path, timeout=60)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute("PRAGMA busy_timeout = 60000")
    return connection


def _require_payload_object(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise ValueError("review_submission_payload_must_be_object")
    return payload


def _validate_submission_task(
    connection: sqlite3.Connection,
    *,
    manifest_path: Path | None,
    payload: dict[str, Any],
    task_type: str,
) -> dict[str, Any] | None:
    """Bind a write request to the current task snapshot and pending state.

    Direct library tests may omit a manifest and exercise the database seam
    alone.  The CLI/API path always supplies the persisted manifest, so an
    HTTP request cannot invent a queue item or submit a stale task silently.
    """

    task_id = str(payload.get("task_id") or "").strip()
    if not task_id:
        raise ValueError("review_task_id_required")
    if manifest_path is None:
        return None
    task_result = find_task(
        manifest_path=manifest_path,
        task_id=task_id,
        stream=task_type,
    )
    task = task_result["task"]
    if str(task.get("task_type") or "") != task_type:
        raise ValueError("review_task_type_task_id_mismatch")

    if task_type == "case_review":
        case_id = str(payload.get("case_id") or "").strip()
        if case_id != str(task.get("case_id") or ""):
            raise ValueError("case_review_task_case_mismatch")
        row = connection.execute(
            "SELECT human_status FROM annotation_cases WHERE case_id = ?",
            (case_id,),
        ).fetchone()
        if row is None:
            raise ValueError(f"case_not_found:{case_id}")
        existing = connection.execute(
            "SELECT case_id FROM review_events WHERE operation_id = ?",
            (str(payload.get("operation_id") or "").strip(),),
        ).fetchone()
        if existing is not None:
            if existing["case_id"] != case_id:
                raise ValueError("operation_id_already_used_for_other_case")
            return task
        if row["human_status"] not in {"pending", "uncertain"}:
            raise ValueError(f"review_task_stale:{task_id}:{row['human_status']}")
    else:
        queue_item_id = str(payload.get("queue_item_id") or "").strip()
        if queue_item_id != str(task.get("queue_item_id") or ""):
            raise ValueError("review_task_queue_item_mismatch")
        table = {
            "target_work_resolution": "target_work_resolution_queue",
            "external_source_resolution": "external_source_resolution_queue",
            "external_passage_resolution": "external_passage_resolution_queue",
        }[task_type]
        row = connection.execute(
            f"SELECT queue_status FROM {table} WHERE queue_item_id = ?",
            (queue_item_id,),
        ).fetchone()
        if row is None:
            raise ValueError(f"review_queue_item_not_found:{queue_item_id}")
        if task_type == "target_work_resolution":
            existing = connection.execute(
                "SELECT case_id FROM review_events WHERE operation_id = ?",
                (str(payload.get("operation_id") or "").strip(),),
            ).fetchone()
            if existing is not None:
                if existing["case_id"] != task.get("case_id"):
                    raise ValueError("operation_id_already_used_for_other_case")
                return task
        else:
            existing = connection.execute(
                "SELECT queue_item_id FROM resolution_events WHERE operation_id = ?",
                (str(payload.get("operation_id") or "").strip(),),
            ).fetchone()
            if existing is not None:
                if existing["queue_item_id"] != queue_item_id:
                    raise ValueError("operation_id_already_used_for_other_resolution")
                return task
        allowed = {
            "target_work_resolution": {"pending", "needs_context", "uncertain"},
            "external_source_resolution": {"pending", "candidate_available", "no_public_match"},
            "external_passage_resolution": {"pending", "candidate_available", "no_public_match"},
        }[task_type]
        if row["queue_status"] not in allowed:
            raise ValueError(f"review_task_stale:{task_id}:{row['queue_status']}")
    return task


def submit_payload(
    database_path: Path,
    payload: dict[str, Any],
    *,
    manifest_path: Path | None = DEFAULT_MANIFEST,
) -> dict[str, Any]:
    """Apply exactly one explicit task decision through the database seam."""

    payload = _require_payload_object(payload)
    task_type = str(payload.get("task_type") or "").strip()
    reviewer = str(payload.get("reviewer") or "").strip()
    operation_id = str(payload.get("operation_id") or "").strip()
    if not task_type:
        raise ValueError("review_task_type_required")
    if task_type not in STREAMS:
        raise ValueError(f"review_task_type_invalid:{task_type}")
    if not str(payload.get("task_id") or "").strip():
        raise ValueError("review_task_id_required")
    if not reviewer:
        raise ValueError("reviewer_required_for_decision")
    if not operation_id:
        raise ValueError("operation_id_required")

    connection = open_writable_database(Path(database_path).resolve())
    try:
        _validate_submission_task(
            connection,
            manifest_path=Path(manifest_path).resolve() if manifest_path is not None else None,
            payload=payload,
            task_type=task_type,
        )

        # Import the actual writer only in the write command.  The read
        # commands never import it and therefore remain independent of DB
        # write state.
        from erwang_v2.database import (
            apply_case_review_submission,
            apply_external_passage_resolution,
            apply_external_source_resolution,
            apply_target_work_resolution,
        )

        if task_type == "case_review":
            case_id = str(payload.get("case_id") or "").strip()
            if not case_id or payload.get("task_id") != f"case-review:{case_id}":
                raise ValueError("case_review_task_id_mismatch")
            review = payload.get("review") or {}
            case_patch = payload.get("case_patch") or {}
            if not isinstance(review, dict) or not isinstance(case_patch, dict):
                raise ValueError("case_review_payload_objects_required")
            result = apply_case_review_submission(
                connection,
                case_id,
                reviewer=reviewer,
                review_status=str(payload.get("review_status") or "").strip(),
                operation_id=operation_id,
                review_note=str(payload.get("review_note") or ""),
                case_patch=case_patch,
                review=review,
            )
        elif task_type == "target_work_resolution":
            queue_item_id = str(payload.get("queue_item_id") or payload.get("task_id") or "").strip()
            result = apply_target_work_resolution(
                connection,
                queue_item_id,
                reviewer=reviewer,
                operation_id=operation_id,
                target_work=payload.get("target_work"),
                target_passage_id=payload.get("target_passage_id"),
                target_scope=payload.get("target_scope") or {},
                resolution_status=str(payload.get("resolution_status") or "").strip(),
                review_note=str(payload.get("review_note") or ""),
            )
        elif task_type == "external_source_resolution":
            queue_item_id = str(payload.get("queue_item_id") or payload.get("task_id") or "").strip()
            result = apply_external_source_resolution(
                connection,
                queue_item_id,
                reviewer=reviewer,
                operation_id=operation_id,
                resolution_status=str(payload.get("resolution_status") or "").strip(),
                source_file=payload.get("source_file"),
                edition=payload.get("edition"),
                location_note=payload.get("location_note"),
                resolution_note=str(payload.get("review_note") or ""),
            )
        else:
            queue_item_id = str(payload.get("queue_item_id") or payload.get("task_id") or "").strip()
            result = apply_external_passage_resolution(
                connection,
                queue_item_id,
                reviewer=reviewer,
                operation_id=operation_id,
                resolution_status=str(payload.get("resolution_status") or "").strip(),
                selected_passage_id=payload.get("selected_passage_id"),
                resolution_note=str(payload.get("review_note") or ""),
            )
        return {"ok": True, "task_type": task_type, "result": result}
    finally:
        connection.close()


def decode_payload(value: str) -> dict[str, Any]:
    try:
        decoded = base64.b64decode(value.encode("ascii"), validate=True).decode("utf-8")
        payload = json.loads(decoded)
    except (ValueError, UnicodeError, binascii.Error, json.JSONDecodeError) as error:
        raise ValueError("review_submission_payload_invalid") from error
    return _require_payload_object(payload)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("tasks", "task", "submit"))
    parser.add_argument("--db", type=Path, default=DEFAULT_DATABASE)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--stream", default="case_review")
    parser.add_argument("--batch", type=int)
    parser.add_argument("--task-id", default="")
    parser.add_argument("--payload-base64", default="")
    args = parser.parse_args()
    try:
        if args.command == "tasks":
            result = read_tasks(
                manifest_path=args.manifest,
                stream=args.stream,
                batch_number=args.batch,
            )
        elif args.command == "task":
            result = find_task(manifest_path=args.manifest, task_id=args.task_id)
        else:
            if not args.payload_base64:
                raise ValueError("review_submission_payload_required")
            result = submit_payload(
                args.db,
                decode_payload(args.payload_base64),
                manifest_path=args.manifest,
            )
        print(json.dumps(result, ensure_ascii=False))
        return 0
    except ValueError as error:
        print(json.dumps({"ok": False, "error_type": "validation", "message": str(error)}, ensure_ascii=False))
        return 0
    except Exception as error:
        print(json.dumps({"ok": False, "error_type": "internal", "message": str(error)}, ensure_ascii=False))
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
