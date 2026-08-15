from __future__ import annotations

"""Reconcile public candidate pages with exact normalized quote spans.

The fetcher intentionally keeps search results separate from quote matches.
This small offline pass looks at the frozen wikitext only.  It upgrades a
manifest entry to ``candidate_found`` only when the full quote (after NFKC,
punctuation/spacing removal, and a small traditional-character map) is a
contiguous substring of the page.  It still never changes V2 quote_check.
"""

import argparse
import hashlib
import json
import sqlite3
from pathlib import Path
from typing import Any

from external_text_normalization import compact_for_match, normalized_contiguous_match


V2_ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = V2_ROOT.parent
DEFAULT_DATABASE = V2_ROOT / "data/real_runs/annotation_v2.db"
DEFAULT_MANIFEST = V2_ROOT / "data/real_runs/external_public_candidate_manifest.json"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def relative(path: Path) -> str:
    try:
        return path.resolve().relative_to(PROJECT_ROOT.resolve()).as_posix()
    except ValueError:
        return path.as_posix()


def _write_manifest(manifest_path: Path, manifest: dict[str, Any]) -> dict[str, Any]:
    """Write a manifest and its sidecar hash after deterministic reconciliation."""

    manifest.pop("manifest_sha256", None)
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    manifest_hash = sha256(manifest_path)
    manifest_path.with_suffix(manifest_path.suffix + ".sha256").write_text(
        f"{manifest_hash}  {manifest_path.name}\n", encoding="utf-8"
    )
    manifest["manifest_sha256"] = manifest_hash
    return manifest


def merge_queue_candidates(
    database: Path,
    manifest_path: Path = DEFAULT_MANIFEST,
) -> dict[str, Any]:
    """Recover frozen candidate refs already persisted in the V2 queue.

    The network fetch is intentionally not the source of truth for a frozen
    page.  If a generated manifest is accidentally replaced or a later API
    search returns a different ranking, the queue still contains the raw file,
    revision and hash of every previously materialized candidate.  Merge those
    refs back into the current 80-entry manifest, then let ``reconcile``
    recompute the contiguous-match status from the frozen files.
    """

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    entries = manifest.get("entries") or []
    by_key = {
        (str(entry.get("case_id")), int(entry.get("evidence_index") or 0), str(entry.get("external_source_id"))): entry
        for entry in entries
    }
    merged = 0
    unmatched = 0
    page_map = {
        str(page.get("raw_file")): page
        for page in (manifest.get("pages") or [])
        if page.get("raw_file")
    }
    connection = sqlite3.connect(database)
    rows = connection.execute(
        "SELECT case_id, evidence_index, external_source_id, candidate_refs_json "
        "FROM external_passage_resolution_queue"
    ).fetchall()
    connection.close()
    for case_id, evidence_index, external_source_id, refs_json in rows:
        entry = by_key.get((str(case_id), int(evidence_index), str(external_source_id)))
        if entry is None:
            unmatched += 1
            continue
        candidates = entry.setdefault("candidates", [])
        by_file = {
            (str(candidate.get("raw_file")), str(candidate.get("raw_sha256") or candidate.get("content_sha256") or "")): candidate
            for candidate in candidates
        }
        try:
            refs = json.loads(refs_json or "[]")
        except (TypeError, ValueError):
            refs = []
        if not isinstance(refs, list):
            continue
        for ref in refs:
            if not isinstance(ref, dict) or not ref.get("raw_file"):
                continue
            key = (str(ref.get("raw_file")), str(ref.get("raw_sha256") or ref.get("content_sha256") or ""))
            candidate = by_file.get(key)
            if candidate is None:
                candidate = dict(ref)
                candidates.append(candidate)
                by_file[key] = candidate
                merged += 1
            for field in (
                "page_title", "pageid", "revid", "timestamp", "page_url",
                "api_url", "raw_file", "raw_sha256", "content_sha256",
                "match_mode", "start_char", "end_char", "matched_text",
            ):
                if ref.get(field) is not None:
                    candidate[field] = ref[field]
            page_map.setdefault(
                str(candidate["raw_file"]),
                {
                    field: candidate.get(field)
                    for field in (
                        "page_title", "pageid", "revid", "timestamp", "page_url",
                        "api_url", "raw_file", "raw_sha256",
                    )
                    if candidate.get(field) is not None
                },
            )
    manifest["pages"] = sorted(page_map.values(), key=lambda item: str(item.get("page_title") or item.get("raw_file") or ""))
    manifest.setdefault("recovery", {})
    manifest["recovery"].update(
        {
            "queue_candidate_refs_merged": merged,
            "queue_rows_without_manifest_entry": unmatched,
            "policy": "frozen_queue_refs_are merged before offline reconciliation; no canonical promotion",
        }
    )
    return manifest


def reconcile(manifest_path: Path = DEFAULT_MANIFEST) -> dict[str, Any]:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    statuses: dict[str, int] = {}
    exact_match_count = 0
    for entry in manifest.get("entries", []):
        candidates = []
        for candidate in entry.get("candidates", []):
            raw_file = PROJECT_ROOT / candidate["raw_file"]
            if not raw_file.exists():
                candidate["offline_match_mode"] = "raw_file_missing"
                candidates.append(candidate)
                continue
            raw = raw_file.read_text(encoding="utf-8")
            matched, start, end = normalized_contiguous_match(raw, entry.get("quote", ""))
            if matched:
                candidate["offline_match_mode"] = "normalized_contiguous"
                candidate["offline_start_char"] = start
                candidate["offline_end_char"] = end
                exact_match_count += 1
            else:
                candidate["offline_match_mode"] = "not_found"
            candidates.append(candidate)
        entry["candidates"] = candidates
        matched = [
            candidate
            for candidate in candidates
            if candidate.get("offline_match_mode") == "normalized_contiguous"
        ]
        if matched:
            entry["status"] = "candidate_found"
            entry["candidate_match_count"] = len(matched)
        elif candidates:
            entry["status"] = "search_hit_only"
            entry["candidate_match_count"] = 0
        else:
            entry["status"] = "no_public_match"
            entry["candidate_match_count"] = 0
        statuses[entry["status"]] = statuses.get(entry["status"], 0) + 1
    manifest["summary"]["status_counts"] = statuses
    manifest["summary"]["candidate_count"] = sum(
        entry.get("candidate_match_count", 0) for entry in manifest.get("entries", [])
    )
    manifest["summary"]["source_count_with_candidate"] = len(
        {
            entry["external_source_id"]
            for entry in manifest.get("entries", [])
            if entry["status"] == "candidate_found"
        }
    )
    manifest["summary"]["page_count"] = len(manifest.get("pages") or [])
    manifest["summary"]["offline_contiguous_match_count"] = exact_match_count
    return _write_manifest(manifest_path, manifest)


def update_registry(database: Path, manifest_path: Path, manifest: dict[str, Any]) -> None:
    source_entries: dict[str, list[dict[str, Any]]] = {}
    for entry in manifest.get("entries", []):
        if entry.get("status") == "candidate_found":
            source_entries.setdefault(str(entry["external_source_id"]), []).append(entry)
    connection = sqlite3.connect(database)
    connection.row_factory = sqlite3.Row
    for external_source_id, entries in source_entries.items():
        existing = connection.execute(
            "SELECT metadata_json FROM external_source_registry WHERE external_source_id = ?",
            (external_source_id,),
        ).fetchone()
        try:
            metadata = json.loads(existing["metadata_json"] or "{}") if existing else {}
        except (TypeError, ValueError):
            metadata = {}
        if not isinstance(metadata, dict):
            metadata = {}
        metadata.update(
            {
                "candidate_status": "public_transcription_candidate",
                "canonical_verified": False,
                "manifest": relative(manifest_path),
                "evidence_count_with_candidate": len(entries),
                "page_titles": sorted(
                    {
                        candidate.get("page_title")
                        for entry in entries
                        for candidate in entry.get("candidates", [])
                        if candidate.get("page_title")
                    }
                ),
                "version_boundary": "Wikisource page/revision is a locating candidate; edition and image verification remain pending.",
            }
        )
        connection.execute(
            "UPDATE external_source_registry SET status='registered', source_file=?, source_file_sha256=?, edition=?, location_note=?, metadata_json=?, updated_at=datetime('now') WHERE external_source_id=?",
            (
                relative(manifest_path),
                manifest["manifest_sha256"],
                "Wikisource public transcription; edition unresolved",
                "quote matched in frozen wikitext; image/edition verification pending",
                json.dumps(metadata, ensure_ascii=False, sort_keys=True),
                external_source_id,
            ),
        )
    connection.commit()
    connection.close()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--database", type=Path, default=DEFAULT_DATABASE)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument(
        "--recover-from-queue",
        action="store_true",
        help="merge frozen candidate refs from the V2 queue before offline reconciliation",
    )
    args = parser.parse_args()
    if args.recover_from_queue:
        recovered = merge_queue_candidates(args.database, args.manifest)
        _write_manifest(args.manifest, recovered)
    manifest = reconcile(args.manifest)
    update_registry(args.database, args.manifest, manifest)
    print(json.dumps(manifest["summary"], ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
