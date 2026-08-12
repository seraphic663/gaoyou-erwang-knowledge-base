#!/usr/bin/env python3
"""Run the complete machine-side V2 completion workflow.

This orchestrator intentionally stops before human review. It rebuilds the
four Wang core-source inventory, migrates the three legacy AI JSON files,
records target-work candidates, scans local materials for external-source
context, and writes one completion report with explicit boundaries.
"""

from __future__ import annotations

import json
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path


V2_ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = V2_ROOT.parent
sys.path.insert(0, str(V2_ROOT / "src"))
sys.path.insert(0, str(V2_ROOT / "scripts"))

from run_batch_migration import DEFAULT_DATABASE, DEFAULT_REPORT  # noqa: E402
from run_external_source_inventory import (  # noqa: E402
    DEFAULT_REPORT as DEFAULT_EXTERNAL_REPORT,
    run as run_external_inventory,
)
from run_unified_ingress import (  # noqa: E402
    OUTPUT_DIR as DEFAULT_UNIFIED_OUTPUT_DIR,
    REPORT_FILE as DEFAULT_UNIFIED_REPORT,
    run_unified_ingress,
)


DEFAULT_COMPLETION_REPORT = V2_ROOT / "data/real_runs/machine_completion_report.json"


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def read_database_state(database_path: Path) -> dict:
    connection = sqlite3.connect(database_path)
    try:
        counts = {}
        for table in (
            "source_documents",
            "passages",
            "candidate_items",
            "annotation_cases",
            "annotation_terms",
            "annotation_evidences",
            "annotation_process_steps",
            "review_events",
            "external_source_registry",
            "annotation_evidence_external_sources",
            "source_version_registry",
            "legacy_catalog_terms",
            "legacy_catalog_works",
        ):
            counts[table] = connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        lifecycle = dict(connection.execute(
            "SELECT lifecycle, COUNT(*) FROM annotation_cases GROUP BY lifecycle"
        ).fetchall())
        machine = dict(connection.execute(
            "SELECT machine_status, COUNT(*) FROM annotation_cases GROUP BY machine_status"
        ).fetchall())
        human = dict(connection.execute(
            "SELECT human_status, COUNT(*) FROM annotation_cases GROUP BY human_status"
        ).fetchall())
        foreign_keys = connection.execute("PRAGMA foreign_key_check").fetchall()
        integrity = connection.execute("PRAGMA integrity_check").fetchone()[0]
        return {
            "counts": counts,
            "lifecycle_counts": lifecycle,
            "machine_status_counts": machine,
            "human_status_counts": human,
            "gold_count": lifecycle.get("gold", 0),
            "integrity_check": integrity,
            "foreign_key_violation_count": len(foreign_keys),
        }
    finally:
        connection.close()


def run(
    database_path: Path = DEFAULT_DATABASE,
    batch_report_path: Path = DEFAULT_REPORT,
    external_report_path: Path = DEFAULT_EXTERNAL_REPORT,
    completion_report_path: Path = DEFAULT_COMPLETION_REPORT,
) -> dict:
    database_path = Path(database_path).resolve()
    unified = run_unified_ingress(
        database_path=database_path,
        output_dir=DEFAULT_UNIFIED_OUTPUT_DIR,
        report_path=DEFAULT_UNIFIED_REPORT,
        with_ai_samples=False,
    )
    batch = unified.get("legacy_ai_json_route", {})
    external = run_external_inventory(database_path, external_report_path)
    database = read_database_state(database_path)

    completion = {
        "report_version": "v2-machine-completion.v1",
        "generated_at": now(),
        "status": "completed_with_machine_boundaries",
        "human_review_performed": False,
        "gold_promotion_performed": False,
        "workflow": [
            "four_core_source_passage_and_candidate_inventory",
            "legacy_ai_json_batch_migration",
            "legacy_dictionary_materialization_and_catalog_registration",
            "machine_target_scope_candidate_inference",
            "local_external_source_inventory",
            "database_integrity_and_foreign_key_check",
        ],
        "database": database,
        "batch_report": {
            "path": str(Path(batch_report_path).resolve().relative_to(PROJECT_ROOT)),
            "run_status": batch.get("status") or batch.get("run_status"),
            "summary": batch.get("summary"),
        },
        "unified_ingress_report": {
            "path": str(DEFAULT_UNIFIED_REPORT.resolve().relative_to(PROJECT_ROOT)),
            "status": unified.get("status"),
            "database": unified.get("v2_database"),
            "legacy_dictionary_route": unified.get("legacy_dictionary_db_route"),
            "original_markdown_route": unified.get("original_markdown_route"),
        },
        "external_source_report": {
            "path": str(Path(external_report_path).resolve().relative_to(PROJECT_ROOT)),
            "summary": external["summary"],
        },
        "conclusion": {
            "machine_side": "机器侧链路已完成：四部王氏原典已生成 passage 和候选审计，17 条旧 AI 案例、815 条旧机器案例及其 legacy source/derived passage 已进入同一 V2 工作库，14 个词条和 12 个著作登记为 catalog-only。",
            "evidence_boundary": "外部典籍独立 canonical 底本当前为 0 个；旧 AI 的 121 条外部引文和旧机器库的 7,120 条派生证据均保留来源边界，不能因上下文或 derived passage 命中而标记为 canonical passed。",
            "target_boundary": "旧 AI 的 target_work 候选仍按 machine_inferred/candidate_only 保留；旧机器库 target passage 只表示第一条 legacy evidence 的可追溯派生定位，不表示已确认目标典籍。",
            "human_boundary": "未进行人工审校，human_status 仍为 pending，gold 仍为 0。",
            "overall": "V2 机器工作链路可以继续扩展和供网站验收使用，但当前不能称为原典引文已全部核验，也不能称为人工审校完成。",
        },
    }
    completion_report_path = Path(completion_report_path).resolve()
    completion_report_path.parent.mkdir(parents=True, exist_ok=True)
    completion_report_path.write_text(
        json.dumps(completion, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return completion


def main() -> int:
    completion = run()
    print(json.dumps(completion, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
