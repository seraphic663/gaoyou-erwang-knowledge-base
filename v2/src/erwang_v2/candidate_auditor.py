from __future__ import annotations

from typing import Any, Iterable


def audit_candidates(
    candidates: Iterable[dict[str, Any]],
    passages: Iterable[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Check candidate references without making a semantic judgment."""

    passage_ids = {p.get("passage_id") for p in passages}
    results: list[dict[str, Any]] = []
    for item in candidates:
        errors: list[str] = []
        passage_id = item.get("passage_id")
        if passage_id not in passage_ids:
            errors.append("missing_passage_id")
        if not item.get("text", "").strip():
            errors.append("empty_candidate_text")
        results.append(
            {
                "candidate_id": item.get("candidate_id"),
                "passage_id": passage_id,
                "machine_status": "approved" if not errors else "rejected",
                "errors": errors,
                "risk_flags": item.get("risk_flags", []),
            }
        )
    return results
