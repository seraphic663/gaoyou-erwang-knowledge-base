#!/usr/bin/env python3
"""Create a deterministic, non-mutating batch plan for candidate materialization.

The plan is intentionally not an annotation_case.v1 import.  It records what
would be needed to create a candidate shell while leaving target identity,
semantic relations, and conclusions unresolved.  A later materializer can
consume one batch at a time and keep the same deterministic planned case ID.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


V2_ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = V2_ROOT.parent
DEFAULT_DATABASE = V2_ROOT / "data/real_runs/annotation_v2.db"
DEFAULT_OUTPUT = V2_ROOT / "data/real_runs/candidate_materialization_plan.candidate_shell.v1.jsonl"
DEFAULT_REPORT = V2_ROOT / "data/real_runs/candidate_materialization_plan_report.json"


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


def parse_list(value: str | None) -> list[Any]:
    try:
        parsed = json.loads(value or "[]")
    except (TypeError, ValueError):
        return []
    return parsed if isinstance(parsed, list) else []


def connect_read_only(database_path: Path) -> sqlite3.Connection:
    connection = sqlite3.connect(f"file:{database_path.resolve()}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA query_only = ON")
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def plan_candidates(database_path: Path, batch_size: int = 100) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    if batch_size < 1:
        raise ValueError("batch_size_must_be_positive")
    connection = connect_read_only(database_path)
    try:
        rows = connection.execute(
            """
            SELECT ci.candidate_id, ci.source_document_id, ci.passage_id,
                   ci.work_key, ci.source_work, ci.candidate_text,
                   ci.rule_hits_json, ci.risk_flags_json, ci.candidate_status,
                   ci.origin, ci.output_case_id, ci.provenance_json,
                   sd.source_file, sd.canonical_status,
                   p.local_ordinal, p.md_line_start, p.md_line_end,
                   p.document_title, p.section_title, p.entry_title
            FROM candidate_items ci
            LEFT JOIN source_documents sd
              ON sd.source_document_id = ci.source_document_id
            LEFT JOIN passages p ON p.passage_id = ci.passage_id
            ORDER BY ci.work_key, ci.candidate_id
            """
        ).fetchall()
    finally:
        connection.close()

    unmaterialized = [row for row in rows if not row["output_case_id"]]
    batch_lookup = {
        row["candidate_id"]: f"original-candidates-{index // batch_size + 1:04d}"
        for index, row in enumerate(unmaterialized)
    }
    plans: list[dict[str, Any]] = []
    state_counts: Counter[str] = Counter()
    risk_counts: Counter[str] = Counter()
    work_counts: Counter[str] = Counter()
    batch_counts: Counter[str] = Counter()
    blocked_examples: list[dict[str, Any]] = []

    for row in rows:
        rule_hits = parse_list(row["rule_hits_json"])
        risk_flags = parse_list(row["risk_flags_json"])
        if row["output_case_id"]:
            plan_state = "already_materialized"
        elif not row["passage_id"] or not row["source_document_id"]:
            plan_state = "blocked_missing_link"
        elif row["canonical_status"] != "canonical_active":
            plan_state = "blocked_noncanonical_source"
        elif not (row["candidate_text"] or "").strip():
            plan_state = "blocked_empty_candidate"
        else:
            plan_state = "ready_candidate_shell"
        risk_class = "risk_bearing" if risk_flags else "no_risk_flag"
        batch_id = batch_lookup.get(row["candidate_id"])
        if plan_state == "ready_candidate_shell":
            batch_counts[batch_id or ""] += 1
        state_counts[plan_state] += 1
        risk_counts[risk_class] += 1
        work_counts[row["work_key"]] += 1
        if plan_state.startswith("blocked") and len(blocked_examples) < 20:
            blocked_examples.append(
                {
                    "candidate_id": row["candidate_id"],
                    "state": plan_state,
                    "source_document_id": row["source_document_id"],
                    "passage_id": row["passage_id"],
                }
            )
        plans.append(
            {
                "plan_schema": "candidate_materialization_plan.v1",
                "plan_state": plan_state,
                "batch_id": batch_id,
                "planned_case_id": f"candidate-shell:{row['candidate_id']}",
                "record_kind": "candidate_shell",
                "materialization_policy": "deterministic_candidate_shell.v1",
                "candidate_id": row["candidate_id"],
                "source_document_id": row["source_document_id"],
                "source_passage_id": row["passage_id"],
                "work_key": row["work_key"],
                "source_work_raw": row["source_work"],
                "candidate_text": row["candidate_text"],
                "candidate_status": row["candidate_status"],
                "rule_hits": rule_hits,
                "risk_flags": risk_flags,
                "risk_class": risk_class,
                "existing_output_case_id": row["output_case_id"],
                "source": {
                    "source_file": relative_path(row["source_file"]),
                    "canonical_status": row["canonical_status"],
                    "local_ordinal": row["local_ordinal"],
                    "md_line_start": row["md_line_start"],
                    "md_line_end": row["md_line_end"],
                    "document_title": row["document_title"],
                    "section_title": row["section_title"],
                    "entry_title": row["entry_title"],
                },
                "case_shell_policy": {
                    "target_work": "",
                    "target_scope_status": "unresolved",
                    "machine_status": "draft",
                    "human_status": "pending",
                    "lifecycle": "machine_draft",
                    "semantic_conclusion": "not_generated",
                    "human_review_performed": False,
                },
                "provenance": {
                    "candidate_origin": row["origin"],
                    "candidate_provenance": json.loads(row["provenance_json"] or "{}"),
                },
                "planned_at": now(),
            }
        )

    report = {
        "report_version": "candidate_materialization_plan.v1",
        "generated_at": now(),
        "database": relative_path(str(database_path)),
        "read_only": True,
        "batch_size": batch_size,
        "policy": {
            "candidate_to_case_identity": "planned_case_id is candidate-shell:<candidate_id>",
            "candidate_status_is_not_human_approval": True,
            "target_and_semantics_remain_unresolved": True,
            "database_mutated": False,
        },
        "counts": {
            "candidate_items": len(rows),
            "already_materialized": state_counts.get("already_materialized", 0),
            "ready_candidate_shell": state_counts.get("ready_candidate_shell", 0),
            "blocked": sum(value for key, value in state_counts.items() if key.startswith("blocked")),
            "batches_for_next_materializer": len(batch_counts),
        },
        "state_counts": dict(state_counts),
        "risk_counts": dict(risk_counts),
        "work_counts": dict(work_counts),
        "batch_counts": dict(batch_counts),
        "blocked_examples": blocked_examples,
    }
    return plans, report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", type=Path, default=DEFAULT_DATABASE)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--batch-size", type=int, default=100)
    args = parser.parse_args()
    plans, report = plan_candidates(args.database, batch_size=args.batch_size)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8") as handle:
        for plan in plans:
            handle.write(json.dumps(plan, ensure_ascii=False, separators=(",", ":")) + "\n")
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report["counts"], ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
