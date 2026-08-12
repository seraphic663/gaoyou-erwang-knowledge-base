from __future__ import annotations

import hashlib
import json
import re
import unicodedata
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


def normalize_work_name(value: str | None) -> str:
    """Normalize a work label for comparison without changing its display form."""

    return normalize_for_match(value or "").strip().strip("《》")


def _compact_title(value: str | None) -> str:
    """Remove markup and punctuation for conservative heading comparison."""

    # Pronunciation/variant notes inside <small> are not lexical heading
    # tokens.  Remove the whole run before comparing a legacy title with a
    # Markdown heading.
    text = re.sub(r"<small\b[^>]*>.*?</small>", "", value or "", flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r"<[^>]+>", "", text)
    text = normalize_for_match(text)
    return "".join(
        char
        for char in text
        if not unicodedata.category(char).startswith(("P", "Z"))
    )


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
    matches: list[dict[str, Any]],
    preferred_title: str | None = None,
    preferred_passage_id: str | None = None,
) -> dict[str, Any] | None:
    if not matches:
        return None

    def score(item: dict[str, Any]) -> tuple[int, int, int, int]:
        passage = item["passage"]
        match = item["match"]
        passage_bonus = int(
            preferred_passage_id is not None
            and passage.get("passage_id") == preferred_passage_id
        )
        title_bonus = int(preferred_title is not None and passage.get("entry_title") == preferred_title)
        exact_bonus = int(match.get("mode") == "exact")
        # Prefer an explicit entry hint, then a title-specific exact match, and
        # only then the shorter passage. Single-character target_text values
        # are common in 经传释词 and otherwise select unrelated passages.
        return (
            passage_bonus,
            title_bonus,
            exact_bonus,
            -len(passage.get("plain_text", "")),
        )

    return max(matches, key=score)


def _preferred_source_passage_id(
    legacy_case: dict[str, Any], passages: list[dict[str, Any]]
) -> str | None:
    """Return a source-entry hint when the legacy target text is ambiguous.

    These are source-structure rules, not evidence guesses.  The 13 migrated
    经传释词 cases all come from the Markdown entry ``以已``; the two Guangya
    cases identify their entries by the long lexical heading in the legacy
    case title.  If a future case does not meet the conservative threshold,
    normal text matching remains in control.
    """

    source_work = normalize_work_name(legacy_case.get("source_work"))
    case_title = _compact_title(legacy_case.get("case_title"))

    if source_work == "经传释词":
        for passage in passages:
            if _compact_title(passage.get("entry_title")) == "以已":
                return passage.get("passage_id")
        return None

    if source_work == "广雅疏证":
        prefix = case_title[:8]
        if not prefix:
            return None
        for passage in passages:
            entry_title = _compact_title(passage.get("entry_title"))
            if entry_title.startswith(prefix):
                return passage.get("passage_id")
        # In the extracted Guangya Markdown the first case is in the body of
        # a passage whose preceding heading is a different lexical item.  A
        # long, punctuation-free prefix still gives a safe block-level anchor.
        for passage in passages:
            if prefix in _compact_title(passage.get("plain_text")):
                return passage.get("passage_id")
        return None

    if source_work == "读书杂志":
        target_prefix = _compact_title(legacy_case.get("target_text"))
        if target_prefix:
            for passage in passages:
                if target_prefix in _compact_title(passage.get("plain_text")):
                    return passage.get("passage_id")

    return None


def _entry_hint_match(passage: dict[str, Any]) -> dict[str, Any]:
    """Create a location match when an entry heading, not a text substring, is the anchor."""

    return {
        "mode": "entry_hint",
        "field": "entry_title",
        "start_char": None,
        "end_char": None,
    }


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


def _fill_machine_process_fields(
    fields: dict[str, str | None],
    legacy_case: dict[str, Any],
    *,
    evidence_count: int,
    source_passage_id: str | None,
) -> dict[str, str]:
    """Complete the five workflow fields without inventing a scholarly claim.

    Old AI files use a partially different process vocabulary and often omit a
    question-shaped field.  These replacements describe what the migration
    machine did and what remains to be checked; they are deliberately not
    presented as a new interpretation of the Wang text.
    """

    case_label = (
        legacy_case.get("case_title")
        or legacy_case.get("target_text")
        or "未命名旧 AI 案例"
    )
    statuses: dict[str, str] = {}
    fallback_values = {
        "problem_discovery": (
            f"机器迁移发现：旧 AI 案例“{case_label}”需要将目标字词、原始引文和来源位置"
            "重新挂接到 annotation_case.v1。"
        ),
        "research_question": (
            f"机器待核问题：案例“{case_label}”的字词关系和引文，能否逐条回到登记的王氏原典 passage"
            "或已登记的外部底本，并确认目标作品与目标位置？"
        ),
        "evidence_collection": (
            f"机器证据整理：已保留 {evidence_count} 条 quote、旧 full_json 段落索引和当前来源解析状态；"
            "外部典籍引文仍须独立底本核验。"
        ),
        "reasoning": (
            "机器定位链：旧 AI 字段 → 王氏 Markdown source passage → quote/source_work 匹配 → "
            "canonical、secondary 或 external pending 状态；未进行语义裁判。"
        ),
        "conclusion": (
            "机器迁移结论：结构化和定位草稿已保存，学术结论、外部版本和目标位置仍待人工审校。"
        ),
    }
    for field, fallback in fallback_values.items():
        value = fields.get(field)
        if isinstance(value, str) and value.strip():
            fields[field] = value.strip()
            statuses[field] = "source_mapped"
        else:
            fields[field] = fallback
            statuses[field] = "machine_synthesized"
    if source_passage_id:
        statuses["source_passage_id"] = "resolved_by_markdown_match"
    else:
        statuses["source_passage_id"] = "unresolved_pending_source_match"
    return statuses


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
    preferred_passage_id = _preferred_source_passage_id(legacy_case, passage_list)
    source_match = _choose_match(
        find_passage_matches(target_text, passage_list),
        preferred_title=legacy_case.get("case_title"),
        preferred_passage_id=preferred_passage_id,
    )
    if source_match is None and preferred_passage_id:
        hinted_passage = next(
            (
                passage
                for passage in passage_list
                if passage.get("passage_id") == preferred_passage_id
            ),
            None,
        )
        if hinted_passage is not None:
            source_match = {
                "passage": hinted_passage,
                "match": _entry_hint_match(hinted_passage),
            }
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
    primary_work = normalize_work_name(legacy_case.get("source_work"))
    for evidence in legacy_case.get("evidences", []):
        quote = evidence.get("quote", "")
        primary_match = _choose_match(find_passage_matches(quote, passage_list))
        cited_work = normalize_work_name(evidence.get("work"))
        same_as_primary = bool(cited_work and cited_work == primary_work)
        cited_match = primary_match if same_as_primary else None
        passage = cited_match["passage"] if cited_match else None
        match_data = cited_match["match"] if cited_match else None
        quote_check = "unchecked"
        if match_data:
            quote_check = (
                "passed" if match_data["mode"] == "exact" else "normalized_passed"
            )
        elif quote and same_as_primary:
            quote_check = "failed"

        secondary_location = (
            _location(primary_match["passage"], primary_match["match"])
            if primary_match and not same_as_primary
            else None
        )
        if cited_match:
            source_resolution = "canonical_source_passage"
            cited_work_match_status = "matched"
        elif same_as_primary:
            source_resolution = "primary_source_no_match"
            cited_work_match_status = "not_found"
        elif primary_match:
            source_resolution = "secondary_citation_match"
            cited_work_match_status = "external_source_pending"
        else:
            source_resolution = "external_source_pending"
            cited_work_match_status = "external_source_pending"
        evidences.append(
            {
                "quote": quote,
                "evidence_role": evidence.get("role"),
                "source_work": evidence.get("work"),
                "passage_id": passage.get("passage_id") if passage else None,
                "quote_sha256": _sha256(quote) if quote else None,
                "quote_check": quote_check,
                "source_location": _location(passage, match_data),
                "source_resolution": source_resolution,
                "cited_work_match_status": cited_work_match_status,
                "secondary_citation_passage_id": (
                    primary_match["passage"].get("passage_id")
                    if primary_match and not same_as_primary
                    else None
                ),
                "secondary_citation_location": secondary_location,
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
    process_fields["conclusion"] = conclusion
    process_field_status = _fill_machine_process_fields(
        process_fields,
        legacy_case,
        evidence_count=len(evidences),
        source_passage_id=source_passage.get("passage_id") if source_passage else None,
    )
    conclusion = process_fields["conclusion"] or "机器迁移结论：待人工审校。"
    process_text = "\n".join(
        f"{field}: {process_fields[field]}"
        for field in ("problem_discovery", "research_question", "evidence_collection", "reasoning", "conclusion")
    )

    provenance = {
        "source_file": str(legacy_ai_json),
        "source_markdown": str(source_markdown),
        "legacy_ai_json": str(legacy_ai_json),
        "legacy_case_index": case_index,
        "database_ingestion": legacy_case.get("database_ingestion"),
    }
    if additional_provenance:
        provenance.update(additional_provenance)

    target_work = legacy_case.get("target_work", "")
    target_works = [target_work] if target_work else []
    target_scope = (
        {
            "status": "resolved",
            "target_works": target_works,
            "resolution_source": "legacy_ai_json",
        }
        if target_works
        else {
            "status": "unresolved",
            "target_works": [],
            "reason": "legacy_target_work_empty",
        }
    )

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
        "target_work": target_work,
        "target_works": target_works,
        "target_scope": target_scope,
        "target_text": target_text,
        "target_location": _location(
            source_passage, source_match["match"] if source_match else None
        ),
        "term_relations": term_relations,
        "evidences": evidences,
        "evidence_state": "present" if evidences else "source_no_citation",
        **process_fields,
        "process_text": process_text,
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
            "source_layer": "legacy_ai_json_output",
            "transformation_kind": "legacy_ai_json_reprocessing",
            "transformation_description": "旧 AI JSON 经字段、段落、证据和状态边界适配为 annotation_case.v1；不重新证明学术结论。",
            "legacy_problem": legacy_case.get("problem"),
            "legacy_claim": legacy_case.get("claim"),
            "legacy_status": legacy_case.get("status"),
            "legacy_certainty": legacy_case.get("certainty"),
            "machine_filled_process_fields": process_field_status,
            **process_migration,
            "provenance": provenance,
        },
    }
