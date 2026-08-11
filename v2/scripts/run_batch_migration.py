from __future__ import annotations

import argparse
import hashlib
import json
import sys
import unicodedata
from collections import Counter
from pathlib import Path
from typing import Any


V2_ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = V2_ROOT.parent
sys.path.insert(0, str(V2_ROOT / "src"))

from erwang_v2.candidate_auditor import audit_candidates
from erwang_v2.candidate_extractor import extract_candidates
from erwang_v2.database import database_counts, ingest_case, ingest_passages, open_database
from erwang_v2.legacy_ai_adapter import (
    adapt_legacy_case,
    load_legacy_ai_json,
)
from erwang_v2.passage_builder import build_passages
from erwang_v2.validate_annotation_case import validate_case


AI_DIR = PROJECT_ROOT / "04-项目文献/D-标注/json/ai_json"
FULL_JSON_DIR = PROJECT_ROOT / "04-项目文献/D-标注/json/full_json"
DEFAULT_DATABASE = V2_ROOT / "data/real_runs/annotation_v2.db"
DEFAULT_REPORT = V2_ROOT / "data/real_runs/batch_migration_report.json"

WORKS = {
    "广雅疏证": {
        "work_key": "guangya_shuzheng",
        "markdown": PROJECT_ROOT / "04-项目文献/A-原著原典/广雅疏证_王念孙.md",
    },
    "经传释词": {
        "work_key": "jingzhuan_shici",
        "markdown": PROJECT_ROOT / "04-项目文献/A-原著原典/经传释词_王引之.md",
    },
    "读书杂志": {
        "work_key": "dushu_zazhi",
        "markdown": PROJECT_ROOT / "04-项目文献/A-原著原典/读书杂志_王念孙.md",
    },
}


def _relative(path: Path) -> str:
    try:
        return path.resolve().relative_to(PROJECT_ROOT.resolve()).as_posix()
    except ValueError:
        return path.as_posix()


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _schema_errors(case: dict[str, Any]) -> tuple[str, list[str]]:
    schema_path = V2_ROOT / "schemas/annotation_case.v1.schema.json"
    try:
        from jsonschema import Draft202012Validator
    except ImportError:
        return "skipped_missing_jsonschema", []

    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    errors = sorted(
        ".".join(str(part) for part in error.absolute_path) + ": " + error.message
        for error in Draft202012Validator(schema).iter_errors(case)
    )
    return ("passed" if not errors else "failed"), errors


def _candidate_profile(passages: list[dict[str, Any]]) -> dict[str, Any]:
    layers = extract_candidates(passages)
    candidates = layers["parsed_items"] + layers["candidate_items"]
    audit = audit_candidates(candidates, passages)
    return {
        "passage_count": len(passages),
        "parsed_count": len(layers["parsed_items"]),
        "candidate_count": len(layers["candidate_items"]),
        "skipped_count": len(layers["skipped_items"]),
        "audited_count": len(audit),
        "audit_status_counts": dict(Counter(item["machine_status"] for item in audit)),
        "risk_flag_counts": dict(
            Counter(flag for item in audit for flag in item.get("risk_flags", []))
        ),
    }


def _source_config(source_work: str) -> dict[str, Any] | None:
    return WORKS.get(source_work.strip().strip("《》"))


def _case_id_fallback(ai_path: Path, case_index: int) -> str:
    return f"legacy-ai:{ai_path.stem}:{case_index}"


def _compact_context_text(value: str) -> str:
    value = unicodedata.normalize("NFKC", value)
    return "".join(
        char
        for char in value
        if not unicodedata.category(char).startswith(("P", "Z"))
        and unicodedata.category(char) != "Cf"
    )


def _load_full_json_context(path: Path) -> dict[int, str]:
    if not path.exists():
        return {}
    data = json.loads(path.read_text(encoding="utf-8-sig"))
    return {
        int(paragraph["index"]): paragraph.get("text", "")
        for paragraph in data.get("paragraphs", [])
        if isinstance(paragraph, dict) and paragraph.get("index") is not None
    }


def _full_json_context_match(
    quote: str,
    paragraph_indexes: list[int],
    context: dict[int, str],
) -> str:
    if not quote or not context:
        return "unavailable"
    texts = [context.get(index, "") for index in paragraph_indexes]
    if any(quote in text for text in texts):
        return "exact"
    compact_quote = _compact_context_text(quote)
    if compact_quote and any(
        compact_quote in _compact_context_text(text) for text in texts
    ):
        return "punctuation_normalized"
    return "not_found"


def _machine_status(
    custom_errors: list[str], schema_errors: list[str]
) -> str:
    if not custom_errors and not schema_errors:
        return "approved"
    soft_prefix = "missing_evidence_passage:"
    if custom_errors and not schema_errors and all(
        error.startswith(soft_prefix) for error in custom_errors
    ):
        # The case is structurally usable, but at least one cited external
        # source is not loaded in the current canonical passage corpus.
        return "draft"
    return "rejected"


def _case_report(
    *,
    ai_path: Path,
    case_index: int,
    legacy_case: dict[str, Any],
    v2_case: dict[str, Any],
    custom_errors: list[str],
    schema_status: str,
    schema_errors: list[str],
    stored_case: dict[str, Any] | None,
    ingest_error: str | None,
) -> dict[str, Any]:
    all_errors = custom_errors + [f"jsonschema:{error}" for error in schema_errors]
    quote_checks = Counter(
        evidence.get("quote_check", "unchecked")
        for evidence in v2_case.get("evidences", [])
    )
    location = v2_case.get("source_location") or {}
    return {
        "case_id": v2_case.get("case_id"),
        "case_title": legacy_case.get("case_title"),
        "source_work": legacy_case.get("source_work"),
        "source_file": _relative(ai_path),
        "case_index": case_index,
        "target_text": legacy_case.get("target_text"),
        "source_passage_id": v2_case.get("source_passage_id"),
        "source_location": {
            "md_line_start": location.get("md_line_start"),
            "md_line_end": location.get("md_line_end"),
            "title_path": location.get("title_path"),
            "match_mode": location.get("match_mode"),
        },
        "term_count": len(v2_case.get("term_relations", [])),
        "evidence_count": len(v2_case.get("evidences", [])),
        "quote_check_counts": dict(quote_checks),
        "source_resolution_counts": dict(
            Counter(
                evidence.get("source_resolution", "unknown")
                for evidence in v2_case.get("evidences", [])
            )
        ),
        "full_json_context_counts": dict(
            Counter(
                evidence.get("annotation_context_check", "unavailable")
                for evidence in v2_case.get("evidences", [])
            )
        ),
        "unlinked_full_json_context_counts": dict(
            Counter(
                evidence.get("annotation_context_check", "unavailable")
                for evidence in v2_case.get("evidences", [])
                if evidence.get("source_resolution") != "canonical_passage"
            )
        ),
        "custom_validator": "passed" if not custom_errors else "failed",
        "schema_validator": schema_status,
        "validation_errors": all_errors,
        "machine_status": v2_case.get("machine_result", {}).get("status"),
        "human_status": v2_case.get("human_review", {}).get("status"),
        "database": {
            "status": "stored" if stored_case else "not_stored",
            "error": ingest_error,
            "lifecycle": stored_case.get("lifecycle") if stored_case else None,
        },
    }


def run_batch(
    *,
    ai_dir: Path = AI_DIR,
    database_path: Path = DEFAULT_DATABASE,
    report_path: Path = DEFAULT_REPORT,
) -> dict[str, Any]:
    ai_paths = sorted(ai_dir.glob("*.json"))
    source_profiles: list[dict[str, Any]] = []
    case_reports: list[dict[str, Any]] = []
    mapping_errors: list[dict[str, Any]] = []
    passage_maps: dict[str, dict[str, dict[str, Any]]] = {}

    with open_database(database_path) as connection:
        for ai_path in ai_paths:
            container = load_legacy_ai_json(ai_path)
            cases = container.get("cases", [])
            source_values = sorted(
                {str(case.get("source_work", "")).strip().strip("《》") for case in cases}
            )
            if len(source_values) != 1 or not _source_config(source_values[0]):
                mapping_errors.append(
                    {
                        "file": _relative(ai_path),
                        "source_values": source_values,
                        "error": "source_work_mapping_failed",
                    }
                )
                continue

            source_work = source_values[0]
            config = _source_config(source_work)
            assert config is not None
            markdown_path = config["markdown"]
            full_json_path = FULL_JSON_DIR / ai_path.name
            full_json_context = _load_full_json_context(full_json_path)
            passages = build_passages(markdown_path, config["work_key"])
            passage_map = {passage["passage_id"]: passage for passage in passages}
            passage_maps[config["work_key"]] = passage_map
            source_document_id = ingest_passages(
                connection,
                passages,
                metadata={
                    "legacy_ai_json": _relative(ai_path),
                    "full_json": _relative(full_json_path),
                },
            )
            source_profiles.append(
                {
                    "source_work": source_work,
                    "work_key": config["work_key"],
                    "markdown": _relative(markdown_path),
                    "markdown_sha256": _sha256(markdown_path),
                    "ai_json": _relative(ai_path),
                    "ai_json_sha256": _sha256(ai_path),
                    "full_json": _relative(full_json_path),
                    "full_json_sha256": _sha256(full_json_path)
                    if full_json_path.exists()
                    else None,
                    "source_document_id": source_document_id,
                    "candidate_profile": _candidate_profile(passages),
                    "legacy_case_count": len(cases),
                }
            )

            for case_index, legacy_case in enumerate(cases):
                provenance = {
                    "source_work": source_work,
                    "work_key": config["work_key"],
                    "source_markdown_sha256": _sha256(markdown_path),
                    "legacy_ai_json_sha256": _sha256(ai_path),
                    "full_json": _relative(full_json_path),
                    "full_json_sha256": _sha256(full_json_path)
                    if full_json_path.exists()
                    else None,
                }
                v2_case = adapt_legacy_case(
                    legacy_case,
                    passages,
                    source_markdown=_relative(markdown_path),
                    legacy_ai_json=_relative(ai_path),
                    case_index=case_index,
                    submitted_by="legacy_ai_json_batch_adapter",
                    additional_provenance=provenance,
                )
                if not legacy_case.get("database_ingestion", {}).get("annotation_case_id"):
                    v2_case["case_id"] = _case_id_fallback(ai_path, case_index)

                primary_work = legacy_case.get("source_work", "").strip().strip("《》")
                for evidence in v2_case.get("evidences", []):
                    if evidence.get("passage_id"):
                        evidence["source_resolution"] = "canonical_passage"
                    elif evidence.get("source_work") and evidence.get("source_work") != primary_work:
                        evidence["source_resolution"] = "external_source_unavailable"
                        # No canonical passage was loaded for this external
                        # work, so this is not a failed quote check; it is an
                        # unverified draft citation.
                        evidence["quote_check"] = "unchecked"
                    else:
                        evidence["source_resolution"] = "primary_source_no_match"
                    paragraph_indexes = evidence.get("legacy_source_paragraph_indexes", [])
                    evidence["annotation_context_check"] = _full_json_context_match(
                        evidence.get("quote", ""), paragraph_indexes, full_json_context
                    )
                    evidence["annotation_context_paragraph_indexes"] = paragraph_indexes

                custom_errors = validate_case(v2_case, passage_map)
                schema_status, schema_errors = _schema_errors(v2_case)
                all_errors = custom_errors + [f"jsonschema:{error}" for error in schema_errors]
                machine_status = _machine_status(custom_errors, schema_errors)
                v2_case["machine_result"] = {
                    "status": machine_status,
                    "validator": "erwang_v2.validate_annotation_case",
                    "errors": all_errors,
                    "jsonschema_status": schema_status,
                    "quote_checks": [
                        {
                            "evidence_index": index,
                            "quote_check": evidence.get("quote_check"),
                            "passage_id": evidence.get("passage_id"),
                        }
                        for index, evidence in enumerate(v2_case.get("evidences", []))
                    ],
                }

                stored_case: dict[str, Any] | None = None
                ingest_error: str | None = None
                try:
                    stored_case = ingest_case(
                        connection,
                        v2_case,
                        origin="legacy_ai_json",
                    )
                except Exception as error:  # pragma: no cover - reported for audit
                    ingest_error = f"{type(error).__name__}:{error}"
                case_reports.append(
                    _case_report(
                        ai_path=ai_path,
                        case_index=case_index,
                        legacy_case=legacy_case,
                        v2_case=v2_case,
                        custom_errors=custom_errors,
                        schema_status=schema_status,
                        schema_errors=schema_errors,
                        stored_case=stored_case,
                        ingest_error=ingest_error,
                    )
                )

        connection.commit()
        database_counts_report = database_counts(connection)
        lifecycle_counts = dict(
            connection.execute(
                "SELECT lifecycle, COUNT(*) FROM annotation_cases GROUP BY lifecycle"
            ).fetchall()
        )
        machine_counts = dict(
            connection.execute(
                "SELECT machine_status, COUNT(*) FROM annotation_cases GROUP BY machine_status"
            ).fetchall()
        )
        human_counts = dict(
            connection.execute(
                "SELECT human_status, COUNT(*) FROM annotation_cases GROUP BY human_status"
            ).fetchall()
        )
        source_version_conflicts: list[dict[str, Any]] = []
        conflict_groups = connection.execute(
            """
            SELECT work_key, source_file, COUNT(*) AS version_count
            FROM source_documents
            GROUP BY work_key, source_file
            HAVING COUNT(*) > 1
            """
        ).fetchall()
        for group in conflict_groups:
            versions = connection.execute(
                """
                SELECT source_document_id, source_file_sha256, created_at
                FROM source_documents
                WHERE work_key = ? AND source_file = ?
                ORDER BY created_at
                """,
                (group["work_key"], group["source_file"]),
            ).fetchall()
            source_version_conflicts.append(
                {
                    "work_key": group["work_key"],
                    "source_file": group["source_file"],
                    "version_count": group["version_count"],
                    "versions": [dict(version) for version in versions],
                }
            )

    total_cases = len(case_reports)
    approved_cases = sum(item["machine_status"] == "approved" for item in case_reports)
    draft_cases = sum(item["machine_status"] == "draft" for item in case_reports)
    rejected_cases = sum(item["machine_status"] == "rejected" for item in case_reports)
    stored_cases = sum(item["database"]["status"] == "stored" for item in case_reports)
    quote_counts = Counter()
    for item in case_reports:
        quote_counts.update(item["quote_check_counts"])
    context_counts = Counter()
    for item in case_reports:
        context_counts.update(item["unlinked_full_json_context_counts"])
    no_evidence_cases = [
        item["case_id"] for item in case_reports if item["evidence_count"] == 0
    ]
    validation_cases = [
        item for item in case_reports if item["validation_errors"]
    ]

    findings: list[dict[str, Any]] = []
    if mapping_errors:
        findings.append(
            {
                "severity": "critical",
                "confidence": "high",
                "finding": "有 AI JSON 无法映射到唯一原典 Markdown。",
                "count": len(mapping_errors),
                "evidence": mapping_errors,
                "remediation": "补充 work_key/source_work 映射后再迁移。",
            }
        )
    if source_version_conflicts:
        findings.append(
            {
                "severity": "high",
                "confidence": "high",
                "finding": "同一 work_key 和 source_file 在工作库中存在多个 source hash 版本。",
                "count": len(source_version_conflicts),
                "evidence": source_version_conflicts,
                "remediation": "先确定当前 canonical Markdown 版本；旧版本保留为历史来源，不要在未确认时混合迁移。",
            }
        )
    if draft_cases:
        findings.append(
            {
                "severity": "medium",
                "confidence": "high",
                "finding": "部分案例结构基本可用，但引用的外部典籍未进入当前 canonical passage 库，保留为 machine draft。",
                "count": draft_cases,
                "evidence": [
                    {
                        "case_id": item["case_id"],
                        "case_title": item["case_title"],
                        "source_resolution": item["source_resolution_counts"],
                        "full_json_context": item["full_json_context_counts"],
                    }
                    for item in case_reports
                    if item["machine_status"] == "draft"
                ],
                "remediation": "建立外部证据来源登记和 passage 后重新核验；在此之前不得升级为 machine approved 或 gold。",
            }
        )
    if rejected_cases:
        findings.append(
            {
                "severity": "high",
                "confidence": "high",
                "finding": "部分旧 AI 案例存在结构性缺项，已作为 rejected 审计记录保留。",
                "count": rejected_cases,
                "evidence": [
                    {
                        "case_id": item["case_id"],
                        "case_title": item["case_title"],
                        "errors": item["validation_errors"],
                    }
                    for item in validation_cases
                    if item["machine_status"] == "rejected"
                ],
                "remediation": "先修复缺失证据、quote 来源或字段，再重新跑入库；不得直接改为 approved。",
            }
        )
    if quote_counts.get("failed"):
        findings.append(
            {
                "severity": "high",
                "confidence": "high",
                "finding": "存在无法在对应 Markdown passage 中命中的证据引文。",
                "count": quote_counts["failed"],
                "evidence": "按 case_reports.quote_check_counts 分案记录。",
                "remediation": "核查底本版本、DOCX/Markdown 转换和 evidence passage 归属；不自动修复字符。",
            }
        )
    if context_counts.get("exact") or context_counts.get("punctuation_normalized"):
        findings.append(
            {
                "severity": "medium",
                "confidence": "high",
                "finding": "部分未挂接 canonical passage 的引文可以在对应 full_json 注释上下文中找到，但这不等于外部底本已核验。",
                "count": context_counts.get("exact", 0)
                + context_counts.get("punctuation_normalized", 0),
                "evidence": dict(context_counts),
                "remediation": "保留 full_json 作为迁移线索，补齐外部来源后再做严格 quote 校验。",
            }
        )
    if no_evidence_cases:
        findings.append(
            {
                "severity": "high",
                "confidence": "high",
                "finding": "存在没有 evidence 的旧 AI 案例；V2 最小 case 要求至少有一条证据。",
                "count": len(no_evidence_cases),
                "evidence": no_evidence_cases,
                "remediation": "保留为 rejected/待补证据，不进入 machine_draft 或 gold。",
            }
        )

    report = {
        "report_version": "v2-batch-migration.v1",
        "run_status": "completed_with_findings" if findings else "completed",
        "workflow": [
            "inventory_legacy_ai_json",
            "map_source_work_to_markdown",
            "build_source_passages",
            "extract_and_audit_candidates",
            "adapt_legacy_cases_to_annotation_case.v1",
            "validate_schema_quote_source_and_hash",
            "ingest_approved_as_machine_draft_and_failures_as_rejected_audit_records",
            "keep_human_review_pending",
        ],
        "inputs": {
            "ai_directory": _relative(ai_dir),
            "file_count": len(ai_paths),
            "expected_case_count": 17,
        },
        "summary": {
            "source_file_count": len(source_profiles),
            "mapping_error_count": len(mapping_errors),
            "case_count": total_cases,
            "machine_approved_count": approved_cases,
            "machine_draft_count": draft_cases,
            "machine_rejected_count": rejected_cases,
            "database_stored_count": stored_cases,
            "human_pending_count": sum(
                item["human_status"] == "pending" for item in case_reports
            ),
            "quote_check_counts": dict(quote_counts),
            "full_json_context_counts": dict(context_counts),
            "no_evidence_case_count": len(no_evidence_cases),
        },
        "source_profiles": source_profiles,
        "database": {
            "path": _relative(database_path),
            "counts": database_counts_report,
            "lifecycle_counts": lifecycle_counts,
            "machine_status_counts": machine_counts,
            "human_status_counts": human_counts,
            "source_version_conflicts": source_version_conflicts,
        },
        "findings": findings,
        "cases": case_reports,
    }
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description="Batch-migrate all legacy AI JSON cases into V2.")
    parser.add_argument("--ai-dir", type=Path, default=AI_DIR)
    parser.add_argument("--database", type=Path, default=DEFAULT_DATABASE)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    args = parser.parse_args()

    report = run_batch(
        ai_dir=args.ai_dir,
        database_path=args.database,
        report_path=args.report,
    )
    print(json.dumps({
        "run_status": report["run_status"],
        "summary": report["summary"],
        "database": report["database"],
        "findings": report["findings"],
        "report": _relative(args.report),
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
