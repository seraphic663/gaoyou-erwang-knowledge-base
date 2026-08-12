from __future__ import annotations

import hashlib
import json
import re
import sqlite3
from pathlib import Path
from typing import Any


TARGET_RE = re.compile(r"[「『]([^」』]+)[」』]")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _json_list(value: Any) -> list[Any]:
    if value is None or value == "":
        return []
    if isinstance(value, list):
        return value
    try:
        parsed = json.loads(value)
    except (TypeError, ValueError):
        return []
    return parsed if isinstance(parsed, list) else []


def _target_text(title: str) -> tuple[str, str]:
    match = TARGET_RE.search(title or "")
    if match:
        return match.group(1).strip(), "legacy_title_quoted_text"
    return (title or "未定").strip() or "未定", "legacy_title_fallback"


def _row_dict(row: sqlite3.Row | None) -> dict[str, Any]:
    return dict(row) if row is not None else {}


def _legacy_passage(
    *,
    passage_id: str,
    work_key: str,
    document_title: str,
    section_title: str | None,
    entry_title: str,
    raw_text: str,
    local_ordinal: int,
    source_file: Path,
    source_file_sha256: str,
    md_line_start: int | None = None,
    md_line_end: int | None = None,
    entry_kind: str = "legacy_derived",
) -> dict[str, Any]:
    text = raw_text.strip()
    normalized = " ".join(text.split())
    return {
        "passage_id": passage_id,
        "work_key": work_key,
        "document_title": document_title,
        "section_title": section_title,
        "entry_title": entry_title,
        "entry_kind": entry_kind,
        "title_path": [item for item in (document_title, section_title, entry_title) if item],
        "local_ordinal": local_ordinal,
        "md_line_start": md_line_start,
        "md_line_end": md_line_end,
        "raw_text": text,
        "plain_text": text,
        "normalized_text": normalized,
        "raw_text_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
        "normalized_text_sha256": hashlib.sha256(normalized.encode("utf-8")).hexdigest(),
        "source_file": str(source_file.resolve()),
        "source_file_sha256": source_file_sha256,
        "inline_notes": [],
    }


def _source_txt_passages(
    source_text: Path,
    legacy_case_rows: list[dict[str, Any]],
    source_text_sha256: str,
) -> tuple[list[dict[str, Any]], dict[int, dict[str, Any]]]:
    """Split the parser input into stable, line-addressable legacy passages."""

    lines = source_text.read_text(encoding="utf-8").splitlines()
    line_by_case: dict[int, int] = {}
    line_pattern = re.compile(r"[（(]行\s*(\d+)[）)]")
    for row in legacy_case_rows:
        match = line_pattern.search(str(row.get("title") or ""))
        if match:
            line_by_case[int(row["id"])] = int(match.group(1))

    ordered = sorted(
        ((case_id, line_number) for case_id, line_number in line_by_case.items()),
        key=lambda item: item[1],
    )
    passages: list[dict[str, Any]] = []
    by_case: dict[int, dict[str, Any]] = {}
    for index, (case_id, start_line) in enumerate(ordered):
        end_line = ordered[index + 1][1] - 1 if index + 1 < len(ordered) else len(lines)
        if start_line < 1 or start_line > len(lines):
            continue
        raw_text = "\n".join(lines[start_line - 1 : end_line])
        row = next(item for item in legacy_case_rows if int(item["id"]) == case_id)
        passage = _legacy_passage(
            passage_id=f"legacy-source:{case_id}",
            work_key="legacy_guangya_shuzheng_source",
            document_title="旧机器库 source.txt",
            section_title=row.get("section_title"),
            entry_title=row.get("title") or f"legacy case {case_id}",
            raw_text=raw_text,
            local_ordinal=index + 1,
            source_file=source_text,
            source_file_sha256=source_text_sha256,
            md_line_start=start_line,
            md_line_end=end_line,
            entry_kind="legacy_source_case",
        )
        passages.append(passage)
        by_case[case_id] = passage
    return passages, by_case


def _legacy_quote_passages(
    database_path: Path,
    evidence_rows: list[dict[str, Any]],
    works: dict[int, str],
    database_sha256: str,
) -> tuple[list[dict[str, Any]], dict[int, dict[str, Any]]]:
    """Materialize each old quote as a derived, non-canonical passage.

    These passages make the old machine evidence addressable without claiming
    that the quote was checked against the cited work's canonical edition.
    """

    passages: list[dict[str, Any]] = []
    by_evidence: dict[int, dict[str, Any]] = {}
    for index, row in enumerate(evidence_rows, start=1):
        evidence_id = int(row["id"])
        quote = str(row.get("quote_text") or row.get("core_snippet") or "").strip()
        if not quote:
            quote = f"legacy evidence {evidence_id} has no quote text"
        cited_work = works.get(int(row["work_id"])) if row.get("work_id") is not None else None
        passage = _legacy_passage(
            passage_id=f"legacy-evidence:{evidence_id}",
            work_key="legacy_dictionary_db_evidence",
            document_title="旧 dictionary.db 派生证据文本",
            section_title=cited_work or f"legacy_work_id:{row.get('work_id')}",
            entry_title=f"legacy evidence {evidence_id}",
            raw_text=quote,
            local_ordinal=index,
            source_file=database_path,
            source_file_sha256=database_sha256,
            entry_kind="legacy_derived_quote",
        )
        passages.append(passage)
        by_evidence[evidence_id] = passage
    return passages, by_evidence


def load_legacy_dictionary_cases(
    database_path: str | Path,
    *,
    source_text_path: str | Path | None = None,
    parser_path: str | Path | None = None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Convert the legacy machine database into auditable V2 case JSON objects.

    This is deliberately a mechanical reprocessing route.  It preserves the
    old rows and IDs, but never treats the old ``确定``/``草稿`` values as
    human review and never invents passage, target-work, or process links.
    """

    db_path = Path(database_path).resolve()
    if not db_path.exists():
        raise FileNotFoundError(db_path)

    source_text = Path(source_text_path).resolve() if source_text_path else None
    parser = Path(parser_path).resolve() if parser_path else None
    database_sha256 = _sha256(db_path)
    source_text_sha256 = _sha256(source_text) if source_text and source_text.exists() else None
    parser_sha256 = _sha256(parser) if parser and parser.exists() else None

    connection = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    try:
        works = {
            int(row["id"]): row["title"]
            for row in connection.execute("SELECT id, title FROM works")
        }
        terms = {
            int(row["id"]): _row_dict(row)
            for row in connection.execute("SELECT * FROM terms")
        }
        evidence_by_case: dict[int, list[dict[str, Any]]] = {}
        for row in connection.execute("SELECT * FROM evidences ORDER BY id"):
            item = _row_dict(row)
            evidence_by_case.setdefault(int(item["case_id"]), []).append(item)

        cases: list[dict[str, Any]] = []
        for row in connection.execute("SELECT * FROM cases ORDER BY id"):
            legacy = _row_dict(row)
            legacy_id = int(legacy["id"])
            target_text, target_text_source = _target_text(legacy.get("title", ""))
            term_ids = [int(value) for value in _json_list(legacy.get("term_ids")) if str(value).isdigit()]
            related_evidence = evidence_by_case.get(legacy_id, [])

            relations: list[dict[str, Any]] = []
            for term_id in term_ids:
                term = terms.get(term_id, {})
                source_term = str(term.get("term") or "未定")
                relations.append(
                    {
                        "source_term": source_term,
                        "target_term": target_text,
                        "relation_type": "未定",
                        "relation_subtype": term.get("term_type"),
                        "relation_note": term.get("core_meaning") or None,
                        "legacy_term_id": term_id,
                        "legacy_term_category": term.get("category"),
                        "mapping_status": "mechanical_field_mapping_only",
                    }
                )
            if not relations:
                relations.append(
                    {
                        "source_term": "未定",
                        "target_term": target_text,
                        "relation_type": "未定",
                        "relation_subtype": None,
                        "relation_note": "legacy dictionary case has no usable term_ids",
                        "mapping_status": "placeholder_due_to_missing_legacy_terms",
                    }
                )

            evidences: list[dict[str, Any]] = []
            for evidence in related_evidence:
                quote = str(evidence.get("quote_text") or evidence.get("core_snippet") or "").strip()
                if not quote:
                    quote = f"legacy evidence {evidence.get('id')} has no quote text"
                work_id = evidence.get("work_id")
                cited_work = works.get(int(work_id)) if work_id is not None else None
                evidences.append(
                    {
                        "quote": quote,
                        "evidence_role": evidence.get("evidence_type"),
                        "source_work": cited_work or f"legacy_work_id:{work_id}",
                        "legacy_work_id": work_id,
                        "passage_id": None,
                        "quote_sha256": hashlib.sha256(quote.encode("utf-8")).hexdigest(),
                        "quote_check": "unchecked",
                        "source_location": None,
                        "source_resolution": "legacy_machine_unlinked",
                        "cited_work_match_status": "legacy_work_reference_only",
                        "legacy_evidence_id": evidence.get("id"),
                        "legacy_term_id": evidence.get("term_id"),
                        "legacy_evidence_type": evidence.get("evidence_type"),
                        "legacy_source_passage_id": evidence.get("source_passage_id"),
                        "mapping_status": "mechanical_field_mapping_only",
                    }
                )

            missing_fields = [
                "target_work",
                "source_passage_id",
                "target_passage_id",
                "process_text",
                "evidence.source_passage_id",
            ]
            case = {
                "schema_version": "annotation_case.v1",
                "case_id": f"legacy-dictionary:{legacy_id}",
                "legacy_case_id": legacy_id,
                "legacy_term_ids": term_ids,
                "case_title": legacy.get("title") or f"legacy dictionary case {legacy_id}",
                "submitted_by": "legacy_dictionary_db_adapter",
                "reviewed_by": None,
                "source_work": "广雅疏证",
                "source_passage_id": None,
                "source_location": {
                    "source_kind": "legacy_machine_database",
                    "source_file": "02-数据库/main/source.txt",
                    "source_file_sha256": source_text_sha256,
                    "database_file": "02-数据库/data/dictionary.db",
                    "database_file_sha256": database_sha256,
                    "legacy_table": "cases",
                    "legacy_case_id": legacy_id,
                    "section_title": legacy.get("section_title"),
                    "volume_title": legacy.get("volume_title"),
                },
                "target_work": "",
                "target_works": [],
                "target_scope": {
                    "status": "unresolved",
                    "target_works": [],
                    "reason": "legacy_dictionary_db_has_no_target_work_field",
                },
                "target_text": target_text,
                "target_location": {
                    "status": "unresolved",
                    "reason": "legacy_dictionary_db_has_no_target_passage_id",
                },
                "term_relations": relations,
                "evidences": evidences,
                "evidence_state": "present" if evidences else "source_no_citation",
                "problem_discovery": legacy.get("problem") or None,
                "research_question": None,
                "evidence_collection": None,
                "reasoning": None,
                "conclusion": legacy.get("conclusion") or legacy.get("title") or "未定",
                "method_profile": {
                    "legacy_method_raw": legacy.get("method") or "",
                    "mapping_policy": "preserve_raw_legacy_method_without_semantic_relabeling",
                },
                "machine_result": {
                    "status": "draft",
                    "validator": "legacy_dictionary_db_adapter",
                    "validation_state": "legacy_fields_incomplete",
                    "validation_errors": [
                        "legacy_source_passage_unlinked",
                        "legacy_target_work_unresolved",
                        "legacy_target_passage_unlinked",
                        "legacy_process_text_missing",
                        "legacy_evidence_passages_unlinked",
                    ],
                },
                "human_review": {
                    "status": "pending",
                    "legacy_status": legacy.get("status"),
                    "legacy_certainty": legacy.get("certainty"),
                },
                "_migration": {
                    "source_format": "legacy_dictionary_db",
                    "source_layer": "machine_output",
                    "transformation_kind": "machine_output_reprocessing",
                    "transformation_description": "从旧 dictionary.db 的 cases/terms/evidences 机械映射为 annotation_case.v1，不重新判定学术结论。",
                    "provenance": {
                        "source_file": "02-数据库/data/dictionary.db",
                        "source_file_sha256": database_sha256,
                        "source_text_file": "02-数据库/main/source.txt",
                        "source_text_sha256": source_text_sha256,
                        "parser_file": "02-数据库/main/parser.py",
                        "parser_sha256": parser_sha256,
                        "legacy_table": "cases",
                        "legacy_case_id": legacy_id,
                        "legacy_term_ids": term_ids,
                        "legacy_evidence_ids": [item.get("id") for item in related_evidence],
                        "output_schema": "annotation_case.v1",
                        "output_database": "v2/data/real_runs/annotation_v2.db",
                    },
                    "field_mapping": {
                        "case_title": "cases.title",
                        "source_work": "legacy pipeline declared source.txt as 广雅疏证",
                        "target_text": target_text_source,
                        "term_relations": "terms + cases.term_ids; relation_type intentionally 未定",
                        "evidences": "evidences.quote_text/work_id/evidence_type; passage link preserved as missing",
                        "conclusion": "cases.conclusion",
                        "human_review": "cases.status/certainty preserved as legacy metadata only",
                    },
                    "unresolved_fields": missing_fields,
                },
            }
            cases.append(case)
        report = {
            "source_kind": "legacy_machine_database",
            "source_file": "02-数据库/data/dictionary.db",
            "source_file_sha256": database_sha256,
            "source_text_file": "02-数据库/main/source.txt",
            "source_text_sha256": source_text_sha256,
            "parser_file": "02-数据库/main/parser.py",
            "parser_sha256": parser_sha256,
            "case_count": len(cases),
            "evidence_count": sum(len(case["evidences"]) for case in cases),
            "term_relation_count": sum(len(case["term_relations"]) for case in cases),
            "transformation_kind": "machine_output_reprocessing",
            "output_schema": "annotation_case.v1",
        }
        return cases, report
    finally:
        connection.close()


def load_legacy_dictionary_material(
    database_path: str | Path,
    *,
    source_text_path: str | Path,
    parser_path: str | Path | None = None,
) -> tuple[
    list[dict[str, Any]],
    list[dict[str, Any]],
    list[dict[str, Any]],
    dict[str, Any],
]:
    """Load cases and build addressable legacy source/target passages.

    The returned passages are explicitly legacy_unverified material. The
    function only makes old rows locatable; it does not turn parser output or
    derived quote text into canonical evidence.
    """

    db_path = Path(database_path).resolve()
    source_text = Path(source_text_path).resolve()
    cases, adapter_report = load_legacy_dictionary_cases(
        db_path,
        source_text_path=source_text,
        parser_path=parser_path,
    )
    database_sha256 = _sha256(db_path)
    source_text_sha256 = _sha256(source_text)

    connection = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    try:
        legacy_case_rows = [
            _row_dict(row) for row in connection.execute("SELECT * FROM cases ORDER BY id")
        ]
        evidence_rows = [
            _row_dict(row) for row in connection.execute("SELECT * FROM evidences ORDER BY id")
        ]
        work_rows = [
            _row_dict(row) for row in connection.execute("SELECT * FROM works ORDER BY id")
        ]
        term_rows = [
            _row_dict(row) for row in connection.execute("SELECT * FROM terms ORDER BY id")
        ]
    finally:
        connection.close()

    works = {int(row["id"]): str(row.get("title") or "") for row in work_rows}
    source_passages, source_by_case = _source_txt_passages(
        source_text,
        legacy_case_rows,
        source_text_sha256,
    )
    target_passages, target_by_evidence = _legacy_quote_passages(
        db_path,
        evidence_rows,
        works,
        database_sha256,
    )

    evidence_by_case: dict[int, list[dict[str, Any]]] = {}
    for row in evidence_rows:
        evidence_by_case.setdefault(int(row["case_id"]), []).append(row)

    for case in cases:
        migration = case.setdefault("_migration", {})
        provenance = migration.setdefault("provenance", {})
        legacy_case_id = int(
            provenance.get("legacy_case_id")
            or case["case_id"].split(":")[-1]
        )
        source_passage = source_by_case.get(legacy_case_id)
        related_rows = evidence_by_case.get(legacy_case_id, [])
        candidates: list[str] = []
        seen_candidates: set[str] = set()
        for row in related_rows:
            cited_work = (
                works.get(int(row["work_id"]))
                if row.get("work_id") is not None
                else None
            )
            if cited_work and cited_work not in seen_candidates:
                seen_candidates.add(cited_work)
                candidates.append(cited_work)

        target_scope = {
            "status": "machine_inferred" if candidates else "unresolved",
            "target_works": candidates,
            "candidate_works": candidates,
            "confidence": "candidate_only" if candidates else None,
            "reason": "derived_from_legacy_evidence_work_id; not a resolved target_work",
            "resolution_source": "legacy_dictionary_db_machine_inference",
            "evidence_indexes": list(range(len(related_rows))),
        }
        first_target = (
            target_by_evidence.get(int(related_rows[0]["id"]))
            if related_rows
            else None
        )
        if source_passage is not None:
            case["source_passage_id"] = source_passage["passage_id"]
            case["source_location"] = {
                **(case.get("source_location") or {}),
                "passage_id": source_passage["passage_id"],
                "source_file": source_passage["source_file"],
                "source_file_sha256": source_passage["source_file_sha256"],
                "md_line_start": source_passage["md_line_start"],
                "md_line_end": source_passage["md_line_end"],
                "title_path": source_passage["title_path"],
                "match_mode": "legacy_case_line_range",
                "source_kind": "legacy_source_txt",
            }
        case["target_scope"] = target_scope
        case["target_works"] = candidates
        case["target_work"] = ""
        case["target_passage_id"] = (
            first_target["passage_id"] if first_target else None
        )
        case["target_location"] = (
            {
                "passage_id": first_target["passage_id"],
                "source_file": first_target["source_file"],
                "source_file_sha256": first_target["source_file_sha256"],
                "title_path": first_target["title_path"],
                "match_mode": "first_legacy_evidence_quote",
                "target_work_candidates": candidates,
                "canonical_status": "legacy_unverified",
            }
            if first_target
            else {
                "status": "unresolved",
                "reason": "legacy_case_has_no_evidence_rows",
            }
        )

        for evidence in case.get("evidences", []):
            evidence_id = evidence.get("legacy_evidence_id")
            target = (
                target_by_evidence.get(int(evidence_id))
                if evidence_id is not None
                else None
            )
            if target is None:
                continue
            evidence["passage_id"] = target["passage_id"]
            evidence["source_location"] = {
                "passage_id": target["passage_id"],
                "source_file": target["source_file"],
                "source_file_sha256": target["source_file_sha256"],
                "title_path": target["title_path"],
                "start_char": 0,
                "end_char": len(evidence.get("quote") or ""),
                "match_mode": "derived_quote_exact",
                "canonical_status": "legacy_unverified",
            }
            evidence["quote_start_char"] = 0
            evidence["quote_end_char"] = len(evidence.get("quote") or "")
            evidence["source_resolution"] = "legacy_derived_passage"
            evidence["cited_work_match_status"] = "legacy_work_reference_only"
            evidence["quote_check"] = "unchecked"
            evidence["legacy_match"] = {
                "mode": "derived_quote_exact",
                "canonical_validation": "not_performed",
                "source_boundary": (
                    "dictionary.db quote text is not a cited-work canonical passage"
                ),
            }

        raw_problem = (
            case.get("problem_discovery")
            or "旧机器库未提供独立发疑记录；待人工核对。"
        )
        raw_conclusion = (
            case.get("conclusion")
            or "旧机器库未提供结论；待人工核对。"
        )
        process_fields = {
            "problem_discovery": raw_problem,
            "research_question": (
                "机器迁移待核：旧 dictionary.db 的该案例、词条关系和证据是否能在对应 canonical 原典中复核？"
            ),
            "evidence_collection": (
                f"旧 dictionary.db case_id={legacy_case_id} 的 {len(related_rows)} 条 evidence "
                "已绑定到 legacy-derived quote passage；引用状态保持 unchecked。"
            ),
            "reasoning": (
                "本步骤仅记录机器再加工规则：source.txt 行区间用于 source passage，旧 evidence quote "
                "用于 derived target passage；没有执行原典语义核验或人工审校。"
            ),
            "conclusion": raw_conclusion,
        }
        case.update(process_fields)
        case["process_text"] = "\n".join(
            f"{label}：{process_fields[field]}"
            for label, field in (
                ("发疑", "problem_discovery"),
                ("设问", "research_question"),
                ("取证", "evidence_collection"),
                ("释理", "reasoning"),
                ("结论", "conclusion"),
            )
        )
        case["machine_result"] = {
            "status": "draft",
            "validator": "legacy_dictionary_db_adapter",
            "validation_state": "legacy_links_materialized_without_canonical_claim",
            "validation_errors": [
                "legacy_quote_not_canonical",
                "legacy_target_work_candidate_only",
                "legacy_derived_passage_is_not_canonical",
                "legacy_process_fields_machine_completed",
            ],
        }
        migration["source_layer"] = "machine_output"
        migration["transformation_kind"] = "legacy_dictionary_db_reprocessing"
        migration["transformation_description"] = (
            "旧 source.txt/parser/importer/dictionary.db 经过机械字段映射、来源段落 materialization "
            "和 derived quote 定位；不重新判定学术结论。"
        )
        migration["legacy_materialization"] = {
            "source_passage_id": case.get("source_passage_id"),
            "target_passage_id": case.get("target_passage_id"),
            "source_passage_kind": "legacy_source_txt",
            "target_passage_kind": "legacy_derived_quote",
            "canonical_quote_validation": "not_performed",
            "process_completion": "machine_generated_traceable_fields",
        }

    term_ids = set()
    for row in legacy_case_rows:
        term_ids.update(
            int(value)
            for value in _json_list(row.get("term_ids"))
            if str(value).isdigit()
        )
    used_work_ids = {
        int(row["work_id"])
        for row in evidence_rows
        if row.get("work_id") is not None
    }
    unreferenced_term_rows = [
        row for row in term_rows if int(row["id"]) not in term_ids
    ]
    unreferenced_work_rows = [
        row for row in work_rows if int(row["id"]) not in used_work_ids
    ]
    report = {
        **adapter_report,
        "materialization": {
            "source_passage_count": len(source_passages),
            "target_passage_count": len(target_passages),
            "evidence_passage_binding_count": sum(
                1
                for case in cases
                for evidence in case.get("evidences", [])
                if evidence.get("passage_id")
            ),
            "case_source_passage_binding_count": sum(
                bool(case.get("source_passage_id")) for case in cases
            ),
            "case_target_passage_binding_count": sum(
                bool(case.get("target_passage_id")) for case in cases
            ),
            "process_text_count": sum(
                bool(case.get("process_text")) for case in cases
            ),
            "five_process_field_complete_count": sum(
                all(
                    case.get(field)
                    for field in (
                        "problem_discovery",
                        "research_question",
                        "evidence_collection",
                        "reasoning",
                        "conclusion",
                    )
                )
                for case in cases
            ),
        },
        "catalog_only": {
            "terms": [
                {
                    "id": row["id"],
                    "term": row.get("term"),
                    "reason": "unreferenced in legacy cases",
                }
                for row in unreferenced_term_rows
            ],
            "works": [
                {
                    "id": row["id"],
                    "title": row.get("title"),
                    "reason": "unreferenced by legacy evidence",
                }
                for row in unreferenced_work_rows
            ],
        },
    }
    return cases, source_passages, target_passages, {
        "report": report,
        "source_sha256": source_text_sha256,
        "database_sha256": database_sha256,
        "all_terms": term_rows,
        "all_works": work_rows,
        "catalog_terms": unreferenced_term_rows,
        "catalog_works": unreferenced_work_rows,
    }
