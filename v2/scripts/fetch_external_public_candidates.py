from __future__ import annotations

"""Fetch public external-text candidates without promoting them to canonical.

The script uses the public Wikisource MediaWiki API as a locating aid.  It
freezes the returned wikitext and revision metadata, but deliberately leaves
the V2 evidence rows unchecked: a public transcription is not by itself a
chosen edition or an image-verified canonical passage.
"""

import argparse
import json
import re
import sqlite3
import time
import urllib.parse
import urllib.request
from collections import Counter
from datetime import datetime, timezone
from html import unescape
from pathlib import Path
from typing import Any

from external_text_normalization import (
    compact_for_match,
    normalized_contiguous_match,
    strip_wikitext,
)


V2_ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = V2_ROOT.parent
DEFAULT_DATABASE = V2_ROOT / "data/real_runs/annotation_v2.db"
DEFAULT_OUTPUT = V2_ROOT / "data/external_sources/wikisource"
DEFAULT_MANIFEST = V2_ROOT / "data/real_runs/external_public_candidate_manifest.json"
DEFAULT_CANDIDATES = V2_ROOT / "data/real_runs/external_passage_candidates.passage.v1.jsonl"
API_URL = "https://zh.wikisource.org/w/api.php"
USER_AGENT = "Erwang-V2-public-source-candidate-fetch/1.0"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _variants(value: str) -> list[str]:
    values = [value, strip_wikitext(value)]
    compact_values = [compact_for_match(item) for item in values]
    return list(dict.fromkeys(item for item in values + compact_values if item))


def _relative(path: Path) -> str:
    try:
        return path.resolve().relative_to(PROJECT_ROOT.resolve()).as_posix()
    except ValueError:
        return path.as_posix()


def _request(params: dict[str, Any]) -> dict[str, Any]:
    query = urllib.parse.urlencode(
        {key: value for key, value in params.items() if value is not None}
    )
    request = urllib.request.Request(
        f"{API_URL}?{query}",
        headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
    )
    with urllib.request.urlopen(request, timeout=40) as response:
        return json.loads(response.read().decode("utf-8"))


def _search_quote(quote: str) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    queries = [f'"{quote.replace(chr(34), " ")}"', quote]
    attempts: list[dict[str, Any]] = []
    for query in queries:
        try:
            data = _request(
                {
                    "action": "query",
                    "list": "search",
                    "srsearch": query,
                    "srnamespace": 0,
                    "srlimit": 10,
                    "srprop": "snippet|timestamp|wordcount",
                    "format": "json",
                }
            )
        except Exception as error:  # pragma: no cover - network dependent
            attempts.append({"query": query, "error": f"{type(error).__name__}:{error}"})
            continue
        results = data.get("query", {}).get("search", [])
        attempts.append({"query": query, "result_count": len(results)})
        if results:
            return results, {"attempts": attempts, "selected_query": query}
        time.sleep(0.15)
    return [], {"attempts": attempts, "selected_query": None}


def _label_tokens(label: str) -> list[str]:
    clean = str(label or "").strip("《》 ")
    clean = clean.replace("》", "").replace("《", "")
    parts = [part for part in re.split(r"[·/、，,；;\s]+", clean) if part]
    if not parts:
        return []
    tokens: list[str] = []
    for part in parts:
        compact = compact_for_match(part)
        if len(compact) >= 2:
            tokens.append(compact)
    return list(dict.fromkeys(tokens))


def _title_score(title: str, cited_work: str) -> int:
    normalized_title = compact_for_match(title)
    return sum(1 for token in _label_tokens(cited_work) if token in normalized_title)


def _fetch_page(title: str) -> dict[str, Any] | None:
    try:
        data = _request(
            {
                "action": "query",
                "prop": "revisions",
                "titles": title,
                "rvprop": "content|ids|timestamp",
                "rvslots": "main",
                "format": "json",
                "formatversion": "2",
            }
        )
    except Exception as error:  # pragma: no cover - network dependent
        return {"title": title, "fetch_error": f"{type(error).__name__}:{error}"}
    pages = data.get("query", {}).get("pages", [])
    if not pages:
        return {"title": title, "page_missing": True}
    page = pages[0]
    revisions = page.get("revisions", [])
    if not revisions:
        return {
            "title": title,
            "pageid": page.get("pageid"),
            "page_missing": page.get("missing", False),
            "revision_missing": True,
        }
    revision = revisions[0]
    content = (
        revision.get("slots", {})
        .get("main", {})
        .get("content", "")
    )
    return {
        "title": page.get("title", title),
        "pageid": page.get("pageid"),
        "revid": revision.get("revid"),
        "timestamp": revision.get("timestamp"),
        "content": content,
    }


def _raw_match(content: str, quote: str) -> dict[str, Any]:
    for variant in _variants(quote):
        start = content.find(variant)
        if start >= 0:
            return {
                "match_mode": "raw_exact" if variant == quote else "raw_variant_exact",
                "start_char": start,
                "end_char": start + len(variant),
                "matched_text": variant,
            }
    matched, _, _ = normalized_contiguous_match(content, quote)
    if matched:
        return {
            "match_mode": "cleaned_compact_match",
            "start_char": None,
            "end_char": None,
            "matched_text": None,
        }
    return {
        "match_mode": "search_only",
        "start_char": None,
        "end_char": None,
        "matched_text": None,
    }


def _snippet(content: str, match: dict[str, Any], quote: str) -> str:
    start = match.get("start_char")
    end = match.get("end_char")
    if isinstance(start, int) and isinstance(end, int):
        return content[max(0, start - 320) : min(len(content), end + 320)]
    return quote


def _load_evidence_rows(
    database: Path,
    *,
    include_secondary_citations: bool = False,
) -> list[dict[str, Any]]:
    connection = sqlite3.connect(database)
    connection.row_factory = sqlite3.Row
    rows = connection.execute(
        """
        SELECT ae.case_id, ae.evidence_index, ae.source_work, ae.quote,
               json_extract(ae.evidence_json, '$.source_resolution') AS source_resolution,
               es.external_source_id, es.normalized_work
        FROM annotation_evidences AS ae
        JOIN annotation_evidence_external_sources AS link
          ON link.case_id = ae.case_id AND link.evidence_index = ae.evidence_index
        JOIN external_source_registry AS es
          ON es.external_source_id = link.external_source_id
        WHERE json_extract(ae.evidence_json, '$.source_resolution') = 'external_source_pending'
           OR (
                ? = 1
                AND json_extract(ae.evidence_json, '$.source_resolution') = 'secondary_citation_match'
           )
        ORDER BY ae.case_id, ae.evidence_index
        """
        , (1 if include_secondary_citations else 0,)
    ).fetchall()
    connection.close()
    return [dict(row) for row in rows]


def _page_filename(page_title: str) -> str:
    safe = re.sub(r"[^0-9A-Za-z一-龥_-]+", "_", page_title).strip("_")[:120]
    return f"{safe or 'page'}.wikitext"


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _write_jsonl(path: Path, values: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for value in values:
            handle.write(json.dumps(value, ensure_ascii=False, separators=(",", ":")) + "\n")


def _register_candidates(
    database: Path,
    manifest_relative: str,
    entries: list[dict[str, Any]],
) -> None:
    """Register a fetched public candidate, never a verified canonical source."""

    by_source: dict[str, list[dict[str, Any]]] = {}
    for entry in entries:
        if entry.get("status") != "candidate_found":
            continue
        by_source.setdefault(entry["external_source_id"], []).append(entry)
    connection = sqlite3.connect(database)
    now = _now()
    for external_source_id, source_entries in by_source.items():
        first = source_entries[0]
        metadata = {
            "candidate_status": "public_transcription_candidate",
            "canonical_verified": False,
            "manifest": manifest_relative,
            "evidence_count_with_candidate": len(source_entries),
            "page_titles": sorted(
                {
                    candidate["page_title"]
                    for entry in source_entries
                    for candidate in entry.get("candidates", [])
                    if candidate.get("page_title")
                }
            ),
            "version_boundary": "Wikisource page/revision is a locating candidate; edition and image verification remain pending.",
        }
        connection.execute(
            """
            UPDATE external_source_registry
            SET status = 'registered', source_file = ?, edition = ?,
                location_note = ?, metadata_json = ?, updated_at = ?
            WHERE external_source_id = ?
            """,
            (
                manifest_relative,
                "Wikisource public transcription; edition unresolved",
                f"{len(source_entries)} quote candidate(s); quote remains unchecked",
                json.dumps(metadata, ensure_ascii=False, sort_keys=True),
                now,
                external_source_id,
            ),
        )
    connection.commit()
    connection.close()


def _reconcile_manifest(manifest_path: Path, database: Path) -> dict[str, Any]:
    """Repair a previously written manifest without making network requests."""

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    _write_json(manifest_path, manifest)
    connection = sqlite3.connect(database)
    connection.execute("UPDATE external_source_registry SET updated_at = ? WHERE source_file = ?", (_now(), _relative(manifest_path)))
    connection.commit()
    connection.close()
    return manifest


def run(
    *,
    database: Path = DEFAULT_DATABASE,
    output_dir: Path = DEFAULT_OUTPUT,
    manifest_path: Path = DEFAULT_MANIFEST,
    candidates_path: Path = DEFAULT_CANDIDATES,
    max_results_per_quote: int = 10,
    include_secondary_citations: bool = False,
) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    pages_dir = output_dir / "pages"
    pages_dir.mkdir(parents=True, exist_ok=True)
    evidence_rows = _load_evidence_rows(
        database,
        include_secondary_citations=include_secondary_citations,
    )
    entries: list[dict[str, Any]] = []
    page_cache: dict[str, dict[str, Any] | None] = {}
    page_records: dict[str, dict[str, Any]] = {}

    for row_index, row in enumerate(evidence_rows):
        quote = row.get("quote") or ""
        search_results, search_meta = _search_quote(quote)
        ranked = sorted(
            search_results[:max_results_per_quote],
            key=lambda result: (
                _title_score(result.get("title", ""), row.get("source_work", "")),
                -len(result.get("title", "")),
            ),
            reverse=True,
        )
        # A full-text search can return unrelated works containing the same
        # short phrase.  Do not download or present those pages as candidates
        # unless the page title contains at least one normalized cited-work
        # token.  The raw search hits are retained below for audit, but remain
        # search-only evidence.
        eligible = [
            result
            for result in ranked
            if _title_score(result.get("title", ""), row.get("source_work", "")) > 0
        ]
        candidate_records: list[dict[str, Any]] = []
        for result in eligible[:max_results_per_quote]:
            title = result.get("title", "")
            if not title:
                continue
            if title not in page_cache:
                page_cache[title] = _fetch_page(title)
                time.sleep(0.15)
            page = page_cache[title]
            if not page or not page.get("content"):
                continue
            content = page["content"]
            match = _raw_match(content, quote)
            page_file = pages_dir / _page_filename(title)
            if not page_file.exists():
                page_file.write_text(content, encoding="utf-8")
            page_record = {
                "page_title": page.get("title", title),
                "pageid": page.get("pageid"),
                "revid": page.get("revid"),
                "timestamp": page.get("timestamp"),
                "page_url": "https://zh.wikisource.org/wiki/" + urllib.parse.quote(title, safe="/"),
                "api_url": API_URL + "?" + urllib.parse.urlencode({"action": "query", "prop": "revisions", "titles": title}),
                "raw_file": _relative(page_file),
            }
            page_records[title] = page_record
            candidate_records.append(
                {
                    **page_record,
                    "title_match_score": _title_score(title, row.get("source_work", "")),
                    "search_snippet": unescape(result.get("snippet", "")),
                    "search_timestamp": result.get("timestamp"),
                    **match,
                    "matched_context": _snippet(content, match, quote),
                }
            )
        found = [item for item in candidate_records if item.get("match_mode") != "search_only"]
        status = "candidate_found" if found else "search_hit_only" if candidate_records else "no_public_match"
        entries.append(
            {
                "case_id": row["case_id"],
                "evidence_index": row["evidence_index"],
                "external_source_id": row["external_source_id"],
                "cited_work": row["source_work"],
                "normalized_work": row["normalized_work"],
                "source_resolution": row["source_resolution"],
                "quote": quote,
                "status": status,
                "search": search_meta,
                "search_hits": [
                    {
                        "page_title": result.get("title"),
                        "title_match_score": _title_score(
                            result.get("title", ""), row.get("source_work", "")
                        ),
                        "search_snippet": unescape(result.get("snippet", "")),
                    }
                    for result in ranked[:max_results_per_quote]
                ],
                "candidates": candidate_records,
                "boundary": "public candidate only; not canonical passed",
            }
        )
        if row_index and row_index % 10 == 0:
            print(f"processed {row_index}/{len(evidence_rows)} external evidence", flush=True)

    manifest = {
        "schema_version": "external_public_candidate_manifest.v1",
        "generated_at": _now(),
        "database": str(database),
        "api": API_URL,
        "source_policy": {
            "source_kind": "public_transcription_candidate",
            "canonical_status": "not_verified",
            "quote_check_mutation": "none; all V2 evidence remains unchecked",
            "version_rule": "Wikisource page/revision metadata is recorded; edition and image-level verification remain pending",
            "evidence_selection": {
                "external_source_pending_included": True,
                "secondary_citation_match_included": include_secondary_citations,
                "secondary_citation_is_not_canonical": True,
            },
        },
        "summary": {
            "evidence_count": len(entries),
            "status_counts": dict(Counter(entry["status"] for entry in entries)),
            "candidate_count": sum(len(entry.get("candidates", [])) for entry in entries),
            "page_count": len(page_records),
            "source_count_with_candidate": len(
                {entry["external_source_id"] for entry in entries if entry["status"] == "candidate_found"}
            ),
        },
        "entries": entries,
        "pages": sorted(page_records.values(), key=lambda item: item["page_title"]),
    }
    _write_json(manifest_path, manifest)
    _write_jsonl(candidates_path, entries)
    _register_candidates(database, _relative(manifest_path), entries)
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", type=Path, default=DEFAULT_DATABASE)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--candidates", type=Path, default=DEFAULT_CANDIDATES)
    parser.add_argument(
        "--include-secondary-citations",
        action="store_true",
        help="also search rows whose source was found in a Wang passage; they remain secondary, not canonical",
    )
    parser.add_argument("--reconcile-only", action="store_true")
    args = parser.parse_args()
    if args.reconcile_only:
        manifest = _reconcile_manifest(args.manifest, args.database)
        print(json.dumps({"status": "reconciled", "entries": len(manifest.get("entries", []))}, ensure_ascii=False, indent=2))
        return 0
    manifest = run(
        database=args.database,
        output_dir=args.output_dir,
        manifest_path=args.manifest,
        candidates_path=args.candidates,
        include_secondary_citations=args.include_secondary_citations,
    )
    print(json.dumps(manifest["summary"], ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
