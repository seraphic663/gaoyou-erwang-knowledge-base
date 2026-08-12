#!/usr/bin/env python3
"""Inventory external citation sources without claiming canonical validation.

The project currently contains Wang's four core Markdown sources, project
notes, and first-level reference material, but not a separately registered
canonical edition for each cited external work. This script records that
boundary explicitly, searches local text for reproducible context hits, and
leaves external_source_registry.status as pending unless a real canonical
source file is present and registered by a separate ingest step.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
import unicodedata
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


V2_ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = V2_ROOT.parent
DEFAULT_DATABASE = V2_ROOT / "data/real_runs/annotation_v2.db"
DEFAULT_REPORT = V2_ROOT / "data/real_runs/external_source_inventory.json"

TEXT_ROOTS = (
    PROJECT_ROOT / "04-项目文献/A-原著原典",
    PROJECT_ROOT / "04-项目文献/B-一级资料",
    PROJECT_ROOT / "04-项目文献/0-当前阅读",
    PROJECT_ROOT / "04-项目文献/E-外部原典",
    PROJECT_ROOT / "02-数据库/main",
)
TEXT_SUFFIXES = {".md", ".txt"}


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def parse_json(value: Any, fallback: Any) -> Any:
    if value is None or value == "":
        return fallback
    try:
        return json.loads(value)
    except (TypeError, ValueError):
        return fallback


def compact(value: str) -> str:
    text = unicodedata.normalize("NFKC", str(value or ""))
    return "".join(
        char
        for char in text
        if not unicodedata.category(char).startswith(("P", "Z"))
        and unicodedata.category(char) != "Cf"
    )


def relative(path: Path) -> str:
    try:
        return path.resolve().relative_to(PROJECT_ROOT.resolve()).as_posix()
    except ValueError:
        return path.as_posix()


def file_role(path: Path) -> str:
    relative_path = relative(path)
    if relative_path.startswith("04-项目文献/A-原著原典/"):
        return "wang_core_context"
    if relative_path.startswith("04-项目文献/B-一级资料/"):
        return "first_level_reference_context"
    if relative_path.startswith("04-项目文献/0-当前阅读/"):
        return "project_note_context"
    if relative_path.startswith("04-项目文献/E-外部原典/"):
        return "external_canonical_candidate"
    return "legacy_database_context"


def load_local_texts() -> list[dict[str, Any]]:
    files: list[dict[str, Any]] = []
    for root in TEXT_ROOTS:
        if not root.exists():
            continue
        for path in sorted(root.rglob("*")):
            if not path.is_file() or path.suffix.lower() not in TEXT_SUFFIXES:
                continue
            try:
                text = path.read_text(encoding="utf-8-sig")
            except (OSError, UnicodeError):
                continue
            files.append(
                {
                    "path": path,
                    "relative_path": relative(path),
                    "role": file_role(path),
                    "text": text,
                    "compact_text": compact(text),
                    "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                }
            )
    return files


def name_candidates(cited_work: str, files: list[dict[str, Any]]) -> list[dict[str, str]]:
    """Find filename candidates only; this never promotes a source."""

    normalized = compact(cited_work.strip("《》"))
    if not normalized:
        return []
    # Locations and commentary suffixes are not reliable filenames. Use the
    # longest meaningful prefix before a chapter separator as a conservative
    # filename signal.
    prefix = normalized.split("·", 1)[0].split(".", 1)[0]
    if len(prefix) < 2:
        return []
    candidates = []
    for item in files:
        if item["role"] != "external_canonical_candidate":
            continue
        stem = compact(item["path"].stem)
        if prefix in stem:
            candidates.append(
                {
                    "path": item["relative_path"],
                    "role": item["role"],
                    "sha256": item["sha256"],
                }
            )
    return candidates


def exact_matches(quote: str, files: list[dict[str, Any]]) -> list[dict[str, str]]:
    if not quote:
        return []
    compact_quote = compact(quote)
    matches: list[dict[str, str]] = []
    for item in files:
        exact = quote in item["text"]
        normalized = bool(compact_quote and compact_quote in item["compact_text"])
        if exact or normalized:
            matches.append(
                {
                    "path": item["relative_path"],
                    "role": item["role"],
                    "sha256": item["sha256"],
                    "match_mode": "exact" if exact else "punctuation_normalized",
                }
            )
    return matches


def run(database_path: Path = DEFAULT_DATABASE, report_path: Path = DEFAULT_REPORT) -> dict[str, Any]:
    database_path = Path(database_path).resolve()
    report_path = Path(report_path).resolve()
    files = load_local_texts()
    connection = sqlite3.connect(database_path, timeout=30)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA busy_timeout = 30000")
    connection.execute("PRAGMA foreign_keys = ON")
    rows = connection.execute(
        "SELECT external_source_id, cited_work, normalized_work, status, source_file, source_file_sha256, metadata_json FROM external_source_registry ORDER BY normalized_work"
    ).fetchall()
    evidence_rows = connection.execute(
        "SELECT case_id, evidence_index, quote, evidence_json FROM annotation_evidences ORDER BY case_id, evidence_index"
    ).fetchall()

    generated_at = now()
    source_records: list[dict[str, Any]] = []
    source_status_counts = Counter()
    source_by_id: dict[str, dict[str, Any]] = {}
    for row in rows:
        filename_candidates = name_candidates(row["cited_work"], files)
        metadata = parse_json(row["metadata_json"], {})
        candidate_status = metadata.get("candidate_status")
        if candidate_status == "public_transcription_candidate":
            status = "public_candidate_registered_unverified"
        else:
            status = "pending_no_canonical_file"
            if filename_candidates:
                status = "pending_candidate_file_unverified"
        record = {
            "external_source_id": row["external_source_id"],
            "cited_work": row["cited_work"],
            "normalized_work": row["normalized_work"],
            "registry_status": row["status"],
            "machine_inventory_status": status,
            "canonical_file_candidates": filename_candidates,
            "source_file": row["source_file"],
            "source_file_sha256": row["source_file_sha256"],
            "candidate_status": candidate_status,
        }
        source_records.append(record)
        source_by_id[row["external_source_id"]] = record
        source_status_counts[status] += 1

    evidence_records: list[dict[str, Any]] = []
    evidence_match_counts = Counter()
    for row in evidence_rows:
        evidence = parse_json(row["evidence_json"], {})
        external_source_id = evidence.get("external_source_id")
        matches = exact_matches(row["quote"], files)
        mode_counts = Counter(match["match_mode"] for match in matches)
        evidence_match_counts["with_local_context_match" if matches else "no_local_context_match"] += 1
        if matches:
            evidence_match_counts.update(mode_counts)
        evidence["local_inventory"] = {
            "generated_at": generated_at,
            "match_count": len(matches),
            "match_modes": dict(mode_counts),
            "matches": matches[:20],
            "canonical_external_source_validated": False,
        }
        connection.execute(
            "UPDATE annotation_evidences SET evidence_json = ? WHERE case_id = ? AND evidence_index = ?",
            (json.dumps(evidence, ensure_ascii=False, sort_keys=True), row["case_id"], row["evidence_index"]),
        )
        evidence_records.append(
            {
                "case_id": row["case_id"],
                "evidence_index": row["evidence_index"],
                "external_source_id": external_source_id,
                "quote": row["quote"],
                "local_context_matches": matches[:20],
            }
        )

    for row in rows:
        record = source_by_id[row["external_source_id"]]
        metadata = parse_json(row["metadata_json"], {})
        metadata["machine_inventory"] = {
            "generated_at": generated_at,
            "status": record["machine_inventory_status"],
            "canonical_file_candidates": record["canonical_file_candidates"],
            "note": "Filename/context candidates do not constitute canonical source registration or quote validation.",
        }
        connection.execute(
            "UPDATE external_source_registry SET metadata_json = ?, updated_at = ? WHERE external_source_id = ?",
            (json.dumps(metadata, ensure_ascii=False, sort_keys=True), generated_at, row["external_source_id"]),
        )

    connection.commit()
    connection.close()

    report = {
        "report_version": "v2-external-source-inventory.v1",
        "generated_at": generated_at,
        "scope": "local_machine_inventory_only",
        "database": str(database_path.relative_to(PROJECT_ROOT)),
        "local_text_files_scanned": len(files),
        "local_text_file_roles": dict(Counter(item["role"] for item in files)),
        "summary": {
            "registry_source_count": len(source_records),
            "registry_status_counts": dict(Counter(item["registry_status"] for item in source_records)),
            "machine_inventory_status_counts": dict(source_status_counts),
            "canonical_file_registered_count": sum(
                item["registry_status"] == "verified" for item in source_records
            ),
            "public_candidate_registered_count": sum(
                item["machine_inventory_status"] == "public_candidate_registered_unverified"
                for item in source_records
            ),
            "canonical_filename_candidate_source_count": sum(bool(item["canonical_file_candidates"]) for item in source_records),
            "evidence_count": len(evidence_records),
            "evidence_local_context_match_counts": dict(evidence_match_counts),
            "external_quote_validation_count": 0,
        },
        "sources": source_records,
        "evidence_records": evidence_records,
        "conclusion": "当前本地材料没有足以登记为外部典籍 canonical 底本的独立来源文件；项目材料中的命中仅作为 local context，所有外部引文继续保持 unchecked/pending。",
    }
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return report


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--database", type=Path, default=DEFAULT_DATABASE)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    args = parser.parse_args()
    report = run(args.database, args.report)
    print(json.dumps({"summary": report["summary"], "report": str(args.report)}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
