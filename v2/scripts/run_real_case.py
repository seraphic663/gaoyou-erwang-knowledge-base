from __future__ import annotations

import argparse
import hashlib
import json
import sys
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
    select_legacy_case,
)
from erwang_v2.passage_builder import build_passages
from erwang_v2.validate_annotation_case import classify_machine_status, validate_case


DEFAULT_MARKDOWN = PROJECT_ROOT / "04-项目文献/A-原著原典/读书杂志_王念孙.md"
DEFAULT_AI_JSON = PROJECT_ROOT / "04-项目文献/D-标注/json/ai_json/读书杂志_平原之隰-譕臣_卢飞宇.json"
DEFAULT_FULL_JSON = PROJECT_ROOT / "04-项目文献/D-标注/json/full_json/读书杂志_平原之隰-譕臣_卢飞宇.json"
DEFAULT_DATABASE = V2_ROOT / "data/real_runs/annotation_v2.db"


def _relative(path: Path) -> str:
    try:
        return path.resolve().relative_to(PROJECT_ROOT.resolve()).as_posix()
    except ValueError:
        return path.as_posix()


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _candidate_profile(
    passages: list[dict[str, Any]],
) -> dict[str, Any]:
    layers = extract_candidates(passages)
    candidates = layers["parsed_items"] + layers["candidate_items"]
    audit = audit_candidates(candidates, passages)
    return {
        "parsed_count": len(layers["parsed_items"]),
        "candidate_count": len(layers["candidate_items"]),
        "skipped_count": len(layers["skipped_items"]),
        "audited_count": len(audit),
        "audit_status_counts": dict(Counter(item["machine_status"] for item in audit)),
        "risk_flag_counts": dict(
            Counter(flag for item in audit for flag in item.get("risk_flags", []))
        ),
    }


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


def run_case(
    *,
    markdown_path: Path,
    ai_json_path: Path,
    full_json_path: Path,
    case_title: str,
    database_path: Path | None = None,
) -> dict[str, Any]:
    container = load_legacy_ai_json(ai_json_path)
    case_index, legacy_case = select_legacy_case(container, case_title)
    passages = build_passages(markdown_path, "dushu_zazhi")
    passage_map = {passage["passage_id"]: passage for passage in passages}

    provenance = {
        "source_markdown_sha256": _sha256(markdown_path),
        "legacy_ai_json_sha256": _sha256(ai_json_path),
        "full_json": _relative(full_json_path),
        "full_json_sha256": _sha256(full_json_path) if full_json_path.exists() else None,
    }
    v2_case = adapt_legacy_case(
        legacy_case,
        passages,
        source_markdown=_relative(markdown_path),
        legacy_ai_json=_relative(ai_json_path),
        case_index=case_index,
        submitted_by="legacy_ai_json_adapter",
        additional_provenance=provenance,
    )
    errors = validate_case(v2_case, passage_map)
    schema_status, schema_errors = _schema_errors(v2_case)
    all_errors = errors + [f"jsonschema:{error}" for error in schema_errors]
    machine_status = classify_machine_status(errors, schema_errors)
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

    database_report: dict[str, Any] = {
        "status": "not_ingested_validation_failed",
        "path": _relative(database_path) if database_path else None,
    }
    if database_path and machine_status in {"approved", "draft"} and schema_status == "passed":
        with open_database(database_path) as connection:
            source_document_id = ingest_passages(
                connection,
                passages,
                metadata={
                    "legacy_ai_json": _relative(ai_json_path),
                    "full_json": _relative(full_json_path),
                },
            )
            stored_case = ingest_case(
                connection,
                v2_case,
                origin="legacy_ai_json",
            )
            connection.commit()
            database_report = {
                "status": "ingested_machine_case",
                "path": _relative(database_path),
                "source_document_id": source_document_id,
                "case": stored_case,
                "counts": database_counts(connection),
            }

    return {
        "run_status": (
            "machine_valid_human_pending"
            if machine_status in {"approved", "draft"} and schema_status == "passed"
            else "machine_rejected"
        ),
        "workflow": [
            "read_real_markdown",
            "build_passages_with_source_hashes",
            "extract_and_audit_candidates",
            "load_legacy_ai_json_container",
            "adapt_one_legacy_case_to_annotation_case.v1",
            "validate_passage_quote_hash_and_status_fields",
            "ingest_validated_machine_case_to_unified_db",
            "leave_human_review_pending",
        ],
        "inputs": {
            "markdown": _relative(markdown_path),
            "legacy_ai_json": _relative(ai_json_path),
            "full_json": _relative(full_json_path),
            "case_title": case_title,
        },
        "profile": {
            "passage_count": len(passages),
            "candidate_layers": _candidate_profile(passages),
            "source_passage_id": v2_case.get("source_passage_id"),
            "source_location": v2_case.get("source_location"),
            "evidence_count": len(v2_case.get("evidences", [])),
        },
        "validation_errors": all_errors,
        "jsonschema_status": schema_status,
        "database": database_report,
        "case": v2_case,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Run one real case through V2.")
    parser.add_argument("--case-title", default="平原之隰")
    parser.add_argument("--markdown", type=Path, default=DEFAULT_MARKDOWN)
    parser.add_argument("--ai-json", type=Path, default=DEFAULT_AI_JSON)
    parser.add_argument("--full-json", type=Path, default=DEFAULT_FULL_JSON)
    parser.add_argument("--database", type=Path, default=DEFAULT_DATABASE)
    parser.add_argument("--output", type=Path, default=None)
    args = parser.parse_args()

    report = run_case(
        markdown_path=args.markdown,
        ai_json_path=args.ai_json,
        full_json_path=args.full_json,
        case_title=args.case_title,
        database_path=args.database,
    )
    serialized = json.dumps(report, ensure_ascii=False, indent=2)
    print(serialized)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(serialized + "\n", encoding="utf-8")
        print(f"report_written={args.output}")
    return 0 if report["run_status"] == "machine_valid_human_pending" else 1


if __name__ == "__main__":
    raise SystemExit(main())
