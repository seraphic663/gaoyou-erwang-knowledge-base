from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Iterable

from .markdown_preprocess import normalize_for_match


REQUIRED_FIELDS = (
    "case_title",
    "submitted_by",
    "source_work",
    "target_work",
    "target_text",
    "term_relations",
    "evidences",
    "conclusion",
)
PROCESS_FIELDS = (
    "problem_discovery",
    "research_question",
    "evidence_collection",
    "reasoning",
    "conclusion",
)
RELATION_TYPES = {"训释", "校勘", "字际关系", "虚词用法", "句义解释", "未定"}
MACHINE_STATUSES = {"pending", "draft", "approved", "rejected"}
HUMAN_STATUSES = {"pending", "approved", "rejected", "uncertain"}
QUOTE_CHECKS = {"unchecked", "passed", "failed", "normalized_passed"}
EVIDENCE_STATES = {"present", "source_no_citation"}
TEMPLATE_MARKERS = ("【必填】", "【建议】", "【选填】")


def _strings(value: Any) -> Iterable[str]:
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for child in value.values():
            yield from _strings(child)
    elif isinstance(value, list):
        for child in value:
            yield from _strings(child)


def validate_case(
    case: dict[str, Any],
    passages: dict[str, dict[str, Any]],
) -> list[str]:
    errors: list[str] = []

    if case.get("schema_version") != "annotation_case.v1":
        errors.append("schema_version_must_be_annotation_case.v1")

    for field in REQUIRED_FIELDS:
        value = case.get(field)
        if value is None or value == "" or value == []:
            if field == "target_work":
                # A legacy case may not identify a unique object work.  Keep
                # it as an auditable unresolved case instead of guessing from
                # the first citation; target_works/target_scope carry the
                # richer state when it is available.
                continue
            if field == "evidences" and case.get("evidence_state") == "source_no_citation":
                continue
            errors.append(f"missing_required:{field}")

    target_work = case.get("target_work") or ""
    target_works = case.get("target_works") or []
    if not target_work and not target_works:
        errors.append("unresolved_target_work")
    target_scope = case.get("target_scope") or {}
    if target_works and target_scope.get("status") not in {None, "resolved"}:
        errors.append(f"target_scope_not_resolved:{target_scope.get('status')}")

    evidence_state = case.get("evidence_state", "present")
    if evidence_state not in EVIDENCE_STATES:
        errors.append(f"invalid_evidence_state:{evidence_state}")
    if evidence_state == "source_no_citation" and case.get("evidences"):
        errors.append("evidence_state_mismatch:source_no_citation_with_evidence")
    elif evidence_state == "source_no_citation":
        errors.append("source_has_no_citation")

    for field in PROCESS_FIELDS:
        if field not in case:
            errors.append(f"missing_process_field:{field}")

    for value in _strings(case):
        if any(marker in value for marker in TEMPLATE_MARKERS):
            errors.append("template_marker_remaining")
            break

    for index, relation in enumerate(case.get("term_relations", [])):
        relation_type = relation.get("relation_type")
        if relation_type and relation_type not in RELATION_TYPES:
            errors.append(f"invalid_relation_type:{index}:{relation_type}")

    for index, evidence in enumerate(case.get("evidences", [])):
        quote = evidence.get("quote", "")
        passage_id = evidence.get("passage_id")
        if not quote:
            errors.append(f"empty_quote:{index}")
            continue
        if passage_id not in passages:
            errors.append(f"missing_evidence_passage:{index}:{passage_id}")
            continue
        plain_text = passages[passage_id].get("plain_text", "")
        quote_check = evidence.get("quote_check")
        if quote_check and quote_check not in QUOTE_CHECKS:
            errors.append(f"invalid_quote_check:{index}:{quote_check}")
        source_resolution = evidence.get("source_resolution")
        if (
            quote_check in {"passed", "normalized_passed"}
            and source_resolution != "canonical_source_passage"
        ):
            errors.append(
                f"noncanonical_quote_cannot_pass:{index}:{source_resolution}"
            )
        if quote not in plain_text:
            normalized_match = normalize_for_match(quote) in normalize_for_match(plain_text)
            if not (quote_check == "normalized_passed" and normalized_match):
                errors.append(f"quote_not_found:{index}:{passage_id}")
        supplied_hash = evidence.get("quote_sha256")
        actual_hash = hashlib.sha256(quote.encode("utf-8")).hexdigest()
        if supplied_hash and supplied_hash != actual_hash:
            errors.append(f"quote_hash_mismatch:{index}")

    machine_status = (case.get("machine_result") or {}).get("status")
    if machine_status and machine_status not in MACHINE_STATUSES:
        errors.append(f"invalid_machine_status:{machine_status}")
    human_status = (case.get("human_review") or {}).get("status")
    if human_status and human_status not in HUMAN_STATUSES:
        errors.append(f"invalid_human_status:{human_status}")

    return errors


def classify_machine_status(
    custom_errors: list[str], schema_errors: list[str] | None = None
) -> str:
    """Map validation results to machine state without promoting human meaning."""

    schema_errors = schema_errors or []
    if not custom_errors and not schema_errors:
        return "approved"
    # These are review-boundary findings, not malformed records: an external
    # quote may be retained without a local canonical passage, a target scope
    # may be candidate-only, and an explicitly no-citation case may need a
    # human decision. Keep the errors in machine_result, but route the case to
    # machine_draft/human_pending so the workflow reaches review rather than
    # stopping at an automated rejection.
    soft_prefixes = (
        "missing_evidence_passage:",
        "target_scope_not_resolved:",
        "unresolved_target_work",
        "source_has_no_citation",
    )
    if custom_errors and not schema_errors and all(
        any(error.startswith(prefix) for prefix in soft_prefixes)
        for error in custom_errors
    ):
        return "draft"
    return "rejected"


def load_passages_jsonl(path: str | Path) -> dict[str, dict[str, Any]]:
    passages: dict[str, dict[str, Any]] = {}
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        if line.strip():
            passage = json.loads(line)
            passages[passage["passage_id"]] = passage
    return passages
