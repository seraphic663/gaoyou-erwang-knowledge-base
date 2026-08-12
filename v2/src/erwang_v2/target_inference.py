from __future__ import annotations

import re
from typing import Any

from .markdown_preprocess import normalize_for_match


WORK_SEPARATOR_RE = re.compile(r"\s*(?:与|和|及|、|,|，|;|；)\s*")
BOOK_TITLE_RE = re.compile(r"《[^》]+》")


def _clean_work_label(value: str) -> str:
    text = str(value or "").strip()
    text = text.strip("《》 \t\r\n")
    return " ".join(text.split())


def _work_labels(raw_value: str) -> list[str]:
    """Split an explicit citation label into conservative work candidates."""

    raw = str(raw_value or "").strip()
    if not raw:
        return []

    marked = BOOK_TITLE_RE.findall(raw)
    if marked:
        labels = [_clean_work_label(item) for item in marked]
        return [item for item in labels if item]

    return [
        _clean_work_label(item)
        for item in WORK_SEPARATOR_RE.split(raw)
        if _clean_work_label(item)
    ]


def infer_target_scope(case: dict[str, Any]) -> dict[str, Any]:
    """Infer candidate target works from explicit evidence source labels.

    This is intentionally not a resolution. Evidence source labels identify
    texts cited by the legacy annotation, but they do not prove that every
    cited text is the case's sole target work. The result therefore uses the
    ``machine_inferred`` scope and records evidence indexes for later review.
    """

    explicit_target = str(case.get("target_work") or "").strip()
    if explicit_target:
        return {
            "status": "resolved",
            "target_works": [explicit_target],
            "resolution_source": "legacy_ai_json",
        }

    candidates: list[str] = []
    normalized_seen: set[str] = set()
    evidence_indexes: list[int] = []
    for index, evidence in enumerate(case.get("evidences") or []):
        labels = _work_labels(evidence.get("source_work", ""))
        if not labels:
            continue
        evidence_indexes.append(index)
        for label in labels:
            normalized = normalize_for_match(label).strip()
            if normalized and normalized not in normalized_seen:
                normalized_seen.add(normalized)
                candidates.append(label)

    if not candidates:
        return {
            "status": "unresolved",
            "target_works": [],
            "reason": "no_explicit_evidence_source_label",
            "resolution_source": "machine_target_inference",
            "evidence_indexes": evidence_indexes,
        }

    return {
        "status": "machine_inferred",
        "target_works": candidates,
        "candidate_works": candidates,
        "reason": "derived_from_explicit_legacy_evidence_source_labels",
        "resolution_source": "machine_target_inference",
        "evidence_indexes": evidence_indexes,
        "confidence": "candidate_only",
    }
