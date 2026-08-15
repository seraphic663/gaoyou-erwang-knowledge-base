#!/usr/bin/env python3
"""Materialize frozen public-text hits as non-canonical V2 candidate passages.

The public candidate fetcher deliberately stops at a manifest and frozen page
files.  This command makes those files reviewable inside the same database,
while preserving the evidence boundary:

* only entries whose frozen file has an ``offline_match_mode`` of
  ``normalized_contiguous`` are materialized;
* the page is stored as ``external_public_candidate`` with
  ``canonical_status=unknown``;
* annotation evidence is never linked and ``quote_check`` is never changed;
* the external passage queue receives stable candidate passage ids for a
  later human selection decision.

This is idempotent for an unchanged page/revision and keeps a changed page as
another hash-addressed candidate rather than overwriting the old candidate.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
import sys
from collections import Counter
from pathlib import Path
from typing import Any


V2_ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = V2_ROOT.parent
DEFAULT_DATABASE = V2_ROOT / "data/real_runs/annotation_v2.db"
DEFAULT_MANIFEST = V2_ROOT / "data/real_runs/external_public_candidate_manifest.json"
DEFAULT_REPORT = V2_ROOT / "data/real_runs/external_candidate_passage_ingest.v1.json"

sys.path.insert(0, str(V2_ROOT / "src"))
from erwang_v2.database import ingest_passages, open_database  # noqa: E402
sys.path.insert(0, str(V2_ROOT / "scripts"))
from external_text_normalization import compact_for_match, strip_wikitext  # noqa: E402


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def parse_json(value: Any, fallback: Any) -> Any:
    if isinstance(value, (dict, list)):
        return value
    try:
        return json.loads(value or "")
    except (TypeError, ValueError):
        return fallback


def relative_path(path: Path, project_root: Path = PROJECT_ROOT) -> str:
    try:
        return path.resolve().relative_to(project_root.resolve()).as_posix()
    except ValueError:
        return path.as_posix()


def _candidate_passage_id(external_source_id: str, raw_sha256: str) -> str:
    return f"external-candidate:{external_source_id}:{raw_sha256[:16]}"


def _candidate_work_key(external_source_id: str, raw_sha256: str) -> str:
    return f"external_candidate:{external_source_id}:{raw_sha256[:16]}"


def _candidate_matches_ref(ref: dict[str, Any], candidate: dict[str, Any]) -> bool:
    if ref.get("raw_file") != candidate.get("raw_file"):
        return False
    for key in ("raw_sha256", "pageid", "revid"):
        left = ref.get(key)
        right = candidate.get(key)
        if left is not None and right is not None and str(left) != str(right):
            return False
    return True


def _candidate_passage(
    *,
    entry: dict[str, Any],
    candidate: dict[str, Any],
    raw_text: str,
    source_file: Path,
    source_hash: str,
    manifest_path: Path,
    manifest_hash: str,
    project_root: Path,
) -> tuple[dict[str, Any], dict[str, Any]]:
    external_source_id = str(entry["external_source_id"])
    work_key = _candidate_work_key(external_source_id, source_hash)
    passage_id = _candidate_passage_id(external_source_id, source_hash)
    plain_text = strip_wikitext(raw_text)
    normalized_text = " ".join(plain_text.split())
    quote = str(entry.get("quote") or "")
    quote_in_candidate = bool(
        compact_for_match(quote)
        and compact_for_match(quote) in compact_for_match(plain_text)
    )
    passage = {
        "passage_id": passage_id,
        "work_key": work_key,
        "document_title": candidate.get("page_title") or entry.get("cited_work"),
        "section_title": f"Wikisource revision {candidate.get('revid') or 'unknown'}",
        "entry_title": entry.get("cited_work"),
        "entry_kind": "external_public_candidate_page",
        "local_ordinal": 1,
        "md_line_start": 1,
        "md_line_end": max(1, len(raw_text.splitlines())),
        "raw_text": raw_text,
        "plain_text": plain_text,
        "normalized_text": normalized_text,
        "raw_text_sha256": sha256_bytes(raw_text.encode("utf-8")),
        "normalized_text_sha256": sha256_bytes(normalized_text.encode("utf-8")),
        "source_file": relative_path(source_file, project_root),
        "source_file_sha256": source_hash,
        "inline_notes": [
            {
                "note_type": "external_public_candidate_metadata",
                "candidate_status": "public_transcription_candidate",
                "canonical_status": "unknown",
                "external_source_id": external_source_id,
                "cited_work": entry.get("cited_work"),
                "quote": quote,
                "quote_in_candidate_compact_text": quote_in_candidate,
                "match_mode": candidate.get("match_mode"),
                "offline_match_mode": candidate.get("offline_match_mode"),
                "offline_start_char": candidate.get("offline_start_char"),
                "offline_end_char": candidate.get("offline_end_char"),
                "page_title": candidate.get("page_title"),
                "pageid": candidate.get("pageid"),
                "revid": candidate.get("revid"),
                "timestamp": candidate.get("timestamp"),
                "page_url": candidate.get("page_url"),
                "api_url": candidate.get("api_url"),
                "manifest_path": relative_path(manifest_path, project_root),
                "manifest_sha256": manifest_hash,
                "transform": "conservative_wikitext_strip_v1",
                "review_boundary": "candidate passage only; edition and canonical status require human verification",
            }
        ],
    }
    source_metadata = {
        "canonical_status": "unknown",
        "source_role": "external_public_candidate_page",
        "source_version_reason": "frozen public transcription candidate; edition and image verification pending",
        "candidate_status": "public_transcription_candidate",
        "canonical_verified": False,
        "external_source_id": external_source_id,
        "cited_work": entry.get("cited_work"),
        "page_title": candidate.get("page_title"),
        "pageid": candidate.get("pageid"),
        "revid": candidate.get("revid"),
        "timestamp": candidate.get("timestamp"),
        "page_url": candidate.get("page_url"),
        "api_url": candidate.get("api_url"),
        "manifest_path": relative_path(manifest_path, project_root),
        "manifest_sha256": manifest_hash,
        "raw_page_sha256": source_hash,
        "quote": quote,
        "quote_in_candidate_compact_text": quote_in_candidate,
        "match_mode": candidate.get("match_mode"),
        "offline_match_mode": candidate.get("offline_match_mode"),
        "offline_start_char": candidate.get("offline_start_char"),
        "offline_end_char": candidate.get("offline_end_char"),
        "transform": "conservative_wikitext_strip_v1",
        "review_boundary": "candidate passage only; do not promote to canonical automatically",
    }
    return passage, source_metadata


def ingest_external_candidate_passages(
    connection: sqlite3.Connection,
    *,
    manifest_path: Path,
    project_root: Path = PROJECT_ROOT,
) -> dict[str, Any]:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest_hash = sha256_file(manifest_path)
    scanned = 0
    matched_candidates = 0
    imported = 0
    skipped = Counter()
    queue_updates = 0
    candidate_ids: list[str] = []
    imported_rows: list[dict[str, Any]] = []

    for entry in manifest.get("entries", []):
        if entry.get("status") != "candidate_found":
            continue
        for candidate in entry.get("candidates", []):
            scanned += 1
            if candidate.get("offline_match_mode") != "normalized_contiguous":
                skipped["not_offline_contiguous"] += 1
                continue
            matched_candidates += 1
            raw_file_value = candidate.get("raw_file")
            if not raw_file_value:
                skipped["missing_raw_file"] += 1
                continue
            raw_file = (project_root / raw_file_value).resolve()
            try:
                raw_file.relative_to(project_root.resolve())
            except ValueError:
                skipped["raw_file_outside_project"] += 1
                continue
            if not raw_file.is_file():
                skipped["raw_file_missing"] += 1
                continue
            raw_bytes = raw_file.read_bytes()
            actual_hash = sha256_bytes(raw_bytes)
            expected_hash = str(candidate.get("raw_sha256") or candidate.get("content_sha256") or "")
            if expected_hash and actual_hash != expected_hash:
                skipped["raw_hash_mismatch"] += 1
                continue
            raw_text = raw_bytes.decode("utf-8")
            passage, source_metadata = _candidate_passage(
                entry=entry,
                candidate=candidate,
                raw_text=raw_text,
                source_file=raw_file,
                source_hash=actual_hash,
                manifest_path=manifest_path,
                manifest_hash=manifest_hash,
                project_root=project_root,
            )
            ingest_passages(
                connection,
                [passage],
                source_kind="external_public_candidate",
                metadata=source_metadata,
            )
            passage_id = passage["passage_id"]
            candidate_ids.append(passage_id)
            imported += 1
            imported_rows.append(
                {
                    "passage_id": passage_id,
                    "source_document_id": f"{passage['work_key']}:{actual_hash[:16]}",
                    "external_source_id": entry.get("external_source_id"),
                    "case_id": entry.get("case_id"),
                    "evidence_index": entry.get("evidence_index"),
                    "page_title": candidate.get("page_title"),
                    "revid": candidate.get("revid"),
                    "raw_file": relative_path(raw_file, project_root),
                    "raw_sha256": actual_hash,
                    "canonical_status": "unknown",
                    "quote_in_candidate_compact_text": source_metadata["quote_in_candidate_compact_text"],
                }
            )

            queue_item_id = f"external-passage:{entry['case_id']}:{entry['evidence_index']}"
            queue_row = connection.execute(
                "SELECT candidate_refs_json, candidate_passage_ids_json "
                "FROM external_passage_resolution_queue WHERE queue_item_id = ?",
                (queue_item_id,),
            ).fetchone()
            if queue_row is None:
                skipped["queue_row_missing"] += 1
                continue
            refs = parse_json(queue_row[0], [])
            if not isinstance(refs, list):
                refs = []
            updated_ref = False
            for ref in refs:
                if isinstance(ref, dict) and _candidate_matches_ref(ref, candidate):
                    ref["candidate_passage_id"] = passage_id
                    updated_ref = True
            passage_ids = parse_json(queue_row[1], [])
            if not isinstance(passage_ids, list):
                passage_ids = []
            if passage_id not in passage_ids:
                passage_ids.append(passage_id)
                passage_ids = sorted(set(str(item) for item in passage_ids))
            connection.execute(
                "UPDATE external_passage_resolution_queue "
                "SET candidate_refs_json = ?, candidate_passage_ids_json = ?, updated_at = datetime('now') "
                "WHERE queue_item_id = ?",
                (
                    json.dumps(refs, ensure_ascii=False, sort_keys=True),
                    json.dumps(passage_ids, ensure_ascii=False),
                    queue_item_id,
                ),
            )
            if updated_ref:
                queue_updates += 1

    candidate_ids = sorted(set(candidate_ids))
    return {
        "report_version": "external_candidate_passage_ingest.v1",
        "manifest_path": relative_path(manifest_path, project_root),
        "manifest_sha256": manifest_hash,
        "policy": {
            "source_kind": "external_public_candidate",
            "canonical_status": "unknown",
            "quote_check_mutation": "none",
            "annotation_evidence_link_mutation": "none",
            "candidate_passage_is_not_canonical": True,
            "selection_requires_human_resolution": True,
        },
        "counts": {
            "candidate_entries_scanned": scanned,
            "offline_contiguous_candidates": matched_candidates,
            "passages_imported_or_upserted": imported,
            "unique_candidate_passage_ids": len(candidate_ids),
            "queue_refs_updated": queue_updates,
        },
        "skipped": dict(skipped),
        "candidate_passage_ids": candidate_ids,
        "imported": imported_rows,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", type=Path, default=DEFAULT_DATABASE)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    args = parser.parse_args()

    with open_database(args.database.resolve()) as connection:
        report = ingest_external_candidate_passages(
            connection,
            manifest_path=args.manifest.resolve(),
            project_root=PROJECT_ROOT,
        )
        connection.commit()
    args.report.resolve().parent.mkdir(parents=True, exist_ok=True)
    args.report.resolve().write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
