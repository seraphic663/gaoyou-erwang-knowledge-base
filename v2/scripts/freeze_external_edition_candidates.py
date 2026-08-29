#!/usr/bin/env python3
"""Freeze public external-edition candidates without changing V2 state.

This is a deliberately separate lane from ``source_documents`` and
``external_source_registry``.  It obtains public Internet Archive metadata,
OCR and (only when a linked quote is found) scan PDFs; it records blocked
metadata leads such as CText 403 responses; and it writes a manifest that
can be attached to later review packets.  It never changes SQLite, quote
checks, canonical status, human status, or gold status.

The downloaded OCR is a locating layer.  A quote match in it is recorded as
``candidate_ocr_match`` only.  It is not an external canonical passage and
cannot promote an evidence row.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sqlite3
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


V2_ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = V2_ROOT.parent
DEFAULT_DATABASE = V2_ROOT / "data/real_runs/annotation_v2.db"
DEFAULT_INPUT = V2_ROOT / "data/real_runs/external_edition_fetch_manifest.v1.json"
DEFAULT_OUTPUT = V2_ROOT / "data/real_runs/external_edition_candidate_manifest.v1.json"
DEFAULT_ROOT = V2_ROOT / "data/external_sources/edition_candidates"
USER_AGENT = "Erwang-V2-external-edition-candidate-fetch/1.0"
MAX_METADATA_BYTES = 20 * 1024 * 1024
CHUNK_SIZE = 1024 * 1024


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def relative(path: Path) -> str:
    try:
        return path.resolve().relative_to(PROJECT_ROOT.resolve()).as_posix()
    except ValueError:
        return path.as_posix()


def compact_work(value: str) -> str:
    """Normalize only enough to match a cited work to a candidate package."""

    value = str(value or "")
    return "".join(char for char in value if char not in "《》[]()（） 　\t\r\n")


def safe_component(value: str) -> str:
    value = str(value or "").strip()
    if not value or value in {".", ".."} or "/" in value or "\\" in value:
        raise ValueError(f"unsafe_path_component:{value!r}")
    if not re.fullmatch(r"[0-9A-Za-z一-龥_.-]+", value):
        raise ValueError(f"unsafe_path_component:{value!r}")
    return value


def request_bytes(url: str, *, retries: int = 3, timeout: int = 45) -> tuple[int, dict[str, str], bytes]:
    last_error: Exception | None = None
    for attempt in range(retries):
        try:
            request = urllib.request.Request(
                url,
                headers={
                    "User-Agent": USER_AGENT,
                    "Accept": "application/json, text/plain, application/pdf, */*",
                },
            )
            with urllib.request.urlopen(request, timeout=timeout) as response:
                return (
                    int(response.status),
                    {str(key).lower(): str(value) for key, value in response.headers.items()},
                    response.read(MAX_METADATA_BYTES),
                )
        except urllib.error.HTTPError as error:
            body = b""
            try:
                body = error.read(MAX_METADATA_BYTES)
            except Exception:
                pass
            return (
                int(error.code),
                {str(key).lower(): str(value) for key, value in error.headers.items()},
                body,
            )
        except Exception as error:  # pragma: no cover - network dependent
            last_error = error
            if attempt + 1 < retries:
                time.sleep(1.0 * (attempt + 1))
    raise RuntimeError(f"request_failed:{type(last_error).__name__}:{last_error}")


def download_file(
    url: str,
    target: Path,
    *,
    expected_size: int | None = None,
    retries: int = 3,
    timeout: int = 90,
) -> dict[str, Any]:
    """Stream one public file and validate the IA metadata size if available."""

    target.parent.mkdir(parents=True, exist_ok=True)
    if target.is_file() and expected_size is not None and target.stat().st_size == expected_size:
        return {
            "status": "reused",
            "http_status": None,
            "size_bytes": expected_size,
            "url": url,
            "reuse_reason": "existing_file_matches_metadata_size",
        }
    partial = target.with_name(target.name + ".part")
    last_error: Exception | None = None
    for attempt in range(retries):
        try:
            request = urllib.request.Request(
                url,
                headers={
                    "User-Agent": USER_AGENT,
                    "Accept": "application/octet-stream, */*",
                },
            )
            size = 0
            with urllib.request.urlopen(request, timeout=timeout) as response:
                status = int(response.status)
                with partial.open("wb") as handle:
                    while True:
                        chunk = response.read(CHUNK_SIZE)
                        if not chunk:
                            break
                        handle.write(chunk)
                        size += len(chunk)
            if expected_size is not None and size != expected_size:
                raise ValueError(f"size_mismatch:expected={expected_size}:actual={size}")
            os.replace(partial, target)
            return {
                "status": "downloaded",
                "http_status": status,
                "size_bytes": size,
                "url": url,
            }
        except urllib.error.HTTPError as error:
            last_error = error
            status = int(error.code)
            if partial.exists():
                partial.unlink()
            if status in {401, 403, 404, 410}:
                return {
                    "status": "blocked_or_missing",
                    "http_status": status,
                    "size_bytes": 0,
                    "url": url,
                    "error": f"HTTPError:{status}",
                }
        except Exception as error:  # pragma: no cover - network dependent
            last_error = error
            if partial.exists():
                partial.unlink()
        if attempt + 1 < retries:
            time.sleep(1.0 * (attempt + 1))
    return {
        "status": "download_error",
        "http_status": None,
        "size_bytes": 0,
        "url": url,
        "error": f"{type(last_error).__name__}:{last_error}",
    }


def load_metadata(identifier: str) -> dict[str, Any]:
    url = f"https://archive.org/metadata/{urllib.parse.quote(identifier, safe='')}"
    status, headers, body = request_bytes(url)
    record: dict[str, Any] = {
        "url": url,
        "http_status": status,
        "content_type": headers.get("content-type"),
    }
    if status != 200:
        record["status"] = "metadata_blocked_or_missing"
        record["error"] = f"HTTPError:{status}"
        return record
    try:
        data = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        record["status"] = "metadata_invalid"
        record["error"] = f"{type(error).__name__}:{error}"
        return record
    record.update(
        {
            "status": "metadata_loaded",
            "metadata": data,
        }
    )
    return record


def metadata_files(metadata: dict[str, Any]) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for raw in metadata.get("files") or []:
        if not isinstance(raw, dict) or not raw.get("name"):
            continue
        result[str(raw["name"])] = raw
    return result


def file_is_public(file_record: dict[str, Any]) -> bool:
    private = file_record.get("private")
    return private not in {True, "true", "True", 1, "1"}


def file_url(identifier: str, filename: str) -> str:
    return "https://archive.org/download/{}/{}".format(
        urllib.parse.quote(identifier, safe=""),
        urllib.parse.quote(filename, safe=""),
    )


def linked_evidence(database: Path, patterns: list[str]) -> list[dict[str, Any]]:
    if not database.is_file():
        return []
    connection = sqlite3.connect(f"file:{database.resolve()}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    try:
        rows = connection.execute(
            """
            SELECT es.external_source_id, es.cited_work, es.normalized_work,
                   ae.case_id, ae.evidence_index, ae.quote
            FROM external_source_registry es
            JOIN annotation_evidence_external_sources link
              ON link.external_source_id = es.external_source_id
            JOIN annotation_evidences ae
              ON ae.case_id = link.case_id AND ae.evidence_index = link.evidence_index
            ORDER BY ae.case_id, ae.evidence_index
            """
        ).fetchall()
    finally:
        connection.close()
    compact_patterns = [compact_work(pattern) for pattern in patterns if compact_work(pattern)]
    result: list[dict[str, Any]] = []
    seen: set[tuple[str, int]] = set()
    for row in rows:
        values = [compact_work(row["cited_work"]), compact_work(row["normalized_work"])]
        if not any(pattern in value for pattern in compact_patterns for value in values):
            continue
        key = (str(row["case_id"]), int(row["evidence_index"]))
        if key in seen:
            continue
        seen.add(key)
        result.append(dict(row))
    return result


def quote_match(raw_text: str, quote: str) -> dict[str, Any]:
    if quote and quote in raw_text:
        start = raw_text.find(quote)
        return {
            "match_mode": "raw_exact",
            "start_char": start,
            "end_char": start + len(quote),
        }
    try:
        import sys

        scripts_root = str(V2_ROOT / "scripts")
        if scripts_root not in sys.path:
            sys.path.insert(0, scripts_root)
        from external_text_normalization import normalized_contiguous_match

        matched, start, end = normalized_contiguous_match(raw_text, quote)
    except Exception as error:  # pragma: no cover - import failure is diagnostic
        return {"match_mode": "normalizer_error", "error": f"{type(error).__name__}:{error}"}
    if matched:
        return {
            "match_mode": "candidate_ocr_match",
            "start_char": start,
            "end_char": end,
        }
    return {"match_mode": "not_found", "start_char": None, "end_char": None}


def save_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def process_candidate(
    candidate: dict[str, Any],
    *,
    database: Path,
    output_root: Path,
) -> dict[str, Any]:
    candidate_id = safe_component(str(candidate["candidate_id"]))
    patterns = [str(value) for value in candidate.get("work_match_patterns") or []]
    linked = linked_evidence(database, patterns)
    candidate_root = output_root / candidate_id
    candidate_root.mkdir(parents=True, exist_ok=True)
    output: dict[str, Any] = {
        "candidate_id": candidate_id,
        "work_match_patterns": patterns,
        "edition": candidate.get("edition"),
        "text_layer": candidate.get("text_layer"),
        "provider": candidate.get("provider"),
        "source_url": candidate.get("source_url"),
        "metadata_url": candidate.get("metadata_url"),
        "linked_evidence_count": len(linked),
        "linked_external_source_ids": sorted({str(row["external_source_id"]) for row in linked}),
        "items": [],
        "candidate_boundary": "downloaded public candidate only; not source_documents canonical and not quote_check passed",
    }
    if candidate.get("blocked_probe"):
        url = str(candidate.get("source_url") or "")
        status = None
        error = None
        try:
            status, headers, body = request_bytes(url, retries=2, timeout=30)
            output["probe"] = {
                "url": url,
                "http_status": status,
                "content_type": headers.get("content-type"),
                "body_bytes_captured": len(body),
            }
        except Exception as exc:  # pragma: no cover - network dependent
            error = f"{type(exc).__name__}:{exc}"
        if error:
            output["probe"] = {"url": url, "http_status": None, "error": error}
        output["availability_status"] = (
            "blocked" if status in {401, 403, 404, 410} else "metadata_only"
        )
        output["items"] = []
        return output

    item_inputs = candidate.get("items") or []
    for item_input in item_inputs:
        identifier = safe_component(str(item_input["identifier"]))
        volume_label = str(item_input.get("volume_label") or "")
        item_root = candidate_root / identifier
        item_root.mkdir(parents=True, exist_ok=True)
        metadata_path = item_root / "archive_metadata.json"
        metadata_record: dict[str, Any]
        if metadata_path.exists():
            try:
                cached_metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                cached_metadata = None
            if isinstance(cached_metadata, dict) and cached_metadata.get("status") == "metadata_loaded":
                metadata_record = cached_metadata
                metadata_record["reuse_reason"] = "existing_archive_metadata_record"
            else:
                metadata_record = load_metadata(identifier)
        else:
            metadata_record = load_metadata(identifier)
        metadata = metadata_record.get("metadata") or {}
        save_json(metadata_path, metadata_record)
        files = metadata_files(metadata)
        item: dict[str, Any] = {
            "identifier": identifier,
            "volume_label": volume_label,
            "item_url": f"https://archive.org/details/{urllib.parse.quote(identifier, safe='')}",
            "metadata_url": metadata_record.get("url"),
            "metadata_status": metadata_record.get("status"),
            "metadata_file": relative(metadata_path),
            "metadata_title": (metadata.get("metadata") or {}).get("title") if isinstance(metadata.get("metadata"), dict) else metadata.get("title"),
            "files": [],
            "quote_matches": [],
        }
        # The API response has a top-level metadata object.  Keep this
        # explicit so a malformed response cannot silently pass the title
        # and file checks.
        api_metadata = metadata.get("metadata") if isinstance(metadata, dict) else {}
        if not isinstance(api_metadata, dict):
            api_metadata = {}
        item["metadata_title"] = api_metadata.get("title")
        if metadata_record.get("status") != "metadata_loaded":
            item["availability_status"] = "metadata_unavailable"
            output["items"].append(item)
            continue

        expected_title = str(api_metadata.get("title") or "")
        item["metadata_creator"] = api_metadata.get("creator")
        item["metadata_date"] = api_metadata.get("date")
        item["metadata_collection"] = api_metadata.get("collection")
        item["metadata_contributor"] = api_metadata.get("contributor")
        item["metadata_volume"] = api_metadata.get("volume")
        item["title_nonempty"] = bool(expected_title)
        ocr_name = f"{identifier}_djvu.txt"
        scan_name = f"{identifier}.pdf"
        ocr_record = files.get(ocr_name)
        scan_record = files.get(scan_name)
        item["expected_files"] = {
            "ocr": ocr_name,
            "scan": scan_name,
            "ocr_public": bool(ocr_record and file_is_public(ocr_record)),
            "scan_public": bool(scan_record and file_is_public(scan_record)),
            "ocr_size_metadata": ocr_record.get("size") if ocr_record else None,
            "scan_size_metadata": scan_record.get("size") if scan_record else None,
        }
        ocr_text = ""
        if candidate.get("download_ocr") and ocr_record and file_is_public(ocr_record):
            expected_size = None
            try:
                expected_size = int(ocr_record.get("size")) if ocr_record.get("size") else None
            except (TypeError, ValueError):
                expected_size = None
            ocr_path = item_root / ocr_name
            fetch = download_file(
                file_url(identifier, ocr_name),
                ocr_path,
                expected_size=expected_size,
                retries=2,
                timeout=30,
            )
            file_entry = {
                "role": "ocr",
                "name": ocr_name,
                "path": relative(ocr_path) if fetch.get("status") in {"downloaded", "reused"} else None,
                "metadata_size": expected_size,
                **fetch,
            }
            item["files"].append(file_entry)
            if fetch.get("status") in {"downloaded", "reused"}:
                ocr_text = ocr_path.read_text(encoding="utf-8", errors="replace")
        elif ocr_record:
            item["files"].append({"role": "ocr", "name": ocr_name, "status": "not_downloaded"})

        matched_rows: list[dict[str, Any]] = []
        for row in linked:
            match = quote_match(ocr_text, str(row.get("quote") or "")) if ocr_text else {
                "match_mode": "ocr_not_available",
                "start_char": None,
                "end_char": None,
            }
            if match["match_mode"] in {"raw_exact", "candidate_ocr_match"}:
                match_record = {
                    "external_source_id": row["external_source_id"],
                    "case_id": row["case_id"],
                    "evidence_index": int(row["evidence_index"]),
                    "cited_work": row["cited_work"],
                    "quote": row["quote"],
                    **match,
                }
                item["quote_matches"].append(match_record)
                matched_rows.append(match_record)
        scan_mode = str(candidate.get("download_scan") or "")
        should_download_scan = bool(
            scan_record
            and file_is_public(scan_record)
            and (
                scan_mode == "always"
                or (scan_mode == "on_match" and matched_rows)
                or (scan_mode == "on_linked" and linked)
            )
        )
        if should_download_scan:
            expected_size = None
            try:
                expected_size = int(scan_record.get("size")) if scan_record.get("size") else None
            except (TypeError, ValueError):
                expected_size = None
            scan_path = item_root / scan_name
            fetch = download_file(
                file_url(identifier, scan_name),
                scan_path,
                expected_size=expected_size,
                retries=2,
                timeout=60,
            )
            item["files"].append(
                {
                    "role": "scan",
                    "name": scan_name,
                    "path": relative(scan_path) if fetch.get("status") in {"downloaded", "reused"} else None,
                    "metadata_size": expected_size,
                    "download_reason": (
                        "linked_evidence" if scan_mode == "on_linked" and linked else
                        "ocr_quote_match" if matched_rows else "manifest_always"
                    ),
                    **fetch,
                }
            )
        elif scan_record:
            item["files"].append(
                {
                    "role": "scan",
                    "name": scan_name,
                    "status": "not_downloaded",
                    "reason": "download_scan_policy_not_triggered",
                }
            )
        item["availability_status"] = (
            "downloaded_candidate" if any(file.get("status") in {"downloaded", "reused"} for file in item["files"]) else "metadata_only"
        )
        output["items"].append(item)

    output["availability_status"] = (
        "downloaded_candidate"
        if any(item.get("availability_status") == "downloaded_candidate" for item in output["items"])
        else "metadata_only"
    )
    output["downloaded_file_count"] = sum(
        1 for item in output["items"] for file in item.get("files", []) if file.get("status") in {"downloaded", "reused"}
    )
    output["quote_match_count"] = sum(len(item.get("quote_matches", [])) for item in output["items"])
    return output


def run(
    *,
    database: Path = DEFAULT_DATABASE,
    input_manifest: Path = DEFAULT_INPUT,
    output_manifest: Path = DEFAULT_OUTPUT,
    output_root: Path = DEFAULT_ROOT,
) -> dict[str, Any]:
    source = json.loads(input_manifest.read_text(encoding="utf-8"))
    if source.get("schema_version") != "external_edition_fetch_manifest.v1":
        raise ValueError("unexpected_input_manifest_schema")
    generated_at = now()
    outputs: list[dict[str, Any]] = []
    for index, candidate in enumerate(source.get("candidates") or [], start=1):
        result = process_candidate(candidate, database=database, output_root=output_root)
        outputs.append(result)
        print(
            f"processed {index}/{len(source.get('candidates') or [])} "
            f"{result['candidate_id']} status={result.get('availability_status')} "
            f"files={result.get('downloaded_file_count', 0)} matches={result.get('quote_match_count', 0)}",
            flush=True,
        )
    manifest: dict[str, Any] = {
        "schema_version": "external_edition_candidate_manifest.v1",
        "generated_at": generated_at,
        "input_manifest": relative(input_manifest),
        "database": relative(database),
        "output_root": relative(output_root),
        "policy": {
            "database_mutation": False,
            "canonical_promotion": False,
            "quote_check_promotion": False,
            "human_review_state": "unchanged",
            "candidate_match_label": "candidate_ocr_match",
            "scan_role": "downloaded only for an OCR-linked quote; image review remains required",
        },
        "summary": {
            "candidate_count": len(outputs),
            "availability_status_counts": dict(Counter(item.get("availability_status") for item in outputs)),
            "item_count": sum(len(item.get("items") or []) for item in outputs),
            "downloaded_file_count": sum(item.get("downloaded_file_count", 0) for item in outputs),
            "quote_match_count": sum(item.get("quote_match_count", 0) for item in outputs),
            "linked_external_source_count": len(
                {
                    source_id
                    for item in outputs
                    for source_id in item.get("linked_external_source_ids", [])
                }
            ),
            "database_rows_changed": 0,
        },
        "candidates": outputs,
        "conclusion": "Downloaded files and OCR matches are frozen public candidates. They remain outside source_documents canonical and outside quote_check passed until edition, image, passage, and human gates are completed.",
    }
    save_json(output_manifest, manifest)
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", type=Path, default=DEFAULT_DATABASE)
    parser.add_argument("--input-manifest", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output-manifest", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_ROOT)
    args = parser.parse_args()
    result = run(
        database=args.database,
        input_manifest=args.input_manifest,
        output_manifest=args.output_manifest,
        output_root=args.output_root,
    )
    print(json.dumps(result["summary"], ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
