from __future__ import annotations

from typing import Any, Iterable


SIGNAL_TERMS = ("也", "一声之转", "當作", "当作", "读为", "疑")


def extract_candidates(passages: Iterable[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    """Produce explainable candidates, never final research conclusions."""

    parsed_items: list[dict[str, Any]] = []
    candidate_items: list[dict[str, Any]] = []
    skipped_items: list[dict[str, Any]] = []

    for passage in passages:
        text = passage.get("plain_text", "")
        rule_hits = [term for term in SIGNAL_TERMS if term in text]
        risk_flags: list[str] = []
        if passage.get("inline_notes"):
            risk_flags.append("has_small_notes")
        if len(text) > 800:
            risk_flags.append("long_passage")

        item = {
            "candidate_id": f"{passage['passage_id']}_candidate",
            "passage_id": passage["passage_id"],
            "text": text,
            "rule_hits": rule_hits,
            "risk_flags": risk_flags,
            "need_review": True,
        }

        if rule_hits:
            if risk_flags:
                candidate_items.append(item)
            else:
                parsed_items.append(item)
        else:
            skipped_items.append(
                {
                    "passage_id": passage["passage_id"],
                    "skipped_reason": "no_initial_signal",
                    "risk_flags": risk_flags,
                }
            )

    return {
        "parsed_items": parsed_items,
        "candidate_items": candidate_items,
        "skipped_items": skipped_items,
    }
