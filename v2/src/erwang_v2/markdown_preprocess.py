from __future__ import annotations

import re
import unicodedata
from typing import Any


SMALL_TAG_RE = re.compile(r"<small\b[^>]*>(.*?)</small>", re.IGNORECASE | re.DOTALL)
HTML_TAG_RE = re.compile(r"<[^>]+>")


def normalize_for_match(text: str) -> str:
    """Normalize only Unicode compatibility forms and whitespace for matching.

    This deliberately does not convert traditional and simplified Chinese, or
    silently repair OCR characters. Those are different evidence states and
    must remain visible to a reviewer.
    """

    compatibility_text = unicodedata.normalize("NFKC", text)
    return re.sub(r"[ 	\r\n]+", " ", compatibility_text).strip()


def preprocess_text(raw_text: str) -> dict[str, Any]:
    """Return plain/normalized text and auditable small-run notes."""

    plain_parts: list[str] = []
    inline_notes: list[dict[str, Any]] = []
    plain_length = 0
    cursor = 0

    for match in SMALL_TAG_RE.finditer(raw_text):
        normal_text = raw_text[cursor:match.start()]
        plain_parts.append(normal_text)
        plain_length += len(normal_text)

        note_text = match.group(1)
        start_char = plain_length
        plain_parts.append(note_text)
        plain_length += len(note_text)
        inline_notes.append(
            {
                "text": note_text,
                "start_char": start_char,
                "end_char": plain_length,
                "note_type": "unknown",
                "source_marker": "docx_small_run",
                "confidence": "rule_high",
            }
        )
        cursor = match.end()

    plain_parts.append(raw_text[cursor:])
    plain_text = HTML_TAG_RE.sub("", "".join(plain_parts))
    normalized_text = normalize_for_match(plain_text)

    return {
        "raw_text": raw_text,
        "plain_text": plain_text,
        "normalized_text": normalized_text,
        "inline_notes": inline_notes,
    }
