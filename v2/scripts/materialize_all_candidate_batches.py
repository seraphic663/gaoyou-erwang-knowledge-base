#!/usr/bin/env python3
"""Materialize every ready original-text candidate batch.

The one-batch command is the auditable write seam.  This wrapper only discovers
ready batch IDs from the immutable plan, calls that seam in deterministic
order, and writes one report per batch plus an aggregate report.  It does not
call AI, infer target works, promote human status, or create gold records.
"""

from __future__ import annotations

import argparse
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
DEFAULT_OUTPUT_DIR = V2_ROOT / "data/real_runs"
DEFAULT_REPORT = V2_ROOT / "data/real_runs/candidate_shell_all_batches_report.json"

sys.path.insert(0, str(V2_ROOT / "scripts"))
from materialize_candidate_batch import materialize_batch  # noqa: E402


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def relative_path(value: str | Path) -> str:
    path = Path(value)
    try:
        return path.resolve().relative_to(PROJECT_ROOT.resolve()).as_posix()
    except ValueError:
        return str(path)


def load_ready_batches(plan_path: Path) -> tuple[list[str], int, int]:
    batch_ids: set[str] = set()
    ready_count = 0
    blocked_count = 0
    for line in plan_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        plan = json.loads(line)
        state = plan.get("plan_state")
        if state == "ready_candidate_shell":
            ready_count += 1
            batch_id = plan.get("batch_id")
            if not batch_id:
                raise ValueError(f"ready_plan_missing_batch_id:{plan.get('candidate_id')}")
            batch_ids.add(str(batch_id))
        elif state and str(state).startswith("blocked"):
            blocked_count += 1

    def batch_sort_key(value: str) -> tuple[int, str]:
        suffix = value.rsplit("-", 1)[-1]
        return (int(suffix) if suffix.isdigit() else 10**9, value)

    return sorted(batch_ids, key=batch_sort_key), ready_count, blocked_count


def _batch_paths(output_dir: Path, batch_id: str) -> tuple[Path, Path]:
    suffix = batch_id.rsplit("-", 1)[-1]
    stem = f"candidate_shell_batch_{suffix}"
    return (
        output_dir / f"{stem}.annotation_case.v1.jsonl",
        output_dir / f"{stem}_report.json",
    )


def _database_counts(database_path: Path) -> dict[str, int]:
    connection = sqlite3.connect(database_path)
    try:
        return {
            "candidate_items": int(connection.execute("SELECT COUNT(*) FROM candidate_items").fetchone()[0]),
            "candidate_output_links": int(
                connection.execute(
                    "SELECT COUNT(*) FROM candidate_items WHERE output_case_id IS NOT NULL"
                ).fetchone()[0]
            ),
            "candidate_shell_cases": int(
                connection.execute(
                    "SELECT COUNT(*) FROM annotation_cases WHERE origin='original_markdown_candidate_shell'"
                ).fetchone()[0]
            ),
            "annotation_cases": int(
                connection.execute("SELECT COUNT(*) FROM annotation_cases").fetchone()[0]
            ),
            "machine_draft_cases": int(
                connection.execute(
                    "SELECT COUNT(*) FROM annotation_cases WHERE machine_status='draft'"
                ).fetchone()[0]
            ),
            "human_pending_cases": int(
                connection.execute(
                    "SELECT COUNT(*) FROM annotation_cases WHERE human_status='pending'"
                ).fetchone()[0]
            ),
            "gold_cases": int(
                connection.execute(
                    "SELECT COUNT(*) FROM annotation_cases WHERE lifecycle='gold'"
                ).fetchone()[0]
            ),
        }
    finally:
        connection.close()


def materialize_all_batches(
    *,
    database_path: Path = DEFAULT_DATABASE,
    plan_path: Path = DEFAULT_PLAN,
    output_dir: Path = DEFAULT_OUTPUT_DIR,
    report_path: Path | None = None,
) -> dict[str, Any]:
    # Test and caller-specific output directories must not overwrite the real
    # production aggregate report when report_path is omitted.
    report_path = report_path or (output_dir / DEFAULT_REPORT.name)
    batch_ids, planned_ready, blocked_count = load_ready_batches(plan_path)
    output_dir.mkdir(parents=True, exist_ok=True)
    reports: list[dict[str, Any]] = []
    totals: Counter[str] = Counter()
    for batch_id in batch_ids:
        output_path, batch_report_path = _batch_paths(output_dir, batch_id)
        batch_report = materialize_batch(
            database_path=database_path,
            plan_path=plan_path,
            batch_id=batch_id,
            output_path=output_path,
            report_path=batch_report_path,
        )
        reports.append(
            {
                "batch_id": batch_id,
                "report_file": relative_path(batch_report_path),
                "output_file": relative_path(output_path),
                "counts": batch_report["counts"],
            }
        )
        for key, value in batch_report["counts"].items():
            if isinstance(value, int):
                totals[key] += value

    database_counts = _database_counts(database_path)
    report = {
        "report_version": "candidate_shell_all_batches_materialization.v1",
        "generated_at": now(),
        "database": relative_path(database_path),
        "plan": relative_path(plan_path),
        "policy": {
            "batch_size_max": 100,
            "ai_called": False,
            "target_work_resolved": False,
            "human_review_performed": False,
            "gold_promotion_performed": False,
            "replay_is_idempotent": True,
            "one_batch_is_the_write_seam": True,
        },
        "counts": {
            "planned_ready_candidate_shell": planned_ready,
            "batch_count": len(batch_ids),
            "blocked_in_plan": blocked_count,
            "materialized_now": totals.get("materialized_now", 0),
            "skipped_existing": totals.get("skipped_existing", 0),
            "annotation_cases_in_batches": totals.get("annotation_cases_in_batch", 0),
            "candidate_output_links_in_batches": totals.get("candidate_output_links_in_batch", 0),
            "candidate_items": database_counts["candidate_items"],
            "candidate_output_links": database_counts["candidate_output_links"],
            "candidate_shell_cases": database_counts["candidate_shell_cases"],
            "annotation_cases": database_counts["annotation_cases"],
            "machine_draft_cases": database_counts["machine_draft_cases"],
            "human_pending_cases": database_counts["human_pending_cases"],
            "gold_cases": database_counts["gold_cases"],
        },
        "validation": {
            "all_ready_candidates_linked": database_counts["candidate_output_links"] == database_counts["candidate_items"],
            "machine_and_human_states_separate": (
                database_counts["machine_draft_cases"] == database_counts["annotation_cases"]
                and database_counts["human_pending_cases"] == database_counts["annotation_cases"]
                and database_counts["gold_cases"] == 0
            ),
            "no_blocked_plan_rows": blocked_count == 0,
        },
        "batches": reports,
    }
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", type=Path, default=DEFAULT_DATABASE)
    parser.add_argument("--plan", type=Path, default=DEFAULT_PLAN)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    report = materialize_all_batches(
        database_path=args.database,
        plan_path=args.plan,
        output_dir=args.output_dir,
        report_path=args.report,
    )
    print(json.dumps(report["counts"], ensure_ascii=False, sort_keys=True))
    return 0 if all(report["validation"].values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
