from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Iterable

from .markdown_preprocess import normalize_for_match


RELATION_MAP = {
    "误字": ("校勘", "误字"),
    "通假": ("字际关系", "通假"),
    "异体": ("字际关系", "异体"),
    "同义": ("训释", "同义"),
    "声近义同": ("训释", "声训"),
}

PROCESS_FIELD_MAP = {
    "发疑": "problem_discovery",
    "取证": "evidence_collection",
    "释理": "reasoning",
}


def load_legacy_ai_json(path: str | Path) -> dict[str, Any]:
    """Load the current AI JSON container without changing the source file."""

    source = Path(path)
    value = json.loads(source.read_text(encoding="utf-8-sig"))
    if isinstance(value, dict) and isinstance(value.get("cases"), list):
        return value
    if isinstance(value, list):
        return {"cases": value, "database_ingestion": None}
    if isinstance(value, dict) and "case_title" in value:
        return {"cases": [value], "database_ingestion": None}
    raise ValueError(f"unsupported_legacy_ai_json_shape:{source}")


def select_legacy_case(
    container: dict[str, Any], case_title: str | None = None
) -> tuple[int, dict[str, Any]]:
    cases = container.get("cases") or []
    if not cases:
        raise ValueError("legacy_ai_json_has_no_cases")
    if case_title is None:
        return 0, cases[0]
    for index, case in enumerate(cases):
        if case.get("case_title") == case_title:
            return index, case
    raise ValueError(f"legacy_case_not_found:{case_title}")


def _sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _match_in_passage(needle: str, passage: dict[str, Any]) -> dict[str, Any] | None:
    if not needle:
        return None
    plain_text = passage.get("plain_text", "")
    exact_start = plain_text.find(needle)
    if exact_start >= 0:
        return {
            "mode": "exact",
            "field": "plain_text",
            "start_char": exact_start,
            "end_char": exact_start + len(needle),
        }

    normalized_needle = normalize_for_match(needle)
    normalized_text = passage.get("normalized_text") or normalize_for_match(plain_text)
    if normalized_needle and normalized_needle in normalized_text:
        return {
            "mode": "normalized",
            "field": "normalized_text",
            "start_char": None,
            "end_char": None,
        }
    return None


def find_passage_matches(
    needle: str, passages: Iterable[dict[str, Any]]
) -> list[dict[str, Any]]:
    matches: list[dict[str, Any]] = []
    for passage in passages:
        match = _match_in_passage(needle, passage)
        if match:
            matches.append({"passage": passage, "match": match})
    return matches


def _choose_match(
    matches: list[dict[str, Any]], preferred_title: str | None = None
) -> dict[str, Any] | None:
    if not matches:
        return None

    def score(item: dict[str, Any]) -> tuple[int, int, int]:
        passage = item["passage"]
        match = item["match"]
        title_bonus = int(preferred_title is not None and passage.get("entry_title") == preferred_title)
        exact_bonus = int(match.get("mode") == "exact")
        # Prefer a title-specific, exact match, then the shorter passage. The
        # latter avoids selecting a large preceding section when both contain
        # the same target phrase.
        return (title_bonus, exact_bonus, -len(passage.get("plain_text", "")))

    return max(matches, key=score)


def _location(
    passage: dict[str, Any] | None, match: dict[str, Any] | None
) -> dict[str, Any] | None:
    if passage is None or match is None:
        return None
    location: dict[str, Any] = {
        "passage_id": passage.get("passage_id"),
        "source_file": passage.get("source_file"),
        "source_file_sha256": passage.get("source_file_sha256"),
        "md_line_start": passage.get("md_line_start"),
        "md_line_end": passage.get("md_line_end"),
        "title_path": passage.get("title_path", []),
        "match_mode": match.get("mode"),
        "match_field": match.get("field"),
    }
    if match.get("start_char") is not None:
        location["start_char"] = match["start_char"]
        location["end_char"] = match["end_char"]
    return location


def _map_relation(raw_relation: str | None) -> tuple[str, str | None]:
    if raw_relation in RELATION_MAP:
        return RELATION_MAP[raw_relation]
    if raw_relation in {"训释", "校勘", "字际关系", "虚词用法", "句义解释", "未定"}:
        return raw_relation, None
    return "未定", raw_relation


def _map_process_steps(
    steps: Iterable[dict[str, Any]], fallback_problem: str | None
) -> tuple[dict[str, str | None], dict[str, Any]]:
    fields: dict[str, str | None] = {
        "problem_discovery": fallback_problem,
        "research_question": None,
        "evidence_collection": None,
        "reasoning": None,
        "conclusion": None,
    }
    retained_steps: list[dict[str, Any]] = []
    unmapped_types: list[str] = []
    for step in steps:
        step_type = step.get("step_type")
        text = step.get("text")
        retained_steps.append(
            {
                "step_type": step_type,
                "text": text,
                "source_paragraph_indexes": step.get("source_paragraph_indexes", []),
                "source_comment_ids": step.get("source_comment_ids", []),
            }
        )
        if step_type in PROCESS_FIELD_MAP:
            fields[PROCESS_FIELD_MAP[step_type]] = text
        elif step_type == "结论":
            fields["conclusion"] = text
        elif step_type == "立论":
            # “立论” is retained, but is not silently relabeled as a
            # research question because the old schema does not preserve a
            # question-shaped field.
            unmapped_types.append(step_type)
        elif step_type:
            unmapped_types.append(step_type)
    return fields, {
        "legacy_process_steps": retained_steps,
        "unmapped_step_types": sorted(set(unmapped_types)),
    }


def adapt_legacy_case(
    legacy_case: dict[str, Any],
    passages: Iterable[dict[str, Any]],
    *,
    source_markdown: str | Path,
    legacy_ai_json: str | Path,
    case_index: int,
    submitted_by: str = "legacy_ai_json",
    additional_provenance: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Map one legacy AI case into V2 while retaining migration evidence."""

    passage_list = list(passages)
    target_text = legacy_case.get("target_text", "")
    source_match = _choose_match(
        find_passage_matches(target_text, passage_list),
        preferred_title=legacy_case.get("case_title"),
    )
    source_passage = source_match["passage"] if source_match else None

    term_relations: list[dict[str, Any]] = []
    for term in legacy_case.get("terms", []):
        relation_type, relation_subtype = _map_relation(term.get("relation_type"))
        term_relations.append(
            {
                "source_term": term.get("term", ""),
                "target_term": term.get("related_term", ""),
                "relation_type": relation_type,
                "relation_subtype": relation_subtype,
                "relation_note": term.get("note"),
                "legacy_term_type": term.get("term_type"),
                "legacy_source_paragraph_indexes": term.get("source_paragraph_indexes", []),
            }
        )

    evidences: list[dict[str, Any]] = []
    for evidence in legacy_case.get("evidences", []):
        quote = evidence.get("quote", "")
        match = _choose_match(find_passage_matches(quote, passage_list))
        passage = match["passage"] if match else None
        match_data = match["match"] if match else None
        quote_check = "unchecked"
        if match_data:
            quote_check = (
                "passed" if match_data["mode"] == "exact" else "normalized_passed"
            )
        elif quote:
            quote_check = "failed"
        evidences.append(
            {
                "quote": quote,
                "evidence_role": evidence.get("role"),
                "source_work": evidence.get("work"),
                "passage_id": passage.get("passage_id") if passage else None,
                "quote_sha256": _sha256(quote) if quote else None,
                "quote_check": quote_check,
                "source_location": _location(passage, match_data),
                "legacy_evidence_type": evidence.get("evidence_type"),
                "legacy_source_paragraph_indexes": evidence.get("source_paragraph_indexes", []),
            }
        )

    process_fields, process_migration = _map_process_steps(
        legacy_case.get("process_steps", []), legacy_case.get("problem")
    )
    conclusion = legacy_case.get("conclusion") or process_fields["conclusion"]
    if not conclusion:
        conclusion = legacy_case.get("claim", "")

    provenance = {
        "source_markdown": str(source_markdown),
        "legacy_ai_json": str(legacy_ai_json),
        "legacy_case_index": case_index,
        "database_ingestion": legacy_case.get("database_ingestion"),
    }
    if additional_provenance:
        provenance.update(additional_provenance)

    return {
        "schema_version": "annotation_case.v1",
        "case_id": f"legacy-ai:{legacy_case.get('database_ingestion', {}).get('annotation_case_id', case_index)}",
        "case_title": legacy_case.get("case_title", ""),
        "submitted_by": submitted_by,
        "reviewed_by": None,
        "source_work": legacy_case.get("source_work", ""),
        "source_passage_id": source_passage.get("passage_id") if source_passage else None,
        "source_location": _location(
            source_passage, source_match["match"] if source_match else None
        ),
        "target_work": legacy_case.get("target_work", ""),
        "target_text": target_text,
        "target_location": _location(
            source_passage, source_match["match"] if source_match else None
        ),
        "term_relations": term_relations,
        "evidences": evidences,
        **process_fields,
        "conclusion": conclusion,
        "method_profile": {
            "legacy_method_tags": legacy_case.get("method_tags", []),
            "mapping_policy": "legacy_relation_type_to_v2_relation_type",
        },
        "machine_result": {
            "status": "pending",
            "validator": "erwang_v2.validate_annotation_case",
        },
        "human_review": {
            "status": "pending",
            "legacy_status": legacy_case.get("status"),
            "legacy_certainty": legacy_case.get("certainty"),
        },
        "_migration": {
            "source_format": "legacy_ai_json",
            "legacy_problem": legacy_case.get("problem"),
            "legacy_claim": legacy_case.get("claim"),
            "legacy_status": legacy_case.get("status"),
            "legacy_certainty": legacy_case.get("certainty"),
            **process_migration,
            "provenance": provenance,
        },
    }
