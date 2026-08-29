from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from .markdown_preprocess import preprocess_text


HEADING_RE = re.compile(r"^(#{1,6})[ \t]+(.+?)\s*$")


def _title_kind(title: str) -> str:
    if "序" in title or "凡例" in title:
        return "preface"
    if "卷" in title:
        return "volume"
    return "unknown"


def build_passages(
    source_path: str | Path,
    work_key: str,
    document_title: str | None = None,
) -> list[dict[str, Any]]:
    """Build a small, deterministic passage preview from a Markdown file."""

    path = Path(source_path)
    lines = path.read_text(encoding="utf-8").splitlines()
    passages: list[dict[str, Any]] = []
    current_document = document_title or ""
    current_section = ""
    current_entry = ""
    body: list[str] = []
    body_start: int | None = None
    ordinal = 0

    def flush(end_line: int) -> None:
        nonlocal body, body_start, ordinal
        raw_text = "\n".join(body).strip()
        body = []
        if not raw_text:
            body_start = None
            return

        ordinal += 1
        processed = preprocess_text(raw_text)
        passage_id = f"{work_key}_{ordinal:04d}"
        title_path = [
            item
            for item in (current_document, current_section, current_entry)
            if item
        ]
        notes = []
        for index, note in enumerate(processed["inline_notes"], start=1):
            note = dict(note)
            note["note_id"] = f"{passage_id}_note_{index:02d}"
            note["passage_id"] = passage_id
            notes.append(note)

        passages.append(
            {
                "passage_id": passage_id,
                "work_key": work_key,
                "document_title": current_document,
                "section_title": current_section or None,
                "entry_title": current_entry or None,
                "entry_kind": _title_kind(current_entry or current_section),
                "title_path": title_path,
                "local_ordinal": ordinal,
                "md_line_start": body_start,
                "md_line_end": end_line,
                "raw_text": processed["raw_text"],
                "plain_text": processed["plain_text"],
                "normalized_text": processed["normalized_text"],
                "source_file": str(path),
                "inline_notes": notes,
            }
        )
        body_start = None

    for line_number, line in enumerate(lines, start=1):
        heading = HEADING_RE.match(line)
        if heading and len(heading.group(1)) <= 3:
            flush(line_number - 1)
            level = len(heading.group(1))
            title = heading.group(2).strip()
            if level == 1:
                current_document = title
                current_section = ""
                current_entry = ""
            elif level == 2:
                current_section = title
                current_entry = ""
            else:
                current_entry = title
            continue

        if line.strip():
            if body_start is None:
                body_start = line_number
            body.append(line)

    flush(len(lines))
    return passages
