from __future__ import annotations

import re
import unicodedata
from typing import Any


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
    """Return plain/normalized text without treating font size as a note."""

    plain_text = HTML_TAG_RE.sub("", raw_text)
    normalized_text = normalize_for_match(plain_text)

    return {
        "raw_text": raw_text,
        "plain_text": plain_text,
        "normalized_text": normalized_text,
        "inline_notes": [],
    }
