from __future__ import annotations

from pathlib import Path
from typing import Any, Iterable


def _location(passage: dict[str, Any]) -> dict[str, Any]:
    return {
        "passage_id": passage.get("passage_id"),
        "source_file": passage.get("source_file"),
        "md_line_start": passage.get("md_line_start"),
        "md_line_end": passage.get("md_line_end"),
        "title_path": passage.get("title_path", []),
    }


def build_candidate_records(
    passages: Iterable[dict[str, Any]],
    layers: dict[str, list[dict[str, Any]]],
    audit: Iterable[dict[str, Any]],
    *,
    source_work: str,
    source_document_id: str,
    source_file: str,
) -> list[dict[str, Any]]:
    """Combine extractor output and audit output into V2 candidate records."""

    passage_map = {item.get("passage_id"): item for item in passages}
    extracted = {
        item.get("candidate_id"): item
        for layer in ("parsed_items", "candidate_items")
        for item in layers.get(layer, [])
    }
    records: list[dict[str, Any]] = []
    for result in audit:
        candidate_id = result.get("candidate_id")
        extracted_item = extracted.get(candidate_id, {})
        passage = passage_map.get(result.get("passage_id"), {})
        records.append(
            {
                "candidate_id": candidate_id,
                "source_document_id": source_document_id,
                "passage_id": result.get("passage_id"),
                "work_key": passage.get("work_key"),
                "source_work": source_work,
                "candidate_text": extracted_item.get("text", ""),
                "rule_hits": extracted_item.get("rule_hits", []),
                "risk_flags": result.get("risk_flags", []),
                "candidate_status": result.get("machine_status", "pending"),
                "output_case_id": None,
                "provenance": {
                    "source_kind": "original_markdown",
                    "source_layer": "original_text_candidate",
                    "transformation_kind": "original_text_machine_extraction",
                    "source_file": source_file,
                    "source_document_id": source_document_id,
                    "passage_id": result.get("passage_id"),
                    "source_location": _location(passage),
                    "candidate_id": candidate_id,
                    "rule_hits": extracted_item.get("rule_hits", []),
                    "risk_flags": result.get("risk_flags", []),
                    "audit_status": result.get("machine_status"),
                    "audit_errors": result.get("errors", []),
                    "output_schema": "candidate_item.v1",
                },
            }
        )
    return records


def candidate_payload(
    candidate: dict[str, Any], passage: dict[str, Any], *, prompt_version: str
) -> dict[str, Any]:
    """Build the inspectable payload sent to an optional candidate AI call."""

    return {
        "schema_version": "candidate_ai_input.v1",
        "prompt_version": prompt_version,
        "source_work": candidate.get("source_work"),
        "candidate_id": candidate.get("candidate_id"),
        "source_passage_id": candidate.get("passage_id"),
        "source_location": _location(passage),
        "candidate_text": candidate.get("candidate_text", ""),
        "rule_hits": candidate.get("rule_hits", []),
        "risk_flags": candidate.get("risk_flags", []),
        "instructions": [
            "只依据 candidate_text 生成机器草稿，不补充外部典籍或外部引文。",
            "quote 必须是 candidate_text 的连续原文子串；无法确定的字段保留空值或未定。",
            "target_work 不由 source_work 推断；没有明确对象时保持空并标记 unresolved。",
            "输出 annotation_case.v1 对象，不代表人工审校或学术结论已确认。",
        ],
    }


def _first_nonempty(value: Any, fallback: str) -> str:
    if isinstance(value, str) and value.strip():
        return value.strip()
    return fallback


def fill_missing_process_fields(case: dict[str, Any]) -> dict[str, Any]:
    """Fill workflow fields with auditable machine steps when input omitted them."""

    source_work = case.get("source_work") or "当前王氏原典"
    target_text = case.get("target_text") or case.get("case_title") or "未定"
    evidence_count = len(case.get("evidences") or [])
    fallback_values = {
        "problem_discovery": (
            f"机器候选发现：在 {source_work} 的 source passage 中登记候选“{target_text}”，"
            "并准备转换为 annotation_case.v1。"
        ),
        "research_question": (
            f"机器待核问题：候选“{target_text}”涉及的字词关系，能否由当前 {source_work} passage "
            "及后续登记的独立证据支持？"
        ),
        "evidence_collection": (
            f"机器证据整理：当前保留 {evidence_count} 条证据；引文只接受 supplied Wang canonical "
            "passage 的连续原文，外部引文未由本适配器补入。"
        ),
        "reasoning": (
            "机器定位规则：source_work/source_passage/location 来自原典 Markdown，quote 只做 exact "
            "匹配；未进行语义判断或人工学术审校。"
        ),
        "conclusion": "机器草稿：结构化和来源定位已完成，学术结论待人工审校。",
    }
    status: dict[str, str] = {}
    for field, fallback in fallback_values.items():
        value = case.get(field)
        if isinstance(value, str) and value.strip():
            case[field] = value.strip()
            status[field] = "source_or_ai_mapped"
        else:
            case[field] = fallback
            status[field] = "machine_synthesized"
    case["process_text"] = "\n".join(
        f"{field}: {case[field]}"
        for field in (
            "problem_discovery",
            "research_question",
            "evidence_collection",
            "reasoning",
            "conclusion",
        )
    )
    migration = case.setdefault("_migration", {})
    migration["machine_filled_process_fields"] = status
    migration["process_boundary"] = (
        "字段完整性由机器补齐；补齐文字描述迁移和定位动作，不代表人文学术结论。"
    )
    return case


def normalize_ai_case(
    raw: dict[str, Any],
    *,
    candidate: dict[str, Any],
    passage: dict[str, Any],
    source_file: str,
    model: str,
    prompt_version: str,
) -> dict[str, Any]:
    """Normalize one AI response while enforcing source-text boundaries."""

    passage_text = passage.get("plain_text", "")
    entry_title = _first_nonempty(passage.get("entry_title"), candidate.get("candidate_id", "未定"))
    raw_relations = raw.get("term_relations") if isinstance(raw.get("term_relations"), list) else []
    relations: list[dict[str, Any]] = []
    for relation in raw_relations:
        if not isinstance(relation, dict):
            continue
        source_term = _first_nonempty(relation.get("source_term"), "未定")
        target_term = _first_nonempty(relation.get("target_term"), "未定")
        relation_type = relation.get("relation_type")
        if relation_type not in {"训释", "校勘", "字际关系", "虚词用法", "句义解释", "未定", None}:
            relation_type = "未定"
        relations.append(
            {
                "source_term": source_term,
                "target_term": target_term,
                "relation_type": relation_type or "未定",
                "relation_subtype": relation.get("relation_subtype"),
                "relation_note": relation.get("relation_note"),
                "mapping_status": "original_text_ai_output",
            }
        )
    if not relations:
        relations = [
            {
                "source_term": entry_title,
                "target_term": "未定",
                "relation_type": "未定",
                "relation_subtype": None,
                "relation_note": "AI 未从该候选中给出可核验的字词关系；保留为机器草稿。",
                "mapping_status": "placeholder_due_to_ai_output_missing_relation",
            }
        ]

    evidences: list[dict[str, Any]] = []
    raw_evidences = raw.get("evidences") if isinstance(raw.get("evidences"), list) else []
    for evidence in raw_evidences:
        if not isinstance(evidence, dict):
            continue
        quote = evidence.get("quote") if isinstance(evidence.get("quote"), str) else ""
        quote = quote.strip()
        if not quote or quote not in passage_text:
            continue
        start = passage_text.find(quote)
        evidences.append(
            {
                "quote": quote,
                "evidence_role": evidence.get("evidence_role") or "original_text_context",
                "source_work": candidate.get("source_work"),
                "passage_id": candidate.get("passage_id"),
                "quote_start_char": start,
                "quote_end_char": start + len(quote),
                "quote_check": "passed",
                "source_location": _location(passage),
                "source_resolution": "canonical_source_passage",
                "cited_work_match_status": "matched",
                "mapping_status": "original_text_ai_output_quote_checked",
            }
        )
    if not evidences:
        # Guarantee one small, exact source quote without allowing the model to
        # create an untraceable external citation.
        quote = entry_title if entry_title and entry_title in passage_text else passage_text[: min(80, len(passage_text))]
        if quote:
            start = passage_text.find(quote)
            evidences = [
                {
                    "quote": quote,
                    "evidence_role": "candidate_context",
                    "source_work": candidate.get("source_work"),
                    "passage_id": candidate.get("passage_id"),
                    "quote_start_char": start,
                    "quote_end_char": start + len(quote),
                    "quote_check": "passed",
                    "source_location": _location(passage),
                    "source_resolution": "canonical_source_passage",
                    "cited_work_match_status": "matched",
                    "mapping_status": "machine_fallback_context_quote",
                }
            ]

    case = {
        "schema_version": "annotation_case.v1",
        "case_id": f"original-ai:{candidate.get('candidate_id')}",
        "case_title": _first_nonempty(raw.get("case_title"), entry_title),
        "submitted_by": "original_markdown_candidate_ai",
        "reviewed_by": None,
        "source_work": candidate.get("source_work", ""),
        "source_passage_id": candidate.get("passage_id"),
        "source_location": _location(passage),
        "target_work": "",
        "target_works": [],
        "target_scope": {
            "status": "unresolved",
            "target_works": [],
            "reason": "not_supplied_by_original_candidate_context",
        },
        "target_text": _first_nonempty(raw.get("target_text"), entry_title),
        "target_location": None,
        "term_relations": relations,
        "evidences": evidences,
        "evidence_state": "present" if evidences else "source_no_citation",
        "problem_discovery": raw.get("problem_discovery"),
        "research_question": raw.get("research_question"),
        "evidence_collection": raw.get("evidence_collection"),
        "reasoning": raw.get("reasoning"),
        "conclusion": _first_nonempty(raw.get("conclusion"), "机器草稿，待后续审校"),
        "method_profile": {
            "ai_generated": True,
            "candidate_rule_hits": candidate.get("rule_hits", []),
            "candidate_risk_flags": candidate.get("risk_flags", []),
            "mapping_policy": "original_text_only_no_external_citation",
        },
        "machine_result": {
            "status": "draft",
            "validator": "original_candidate_ai_adapter",
            "validation_state": "machine_draft_not_human_reviewed",
            "model": model,
            "prompt_version": prompt_version,
        },
        "human_review": {"status": "pending"},
        "_migration": {
            "source_format": "original_markdown_candidate_ai",
            "source_layer": "original_text",
            "transformation_kind": "original_text_ai_generation",
            "provenance": {
                "source_file": source_file,
                "source_document_id": candidate.get("source_document_id"),
                "candidate_id": candidate.get("candidate_id"),
                "source_passage_id": candidate.get("passage_id"),
                "candidate_rule_hits": candidate.get("rule_hits", []),
                "candidate_risk_flags": candidate.get("risk_flags", []),
                "model": model,
                "prompt_version": prompt_version,
                "ai_generation_performed": True,
                "output_schema": "annotation_case.v1",
                "output_database": "v2/data/real_runs/annotation_v2.db",
            },
            "raw_ai_output": raw,
            "field_boundary": {
                "source_fields": "derived from Wang original passage and candidate metadata",
                "target_work": "left unresolved unless explicitly supplied by input; not inferred from source_work",
                "evidences": "restricted to exact quotes in the supplied source passage",
                "human_review": "not performed",
            },
        },
    }
    return fill_missing_process_fields(case)
