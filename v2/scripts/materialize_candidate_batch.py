#!/usr/bin/env python3
"""Materialize one deterministic candidate batch as machine candidate shells.

The command is intentionally narrow: it consumes one batch from the immutable
candidate plan, creates traceable ``annotation_case.v1`` shells, and links each
candidate through ``candidate_items.output_case_id``.  It never calls AI, never
resolves target works, and never changes human/gold state.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


V2_ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = V2_ROOT.parent
DEFAULT_DATABASE = V2_ROOT / "data/real_runs/annotation_v2.db"
DEFAULT_PLAN = V2_ROOT / "data/real_runs/candidate_materialization_plan.candidate_shell.v1.jsonl"
DEFAULT_OUTPUT = V2_ROOT / "data/real_runs/candidate_shell_batch_0001.annotation_case.v1.jsonl"
DEFAULT_REPORT = V2_ROOT / "data/real_runs/candidate_shell_batch_0001_report.json"

sys.path.insert(0, str(V2_ROOT / "src"))
from erwang_v2.database import ingest_case, open_database  # noqa: E402
from erwang_v2.original_candidate_adapter import fill_missing_process_fields  # noqa: E402
from erwang_v2.validate_annotation_case import validate_case  # noqa: E402


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def relative_path(value: str | None) -> str | None:
    if not value:
        return None
    path = Path(value)
    try:
        return path.resolve().relative_to(PROJECT_ROOT.resolve()).as_posix()
    except ValueError:
        return str(path)


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def load_plan(path: Path, batch_id: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        value = json.loads(line)
        if value.get("batch_id") == batch_id:
            rows.append(value)
    rows.sort(key=lambda item: item.get("candidate_id", ""))
    if not rows:
        raise ValueError(f"batch_not_found:{batch_id}")
    return rows


def _passage_map(connection: sqlite3.Connection, passage_ids: list[str]) -> dict[str, dict[str, Any]]:
    placeholders = ",".join("?" for _ in passage_ids)
    rows = connection.execute(
        f"""
        SELECT p.*, sd.source_file, sd.source_file_sha256,
               sd.source_document_id AS joined_source_document_id,
               sd.canonical_status
        FROM passages p
        JOIN source_documents sd ON sd.source_document_id=p.source_document_id
        WHERE p.passage_id IN ({placeholders})
        """,
        tuple(passage_ids),
    ).fetchall()
    return {row["passage_id"]: dict(row) for row in rows}


def build_candidate_shell(
    plan: dict[str, Any], passage: dict[str, Any]
) -> dict[str, Any]:
    candidate_id = plan["candidate_id"]
    candidate_text = plan.get("candidate_text") or ""
    entry_title = (passage.get("entry_title") or "").strip()
    shell_label = entry_title or candidate_id
    quote_start = passage.get("plain_text", "").find(candidate_text)
    if quote_start < 0:
        raise ValueError(f"candidate_not_in_source_passage:{candidate_id}")
    source_location = {
        "passage_id": plan["source_passage_id"],
        "source_document_id": plan["source_document_id"],
        "source_file": relative_path(passage.get("source_file")),
        "source_file_sha256": passage.get("source_file_sha256"),
        "canonical_status": passage.get("canonical_status"),
        "local_ordinal": passage.get("local_ordinal"),
        "md_line_start": passage.get("md_line_start"),
        "md_line_end": passage.get("md_line_end"),
        "document_title": passage.get("document_title"),
        "section_title": passage.get("section_title"),
        "entry_title": passage.get("entry_title"),
    }
    case: dict[str, Any] = {
        "schema_version": "annotation_case.v1",
        "case_id": plan["planned_case_id"],
        "case_title": f"[候选壳] {plan['source_work_raw']} · {shell_label}",
        "submitted_by": "original_markdown_candidate_shell_materializer",
        "reviewed_by": None,
        "source_work": plan["source_work_raw"],
        "source_passage_id": plan["source_passage_id"],
        "source_location": source_location,
        "target_work": "",
        "target_works": [],
        "target_scope": {
            "status": "unresolved",
            "target_works": [],
            "reason": "candidate_shell_does_not_resolve_target_work",
        },
        "target_text": shell_label or candidate_id,
        "target_location": None,
        "term_relations": [
            {
                "source_term": shell_label or "候选文本",
                "target_term": "未定",
                "relation_type": "未定",
                "relation_subtype": None,
                "relation_note": "candidate shell only; no semantic relation generated",
                "mapping_status": "candidate_shell_unresolved",
            }
        ],
        "evidences": [
            {
                "quote": candidate_text,
                "evidence_role": "candidate_source_context",
                "semantic_role": "context_only",
                "source_work": plan["source_work_raw"],
                "passage_id": plan["source_passage_id"],
                "quote_start_char": quote_start,
                "quote_end_char": quote_start + len(candidate_text),
                "quote_sha256": sha256_text(candidate_text),
                "quote_check": "passed",
                "source_location": source_location,
                "source_resolution": "canonical_source_passage",
                "cited_work_match_status": "matched",
                "mapping_status": "candidate_shell_exact_source_quote",
            }
        ],
        "evidence_state": "present",
        "problem_discovery": None,
        "research_question": None,
        "evidence_collection": None,
        "reasoning": None,
        "conclusion": "机器候选壳：仅完成候选入列、原典 passage 绑定和结构化占位，未生成学术结论。",
        "method_profile": {
            "record_kind": "candidate_shell",
            "ai_generated": False,
            "semantic_generation": False,
            "candidate_rule_hits": plan.get("rule_hits", []),
            "candidate_risk_flags": plan.get("risk_flags", []),
            "materialization_policy": "deterministic_candidate_shell.v1",
        },
        "machine_result": {
            "status": "draft",
            "validator": "candidate_shell_materializer",
            "validation_state": "candidate_shell_structural_only",
            "record_kind": "candidate_shell",
            "batch_id": plan.get("batch_id"),
            "candidate_id": candidate_id,
        },
        "human_review": {"status": "pending"},
        "_migration": {
            "source_format": "candidate_item.v1",
            "source_layer": "original_text_candidate",
            "transformation_kind": "deterministic_candidate_shell_materialization",
            "record_kind": "candidate_shell",
            "batch_id": plan.get("batch_id"),
            "provenance": {
                "candidate_id": candidate_id,
                "candidate_status": plan.get("candidate_status"),
                "candidate_text_sha256": sha256_text(candidate_text),
                "candidate_rule_hits": plan.get("rule_hits", []),
                "candidate_risk_flags": plan.get("risk_flags", []),
                "candidate_risk_class": plan.get("risk_class"),
                "source_document_id": plan["source_document_id"],
                "source_passage_id": plan["source_passage_id"],
                "source_file": plan.get("source", {}).get("source_file"),
                "source_file_sha256": plan.get("source", {}).get("source_file_sha256"),
                "source_canonical_status": plan.get("source", {}).get("canonical_status"),
                "plan_schema": plan.get("plan_schema"),
                "plan_policy": plan.get("materialization_policy"),
                "planned_case_id": plan["planned_case_id"],
                "ai_generation_performed": False,
                "human_review_performed": False,
            },
            "field_boundary": {
                "target_work": "unresolved; candidate shell must not infer the target",
                "term_relations": "placeholder only; relation_type=未定",
                "evidence": "exact source context quote only; not an external citation claim",
                "conclusion": "machine structural placeholder; not an academic conclusion",
                "human_review": "not performed",
            },
        },
    }
    return fill_missing_process_fields(case)


def materialize_batch(
    *,
    database_path: Path = DEFAULT_DATABASE,
    plan_path: Path = DEFAULT_PLAN,
    batch_id: str = "original-candidates-0001",
    output_path: Path = DEFAULT_OUTPUT,
    report_path: Path = DEFAULT_REPORT,
) -> dict[str, Any]:
    plans = load_plan(plan_path, batch_id)
    if not 1 <= len(plans) <= 100:
        raise ValueError(f"selected_batch_must_have_1_to_100_rows:{batch_id}:{len(plans)}")
    if any(plan.get("plan_state") != "ready_candidate_shell" for plan in plans):
        raise ValueError(f"selected_batch_contains_nonready_plan:{batch_id}")

    output_cases: list[dict[str, Any]] = []
    skipped_existing = 0
    validation_counts: Counter[str] = Counter()
    with open_database(database_path) as connection:
        passage_map = _passage_map(
            connection,
            [plan["source_passage_id"] for plan in plans],
        )
        missing = [plan["candidate_id"] for plan in plans if plan["source_passage_id"] not in passage_map]
        if missing:
            raise ValueError("batch_passage_missing:" + ",".join(missing[:10]))

        # Preflight all shells before opening the write transaction.
        for plan in plans:
            case = build_candidate_shell(plan, passage_map[plan["source_passage_id"]])
            errors = validate_case(case, {plan["source_passage_id"]: passage_map[plan["source_passage_id"]]})
            case["machine_result"]["validation_errors"] = errors
            case["machine_result"]["validation_status"] = "draft_with_review_boundary" if errors else "passed"
            validation_counts["with_boundary_errors" if errors else "structurally_clean"] += 1
            output_cases.append(case)

        connection.execute("BEGIN IMMEDIATE")
        materialized = 0
        for plan, case in zip(plans, output_cases):
            candidate_row = connection.execute(
                "SELECT output_case_id, provenance_json FROM candidate_items WHERE candidate_id = ?",
                (plan["candidate_id"],),
            ).fetchone()
            if candidate_row is None:
                raise ValueError(f"candidate_not_found:{plan['candidate_id']}")
            existing_case_id = candidate_row["output_case_id"]
            if existing_case_id:
                if existing_case_id != case["case_id"]:
                    raise ValueError(
                        f"candidate_link_conflict:{plan['candidate_id']}:{existing_case_id}:{case['case_id']}"
                    )
                skipped_existing += 1
                continue
            ingest_case(connection, case, origin="original_markdown_candidate_shell")
            provenance = json.loads(candidate_row["provenance_json"] or "{}")
            provenance["materialization"] = {
                "record_kind": "candidate_shell",
                "batch_id": batch_id,
                "case_id": case["case_id"],
                "materializer": "materialize_candidate_batch.v1",
                "materialized_at": now(),
                "human_review_performed": False,
            }
            connection.execute(
                """
                UPDATE candidate_items
                SET output_case_id = ?, provenance_json = ?, updated_at = ?
                WHERE candidate_id = ?
                """,
                (
                    case["case_id"],
                    json.dumps(provenance, ensure_ascii=False, sort_keys=True),
                    now(),
                    plan["candidate_id"],
                ),
            )
            materialized += 1
        connection.commit()

        linked = connection.execute(
            """
            SELECT COUNT(*) FROM candidate_items
            WHERE output_case_id IN (
                SELECT case_id FROM annotation_cases WHERE origin='original_markdown_candidate_shell'
                  AND json_extract(machine_result_json, '$.batch_id') = ?
            )
            """,
            (batch_id,),
        ).fetchone()[0]
        case_count = connection.execute(
            """
            SELECT COUNT(*) FROM annotation_cases
            WHERE origin='original_markdown_candidate_shell'
              AND json_extract(machine_result_json, '$.batch_id') = ?
            """,
            (batch_id,),
        ).fetchone()[0]

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as handle:
        for case in output_cases:
            handle.write(json.dumps(case, ensure_ascii=False, separators=(",", ":")) + "\n")
    report = {
        "report_version": "candidate_shell_batch_materialization.v1",
        "generated_at": now(),
        "database": relative_path(str(database_path)),
        "plan": relative_path(str(plan_path)),
        "batch_id": batch_id,
        "policy": {
            "batch_size_max": 100,
            "ai_called": False,
            "target_work_resolved": False,
            "human_review_performed": False,
            "gold_promotion_performed": False,
            "candidate_link_is_idempotent": True,
        },
        "counts": {
            "planned": len(plans),
            "materialized_now": materialized,
            "skipped_existing": skipped_existing,
            "annotation_cases_in_batch": case_count,
            "candidate_output_links_in_batch": linked,
            "machine_draft": case_count,
            "human_pending": case_count,
            "gold": 0,
        },
        "validation_counts": dict(validation_counts),
        "output": relative_path(str(output_path)),
        "case_ids": [case["case_id"] for case in output_cases],
    }
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", type=Path, default=DEFAULT_DATABASE)
    parser.add_argument("--plan", type=Path, default=DEFAULT_PLAN)
    parser.add_argument("--batch-id", default="original-candidates-0001")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    args = parser.parse_args()
    report = materialize_batch(
        database_path=args.database,
        plan_path=args.plan,
        batch_id=args.batch_id,
        output_path=args.output,
        report_path=args.report,
    )
    print(json.dumps(report["counts"], ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
