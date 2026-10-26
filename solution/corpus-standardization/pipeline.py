"""Read-only corpus ingestion into a new, isolated SQLite release.

Coordinates are Python Unicode codepoints in the exact UTF-8 decoded source,
including BOM and original CR/LF characters. Normalization is *per-codepoint*
NFKC followed by whitespace-run collapse; it is not whole-string NFKC.
Mapping entries are [norm_start, norm_end, raw_start, raw_end, kind].
Only equal-length identity entries support linear partial projection; other
entries project to the complete originating raw interval. Adjacent mappings
may overlap in raw coordinates when one compatibility character expands into
both words and whitespace. Neither source identities nor metadata are merged.
"""

from __future__ import annotations

import argparse
import bisect
from collections import Counter
from datetime import datetime, timezone
import hashlib
import heapq
import importlib.util
import json
from pathlib import Path
import re
import sqlite3
import statistics
import time
import unicodedata
from typing import Any


PIPELINE_VERSION = "corpus-standardization-v3"
NORMALIZATION_VERSION = "per-codepoint-nfkc-whitespace-v1"
MAPPING_VERSION = "absolute-codepoint-rle-v1"
CHUNK_SIZE = 600
CHUNK_OVERLAP = 100
READING_LIMIT = 1200
WANG_NAMES = (
    "读书杂志_王念孙.md", "广雅疏证_王念孙.md",
    "经传释词_王引之.md", "经义述闻_王引之.md",
)
TIERS = (("高频", "external_high"), ("中频", "external_mid"), ("低频", "external_low"))
SCHEMA = """
PRAGMA foreign_keys=ON;
CREATE TABLE sources (
 source_id TEXT PRIMARY KEY, collection TEXT NOT NULL, relpath TEXT NOT NULL UNIQUE,
 title TEXT NOT NULL, sha256 TEXT NOT NULL, encoding TEXT NOT NULL,
 raw_text TEXT NOT NULL, body_start INTEGER NOT NULL, body_end INTEGER NOT NULL,
 codepoints INTEGER NOT NULL, byte_size INTEGER NOT NULL, line_count INTEGER NOT NULL,
 metadata_json TEXT NOT NULL, flags_json TEXT NOT NULL
);
CREATE TABLE chunks (
 chunk_id TEXT PRIMARY KEY, source_id TEXT NOT NULL REFERENCES sources(source_id),
 ordinal INTEGER NOT NULL, start_cp INTEGER NOT NULL, end_cp INTEGER NOT NULL,
 reading_start_cp INTEGER NOT NULL, reading_end_cp INTEGER NOT NULL,
 line_start INTEGER NOT NULL, line_end INTEGER NOT NULL, role TEXT NOT NULL,
 flags_json TEXT NOT NULL, normalized_text TEXT NOT NULL, mapping_json TEXT NOT NULL,
 structure_json TEXT NOT NULL DEFAULT '{}',
 UNIQUE(source_id,ordinal)
);
CREATE INDEX chunks_source_span ON chunks(source_id,start_cp,end_cp);
CREATE INDEX sources_collection ON sources(collection);
"""
_NEWLINES = re.compile(r"\r\n|\r|\n")
_BOUNDARIES = re.compile(r"[\r\n。！？；]")
_BRACKETS = re.compile(r"[【】（）\[\]()]" )
_OPEN_TO_CLOSE = {"【": "】", "（": "）", "[": "]", "(": ")"}
_FLAG_PATTERNS = {
    "replacement_marker": re.compile("[□〓�]"),
    "private_use": re.compile("[\ue000-\uf8ff\U000f0000-\U000ffffd\U00100000-\U0010fffd]"),
    "supplementary_codepoint": re.compile("[\U00010000-\U0010ffff]"),
    "markup": re.compile(r"<[^>\r\n]*>|(?m:^\s*#{1,6}\s)|\\\["),
    "bracket_marker": _BRACKETS,
}


def _structural_spans(raw: str, body_start: int, source_id: str,
                      segmentation: str = "structure-v3") -> list[dict[str, Any]]:
    # Tests also load this file directly by path, without putting its directory
    # on sys.path. Keep the sibling module independent of import context.
    modules = {
        "structure-v3": ("segmentation.py", "corpus_structure_segmentation_v3"),
        "structure-clean": ("segmentation_clean.py", "corpus_structure_segmentation_clean"),
    }
    module_name, import_name = modules[segmentation]
    module_path = Path(__file__).with_name(module_name)
    spec = importlib.util.spec_from_file_location(import_name, module_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.segment_source(raw, body_start, source_id)


def _fixed_spans(body_start: int, body_end: int):
    for start in range(body_start, body_end, CHUNK_SIZE - CHUNK_OVERLAP):
        end = min(start + CHUNK_SIZE, body_end)
        yield {"start_cp": start, "end_cp": end, "role": "unknown", "structure": {}}
        if end == body_end:
            break


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def _within(path: Path, root: Path) -> bool:
    return path == root or root in path.parents


def _hash_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for data in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(data)
    return digest.hexdigest()


def iter_source_paths(workspace: str | Path) -> list[tuple[str, Path]]:
    """Enumerate the explicit four Wang files and the three external tiers only."""
    root = Path(workspace).resolve(strict=True)
    wang = root / "data" / "A-原著原典"
    allowed = [("wang", wang / name, wang) for name in WANG_NAMES]
    external = root / "data" / "daizhigev20"
    for tier, collection in TIERS:
        directory = external / tier
        if not directory.is_dir():
            raise FileNotFoundError(f"Missing input tier: {directory}")
        allowed.extend((collection, path, directory) for path in directory.rglob("*.md"))
    result = []
    seen = set()
    for collection, path, directory in allowed:
        if not path.is_file():
            raise FileNotFoundError(f"Missing source: {path}")
        resolved = path.resolve(strict=True)
        # Both the whitelist root and each file must stay inside the workspace.
        if not _within(resolved, root) or not _within(resolved, directory.resolve()):
            raise ValueError(f"Source escapes allowed directory: {path}")
        if any(part.is_symlink() or part.is_junction() for part in (path, *path.parents) if _within(part, root)):
            raise ValueError(f"Symlinked/junction source is not accepted: {path}")
        relpath = path.relative_to(root).as_posix()
        if relpath in seen:
            raise ValueError(f"Duplicate source path: {relpath}")
        seen.add(relpath)
        result.append((collection, path))
    return sorted(result, key=lambda item: item[1].relative_to(root).as_posix())


def normalize_with_mapping(text: str, raw_offset: int = 0) -> tuple[str, list[list[Any]]]:
    """Return normalized text and compact, source-absolute span mappings."""
    if not isinstance(raw_offset, int) or raw_offset < 0:
        raise ValueError("raw_offset must be a nonnegative integer")
    output: list[str] = []
    mapping: list[list[Any]] = []
    norm_position = 0
    whitespace: list[int] | None = None

    def emit(value: str, start: int, end: int, kind: str) -> None:
        nonlocal norm_position
        if not value:
            return
        next_position = norm_position + len(value)
        if mapping and mapping[-1][4] == kind:
            previous = mapping[-1]
            if kind == "identity" and previous[3] == start:
                previous[1], previous[3] = next_position, end
            elif kind == "nfkc" and previous[2:4] == [start, end]:
                previous[1] = next_position
            else:
                mapping.append([norm_position, next_position, start, end, kind])
        else:
            mapping.append([norm_position, next_position, start, end, kind])
        output.append(value)
        norm_position = next_position

    for index, character in enumerate(text):
        start = raw_offset + index
        transformed = unicodedata.normalize("NFKC", character)
        for value in transformed:
            if value.isspace():
                if whitespace is None:
                    whitespace = [start, start + 1]
                else:
                    whitespace[1] = start + 1
                continue
            if whitespace is not None:
                emit(" ", *whitespace, "whitespace")
                whitespace = None
            emit(value, start, start + 1, "identity" if transformed == character else "nfkc")
    if whitespace is not None:
        emit(" ", *whitespace, "whitespace")
    return "".join(output), mapping


def normalized_span_to_raw(mapping: list[list[Any]], start: int, end: int) -> tuple[int, int]:
    """Project a nonempty normalized range; reject invalid/empty selections."""
    length = mapping[-1][1] if mapping else 0
    if not isinstance(start, int) or not isinstance(end, int) or not 0 <= start < end <= length:
        raise ValueError("Expected a nonempty normalized [start,end) range")
    raw_start, raw_end = None, None
    for ns, ne, rs, re_, kind in mapping:
        if ne <= start:
            continue
        if ns >= end:
            break
        left, right = max(start, ns), min(end, ne)
        if kind == "identity":
            left_raw, right_raw = rs + left - ns, rs + right - ns
        else:
            left_raw, right_raw = rs, re_
        raw_start = left_raw if raw_start is None else min(raw_start, left_raw)
        raw_end = right_raw if raw_end is None else max(raw_end, right_raw)
    if raw_start is None or raw_end is None:
        raise ValueError("Mapping does not cover selection")
    return raw_start, raw_end


def _frontmatter(raw: str) -> tuple[int, dict[str, Any], dict[str, Any]]:
    """Extract only declared title/author/category; do not resolve work identity."""
    initial = 1 if raw.startswith("\ufeff") else 0
    lines = raw[initial:].splitlines(keepends=True)
    metadata: dict[str, Any] = {
        "declared": {}, "frontmatter_raw": "", "metadata_status": "unverified",
        "work_identity": "unknown", "edition_identity": "unknown",
    }
    if not lines or lines[0].strip() != "---":
        return initial, metadata, {}
    offset = initial + len(lines[0])
    end = None
    header = []
    for line in lines[1:]:
        offset += len(line)
        if line.strip() in {"---", "..."}:
            end = offset
            break
        header.append(line)
    if end is None:
        return initial, metadata, {"unterminated_frontmatter": True}
    metadata["frontmatter_raw"] = raw[initial:end]
    current = None
    for line in header:
        match = re.match(r"^(title|author|category):[ \t]*(.*?)[\r\n]*$", line)
        if match:
            current = match.group(1)
            metadata["declared"][current] = match.group(2)
        elif current == "title" and (nested := re.match(r"^[ \t]+(zh-hans|zh-hant):[ \t]*(.*?)[\r\n]*$", line)):
            title = metadata["declared"].get("title")
            if not isinstance(title, dict):
                title = {"raw_scalar": title} if title else {}
                metadata["declared"]["title"] = title
            title[nested.group(1)] = nested.group(2)
        elif line and not line[0].isspace() and not line.startswith("#"):
            current = None
    return end, metadata, {}


def _display_title(metadata: dict[str, Any], fallback: str) -> str:
    value = metadata["declared"].get("title")
    if isinstance(value, dict):
        value = value.get("zh-hans") or value.get("zh-hant") or value.get("raw_scalar")
    return str(value or fallback).strip().strip("\"'")


def _observations(text: str) -> dict[str, int]:
    return {name: count for name, pattern in _FLAG_PATTERNS.items() if (count := sum(1 for _ in pattern.finditer(text)))}


def _bracket_spans(raw: str, body_start: int) -> tuple[list[int], list[int], list[int]]:
    """Observed outermost simple bracket pairs, not semantic annotation roles."""
    stack: list[tuple[str, int]] = []
    starts, ends, unmatched = [], [], []
    for match in _BRACKETS.finditer(raw, body_start):
        character, position = match.group(), match.start()
        if character in _OPEN_TO_CLOSE:
            stack.append((character, position))
        elif stack and _OPEN_TO_CLOSE[stack[-1][0]] == character:
            opening, start = stack.pop()
            if not stack:
                starts.append(start)
                ends.append(position + 1)
        else:
            unmatched.append(position)
            unmatched.extend(position_ for _, position_ in stack)
            stack.clear()
    unmatched.extend(position for _, position in stack)
    return starts, ends, sorted(unmatched)


def _crossing(starts: list[int], ends: list[int], position: int) -> tuple[int, int] | None:
    index = bisect.bisect_left(starts, position) - 1
    if index >= 0 and position < ends[index]:
        return starts[index], ends[index]
    return None


def _reading_range(raw: str, start: int, end: int, body_start: int,
                   brackets: tuple[list[int], list[int], list[int]]) -> tuple[int, int, dict[str, Any]]:
    spare = READING_LIMIT - (end - start)
    left = max(body_start, start - spare // 2)
    right = min(len(raw), end + spare - (start - left))
    left = max(body_start, start - (READING_LIMIT - (right - start)))
    # Snap inward to generic sentence/newline boundaries, retaining the chunk.
    left_boundary = _BOUNDARIES.search(raw, left, start)
    if left_boundary:
        left = left_boundary.end()
        if left < start and raw[left - 1:left + 1] == "\r\n":
            left += 1
    right_boundaries = list(_BOUNDARIES.finditer(raw, end, right))
    if right_boundaries:
        right = right_boundaries[-1].end()
        if raw[right - 1:right + 1] == "\r\n" and right - left < READING_LIMIT:
            right += 1
    starts, ends, unmatched = brackets
    flags: dict[str, Any] = {}
    if _crossing(starts, ends, start) or _crossing(starts, ends, end):
        flags["chunk_bracket_boundary"] = True
    for boundary in ("left", "right"):
        span = _crossing(starts, ends, left if boundary == "left" else right)
        if span:
            proposed_left, proposed_right = min(left, span[0]), max(right, span[1])
            if proposed_right - proposed_left <= READING_LIMIT:
                left, right = proposed_left, proposed_right
            else:
                flags["reading_bracket_truncated"] = True
    if bisect.bisect_left(unmatched, right) > bisect.bisect_left(unmatched, left):
        flags["unmatched_bracket"] = True
    if unmatched and unmatched[0] < right:
        flags["source_bracket_context_uncertain"] = True
    if left > body_start and raw[left - 1] not in "\r\n。！？；":
        flags["reading_start_hard_boundary"] = True
    if right < len(raw) and raw[right - 1] not in "\r\n。！？；":
        flags["reading_end_hard_boundary"] = True
    return left, right, flags


def _line_starts(raw: str) -> list[int]:
    return [0, *(match.end() for match in _NEWLINES.finditer(raw))] if raw else []


def _validate_mapping(raw: str, row: sqlite3.Row) -> bool:
    start, end = row["start_cp"], row["end_cp"]
    normalized = row["normalized_text"]
    mapping = json.loads(row["mapping_json"])
    # Independent expression of the normalization contract (no call to builder).
    expected = re.sub(r"\s+", " ", "".join(unicodedata.normalize("NFKC", cp) for cp in raw[start:end]))
    if expected != normalized or not mapping:
        return False
    norm_end, covered_raw_end = 0, start
    for segment in mapping:
        if len(segment) != 5:
            return False
        ns, ne, rs, re_, kind = segment
        if not (ns == norm_end and ns < ne <= len(normalized) and start <= rs < re_ <= end and rs <= covered_raw_end):
            return False
        if kind == "identity":
            if ne - ns != re_ - rs or normalized[ns:ne] != raw[rs:re_]:
                return False
        elif kind == "nfkc":
            if re_ - rs != 1 or normalized[ns:ne] not in unicodedata.normalize("NFKC", raw[rs:re_]):
                return False
        elif kind == "whitespace":
            expanded = "".join(unicodedata.normalize("NFKC", cp) for cp in raw[rs:re_])
            if normalized[ns:ne] != " " or not any(cp.isspace() for cp in expanded):
                return False
        else:
            return False
        norm_end, covered_raw_end = ne, max(covered_raw_end, re_)
    return norm_end == len(normalized) and covered_raw_end == end and mapping[0][2] == start


def _validate_database(connection: sqlite3.Connection, segmentation: str = "fixed") -> dict[str, Any]:
    connection.row_factory = sqlite3.Row
    counts = Counter(mapping_errors=0, coverage_errors=0, raw_hash_errors=0, window_errors=0, source_coordinate_errors=0,
                     line_coordinate_errors=0, checked_chunks=0, checked_sources=0, empty_body_sources=0)
    failures = []
    for source in connection.execute("SELECT * FROM sources ORDER BY source_id"):
        counts["checked_sources"] += 1
        raw = source["raw_text"]
        lines = _line_starts(raw)
        if (source["codepoints"] != len(raw) or source["byte_size"] != len(raw.encode("utf-8"))
                or source["line_count"] != len(lines) or not 0 <= source["body_start"] <= source["body_end"] == len(raw)):
            counts["source_coordinate_errors"] += 1
        if hashlib.sha256(raw.encode("utf-8")).hexdigest() != source["sha256"]:
            counts["raw_hash_errors"] += 1
        position, last_start, ordinal = source["body_start"], None, 0
        for row in connection.execute("SELECT * FROM chunks WHERE source_id=? ORDER BY ordinal", (source["source_id"],)):
            counts["checked_chunks"] += 1
            start, end = row["start_cp"], row["end_cp"]
            ordinal += 1
            valid_span = source["body_start"] <= start < end <= source["body_end"]
            if (not valid_span or start > position or row["ordinal"] != ordinal
                    or (last_start is None and start != position)
                    or (last_start is not None and
                        (start != last_start + CHUNK_SIZE - CHUNK_OVERLAP if segmentation == "fixed" else start <= last_start))):
                counts["coverage_errors"] += 1
            if (not valid_span or
                    (end != min(start + CHUNK_SIZE, source["body_end"]) if segmentation == "fixed" else end - start > READING_LIMIT)
                    or not source["body_start"] <= row["reading_start_cp"] <= start < end <= row["reading_end_cp"] <= source["body_end"]
                    or row["reading_end_cp"] - row["reading_start_cp"] > READING_LIMIT):
                counts["window_errors"] += 1
            if segmentation != "fixed":
                structure = json.loads(row["structure_json"])
                if (not structure or not structure["parent_start_cp"] <= start < end <= structure["parent_end_cp"]
                        or not 1 <= structure["part_index"] <= structure["part_count"]):
                    counts["window_errors"] += 1
            if row["line_start"] != bisect.bisect_right(lines, start) or row["line_end"] != bisect.bisect_right(lines, end - 1):
                counts["line_coordinate_errors"] += 1
            if not _validate_mapping(raw, row):
                counts["mapping_errors"] += 1
                if len(failures) < 20:
                    failures.append(row["chunk_id"])
            position, last_start = max(position, end), start
        if position != source["body_end"]:
            counts["coverage_errors"] += 1
        if source["body_start"] == source["body_end"]:
            counts["empty_body_sources"] += 1
    counts["foreign_key_errors"] = len(connection.execute("PRAGMA foreign_key_check").fetchall())
    integrity = [row[0] for row in connection.execute("PRAGMA integrity_check")]
    counts["sqlite_integrity_errors"] = 0 if integrity == ["ok"] else len(integrity)
    return {**dict(counts), "first_mapping_failure_chunk_ids": failures, "sqlite_integrity": integrity}


def _timing(values: list[float]) -> dict[str, Any]:
    ordered = sorted(values)
    return {"count": len(ordered), "unit": "seconds", "p50": statistics.median(ordered) if ordered else 0,
            "p95": ordered[max(0, (95 * len(ordered) + 99) // 100 - 1)] if ordered else 0,
            "total": sum(ordered)}


def build_corpus(workspace: str | Path, output: str | Path,
                 segmentation: str = "structure-clean") -> dict[str, Any]:
    """Create a fresh release; never overwrite, mutate inputs, or use production DBs."""
    if segmentation not in {"structure-v3", "structure-clean", "structure", "fixed"}:
        raise ValueError("segmentation must be 'structure-v3', 'structure-clean', 'structure', or 'fixed'")
    if segmentation == "structure":
        segmentation = "structure-v3"
    started = time.perf_counter()
    root = Path(workspace).resolve(strict=True)
    destination_input = Path(output)
    destination = destination_input.resolve()
    project = root / "solution" / "corpus-standardization"
    if not _within(destination, project) or destination == project:
        raise ValueError("Output must be a new descendant of workspace/solution/corpus-standardization")
    if destination_input.exists() or destination_input.is_symlink() or destination.exists():
        raise FileExistsError(f"Refusing existing output: {destination}")
    input_paths = iter_source_paths(root)
    for _, path in input_paths:
        if _within(path.resolve(), destination) or _within(destination, path.parent.resolve()):
            raise ValueError("Output and input locations overlap")
    destination.mkdir(parents=True, exist_ok=False)
    database = destination / "corpus.sqlite3"
    connection = sqlite3.connect(database)
    connection.executescript(SCHEMA)
    manifest: dict[str, Any] = {
        "schema_version": "corpus-sqlite-v2", "pipeline_version": PIPELINE_VERSION,
        "segmentation_mode": segmentation,
        "normalization_version": NORMALIZATION_VERSION, "mapping_version": MAPPING_VERSION,
        "created_at_utc": datetime.now(timezone.utc).isoformat(), "status": "building",
        "database": database.name, "workspace": str(root), "source_count_discovered": len(input_paths),
        "parameters": {"chunk_size_codepoints": CHUNK_SIZE, "overlap_codepoints": CHUNK_OVERLAP,
                       "reading_limit_codepoints": READING_LIMIT,
                       "structural_target_codepoints": 600, "structural_max_codepoints": 1200},
        "coordinate_contract": "source-absolute Python Unicode codepoints [start,end); raw BOM/CR/LF retained",
        "mapping_fields": ["norm_start", "norm_end", "raw_start", "raw_end", "kind"],
        "normalization_contract": "NFKC applied independently to each codepoint, then consecutive Unicode whitespace collapsed to one ASCII space; no strip; markup retained",
        "input_allowlist": ["data/A-原著原典/" + name for name in WANG_NAMES]
                           + [f"data/daizhigev20/{tier}/**/*.md" for tier, _ in TIERS],
        "files": [], "failed_sources": [],
    }
    source_times, chunk_times = [], []
    flag_counts: Counter[str] = Counter()
    warning_chunks = 0
    sample_heap: list[tuple[int, str]] = []
    try:
        for collection, path in input_paths:
            source_started = time.perf_counter()
            relpath = path.relative_to(root).as_posix()
            data = path.read_bytes()
            digest = hashlib.sha256(data).hexdigest()
            source_id = "src_" + hashlib.sha256(relpath.encode("utf-8")).hexdigest()
            file_record = {"source_id": source_id, "collection": collection, "relpath": relpath,
                           "sha256": digest, "byte_size": len(data)}
            manifest["files"].append(file_record)
            try:
                raw = data.decode("utf-8", errors="strict")
            except UnicodeDecodeError as error:
                failure = {**file_record, "error": "invalid_utf8", "byte_start": error.start, "byte_end": error.end}
                manifest["failed_sources"].append(failure)
                file_record["status"] = "failed"
                source_times.append(time.perf_counter() - source_started)
                continue
            del data
            body_start, metadata, extra_flags = _frontmatter(raw)
            observations = {**_observations(raw), **extra_flags}
            if body_start == len(raw):
                observations["empty_body"] = True
            brackets = _bracket_spans(raw, body_start)
            if brackets[2]:
                observations["unmatched_bracket"] = len(brackets[2])
            lines = _line_starts(raw)
            connection.execute("INSERT INTO sources VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)", (
                source_id, collection, relpath, _display_title(metadata, path.stem), digest,
                "utf-8-bom" if raw.startswith("\ufeff") else "utf-8", raw, body_start, len(raw),
                len(raw), file_record["byte_size"], len(lines), _json(metadata), _json(observations),
            ))
            ordinal = 0
            spans = (_structural_spans(raw, body_start, source_id, segmentation)
                     if segmentation in {"structure-v3", "structure-clean"}
                     else _fixed_spans(body_start, len(raw)))
            for span in spans:
                chunk_started = time.perf_counter()
                start, end = span["start_cp"], span["end_cp"]
                normalized, mapping = normalize_with_mapping(raw[start:end], start)
                left, right, flags = _reading_range(raw, start, end, body_start, brackets)
                flags.update(_observations(raw[start:end]))
                if extra_flags:
                    flags.update(extra_flags)
                role = (span["role"] if segmentation in {"structure-v3", "structure-clean"} else
                        "mixed" if flags.get("markup") or flags.get("bracket_marker") else "unknown")
                ordinal += 1
                chunk_id = "chk_" + hashlib.sha256(f"{source_id}:{digest}:{start}:{end}".encode()).hexdigest()
                connection.execute("INSERT INTO chunks VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)", (
                    chunk_id, source_id, ordinal, start, end, left, right,
                    bisect.bisect_right(lines, start), bisect.bisect_right(lines, end - 1), role,
                    _json(flags), normalized, _json(mapping), _json(span["structure"]),
                ))
                flag_counts.update(flags.keys())
                warning_chunks += bool(flags)
                sample_key = int(hashlib.sha256(chunk_id.encode()).hexdigest(), 16)
                heapq.heappush(sample_heap, (-sample_key, chunk_id))
                if len(sample_heap) > 12:
                    heapq.heappop(sample_heap)
                chunk_times.append(time.perf_counter() - chunk_started)
            connection.commit()
            file_record.update(status="ingested", codepoints=len(raw), body_start=body_start,
                               body_end=len(raw), chunks=ordinal)
            source_times.append(time.perf_counter() - source_started)
        validation_started = time.perf_counter()
        quality = _validate_database(connection, segmentation)
        validation_seconds = time.perf_counter() - validation_started
        hash_mismatches = []
        for item, (_, path) in zip(manifest["files"], input_paths):
            try:
                after = _hash_file(path)
            except OSError as error:
                after = None
                item["after_read_error"] = type(error).__name__
            item["sha256_after"] = after
            item["hash_unchanged"] = after == item["sha256"]
            if not item["hash_unchanged"]:
                hash_mismatches.append(item["relpath"])
        quality.update({"source_hash_mismatches": len(hash_mismatches), "hash_mismatch_paths": hash_mismatches,
                        "source_count_discovered": len(input_paths), "failed_source_count": len(manifest["failed_sources"]),
                        "warning_chunks": warning_chunks, "chunk_flag_counts": dict(flag_counts),
                        "timings": {"source_build": _timing(source_times), "chunk_build": _timing(chunk_times),
                                    "validation_seconds": validation_seconds, "total_seconds": time.perf_counter() - started},
                        "scope": "mechanical full-source/full-chunk invariants; not semantic, editorial, retrieval or model quality"})
        error_keys = ("mapping_errors", "coverage_errors", "raw_hash_errors", "window_errors", "source_coordinate_errors", "line_coordinate_errors",
                      "foreign_key_errors", "sqlite_integrity_errors", "source_hash_mismatches", "failed_source_count")
        passed = not any(quality[key] for key in error_keys)
        quality.update(passed=passed, validation_passed=passed, status="passed" if passed else "failed")
        manifest.update(status="complete" if passed else "failed", validation_passed=passed,
                        source_count=quality["checked_sources"], chunk_count=quality["checked_chunks"],
                        quality_file="quality.json", sample_strategy="12 lowest SHA256(chunk_id), no case-specific selection",
                        sample_chunk_ids=[chunk_id for _, chunk_id in sorted(sample_heap, reverse=True)])
        connection.close()
        connection = None
        manifest["database_sha256"] = _hash_file(database)
        (destination / "quality.json").write_text(json.dumps(quality, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        (destination / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return manifest
    except Exception as error:
        if connection is not None:
            connection.rollback()
            connection.close()
        manifest.update(status="failed", validation_passed=False,
                        failure={"type": type(error).__name__, "message": str(error)})
        (destination / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        raise


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    build = commands.add_parser("build", help="Create a fresh isolated corpus release")
    build.add_argument("--workspace", type=Path, required=True)
    build.add_argument("--output", type=Path, required=True)
    build.add_argument("--segmentation", choices=("structure-clean", "structure-v3", "structure", "fixed"), default="structure-clean")
    arguments = parser.parse_args(argv)
    try:
        manifest = build_corpus(arguments.workspace, arguments.output, arguments.segmentation)
    except (OSError, ValueError, sqlite3.Error) as error:
        print(_json({"status": "failed", "error": type(error).__name__, "message": str(error)}))
        return 2
    print(_json({key: manifest[key] for key in ("status", "validation_passed", "source_count", "chunk_count")}))
    return 0 if manifest["validation_passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
