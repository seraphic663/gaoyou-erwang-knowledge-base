"""Replace the legacy annotation library from the case-level V2 JSONL.

Default mode is read-only. ``--replace`` creates a SQLite backup and replaces
all annotation documents/cases/terms/evidence/process steps in one transaction.
All imported cases remain 草稿/待核; JSONL raw records and Markdown provenance
are retained in ``raw_case_json`` and the child ``raw_*_json`` fields.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import sqlite3
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[3]
DEFAULT_JSONL = (
    ROOT
    / "v2"
    / "data"
    / "real_runs"
    / "manual_annotation_ingress"
    / "manual_annotation_cases.annotation_case.v1.candidates.jsonl"
)
DEFAULT_DB = ROOT / "solution/legacy-db" / "data" / "annotations.db"
SNAPSHOT = ROOT / "solution/website" / "data" / "annotation-snapshot.json"
PROCESS_FIELDS = (
    ("problem_discovery", "发疑"),
    ("research_question", "立论"),
    ("evidence_collection", "取证"),
    ("reasoning", "释理"),
    ("conclusion", "结论"),
)
COMMENT_RE = re.compile(r"(?m)^###\s*批注\s*\d+")


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            value = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(f"invalid_jsonl_line:{number}:{exc}") from exc
        if not isinstance(value, dict):
            raise ValueError(f"jsonl_record_not_object:{number}")
        records.append(value)
    return records


def _validate_sources(records: list[dict[str, Any]]) -> dict[str, Path]:
    seen: set[str] = set()
    documents: dict[str, Path] = {}
    for record in records:
        case_id = record.get("case_id")
        if not isinstance(case_id, str) or not case_id.startswith("manual_md:"):
            raise ValueError(f"unexpected_case_id:{case_id!r}")
        if case_id in seen:
            raise ValueError(f"duplicate_case_id:{case_id}")
        seen.add(case_id)
        migration = record.get("_migration") or {}
        if migration.get("source_layer") != "manual_annotation_markdown":
            raise ValueError(f"unexpected_source_layer:{case_id}")
        if record.get("machine_result", {}).get("status") != "draft":
            raise ValueError(f"not_a_machine_draft:{case_id}")
        if record.get("human_review", {}).get("status") != "pending":
            raise ValueError(f"not_human_pending:{case_id}")
        if record.get("reviewed_by") is not None:
            raise ValueError(f"unexpected_reviewer:{case_id}")

        source_path = ROOT / str(migration.get("source_file") or "")
        if not source_path.is_file():
            raise FileNotFoundError(f"case_markdown_missing:{case_id}:{source_path}")
        if _sha256(source_path.read_bytes()) != migration.get("source_sha256"):
            raise ValueError(f"case_markdown_hash_mismatch:{case_id}")

        archive_relative = str(migration.get("archive_markdown_file") or "")
        archive_path = ROOT / archive_relative
        if not archive_path.is_file():
            raise FileNotFoundError(f"archive_markdown_missing:{case_id}:{archive_path}")
        archive_hash = migration.get("archive_markdown_sha256")
        if not archive_hash or _sha256(archive_path.read_bytes()) != archive_hash:
            raise ValueError(f"archive_markdown_hash_mismatch:{case_id}")
        documents[archive_relative] = archive_path

        for evidence in record.get("evidences", []):
            if not evidence.get("quote"):
                raise ValueError(f"empty_evidence_quote:{case_id}")
            if evidence.get("quote_check") != "unchecked":
                raise ValueError(f"unexpected_quote_check:{case_id}")
    if not records:
        raise ValueError("jsonl_has_no_cases")
    return documents


def _paragraph_count(text: str) -> int:
    return sum(bool(part.strip()) for part in re.split(r"\n\s*\n", text))


def _method_tags(record: dict[str, Any]) -> list[str]:
    tags: list[str] = []
    for relation in record.get("term_relations", []):
        label = str(relation.get("relation_type") or "").strip()
        if label and label != "未定" and label not in tags:
            tags.append(label)
    return tags


def _legacy_case_title(record: dict[str, Any]) -> str:
    stable_id = str(record["case_id"]).split(":", 1)[1]
    title = str(record.get("case_title") or stable_id)
    return f"{stable_id} · {title}"


def _target_work_for_display(record: dict[str, Any]) -> str:
    target_work = str(record.get("target_work") or "").strip()
    if target_work:
        return target_work
    return str((record.get("target_scope") or {}).get("raw_label") or "").strip()


def _evidence_work(evidence: dict[str, Any]) -> str:
    direct = str(evidence.get("source_work") or "").strip()
    if direct:
        return direct
    titles = list(dict.fromkeys(re.findall(r"《([^》]+)》", str(evidence.get("citation_context") or ""))))
    return "、".join(titles)


def _new_counts(records: list[dict[str, Any]], documents: dict[str, Path]) -> dict[str, int]:
    return {
        "documents": len(documents),
        "cases": len(records),
        "terms": sum(len(record.get("term_relations", [])) for record in records),
        "evidences": sum(len(record.get("evidences", [])) for record in records),
        "processSteps": sum(
            bool(record.get(field)) for record in records for field, _label in PROCESS_FIELDS
        ),
        "word_comments": sum(
            int((record.get("_migration") or {}).get("word_comments_count") or 0)
            for record in records
        ),
    }


def _old_counts(connection: sqlite3.Connection) -> dict[str, int]:
    return {
        "documents": int(connection.execute("SELECT COUNT(*) FROM source_documents").fetchone()[0]),
        "cases": int(connection.execute("SELECT COUNT(*) FROM annotation_cases").fetchone()[0]),
        "terms": int(connection.execute("SELECT COUNT(*) FROM annotation_terms").fetchone()[0]),
        "evidences": int(connection.execute("SELECT COUNT(*) FROM annotation_evidences").fetchone()[0]),
        "processSteps": int(connection.execute("SELECT COUNT(*) FROM annotation_process_steps").fetchone()[0]),
    }


def _backup(database_path: Path, snapshot_path: Path, backup_dir: Path) -> dict[str, str | None]:
    backup_dir.mkdir(parents=True, exist_ok=False)
    backup_db = backup_dir / "annotations.db.before_jsonl_replace.sqlite"
    source = sqlite3.connect(database_path)
    target = sqlite3.connect(backup_db)
    try:
        source.backup(target)
    finally:
        target.close()
        source.close()
    backup_snapshot: Path | None = None
    if snapshot_path.is_file():
        backup_snapshot = backup_dir / "annotation-snapshot.json.before_jsonl_replace"
        shutil.copy2(snapshot_path, backup_snapshot)
    return {
        "database_backup": str(backup_db),
        "database_backup_sha256": _sha256(backup_db.read_bytes()),
        "snapshot_backup": str(backup_snapshot) if backup_snapshot else None,
    }


def replace_database(database_path: Path, records: list[dict[str, Any]], document_paths: dict[str, Path], jsonl_path: Path, backup_dir: Path) -> dict[str, Any]:
    _backup(database_path, SNAPSHOT, backup_dir)
    jsonl_hash = _sha256(jsonl_path.read_bytes())
    now = datetime.now(timezone.utc).isoformat()
    connection = sqlite3.connect(database_path, timeout=30)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute("PRAGMA busy_timeout = 30000")
    try:
        connection.execute("BEGIN IMMEDIATE")
        for table in (
            "annotation_process_steps",
            "annotation_evidences",
            "annotation_terms",
            "annotation_cases",
            "source_documents",
        ):
            connection.execute(f"DELETE FROM {table}")

        document_ids: dict[str, int] = {}
        comment_totals: dict[str, int] = defaultdict(int)
        for record in records:
            key = str(record["_migration"]["archive_markdown_file"])
            comment_totals[key] += int(record["_migration"].get("word_comments_count") or 0)

        for archive_relative, archive_path in sorted(document_paths.items()):
            text = archive_path.read_text(encoding="utf-8-sig")
            comment_count = len(COMMENT_RE.findall(text))
            child_comment_count = comment_totals.get(archive_relative, 0)
            anchored_count = comment_count if child_comment_count == comment_count else 0
            cursor = connection.execute(
                """INSERT INTO source_documents(
                    source_file_name, source_file_path, full_json_file, ai_json_file,
                    doc_type, paragraph_count, comment_count, anchored_comment_count,
                    source_docx_sha256, paragraph_text_sha256, comment_text_sha256
                ) VALUES (?, ?, NULL, NULL, ?, ?, ?, ?, NULL, NULL, NULL)""",
                (
                    archive_path.name,
                    archive_relative,
                    "markdown_manual_annotation",
                    _paragraph_count(text),
                    comment_count,
                    anchored_count,
                ),
            )
            document_ids[archive_relative] = int(cursor.lastrowid)

        case_id_to_db_id: dict[str, int] = {}
        for record in records:
            migration = record["_migration"]
            archive_relative = str(migration["archive_markdown_file"])
            target_scope = record.get("target_scope") or {}
            problem = record.get("problem_discovery") or record.get("research_question")
            claim = (record.get("method_profile") or {}).get("claim_text")
            cursor = connection.execute(
                """INSERT INTO annotation_cases(
                    source_document_id, case_title, source_work, target_work, target_text,
                    problem, claim, method_tags_json, conclusion, certainty, status, raw_case_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, '待核', '草稿', ?)""",
                (
                    document_ids[archive_relative],
                    _legacy_case_title(record),
                    record.get("source_work") or "",
                    _target_work_for_display(record),
                    record.get("target_text") or "",
                    problem,
                    claim,
                    _json(_method_tags(record)),
                    record.get("conclusion") or "",
                    _json(
                        {
                            "manual_case_key": record["case_id"],
                            "source_jsonl": jsonl_path.relative_to(ROOT).as_posix(),
                            "source_jsonl_sha256": jsonl_hash,
                            "source_markdown_sha256": migration.get("source_sha256"),
                            "archive_markdown_sha256": migration.get("archive_markdown_sha256"),
                            "legacy_projection": {
                                "certainty": "待核",
                                "status": "草稿",
                                "target_work_raw_label": target_scope.get("raw_label"),
                                "target_scope_status": target_scope.get("status"),
                                "evidence_quotes_unverified": True,
                            },
                            "annotation_case_v1": record,
                        }
                    ),
                ),
            )
            database_case_id = int(cursor.lastrowid)
            case_id_to_db_id[str(record["case_id"])] = database_case_id

            for index, term in enumerate(record.get("term_relations", [])):
                connection.execute(
                    """INSERT INTO annotation_terms(
                        case_id, term, term_type, relation_type, related_term, note,
                        source_paragraph_indexes_json, source_comment_ids_json, raw_term_json
                    ) VALUES (?, ?, '字词', ?, ?, ?, '[]', '[]', ?)""",
                    (
                        database_case_id,
                        str(term.get("source_term") or ""),
                        term.get("relation_type"),
                        str(term.get("target_term") or ""),
                        term.get("relation_note") or term.get("relation_subtype") or "",
                        _json({"manual_case_key": record["case_id"], "term_index": index, "v2_term_relation": term}),
                    ),
                )

            for index, evidence in enumerate(record.get("evidences", [])):
                connection.execute(
                    """INSERT INTO annotation_evidences(
                        case_id, evidence_type, work, quote, role, term,
                        source_paragraph_indexes_json, source_comment_ids_json, raw_evidence_json
                    ) VALUES (?, '书证', ?, ?, ?, '', '[]', '[]', ?)""",
                    (
                        database_case_id,
                        _evidence_work(evidence),
                        str(evidence.get("quote") or ""),
                        str(evidence.get("evidence_role") or ""),
                        _json(
                            {
                                "manual_case_key": record["case_id"],
                                "evidence_index": index,
                                "v2_evidence": evidence,
                                "quote_check": "unchecked",
                                "source_resolution": evidence.get("source_resolution"),
                            }
                        ),
                    ),
                )

            for step_order, (field_name, step_type) in enumerate(PROCESS_FIELDS, 1):
                text = record.get(field_name)
                if not text:
                    continue
                connection.execute(
                    """INSERT INTO annotation_process_steps(
                        case_id, step_order, step_type, text,
                        source_paragraph_indexes_json, source_comment_ids_json, raw_step_json
                    ) VALUES (?, ?, ?, ?, '[]', '[]', ?)""",
                    (
                        database_case_id,
                        step_order,
                        step_type,
                        str(text),
                        _json(
                            {
                                "manual_case_key": record["case_id"],
                                "field_name": field_name,
                                "text": text,
                                "source_spans": migration.get("source_section_spans", {}).get(field_name, []),
                            }
                        ),
                    ),
                )

        meta_values = {
            "manual_import_source": "v2/data/real_runs/manual_annotation_ingress/manual_annotation_cases.annotation_case.v1.candidates.jsonl",
            "manual_import_source_sha256": jsonl_hash,
            "manual_import_source_case_count": str(len(records)),
            "manual_imported_at_utc": now,
            "manual_import_status_mapping": "machine draft + human pending -> 草稿/待核",
        }
        connection.executemany(
            "INSERT INTO meta(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            list(meta_values.items()),
        )
        counts = _old_counts(connection)
        foreign_keys = connection.execute("PRAGMA foreign_key_check").fetchall()
        expected = _new_counts(records, document_paths)
        if foreign_keys:
            raise RuntimeError(f"foreign_key_check_failed:{len(foreign_keys)}")
        for key in ("documents", "cases", "terms", "evidences", "processSteps"):
            if counts[key] != expected[key]:
                raise RuntimeError(f"post_replace_count_mismatch:{key}:{counts[key]}!={expected[key]}")
        connection.commit()
    except Exception:
        connection.rollback()
        connection.close()
        raise
    connection.close()

    check = sqlite3.connect(f"file:{database_path.as_posix()}?mode=ro", uri=True)
    try:
        integrity = check.execute("PRAGMA integrity_check").fetchone()[0]
        if integrity != "ok":
            raise RuntimeError(f"integrity_check_failed:{integrity}")
    finally:
        check.close()
    return {
        "database": str(database_path),
        "jsonl_sha256": jsonl_hash,
        "case_id_to_database_id": case_id_to_db_id,
        "counts": counts,
        "integrity_check": integrity,
        "foreign_key_violation_count": 0,
        "imported_at_utc": now,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--jsonl", type=Path, default=DEFAULT_JSONL)
    parser.add_argument("--database", type=Path, default=DEFAULT_DB)
    parser.add_argument("--backup-dir", type=Path)
    parser.add_argument("--replace", action="store_true", help="Back up and replace all legacy annotation content tables.")
    args = parser.parse_args()
    jsonl_path = args.jsonl.resolve()
    database_path = args.database.resolve()
    records = _read_jsonl(jsonl_path)
    documents = _validate_sources(records)
    proposed = _new_counts(records, documents)
    connection = sqlite3.connect(f"file:{database_path.as_posix()}?mode=ro", uri=True)
    try:
        before = _old_counts(connection)
    finally:
        connection.close()
    if not args.replace:
        print(json.dumps({"mode": "dry_run", "database": str(database_path), "before": before, "would_replace_with": proposed}, ensure_ascii=False, indent=2))
        return 0

    backup_dir = args.backup_dir
    if backup_dir is None:
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        backup_dir = ROOT / "tmp" / f"manual-annotation-overwrite-{stamp}"
    result = replace_database(database_path, records, documents, jsonl_path, backup_dir.resolve())
    result["before"] = before
    result["backup_directory"] = str(backup_dir.resolve())
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
