from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.error
import urllib.request
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


V2_ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = V2_ROOT.parent
sys.path.insert(0, str(V2_ROOT / "src"))
sys.path.insert(0, str(V2_ROOT / "scripts"))

from erwang_v2.candidate_auditor import audit_candidates
from erwang_v2.candidate_extractor import extract_candidates
from erwang_v2.database import (
    database_counts,
    ingest_candidate_items,
    ingest_case,
    ingest_legacy_catalog,
    ingest_legacy_dictionary_inventory,
    ingest_passages,
    open_database,
)
from erwang_v2.legacy_dictionary_adapter import load_legacy_dictionary_material
from erwang_v2.original_candidate_adapter import (
    build_candidate_records,
    candidate_payload,
    fill_missing_process_fields,
    normalize_ai_case,
)
from erwang_v2.passage_builder import build_passages
from erwang_v2.validate_annotation_case import validate_case
from run_batch_migration import run_batch


LEGACY_DATABASE = PROJECT_ROOT / "02-数据库/data/dictionary.db"
LEGACY_SOURCE = PROJECT_ROOT / "02-数据库/main/source.txt"
LEGACY_PARSER = PROJECT_ROOT / "02-数据库/main/parser.py"
V2_DATABASE = V2_ROOT / "data/real_runs/annotation_v2.db"
OUTPUT_DIR = V2_ROOT / "data/real_runs/unified_ingress"
REPORT_FILE = V2_ROOT / "data/real_runs/unified_ingress_report.json"

ORIGINAL_WORKS = {
    "读书杂志": {
        "work_key": "dushu_zazhi",
        "markdown": PROJECT_ROOT / "04-项目文献/A-原著原典/读书杂志_王念孙.md",
    },
    "广雅疏证": {
        "work_key": "guangya_shuzheng",
        "markdown": PROJECT_ROOT / "04-项目文献/A-原著原典/广雅疏证_王念孙.md",
    },
    "经传释词": {
        "work_key": "jingzhuan_shici",
        "markdown": PROJECT_ROOT / "04-项目文献/A-原著原典/经传释词_王引之.md",
    },
    "经义述闻": {
        "work_key": "jingyi_shuwen",
        "markdown": PROJECT_ROOT / "04-项目文献/A-原著原典/经义述闻_王引之.md",
    },
}

PROMPT_VERSION = "original-text-to-annotation-case.v1"
DEFAULT_MODEL = "deepseek-v4-flash"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _relative(path: Path) -> str:
    try:
        return path.resolve().relative_to(PROJECT_ROOT.resolve()).as_posix()
    except ValueError:
        return path.as_posix()


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _write_jsonl(path: Path, values: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for value in values:
            handle.write(json.dumps(value, ensure_ascii=False, separators=(",", ":")) + "\n")


def _schema_errors(case: dict[str, Any]) -> list[str]:
    try:
        from jsonschema import Draft202012Validator
    except ImportError:
        return ["jsonschema_dependency_required"]
    schema = json.loads(
        (V2_ROOT / "schemas/annotation_case.v1.schema.json").read_text(encoding="utf-8")
    )
    return sorted(
        ".".join(str(part) for part in error.absolute_path) + ": " + error.message
        for error in Draft202012Validator(schema).iter_errors(case)
    )


def _load_env_file(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.exists():
        return values
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def _api_settings() -> tuple[str | None, str, str]:
    env = {}
    env.update(_load_env_file(PROJECT_ROOT / "04-项目文献/D-标注/json/.env"))
    env.update(_load_env_file(PROJECT_ROOT / "03-项目网站/.env"))
    key = os.environ.get("DEEPSEEK_API_KEY") or env.get("DEEPSEEK_API_KEY")
    model = os.environ.get("DEEPSEEK_MODEL") or env.get("DEEPSEEK_MODEL") or DEFAULT_MODEL
    return key, model, env.get("DEEPSEEK_URL", "https://api.deepseek.com/chat/completions")


def _extract_json_content(content: str) -> dict[str, Any]:
    text = content.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.IGNORECASE)
        text = re.sub(r"\s*```$", "", text)
    value = json.loads(text)
    if isinstance(value, dict) and isinstance(value.get("cases"), list):
        return value["cases"][0] if value["cases"] else {}
    if not isinstance(value, dict):
        raise ValueError("ai_output_is_not_object")
    return value


def _call_candidate_ai(
    candidate: dict[str, Any], passage: dict[str, Any], *, api_key: str, model: str, url: str
) -> tuple[dict[str, Any], dict[str, Any]]:
    payload = candidate_payload(candidate, passage, prompt_version=PROMPT_VERSION)
    system = (
        "你是古汉语考据数据结构化助手。只生成机器草稿，不进行人工审校。"
        "你只能使用用户提供的王氏原文候选，不得编造外部典籍、外部引文或不存在的结论。"
    )
    user = (
        "请输出一个 annotation_case.v1 JSON 对象。source_work、source_passage_id、"
        "source_location 必须保留。target_work 如果输入没有明确给出就留空，"
        "target_scope.status 使用 unresolved。所有 quote 必须是 candidate_text 的连续子串；"
        "无法确定的 term_relations 可以使用 relation_type=未定。不要输出 Markdown。\n\n"
        + json.dumps(payload, ensure_ascii=False, indent=2)
    )
    request_payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "temperature": 0.1,
        "max_tokens": 3000,
    }
    request = urllib.request.Request(
        url,
        data=json.dumps(request_payload, ensure_ascii=False).encode("utf-8"),
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=120) as response:
        body = json.loads(response.read().decode("utf-8"))
    content = body["choices"][0]["message"]["content"]
    return _extract_json_content(content), {"model": body.get("model", model), "payload": payload}


def _choose_sample(records: list[dict[str, Any]], passage_map: dict[str, dict[str, Any]]) -> dict[str, Any]:
    usable = [
        record
        for record in records
        if record.get("candidate_status") == "approved"
        and 40 <= len(record.get("candidate_text", "")) <= 600
        and not record.get("risk_flags")
        and record.get("passage_id") in passage_map
    ]
    if not usable:
        usable = [record for record in records if record.get("passage_id") in passage_map]
    return min(usable, key=lambda item: len(item.get("candidate_text", "")))


def _fallback_original_case(
    candidate: dict[str, Any], passage: dict[str, Any], *, source_file: str
) -> dict[str, Any]:
    raw = {
        "case_title": passage.get("entry_title") or candidate.get("candidate_id"),
        "target_text": passage.get("entry_title") or "未定",
        "term_relations": [],
        "evidences": [],
        "conclusion": "机器候选记录，尚未进行 AI 语义生成。",
    }
    case = normalize_ai_case(
        raw,
        candidate=candidate,
        passage=passage,
        source_file=source_file,
        model="not_called",
        prompt_version="original-text-machine-fallback.v1",
    )
    case["case_id"] = f"original-machine:{candidate['candidate_id']}"
    case["submitted_by"] = "original_markdown_machine_adapter"
    case["method_profile"]["ai_generated"] = False
    case["machine_result"]["status"] = "draft"
    case["machine_result"]["validation_state"] = "candidate_machine_fallback"
    case["_migration"]["source_format"] = "original_markdown_candidate_machine"
    case["_migration"]["transformation_kind"] = "original_text_machine_case_adapter"
    case["_migration"]["provenance"]["ai_generation_performed"] = False
    case["_migration"]["field_boundary"]["ai_generation"] = "not_called; this is a source-text machine fallback"
    return case


def _validate_original_case(case: dict[str, Any], passage_map: dict[str, dict[str, Any]]) -> list[str]:
    custom_errors = validate_case(case, passage_map)
    schema_errors = _schema_errors(case)
    case["machine_result"]["validation_errors"] = custom_errors + [
        f"jsonschema:{error}" for error in schema_errors
    ]
    case["machine_result"]["jsonschema_status"] = "passed" if not schema_errors else "failed"
    return custom_errors + schema_errors


def run_unified_ingress(
    *,
    database_path: Path = V2_DATABASE,
    output_dir: Path = OUTPUT_DIR,
    report_path: Path = REPORT_FILE,
    with_ai_samples: bool = True,
) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    report: dict[str, Any] = {
        "report_version": "v2-unified-ingress.v1",
        "generated_at": _now(),
        "output_schema": "annotation_case.v1",
        "provenance_contract": {
            "origin_values": {
                "legacy_ai_json_reprocessing": "旧 AI JSON 经过 V2 adapter 的再加工",
                "legacy_dictionary_db_reprocessing": "旧机器 dictionary.db 经过字段映射的再加工",
                "original_markdown_ai": "王氏原文 passage/candidate 经 AI 生成后的再加工",
                "original_markdown_machine_extraction": "王氏原文经 parser/candidate/auditor 的机器抽取",
            },
            "human_review_performed": False,
            "gold_promotion_performed": False,
            "semantic_claim": "origin 和 provenance 记录处理来源，但不证明学术结论正确。",
        },
    }

    batch_report = run_batch(
        database_path=database_path,
        report_path=V2_ROOT / "data/real_runs/batch_migration_report.json",
    )
    report["legacy_ai_json_route"] = {
        "status": "completed",
        "source": batch_report.get("inputs"),
        "summary": batch_report.get("summary"),
        "origin": "legacy_ai_json_reprocessing",
        "report_file": "v2/data/real_runs/batch_migration_report.json",
    }

    legacy_cases, legacy_source_passages, legacy_target_passages, legacy_material = load_legacy_dictionary_material(
        LEGACY_DATABASE,
        source_text_path=LEGACY_SOURCE,
        parser_path=LEGACY_PARSER,
    )
    _write_jsonl(output_dir / "legacy_dictionary_cases.annotation_case.v1.jsonl", legacy_cases)
    _write_jsonl(output_dir / "legacy_source_passages.passage.v1.jsonl", legacy_source_passages)
    _write_jsonl(output_dir / "legacy_derived_evidence_passages.passage.v1.jsonl", legacy_target_passages)
    legacy_report = legacy_material["report"]
    legacy_schema_errors = sum(len(_schema_errors(case)) for case in legacy_cases)

    original_reports: list[dict[str, Any]] = []
    all_candidate_records: list[dict[str, Any]] = []
    original_ai_cases: list[dict[str, Any]] = []
    original_sample_reports: list[dict[str, Any]] = []
    api_key, model, api_url = _api_settings()

    with open_database(database_path) as connection:
        legacy_source_document_id = ingest_passages(
            connection,
            legacy_source_passages,
            source_kind="legacy_source_txt",
            metadata={
                "canonical_status": "legacy_unverified",
                "source_role": "legacy_source",
                "source_version_reason": "source.txt is upstream parser input, not an original-canonical edition",
            },
        )
        legacy_target_document_id = ingest_passages(
            connection,
            legacy_target_passages,
            source_kind="legacy_derived_quote",
            metadata={
                "canonical_status": "legacy_unverified",
                "source_role": "legacy_derived",
                "source_version_reason": "quote text was derived from dictionary.db evidence rows and is not a cited-work canonical edition",
            },
        )
        legacy_catalog_counts = ingest_legacy_catalog(
            connection,
            terms=legacy_material["catalog_terms"],
            works=legacy_material["catalog_works"],
            source_file=_relative(LEGACY_DATABASE),
        )
        for source_work, config in ORIGINAL_WORKS.items():
            markdown = config["markdown"]
            passages = build_passages(markdown, config["work_key"])
            source_document_id = ingest_passages(
                connection,
                passages,
                source_kind="original_markdown",
                metadata={
                    "ingress_route": "original_text",
                    "provenance_contract": "original_markdown_machine_extraction",
                },
            )
            layers = extract_candidates(passages)
            audit = audit_candidates(
                layers["parsed_items"] + layers["candidate_items"], passages
            )
            records = build_candidate_records(
                passages,
                layers,
                audit,
                source_work=source_work,
                source_document_id=source_document_id,
                source_file=_relative(markdown),
            )
            ingest_candidate_items(
                connection,
                records,
                source_document_id=source_document_id,
                origin="original_markdown_machine_extraction",
            )
            all_candidate_records.extend(records)
            passage_map = {passage["passage_id"]: passage for passage in passages}
            sample = _choose_sample(records, passage_map)
            ai_input = candidate_payload(sample, passage_map[sample["passage_id"]], prompt_version=PROMPT_VERSION)
            original_sample_reports.append(
                {
                    "source_work": source_work,
                    "candidate_id": sample["candidate_id"],
                    "passage_id": sample["passage_id"],
                    "candidate_text_length": len(sample.get("candidate_text", "")),
                    "ai_input": ai_input,
                }
            )
            original_reports.append(
                {
                    "source_work": source_work,
                    "work_key": config["work_key"],
                    "source_file": _relative(markdown),
                    "source_document_id": source_document_id,
                    "passage_count": len(passages),
                    "parsed_count": len(layers["parsed_items"]),
                    "candidate_count": len(layers["candidate_items"]),
                    "skipped_count": len(layers["skipped_items"]),
                    "audited_count": len(audit),
                    "candidate_status_counts": dict(Counter(item.get("machine_status") for item in audit)),
                }
            )

        _write_jsonl(output_dir / "original_text_candidate_items.candidate_item.v1.jsonl", all_candidate_records)
        _write_jsonl(output_dir / "original_text_ai_inputs.candidate_ai_input.v1.jsonl", [item["ai_input"] for item in original_sample_reports])

        for sample_report in original_sample_reports:
            candidate = next(
                item for item in all_candidate_records if item["candidate_id"] == sample_report["candidate_id"]
            )
            existing = connection.execute(
                "SELECT case_json, origin, machine_status, lifecycle FROM annotation_cases WHERE case_id = ?",
                (f"original-ai:{candidate['candidate_id']}",),
            ).fetchone()
            if (
                not with_ai_samples
                and existing is not None
                and existing["origin"] == "original_markdown_ai"
            ):
                preserved_case = json.loads(existing["case_json"])
                fill_missing_process_fields(preserved_case)
                ingest_case(connection, preserved_case, origin="original_markdown_ai")
                connection.execute(
                    "UPDATE candidate_items SET output_case_id = ?, updated_at = ? WHERE candidate_id = ?",
                    (preserved_case["case_id"], _now(), candidate["candidate_id"]),
                )
                original_ai_cases.append(preserved_case)
                sample_report.update(
                    {
                        "ai_status": "preserved_existing_ai_case",
                        "model": preserved_case.get("_migration", {})
                        .get("provenance", {})
                        .get("model"),
                        "case_id": preserved_case["case_id"],
                        "machine_status": preserved_case.get("machine_result", {}).get("status"),
                        "validation_error_count": len(
                            preserved_case.get("machine_result", {}).get("validation_errors", [])
                        ),
                        "database_status": existing["lifecycle"],
                    }
                )
                continue
            passage = connection.execute(
                "SELECT passage_id, work_key, document_title, section_title, entry_title, md_line_start, md_line_end, raw_text, plain_text, normalized_text, inline_notes_json FROM passages WHERE passage_id = ?",
                (candidate["passage_id"],),
            ).fetchone()
            if passage is None:
                sample_report["status"] = "failed_missing_passage"
                continue
            passage_dict = dict(passage)
            passage_dict["source_file"] = candidate["provenance"]["source_file"]
            try:
                if with_ai_samples and api_key:
                    raw_ai, ai_meta = _call_candidate_ai(
                        candidate,
                        passage_dict,
                        api_key=api_key,
                        model=model,
                        url=api_url,
                    )
                    case = normalize_ai_case(
                        raw_ai,
                        candidate=candidate,
                        passage=passage_dict,
                        source_file=candidate["provenance"]["source_file"],
                        model=ai_meta["model"],
                        prompt_version=PROMPT_VERSION,
                    )
                    sample_report["ai_status"] = "completed"
                    sample_report["model"] = ai_meta["model"]
                else:
                    case = _fallback_original_case(
                        candidate,
                        passage_dict,
                        source_file=candidate["provenance"]["source_file"],
                    )
                    sample_report["ai_status"] = "not_called_fallback"
                    sample_report["model"] = "not_called"
                validation_errors = _validate_original_case(case, {candidate["passage_id"]: passage_dict})
                stored_origin = (
                    "original_markdown_ai"
                    if case["_migration"]["provenance"].get("ai_generation_performed")
                    else "original_markdown_machine_extraction"
                )
                stored = ingest_case(connection, case, origin=stored_origin)
                connection.execute(
                    "UPDATE candidate_items SET output_case_id = ?, updated_at = ? WHERE candidate_id = ?",
                    (case["case_id"], _now(), candidate["candidate_id"]),
                )
                original_ai_cases.append(case)
                sample_report["case_id"] = case["case_id"]
                sample_report["machine_status"] = case["machine_result"]["status"]
                sample_report["validation_error_count"] = len(validation_errors)
                sample_report["database_status"] = stored.get("lifecycle")
            except (
                urllib.error.HTTPError,
                urllib.error.URLError,
                TimeoutError,
                OSError,
                ValueError,
                KeyError,
            ) as error:
                sample_report["ai_status"] = "api_failed_fallback"
                sample_report["error"] = f"{type(error).__name__}:{error}"
                case = _fallback_original_case(
                    candidate,
                    passage_dict,
                    source_file=candidate["provenance"]["source_file"],
                )
                validation_errors = _validate_original_case(case, {candidate["passage_id"]: passage_dict})
                stored = ingest_case(connection, case, origin="original_markdown_machine_extraction")
                connection.execute(
                    "UPDATE candidate_items SET output_case_id = ?, updated_at = ? WHERE candidate_id = ?",
                    (case["case_id"], _now(), candidate["candidate_id"]),
                )
                original_ai_cases.append(case)
                sample_report["case_id"] = case["case_id"]
                sample_report["machine_status"] = case["machine_result"]["status"]
                sample_report["validation_error_count"] = len(validation_errors)
                sample_report["database_status"] = stored.get("lifecycle")

        for case in legacy_cases:
            ingest_case(connection, case, origin="legacy_dictionary_db_reprocessing")
        legacy_inventory_counts = ingest_legacy_dictionary_inventory(
            connection,
            terms=legacy_material["all_terms"],
            works=legacy_material["all_works"],
            cases=legacy_cases,
            source_file=_relative(LEGACY_DATABASE),
        )
        connection.commit()

        db_counts = database_counts(connection)
        integrity = connection.execute("PRAGMA integrity_check").fetchone()[0]
        foreign_keys = connection.execute("PRAGMA foreign_key_check").fetchall()
        origin_counts = {
            row[0]: row[1]
            for row in connection.execute("SELECT origin, COUNT(*) FROM annotation_cases GROUP BY origin")
        }
        candidate_origin_counts = {
            row[0]: row[1]
            for row in connection.execute("SELECT origin, COUNT(*) FROM candidate_items GROUP BY origin")
        }
        candidate_counts = {
            row[0]: row[1]
            for row in connection.execute("SELECT candidate_status, COUNT(*) FROM candidate_items GROUP BY candidate_status")
        }
        gold_count = connection.execute(
            "SELECT COUNT(*) FROM v_gold_cases"
        ).fetchone()[0]
        review_event_count = connection.execute(
            "SELECT COUNT(*) FROM review_events"
        ).fetchone()[0]

    _write_jsonl(output_dir / "original_text_ai_cases.annotation_case.v1.jsonl", original_ai_cases)
    _write_jsonl(output_dir / "legacy_dictionary_cases.annotation_case.v1.jsonl", legacy_cases)

    report.update(
        {
            "status": "completed_with_machine_boundaries",
            "legacy_dictionary_db_route": {
                **legacy_report,
                "origin": "legacy_dictionary_db_reprocessing",
                "schema_error_count": legacy_schema_errors,
                "output_file": _relative(output_dir / "legacy_dictionary_cases.annotation_case.v1.jsonl"),
                "source_passage_file": _relative(output_dir / "legacy_source_passages.passage.v1.jsonl"),
                "target_passage_file": _relative(output_dir / "legacy_derived_evidence_passages.passage.v1.jsonl"),
                "source_document_ids": {
                    "legacy_source": legacy_source_document_id,
                    "legacy_derived": legacy_target_document_id,
                },
                "catalog_counts": legacy_catalog_counts,
                "inventory_counts": legacy_inventory_counts,
            },
            "original_markdown_route": {
                "status": "completed",
                "origin_candidates": "original_markdown_machine_extraction",
                "origin_cases": [
                    "original_markdown_ai",
                    "original_markdown_machine_extraction",
                ],
                "sources": original_reports,
                "candidate_count": len(all_candidate_records),
                "candidate_status_counts": candidate_counts,
                "candidate_output_file": _relative(output_dir / "original_text_candidate_items.candidate_item.v1.jsonl"),
                "ai_input_file": _relative(output_dir / "original_text_ai_inputs.candidate_ai_input.v1.jsonl"),
                "sample_runs": original_sample_reports,
                "case_output_file": _relative(output_dir / "original_text_ai_cases.annotation_case.v1.jsonl"),
            },
            "v2_database": {
                "path": _relative(database_path),
                "counts": db_counts,
                "case_origin_counts": origin_counts,
                "candidate_origin_counts": candidate_origin_counts,
                "integrity_check": integrity,
                "foreign_key_violation_count": len(foreign_keys),
                "gold_count": gold_count,
                "review_event_count": review_event_count,
            },
            "boundaries": {
                "human_review_performed": False,
                "gold_promotion_performed": False,
                "original_candidate_batch_ai_enrichment": "only one representative candidate per Wang work is AI-called; all candidates are stored as candidate_item.v1 inputs",
                "legacy_dictionary_semantic_revalidation": "not performed; old fields and missing links are preserved as machine draft metadata",
            },
        }
    )
    _write_json(report_path, report)
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description="Run legacy-machine and original-text ingress routes into V2.")
    parser.add_argument("--database", type=Path, default=V2_DATABASE)
    parser.add_argument("--output-dir", type=Path, default=OUTPUT_DIR)
    parser.add_argument("--report", type=Path, default=REPORT_FILE)
    parser.add_argument("--no-ai-samples", action="store_true")
    args = parser.parse_args()
    report = run_unified_ingress(
        database_path=args.database,
        output_dir=args.output_dir,
        report_path=args.report,
        with_ai_samples=not args.no_ai_samples,
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report.get("status") == "completed_with_machine_boundaries" else 1


if __name__ == "__main__":
    raise SystemExit(main())
