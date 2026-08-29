#!/usr/bin/env python3
"""Read-only API bridge for the V2/VR acceptance page.

The website intentionally does not import the V2 writer.  Every command opens
annotation_v2.db with SQLite's read-only URI and query_only enabled, then
prints one JSON response for the Node server.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
from collections import Counter
from pathlib import Path
from typing import Any


WORKSPACE_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DB = WORKSPACE_ROOT / "v2" / "data" / "real_runs" / "annotation_v2.db"
REPORT_FILE = WORKSPACE_ROOT / "v2" / "data" / "real_runs" / "batch_migration_report.json"
UNIFIED_REPORT_FILE = WORKSPACE_ROOT / "v2" / "data" / "real_runs" / "unified_ingress_report.json"
EXTERNAL_INVENTORY_FILE = WORKSPACE_ROOT / "v2" / "data" / "real_runs" / "external_source_inventory.json"
WORK_QUEUE_REPORT_FILE = WORKSPACE_ROOT / "v2" / "data" / "real_runs" / "work_queues_report.json"
REVIEW_TASK_MANIFEST_FILE = WORKSPACE_ROOT / "v2" / "data" / "real_runs" / "review_tasks" / "review_task_manifest.review.v1.json"
VALIDATION_REPORT_FILE = WORKSPACE_ROOT / "v2" / "data" / "real_runs" / "v2_validation_report.json"
CANDIDATE_BATCH_REPORT_DIR = WORKSPACE_ROOT / "v2" / "data" / "real_runs"


def parse_json(value: Any, fallback: Any) -> Any:
    if value is None or value == "":
        return fallback
    if isinstance(value, (dict, list)):
        return value
    try:
        return json.loads(value)
    except (TypeError, ValueError):
        return fallback


def row_dict(row: sqlite3.Row | None) -> dict[str, Any] | None:
    return dict(row) if row is not None else None


def rows_dict(rows: list[sqlite3.Row]) -> list[dict[str, Any]]:
    return [dict(row) for row in rows]


def connect(db_path: Path) -> sqlite3.Connection:
    if not db_path.exists():
        raise FileNotFoundError(f"V2 database not found: {db_path}")
    uri = f"file:{db_path.resolve()}?mode=ro"
    connection = sqlite3.connect(uri, uri=True)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA query_only = ON")
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def load_report() -> dict[str, Any]:
    report_path = UNIFIED_REPORT_FILE if UNIFIED_REPORT_FILE.exists() else REPORT_FILE
    if not report_path.exists():
        return {}
    try:
        return json.loads(report_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def load_batch_report() -> dict[str, Any]:
    if not REPORT_FILE.exists():
        return {}
    try:
        return json.loads(REPORT_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def load_external_inventory() -> dict[str, Any]:
    if not EXTERNAL_INVENTORY_FILE.exists():
        return {}
    try:
        return json.loads(EXTERNAL_INVENTORY_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def load_work_queue_report() -> dict[str, Any]:
    if not WORK_QUEUE_REPORT_FILE.exists():
        return {}
    try:
        return json.loads(WORK_QUEUE_REPORT_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def load_review_task_manifest() -> dict[str, Any]:
    if not REVIEW_TASK_MANIFEST_FILE.exists():
        return {}
    try:
        return json.loads(REVIEW_TASK_MANIFEST_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def load_validation_report() -> dict[str, Any]:
    if not VALIDATION_REPORT_FILE.exists():
        return {}
    try:
        return json.loads(VALIDATION_REPORT_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def validation_report_is_current(db_path: Path, report: dict[str, Any]) -> bool:
    """Return whether the persisted read-only acceptance report covers this DB."""

    if not report or report.get("status") not in {"passed", "failed"}:
        return False
    database_value = str(report.get("database") or "")
    expected = str(db_path.resolve().relative_to(WORKSPACE_ROOT.resolve())).replace("\\", "/")
    if database_value != expected:
        return False
    try:
        generated_at = report.get("generated_at")
        if not generated_at:
            return False
        # The report timestamp is ISO-8601; comparing file mtimes avoids
        # re-running a 399 MB integrity scan on every page load.
        from datetime import datetime

        report_time = datetime.fromisoformat(str(generated_at).replace("Z", "+00:00")).timestamp()
        return report_time >= db_path.stat().st_mtime
    except (OSError, TypeError, ValueError):
        return False


def load_candidate_batch_reports() -> list[dict[str, Any]]:
    reports: list[dict[str, Any]] = []
    for path in sorted(CANDIDATE_BATCH_REPORT_DIR.glob("candidate_shell_batch_*_report.json")):
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        value["report_file"] = str(path.relative_to(WORKSPACE_ROOT)).replace("\\", "/")
        reports.append(value)
    return reports


def grouped_count(connection: sqlite3.Connection, column: str) -> dict[str, int]:
    allowed = {"lifecycle", "machine_status", "human_status", "review_status"}
    if column not in allowed:
        raise ValueError(f"Unsupported grouped column: {column}")
    rows = connection.execute(
        f"SELECT {column} AS value, COUNT(*) AS count FROM annotation_cases GROUP BY {column}"
    ).fetchall()
    return {str(row["value"]): int(row["count"]) for row in rows}


def evidence_counters(connection: sqlite3.Connection) -> dict[str, dict[str, int]]:
    resolution = Counter()
    cited_match = Counter()
    quote_check = Counter()
    context_check = Counter()
    rows = connection.execute(
        "SELECT evidence_json, quote_check FROM annotation_evidences"
    ).fetchall()
    for row in rows:
        evidence = parse_json(row["evidence_json"], {})
        source_resolution = evidence.get("source_resolution") or "unknown"
        cited_work_match = evidence.get("cited_work_match_status") or "unknown"
        resolution[str(source_resolution)] += 1
        cited_match[str(cited_work_match)] += 1
        quote_check[str(row["quote_check"] or evidence.get("quote_check") or "unknown")] += 1
        context_check[str(evidence.get("annotation_context_check") or "unknown")] += 1
    return {
        "source_resolution": dict(resolution),
        "cited_work_match": dict(cited_match),
        "quote_check": dict(quote_check),
        "annotation_context_check": dict(context_check),
    }


def source_rows(connection: sqlite3.Connection) -> list[dict[str, Any]]:
    rows = connection.execute(
        "SELECT * FROM source_documents ORDER BY work_key"
    ).fetchall()
    passage_counts = {
        row["source_document_id"]: int(row["count"])
        for row in connection.execute(
            "SELECT source_document_id, COUNT(*) AS count FROM passages GROUP BY source_document_id"
        ).fetchall()
    }
    case_counts = {
        row["source_document_id"]: int(row["count"])
        for row in connection.execute(
            """
            SELECT p.source_document_id, COUNT(*) AS count
            FROM annotation_cases ac
            JOIN passages p ON p.passage_id = ac.source_passage_id
            GROUP BY p.source_document_id
            """
        ).fetchall()
    }
    result = []
    for row in rows:
        item = dict(row)
        source_document_id = item["source_document_id"]
        item["passage_count"] = passage_counts.get(source_document_id, 0)
        item["case_count"] = case_counts.get(source_document_id, 0)
        item["metadata"] = parse_json(item.pop("metadata_json", "{}"), {})
        result.append(item)
    return result


def source_conflicts(connection: sqlite3.Connection) -> list[dict[str, Any]]:
    return []


def orphan_counts(connection: sqlite3.Connection) -> dict[str, int]:
    queries = {
        "orphan_passages": """
            SELECT COUNT(*) FROM passages p
            LEFT JOIN source_documents sd ON sd.source_document_id = p.source_document_id
            WHERE sd.source_document_id IS NULL
        """,
        "orphan_case_source_passages": """
            SELECT COUNT(*) FROM annotation_cases ac
            LEFT JOIN passages p ON p.passage_id = ac.source_passage_id
            WHERE ac.source_passage_id IS NOT NULL AND p.passage_id IS NULL
        """,
        "orphan_evidence_passages": """
            SELECT COUNT(*) FROM annotation_evidences ae
            LEFT JOIN passages p ON p.passage_id = ae.passage_id
            WHERE ae.passage_id IS NOT NULL AND p.passage_id IS NULL
        """,
        "orphan_external_links": """
            SELECT COUNT(*) FROM annotation_evidence_external_sources link
            LEFT JOIN external_source_registry es ON es.external_source_id = link.external_source_id
            WHERE es.external_source_id IS NULL
        """,
        "orphan_candidate_source_documents": """
            SELECT COUNT(*) FROM candidate_items ci
            LEFT JOIN source_documents sd ON sd.source_document_id = ci.source_document_id
            WHERE sd.source_document_id IS NULL
        """,
        "orphan_candidate_passages": """
            SELECT COUNT(*) FROM candidate_items ci
            LEFT JOIN passages p ON p.passage_id = ci.passage_id
            WHERE p.passage_id IS NULL
        """,
        "orphan_candidate_output_cases": """
            SELECT COUNT(*) FROM candidate_items ci
            LEFT JOIN annotation_cases ac ON ac.case_id = ci.output_case_id
            WHERE ci.output_case_id IS NOT NULL AND ac.case_id IS NULL
        """,
        "orphan_candidate_target_locations": """
            SELECT COUNT(*) FROM candidate_target_locations ctl
            LEFT JOIN candidate_items ci ON ci.candidate_id = ctl.candidate_id
            LEFT JOIN annotation_cases ac ON ac.case_id = ctl.case_id
            LEFT JOIN passages sp ON sp.passage_id = ctl.source_passage_id
            LEFT JOIN passages tp ON tp.passage_id = ctl.target_passage_candidate_id
            WHERE ci.candidate_id IS NULL
               OR ac.case_id IS NULL
               OR sp.passage_id IS NULL
               OR (ctl.target_passage_candidate_id IS NOT NULL AND tp.passage_id IS NULL)
        """,
        "orphan_target_work_queue_cases": """
            SELECT COUNT(*) FROM target_work_resolution_queue q
            LEFT JOIN annotation_cases ac ON ac.case_id = q.case_id
            WHERE ac.case_id IS NULL
        """,
        "orphan_external_source_queue_sources": """
            SELECT COUNT(*) FROM external_source_resolution_queue q
            LEFT JOIN external_source_registry es ON es.external_source_id = q.external_source_id
            WHERE es.external_source_id IS NULL
        """,
        "orphan_external_passage_queue_evidence": """
            SELECT COUNT(*) FROM external_passage_resolution_queue q
            LEFT JOIN annotation_evidences ae
              ON ae.case_id = q.case_id AND ae.evidence_index = q.evidence_index
            WHERE ae.case_id IS NULL
        """,
        "orphan_resolution_events": """
            SELECT COUNT(*) FROM resolution_events e
            LEFT JOIN external_source_resolution_queue esq
              ON esq.queue_item_id = e.queue_item_id
             AND e.resolution_kind = 'external_source_resolution'
            LEFT JOIN external_passage_resolution_queue epq
              ON epq.queue_item_id = e.queue_item_id
             AND e.resolution_kind = 'external_passage_resolution'
            WHERE (e.resolution_kind = 'external_source_resolution' AND esq.queue_item_id IS NULL)
               OR (e.resolution_kind = 'external_passage_resolution' AND epq.queue_item_id IS NULL)
        """,
    }
    return {
        name: int(connection.execute(query).fetchone()[0])
        for name, query in queries.items()
    }


def acceptance_check(
    key: str,
    label: str,
    status: str,
    value: str,
    detail: str,
    *,
    severity: str,
    why_it_matters: str,
    next_action: str,
    evidence_basis: str,
) -> dict[str, str]:
    return {
        "key": key,
        "label": label,
        "status": status,
        "value": value,
        "detail": detail,
        "severity": severity,
        "why_it_matters": why_it_matters,
        "next_action": next_action,
        "evidence_basis": evidence_basis,
    }


def build_summary(connection: sqlite3.Connection, db_path: Path) -> dict[str, Any]:
    report = load_report()
    batch_report = load_batch_report()
    external_inventory = load_external_inventory()
    work_queue_report = load_work_queue_report()
    review_task_manifest = load_review_task_manifest()
    validation_report = load_validation_report()
    candidate_batch_reports = load_candidate_batch_reports()
    validation_current = validation_report_is_current(db_path, validation_report)
    report_summary = batch_report.get("summary") or {}
    counts = {}
    for table in (
        "source_documents",
        "passages",
        "candidate_items",
        "candidate_target_locations",
        "annotation_cases",
        "annotation_terms",
        "annotation_evidences",
        "annotation_process_steps",
        "review_events",
        "resolution_events",
        "external_source_registry",
        "annotation_evidence_external_sources",
        "work_registry",
        "work_aliases",
        "target_work_resolution_queue",
        "external_source_resolution_queue",
        "external_passage_resolution_queue",
        "legacy_catalog_terms",
        "legacy_catalog_works",
        "legacy_dictionary_terms",
        "legacy_dictionary_works",
        "legacy_term_case_links",
        "legacy_work_evidence_links",
    ):
        counts[table] = int(connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])

    candidate_status_counts = {
        str(row["value"]): int(row["count"])
        for row in connection.execute(
            "SELECT candidate_status AS value, COUNT(*) AS count FROM candidate_items GROUP BY candidate_status"
        ).fetchall()
    }
    candidate_origin_counts = {
        str(row["value"]): int(row["count"])
        for row in connection.execute(
            "SELECT origin AS value, COUNT(*) AS count FROM candidate_items GROUP BY origin"
        ).fetchall()
    }
    candidate_work_counts = {
        str(row["value"]): int(row["count"])
        for row in connection.execute(
            "SELECT source_work AS value, COUNT(*) AS count FROM candidate_items GROUP BY source_work ORDER BY source_work"
        ).fetchall()
    }
    candidate_output_case_count = int(connection.execute(
        "SELECT COUNT(*) FROM candidate_items WHERE output_case_id IS NOT NULL"
    ).fetchone()[0])
    candidate_shell_case_count = int(connection.execute(
        "SELECT COUNT(*) FROM annotation_cases WHERE origin='original_markdown_candidate_shell'"
    ).fetchone()[0])
    candidate_link_count = int(connection.execute(
        "SELECT COUNT(*) FROM candidate_items WHERE output_case_id IS NOT NULL"
    ).fetchone()[0])
    candidate_link_orphans = int(connection.execute(
        """
        SELECT COUNT(*) FROM candidate_items ci
        LEFT JOIN annotation_cases ac ON ac.case_id=ci.output_case_id
        WHERE ci.output_case_id IS NOT NULL AND ac.case_id IS NULL
        """
    ).fetchone()[0])
    candidate_target_location_count = counts["candidate_target_locations"]
    candidate_target_canonical_count = int(connection.execute(
        "SELECT COUNT(*) FROM candidate_target_locations WHERE work_identity_status = 'canonical'"
    ).fetchone()[0])
    candidate_target_passage_candidate_count = int(connection.execute(
        "SELECT COUNT(*) FROM candidate_target_locations WHERE target_passage_match_status = 'candidate_match'"
    ).fetchone()[0])
    candidate_target_same_source_count = int(connection.execute(
        "SELECT COUNT(*) FROM candidate_target_locations WHERE target_passage_match_status = 'same_source_only'"
    ).fetchone()[0])
    candidate_target_no_match_count = int(connection.execute(
        "SELECT COUNT(*) FROM candidate_target_locations WHERE target_passage_match_status = 'no_match'"
    ).fetchone()[0])
    candidate_target_not_searched_count = int(connection.execute(
        "SELECT COUNT(*) FROM candidate_target_locations WHERE target_passage_match_status = 'not_searched'"
    ).fetchone()[0])
    candidate_target_automatic_promotion_count = 0
    candidate_target_canonical_singleton_count = int(connection.execute(
        """
        SELECT COUNT(*) FROM candidate_target_locations
        WHERE work_identity_status = 'canonical'
          AND target_passage_match_status = 'candidate_match'
          AND target_passage_candidate_count = 1
        """
    ).fetchone()[0])
    candidate_target_canonical_ambiguous_count = int(connection.execute(
        """
        SELECT COUNT(*) FROM candidate_target_locations
        WHERE work_identity_status = 'canonical'
          AND target_passage_match_status = 'candidate_match'
          AND target_passage_candidate_count > 1
        """
    ).fetchone()[0])
    candidate_target_without_selected_passage_count = int(connection.execute(
        """
        SELECT COUNT(*) FROM candidate_target_locations
        WHERE work_identity_status = 'canonical'
          AND target_passage_match_status = 'candidate_match'
          AND target_passage_candidate_id IS NULL
        """
    ).fetchone()[0])
    candidate_target_unresolved_count = int(connection.execute(
        "SELECT COUNT(*) FROM candidate_target_locations WHERE work_identity_status = 'candidate'"
    ).fetchone()[0])
    candidate_target_boundary_breaches = int(connection.execute(
        """
        SELECT COUNT(*) FROM candidate_target_locations
        WHERE machine_status <> 'candidate_only' OR human_status <> 'pending'
        """
    ).fetchone()[0])
    queue_counts = {
        table: int(connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])
        for table in (
            "target_work_resolution_queue",
            "external_source_resolution_queue",
            "external_passage_resolution_queue",
        )
    }

    lifecycle_counts = grouped_count(connection, "lifecycle")
    machine_counts = grouped_count(connection, "machine_status")
    human_counts = grouped_count(connection, "human_status")
    review_counts = grouped_count(connection, "review_status")
    evidence_counts = evidence_counters(connection)
    sources = source_rows(connection)
    conflicts = source_conflicts(connection)
    if validation_current:
        # The VR page is read-only.  Reuse the last persisted validation result
        # instead of repeating a full integrity/foreign-key/orphan scan on a
        # 399 MB database every time the page is opened.
        orphans = validation_report.get("orphan_counts") or {}
        integrity = str(validation_report.get("integrity_check") or "unknown")
        foreign_key_rows = validation_report.get("foreign_key_violations") or []
    else:
        orphans = orphan_counts(connection)
        integrity = str(connection.execute("PRAGMA integrity_check").fetchone()[0])
        foreign_key_rows = connection.execute("PRAGMA foreign_key_check").fetchall()
    legacy_ai_cases = int(
        ((report.get("legacy_ai_json_route") or {}).get("summary") or {}).get("case_count") or 0
    )
    legacy_dictionary_cases = int(
        (report.get("legacy_dictionary_db_route") or {}).get("case_count") or 0
    )
    original_sample_cases = len(
        ((report.get("original_markdown_route") or {}).get("sample_runs") or [])
    )
    expected_cases = legacy_ai_cases + legacy_dictionary_cases + original_sample_cases
    expected_cases += sum(
        int((item.get("counts") or {}).get("annotation_cases_in_batch") or 0)
        for item in candidate_batch_reports
    )
    if expected_cases == 0:
        expected_cases = int((batch_report.get("inputs") or {}).get("expected_case_count") or counts["annotation_cases"])
    expected_candidates = int(
        (report.get("original_markdown_route") or {}).get("candidate_count") or counts["candidate_items"]
    )
    unresolved_targets = int(connection.execute(
        """
        SELECT COUNT(*) FROM annotation_cases
        WHERE target_work = '' OR json_extract(target_scope_json, '$.status') = 'unresolved'
        """
    ).fetchone()[0])
    no_citation_cases = int(connection.execute(
        "SELECT COUNT(*) FROM annotation_cases WHERE evidence_state = 'source_no_citation'"
    ).fetchone()[0])
    gold_count = lifecycle_counts.get("gold", 0)
    external_pending = evidence_counts["source_resolution"].get("external_source_pending", 0)
    canonical_count = evidence_counts["source_resolution"].get("canonical_source_passage", 0)
    secondary_count = evidence_counts["source_resolution"].get("secondary_citation_match", 0)
    external_summary = external_inventory.get("summary") or {}
    pending_human = human_counts.get("pending", 0)
    orphan_total = sum(orphans.values())
    fk_status = "pass" if not foreign_key_rows else "fail"
    integrity_status = "pass" if integrity == "ok" else "fail"
    expected_status = "pass" if counts["annotation_cases"] == expected_cases else "fail"
    candidate_status = "pass" if counts["candidate_items"] == expected_candidates else "fail"
    candidate_materialization_status = "pass" if (
        candidate_link_count == counts["candidate_items"] and candidate_link_orphans == 0
    ) else "warn"
    candidate_target_location_status = "pass" if (
        orphans.get("orphan_candidate_target_locations", 0) == 0
        and candidate_target_boundary_breaches == 0
    ) else "fail"
    separation_status = "pass" if gold_count == 0 and pending_human == counts["annotation_cases"] else "warn"
    source_status = "pass" if not conflicts else "fail"
    orphan_status = "pass" if orphan_total == 0 else "fail"
    expected_queue_counts = work_queue_report.get("counts") or {}
    queue_status = "pass" if (
        all(orphans.get(key, 0) == 0 for key in (
            "orphan_target_work_queue_cases",
            "orphan_external_source_queue_sources",
            "orphan_external_passage_queue_evidence",
        ))
        and queue_counts.get("target_work_resolution_queue") == expected_queue_counts.get("target_work_queue")
        and queue_counts.get("external_source_resolution_queue") == expected_queue_counts.get("external_source_queue")
        and queue_counts.get("external_passage_resolution_queue") == expected_queue_counts.get("external_passage_queue")
    ) else "fail"
    review_task_validation = validation_report.get("review_task_artifact_validation") or {}
    review_task_counts = review_task_manifest.get("counts") or {}
    review_task_coverage = review_task_manifest.get("coverage") or {}
    review_task_artifacts = {
        "manifest_path": "v2/data/real_runs/review_tasks/review_task_manifest.review.v1.json",
        "generated_at": review_task_manifest.get("generated_at"),
        "batch_size": review_task_manifest.get("batch_size"),
        "review_sequence": review_task_manifest.get("review_sequence") or [],
        "counts": review_task_counts,
        "coverage": review_task_coverage,
        "policy": review_task_manifest.get("policy") or {},
        "valid": bool(review_task_validation.get("valid")),
        "validation_errors": review_task_validation.get("errors") or [],
    }
    review_task_status = "pass" if review_task_artifacts["valid"] else "warn"
    review_task_value = (
        "；".join(
            f"{key} {int(review_task_counts.get(key, 0))}/"
            f"{int(((review_task_coverage.get('stream_validation') or {}).get(key) or {}).get('batch_count', 0))}批"
            for key in (
                "case_review",
                "target_work_resolution",
                "external_source_resolution",
                "external_passage_resolution",
            )
        )
        if review_task_counts
        else "未生成"
    )

    validation_boundary_status = "pass" if validation_current else "warn"
    validation_boundary_value = "当前验收报告覆盖数据库" if validation_current else "验收报告过期，需重新运行"
    checks = [
        acceptance_check(
            "validation_report_freshness",
            "验收报告时效",
            validation_boundary_status,
            validation_boundary_value,
            "VR 页面复用持久化验收报告；报告过期时不在每次打开页面时重复扫描大型 SQLite 文件。",
            severity="high",
            why_it_matters="避免页面加载阻塞，同时防止把旧验收结果误显示为当前数据库状态。",
            next_action="数据库发生写入后重新运行 v2/scripts/run_v2_validation.py，再刷新页面。",
            evidence_basis="v2/data/real_runs/v2_validation_report.json 的 generated_at 与数据库 mtime",
        ),
        acceptance_check(
            "integrity",
            "数据库完整性",
            integrity_status,
            integrity,
            "SQLite integrity_check；只读验收接口不会写入数据库。",
            severity="critical",
            why_it_matters="数据库文件本身损坏时，所有案例、证据和状态统计都不能作为可靠输入。",
            next_action="保持每次数据重建后的只读 integrity_check；失败时停止交接。",
            evidence_basis="PRAGMA integrity_check",
        ),
        acceptance_check(
            "foreign_keys",
            "外键完整性",
            fk_status,
            "0 个违规" if not foreign_key_rows else f"{len(foreign_key_rows)} 个违规",
            "案例、段落、证据与外部来源的引用关系。",
            severity="high",
            why_it_matters="孤儿引用会让案例看似有证据，但无法回到实际 passage 或登记来源。",
            next_action="修复外键或阻止导入；不能用前端隐藏孤儿记录。",
            evidence_basis="PRAGMA foreign_key_check",
        ),
        acceptance_check(
            "canonical_source",
            "原典版本唯一",
            source_status,
            f"{len(sources)} 个来源版本" if not conflicts else f"{len(conflicts)} 个冲突",
            "同一 work_key + source_file 不得混入多个版本标识；当前读书杂志只保留 1460…版本。",
            severity="high",
            why_it_matters="来源版本不唯一会使 passage、行号和 quote 校验无法证明针对哪一版原文。",
            next_action="保留历史版本记录，但只允许一个 active canonical 版本；当前读书杂志固定为 1460a906825998bf…。",
            evidence_basis="source_documents 的 (work_key, source_file) 唯一约束",
        ),
        acceptance_check(
            "no_orphans",
            "引用无孤儿",
            orphan_status,
            f"{orphan_total} 个孤儿引用",
            "source_passage、evidence passage 和 external source link 都必须能回指。",
            severity="high",
            why_it_matters="验收页面无法修复引用关系；孤儿记录必须在入库层被发现。",
            next_action="在批量入库后重新跑孤儿查询，保持所有 orphan count 为 0。",
            evidence_basis="orphan_counts() 的 7 类引用查询",
        ),
        acceptance_check(
            "stored_cases",
            "案例入库数量",
            expected_status,
            f"{counts['annotation_cases']} / {expected_cases}",
            "与本轮批量迁移清单中的预期案例数对照。",
            severity="medium",
            why_it_matters="数量不一致意味着迁移清单、候选输出或数据库之间存在遗漏。",
            next_action="核对三条来源路线的输入清单、case_id 和输出报告。",
            evidence_basis="unified_ingress_report + annotation_cases",
        ),
        acceptance_check(
            "stored_candidates",
            "候选层入库数量",
            candidate_status,
            f"{counts['candidate_items']} / {expected_candidates}",
            "四部王氏原文先进入 candidate_item.v1；只有明确走 AI 的记录才生成 annotation_case.v1。",
            severity="medium",
            why_it_matters="候选层是原典入口，漏候选会使后续人工审校范围不完整。",
            next_action="批量推进尚未生成案例的 candidate_items，但保持 candidate 与 case 两层可区分。",
            evidence_basis="candidate_items + original_markdown_route",
        ),
        acceptance_check(
            "candidate_materialization",
            "候选到案例壳的覆盖",
            candidate_materialization_status,
            f"已关联 {candidate_link_count} / {counts['candidate_items']}",
            "每条原典 candidate_item 都应有可追踪的 annotation_case.v1 壳；壳仍是 machine draft，不代表语义结论已确认。",
            severity="medium",
            why_it_matters="候选层如果没有对应审校入口，原典抽取结果会成为不可操作的隐藏孤立项。",
            next_action="运行 materialize_all_candidate_batches.py；若有阻塞行，先修复来源段落或候选文本边界。",
            evidence_basis="candidate_items.output_case_id + annotation_cases(origin=original_markdown_candidate_shell)",
        ),
        acceptance_check(
            "candidate_target_locations",
            "目标位置机器候选",
            candidate_target_location_status,
            f"{candidate_target_location_count} 条；canonical 标签 {candidate_target_canonical_count}；其他 canonical passage 候选 {candidate_target_passage_candidate_count}",
            "书名标记和精确片段命中只进入 candidate_target_locations；不得自动写入 annotation_cases.target_work 或 target_passage_id。",
            severity="high",
            why_it_matters="目标定位是人工审校的核心判断；机器命中只能缩小范围，不能把候选伪装成已确认学术证据。",
            next_action="先按批次查看候选，再由人工确认 target_work、target passage 和证据边界。",
            evidence_basis="candidate_target_locations 外键、固定状态和 target 字段未升级查询",
        ),
        acceptance_check(
            "work_queues",
            "三类工作队列",
            queue_status,
            f"target {queue_counts.get('target_work_resolution_queue', 0)}；external source {queue_counts.get('external_source_resolution_queue', 0)}；external passage {queue_counts.get('external_passage_resolution_queue', 0)}",
            "target_work 消歧、外部版本/段落核验和人工审校必须有显式队列，不能依靠前端临时拼接或隐藏待办。",
            severity="high",
            why_it_matters="没有持久队列就无法知道哪些机器候选尚未处理、哪些外部引文已有公开候选、哪些案例等待人工审校。",
            next_action="按队列状态推进；队列构建失败或出现孤儿时停止后续物化和 gold 晋级。",
            evidence_basis="target_work_resolution_queue + external_*_resolution_queue + work_queues_report.json",
        ),
        acceptance_check(
            "review_task_artifacts",
            "分批审校任务包",
            review_task_status,
            review_task_value,
            "案例、target_work、外部来源和外部 passage 分成独立 JSONL 任务流；每批上限由 manifest 固定，任务包本身不写数据库、不产生 review_event。",
            severity="high",
            why_it_matters="人工审校需要可分批交接的稳定输入；没有 task_id、批次和当前队列反向覆盖校验，审校会遗漏或重复处理。",
            next_action="先按 task_type 和 batch_id 读取；审校提交只能调用受控 review event 写入边界，任何任务包重建后都要重新验证覆盖。",
            evidence_basis="review_task_manifest.review.v1.json + review_task_artifact_validation",
        ),
        acceptance_check(
            "machine_human_separation",
            "机器与人工状态分离",
            separation_status,
            f"machine draft {machine_counts.get('draft', 0)}；rejected {machine_counts.get('rejected', 0)}；human pending {pending_human}",
            "机器入库不等于人工通过；当前没有 gold。",
            severity="critical",
            why_it_matters="这是防止机器结果越过人工审校直接成为 gold 或主库内容的核心边界。",
            next_action="保持 machine_status、human_status、lifecycle 分离；人工审校后再记录 review_event。",
            evidence_basis="annotation_cases 状态分组 + v_gold_cases",
        ),
        acceptance_check(
            "canonical_evidence",
            "原典引文核验",
            "pass" if external_pending == 0 and canonical_count == counts["annotation_evidences"] else "warn",
            f"canonical {canonical_count}；secondary {secondary_count}；external pending {external_pending}",
            "secondary citation match 仍是王氏正文中的二次引文命中，不是被引原典核验通过。",
            severity="high",
            why_it_matters="只有 quote 真正在对应 canonical passage 中，才能标记 canonical quote passed。",
            next_action="为 external_source_pending 登记版本和 passage；未完成前保持 unchecked。",
            evidence_basis="annotation_evidences.source_resolution + quote_check",
        ),
        acceptance_check(
            "external_canonical_files",
            "外部 canonical 底本",
            "pass" if external_summary.get("canonical_file_registered_count", 0) else "warn",
            f"{external_summary.get('canonical_file_registered_count', 0)} 个已登记",
            "项目内现有材料命中只能作为 local context，不能替代外部典籍底本。",
            severity="high",
            why_it_matters="没有外部底本，80 条外部引文无法完成版本、位置和 quote 边界核验。",
            next_action="继续登记可核验的公开底本或用户提供的版本；不能把搜索命中直接变成 canonical。",
            evidence_basis="external_source_inventory.json",
        ),
        acceptance_check(
            "target_work",
            "target_work 完整度",
            "pass" if unresolved_targets == 0 else "warn",
            f"{unresolved_targets} 条待补",
            "target_work 缺失的案例保持 machine draft/human pending，进入消歧队列；不伪造目标典籍。",
            severity="high",
            why_it_matters="没有明确目标典籍，研究问题、证据范围和目标 passage 都无法稳定定位。",
            next_action="从原始 AI/full JSON 或人工审校确认；无法确认时保持 unresolved。",
            evidence_basis="annotation_cases.target_work + target_scope_json",
        ),
        acceptance_check(
            "no_citation",
            "无引文状态",
            "pass" if no_citation_cases == 0 else "warn",
            f"{no_citation_cases} 条 source_no_citation",
            "原典明确无引文时保留状态，不制造 evidence 占位记录。",
            severity="medium",
            why_it_matters="无引文和缺失引文是不同状态；制造占位 evidence 会污染证据统计。",
            next_action="人工确认是否确为无引文；确认前保持 source_no_citation。",
            evidence_basis="annotation_cases.evidence_state",
        ),
    ]
    overall = "fail" if any(item["status"] == "fail" for item in checks) else (
        "pass_with_warnings" if any(item["status"] == "warn" for item in checks) else "pass"
    )

    schema_version_row = connection.execute(
        "SELECT meta_value FROM schema_meta WHERE meta_key = 'schema_version'"
    ).fetchone()
    return {
        "ok": True,
        "overall_status": overall,
        "database": {
            "path": str(db_path),
            "display_path": "v2/data/real_runs/annotation_v2.db",
            "schema_version": schema_version_row[0] if schema_version_row else "unknown",
            "read_only": True,
        },
        "counts": counts,
        "candidate_status_counts": candidate_status_counts,
        "candidate_origin_counts": candidate_origin_counts,
        "candidate_work_counts": candidate_work_counts,
        "candidate_output_case_count": candidate_output_case_count,
        "candidate_link_orphan_count": candidate_link_orphans,
        "candidate_shell_case_count": candidate_shell_case_count,
        "candidate_target_location_count": candidate_target_location_count,
        "candidate_target_canonical_count": candidate_target_canonical_count,
        "candidate_target_passage_candidate_count": candidate_target_passage_candidate_count,
        "candidate_target_same_source_count": candidate_target_same_source_count,
        "candidate_target_no_match_count": candidate_target_no_match_count,
        "candidate_target_not_searched_count": candidate_target_not_searched_count,
        "candidate_target_canonical_singleton_count": candidate_target_canonical_singleton_count,
        "candidate_target_canonical_ambiguous_count": candidate_target_canonical_ambiguous_count,
        "candidate_target_without_selected_passage_count": candidate_target_without_selected_passage_count,
        "candidate_target_automatic_promotion_count": candidate_target_automatic_promotion_count,
        "candidate_target_unresolved_count": candidate_target_unresolved_count,
        "candidate_target_boundary_breach_count": candidate_target_boundary_breaches,
        "queue_counts": queue_counts,
        "review_task_artifacts": review_task_artifacts,
        "lifecycle_counts": lifecycle_counts,
        "machine_status_counts": machine_counts,
        "human_status_counts": human_counts,
        "review_status_counts": review_counts,
        "evidence_counts": evidence_counts,
        "sources": sources,
        "source_version_conflicts": conflicts,
        "orphans": orphans,
        "checks": checks,
        "validation_report": {
            "current": validation_current,
            "generated_at": validation_report.get("generated_at"),
            "status": validation_report.get("status"),
            "path": "v2/data/real_runs/v2_validation_report.json",
        },
        "report_context": {
            "report_version": report.get("report_version"),
            "run_status": report.get("status") or report.get("run_status"),
            "full_json_context_counts": report_summary.get("full_json_context_counts", {}),
            "source_file_count": report_summary.get("source_file_count"),
            "external_source_inventory": external_summary,
            "provenance_contract": report.get("provenance_contract", {}),
            "unified_ingress_report": "v2/data/real_runs/unified_ingress_report.json",
            "work_queues_report": "v2/data/real_runs/work_queues_report.json",
            "work_queue_counts": work_queue_report.get("counts", {}),
            "review_task_manifest": review_task_artifacts,
            "candidate_batch_reports": candidate_batch_reports,
        },
    }


def passage_payload(row: sqlite3.Row | None) -> dict[str, Any] | None:
    if row is None:
        return None
    item = dict(row)
    item["inline_notes"] = parse_json(item.pop("inline_notes_json", "[]"), [])
    return item


def external_candidate_passage_payload(
    connection: sqlite3.Connection,
    passage_id: str,
) -> dict[str, Any] | None:
    """Return a candidate passage with its non-canonical source metadata."""

    row = connection.execute(
        """
        SELECT p.*,
               sd.source_kind AS source_kind,
               sd.canonical_status AS source_canonical_status,
               sd.source_file AS source_document_file,
               sd.metadata_json AS source_metadata_json
        FROM passages p
        JOIN source_documents sd ON sd.source_document_id = p.source_document_id
        WHERE p.passage_id = ? AND sd.source_kind = 'external_public_candidate'
        """,
        (passage_id,),
    ).fetchone()
    payload = passage_payload(row)
    if payload is None:
        return None
    payload["source_metadata"] = parse_json(payload.pop("source_metadata_json", "{}"), {})
    return payload


def provenance_payload(case_data: dict[str, Any]) -> dict[str, Any]:
    migration = case_data.get("_migration") or {}
    provenance = migration.get("provenance") or {}
    return {
        "source_format": migration.get("source_format"),
        "source_layer": migration.get("source_layer"),
        "transformation_kind": migration.get("transformation_kind"),
        "source_file": provenance.get("source_file") or provenance.get("database_file"),
        "source_text_file": provenance.get("source_text_file"),
        "source_document_id": provenance.get("source_document_id"),
        "source_passage_id": provenance.get("source_passage_id"),
        "candidate_id": provenance.get("candidate_id"),
        "legacy_case_id": provenance.get("legacy_case_id"),
        "legacy_ai_json": provenance.get("legacy_ai_json"),
        "model": provenance.get("model"),
        "prompt_version": provenance.get("prompt_version"),
        "ai_generation_performed": provenance.get("ai_generation_performed"),
    }


def list_cases(
    connection: sqlite3.Connection,
    *,
    query: str = "",
    source_work: str = "",
    machine_status: str = "",
    page: int | None = None,
    page_size: int | None = None,
) -> dict[str, Any]:
    conditions = []
    parameters: list[Any] = []
    if query:
        needle = f"%{query}%"
        conditions.append(
            "("
            "ac.case_id LIKE ? OR ac.case_title LIKE ? OR ac.source_work LIKE ? OR "
            "ac.target_work LIKE ? OR ac.target_text LIKE ? OR ac.target_works_json LIKE ? OR "
            "ac.target_location_json LIKE ? OR p.document_title LIKE ? OR p.section_title LIKE ? OR "
            "p.entry_title LIKE ? OR ac.lifecycle LIKE ? OR ac.machine_status LIKE ?"
            ")"
        )
        parameters.extend([needle] * 12)
    if source_work:
        conditions.append("ac.source_work = ?")
        parameters.append(source_work)
    if machine_status:
        conditions.append("ac.machine_status = ?")
        parameters.append(machine_status)
    where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""

    total = int(connection.execute(
        f"""
        SELECT COUNT(*)
        FROM annotation_cases ac
        LEFT JOIN passages p ON p.passage_id = ac.source_passage_id
        {where_clause}
        """,
        parameters,
    ).fetchone()[0])
    source_works = [
        str(row["source_work"])
        for row in connection.execute(
            "SELECT DISTINCT source_work FROM annotation_cases ORDER BY source_work"
        ).fetchall()
    ]

    pagination: dict[str, Any] = {}
    limit_clause = ""
    if page is not None and page_size is not None:
        safe_page_size = max(1, min(page_size, 200))
        page_count = max(1, (total + safe_page_size - 1) // safe_page_size)
        safe_page = max(1, min(page, page_count))
        pagination = {
            "page": safe_page,
            "page_size": safe_page_size,
            "page_count": page_count,
            "total": total,
        }
        limit_clause = " LIMIT ? OFFSET ?"
        parameters = [*parameters, safe_page_size, (safe_page - 1) * safe_page_size]

    rows = connection.execute(
        f"""
        SELECT ac.*,
               p.document_title AS source_document_title,
               p.section_title AS source_section_title,
               p.entry_title AS source_entry_title,
               p.md_line_start AS source_md_line_start,
               p.md_line_end AS source_md_line_end,
               (SELECT COUNT(*) FROM annotation_terms t WHERE t.case_id = ac.case_id) AS term_count,
               (SELECT COUNT(*) FROM annotation_evidences e WHERE e.case_id = ac.case_id) AS evidence_count,
               (SELECT COUNT(*) FROM annotation_process_steps ps WHERE ps.case_id = ac.case_id) AS process_step_count
               ,(SELECT COUNT(*) FROM candidate_target_locations ctl WHERE ctl.case_id = ac.case_id) AS target_location_candidate_count
               ,(SELECT COUNT(*) FROM candidate_target_locations ctl WHERE ctl.case_id = ac.case_id AND ctl.work_identity_status = 'canonical') AS target_location_canonical_count
               ,(SELECT COUNT(*) FROM candidate_target_locations ctl WHERE ctl.case_id = ac.case_id AND ctl.target_passage_match_status = 'candidate_match') AS target_location_passage_candidate_count
        FROM annotation_cases ac
        LEFT JOIN passages p ON p.passage_id = ac.source_passage_id
        {where_clause}
        ORDER BY CASE ac.source_work WHEN '读书杂志' THEN 1 WHEN '广雅疏证' THEN 2 ELSE 3 END,
                 ac.case_id
        {limit_clause}
        """,
        parameters,
    ).fetchall()
    result = []
    for row in rows:
        item = dict(row)
        item["target_works"] = parse_json(item.pop("target_works_json", "[]"), [])
        item["target_scope"] = parse_json(item.pop("target_scope_json", "{}"), {})
        item["machine_result"] = parse_json(item.pop("machine_result_json", "{}"), {})
        item["human_review"] = parse_json(item.pop("human_review_json", "{}"), {})
        case_data = parse_json(item.pop("case_json", "{}"), {})
        item["provenance"] = provenance_payload(case_data)
        item["evidence_summary"] = {}
        evidence_rows = connection.execute(
            "SELECT evidence_json FROM annotation_evidences WHERE case_id = ?",
            (item["case_id"],),
        ).fetchall()
        for evidence_row in evidence_rows:
            evidence = parse_json(evidence_row["evidence_json"], {})
            key = evidence.get("source_resolution") or "unknown"
            item["evidence_summary"][key] = item["evidence_summary"].get(key, 0) + 1
        result.append(item)
    payload = {
        "ok": True,
        "items": result,
        "total": total,
        "source_works": source_works,
        "filters": {
            "query": query,
            "source_work": source_work,
            "machine_status": machine_status,
        },
    }
    payload.update(pagination)
    return payload


def get_case(connection: sqlite3.Connection, case_id: str) -> dict[str, Any] | None:
    row = connection.execute(
        "SELECT * FROM annotation_cases WHERE case_id = ?",
        (case_id,),
    ).fetchone()
    if row is None:
        return None
    item = dict(row)
    item["target_works"] = parse_json(item.pop("target_works_json", "[]"), [])
    item["target_scope"] = parse_json(item.pop("target_scope_json", "{}"), {})
    item["machine_result"] = parse_json(item.pop("machine_result_json", "{}"), {})
    item["human_review"] = parse_json(item.pop("human_review_json", "{}"), {})
    item["case_data"] = parse_json(item.pop("case_json", "{}"), {})
    item["provenance"] = provenance_payload(item["case_data"])

    source_passage = connection.execute(
        "SELECT * FROM passages WHERE passage_id = ?",
        (item.get("source_passage_id"),),
    ).fetchone() if item.get("source_passage_id") else None
    item["source_passage"] = passage_payload(source_passage)
    target_passage = connection.execute(
        "SELECT * FROM passages WHERE passage_id = ?",
        (item.get("target_passage_id"),),
    ).fetchone() if item.get("target_passage_id") else None
    item["target_passage"] = passage_payload(target_passage)

    target_location_rows = connection.execute(
        """
        SELECT * FROM candidate_target_locations
        WHERE case_id = ?
        ORDER BY label_start_char, candidate_target_id
        """,
        (case_id,),
    ).fetchall()
    target_locations = []
    for target_location_row in target_location_rows:
        target_location = dict(target_location_row)
        target_location["evidence_indexes"] = parse_json(
            target_location.pop("evidence_indexes_json", "[]"), []
        )
        target_location["provenance"] = parse_json(
            target_location.pop("provenance_json", "{}"), {}
        )
        target_candidate_passage = connection.execute(
            "SELECT * FROM passages WHERE passage_id = ?",
            (target_location.get("target_passage_candidate_id"),),
        ).fetchone() if target_location.get("target_passage_candidate_id") else None
        target_location["target_passage_candidate"] = passage_payload(target_candidate_passage)
        target_locations.append(target_location)
    item["target_location_candidates"] = target_locations

    term_rows = connection.execute(
        """
        SELECT case_id, term_index, source_term, target_term, relation_type,
               relation_subtype, relation_note, term_json
        FROM annotation_terms WHERE case_id = ? ORDER BY term_index
        """,
        (case_id,),
    ).fetchall()
    terms = []
    for term_row in term_rows:
        term = dict(term_row)
        term["data"] = parse_json(term.pop("term_json", "{}"), {})
        terms.append(term)
    item["terms"] = terms

    evidence_rows = connection.execute(
        """
        SELECT e.*, link.external_source_id,
               es.cited_work AS external_cited_work,
               es.status AS external_status,
               es.source_file AS external_source_file,
               es.edition AS external_edition,
               es.location_note AS external_location_note,
               epq.queue_item_id AS external_queue_item_id,
               epq.queue_status AS external_queue_status,
               epq.edition_status AS external_edition_status,
               epq.passage_status AS external_passage_status,
               epq.selected_passage_id AS external_selected_passage_id,
               epq.candidate_passage_ids_json AS external_candidate_passage_ids_json,
               epq.candidate_refs_json AS external_candidate_refs_json
        FROM annotation_evidences e
        LEFT JOIN annotation_evidence_external_sources link
          ON link.case_id = e.case_id AND link.evidence_index = e.evidence_index
        LEFT JOIN external_source_registry es
          ON es.external_source_id = link.external_source_id
        LEFT JOIN external_passage_resolution_queue epq
          ON epq.case_id = e.case_id AND epq.evidence_index = e.evidence_index
        WHERE e.case_id = ?
        ORDER BY e.evidence_index
        """,
        (case_id,),
    ).fetchall()
    evidences = []
    for evidence_row in evidence_rows:
        evidence = dict(evidence_row)
        evidence["data"] = parse_json(evidence.pop("evidence_json", "{}"), {})
        candidate_ids = parse_json(
            evidence.pop("external_candidate_passage_ids_json", "[]"), []
        )
        if not isinstance(candidate_ids, list):
            candidate_ids = []
        evidence["external_candidate_passage_ids"] = [
            str(candidate_id) for candidate_id in candidate_ids if candidate_id
        ]
        evidence["external_candidate_passages"] = [
            candidate
            for candidate_id in evidence["external_candidate_passage_ids"]
            if (candidate := external_candidate_passage_payload(connection, candidate_id))
        ]
        evidence["external_candidate_refs"] = parse_json(
            evidence.pop("external_candidate_refs_json", "[]"), []
        )
        evidence["source_passage"] = passage_payload(
            connection.execute(
                "SELECT * FROM passages WHERE passage_id = ?",
                (evidence.get("passage_id"),),
            ).fetchone() if evidence.get("passage_id") else None
        )
        evidences.append(evidence)
    item["evidences"] = evidences
    item["evidence_summary"] = {}
    for evidence in evidences:
        key = evidence["data"].get("source_resolution") or "unknown"
        item["evidence_summary"][key] = item["evidence_summary"].get(key, 0) + 1

    steps = connection.execute(
        """
        SELECT step_index, field_name, step_text, step_json
        FROM annotation_process_steps WHERE case_id = ? ORDER BY step_index
        """,
        (case_id,),
    ).fetchall()
    item["process_steps"] = [
        {
            **dict(step),
            "data": parse_json(step["step_json"], {}),
        }
        for step in steps
    ]
    item["review_events"] = rows_dict(connection.execute(
        """
        SELECT review_event_id, reviewer, review_status, review_note,
               review_json, created_at
        FROM review_events WHERE case_id = ? ORDER BY review_event_id
        """,
        (case_id,),
    ).fetchall())
    for review in item["review_events"]:
        review["data"] = parse_json(review.pop("review_json", "{}"), {})
    item["resolution_events"] = rows_dict(connection.execute(
        """
        SELECT resolution_event_id, resolution_kind, queue_item_id,
               external_source_id, evidence_index, reviewer, operation_id,
               from_queue_status, to_queue_status, resolution_note,
               resolution_json, created_at
        FROM resolution_events
        WHERE case_id = ? ORDER BY resolution_event_id
        """,
        (case_id,),
    ).fetchall())
    for resolution in item["resolution_events"]:
        resolution["data"] = parse_json(resolution.pop("resolution_json", "{}"), {})
    return item


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("summary", "cases", "case"))
    parser.add_argument("case_id", nargs="?")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--query", default="")
    parser.add_argument("--source-work", default="")
    parser.add_argument("--machine-status", default="")
    parser.add_argument("--page", type=int)
    parser.add_argument("--page-size", type=int)
    args = parser.parse_args()

    try:
        connection = connect(args.db)
        try:
            if args.command == "summary":
                payload = build_summary(connection, args.db)
            elif args.command == "cases":
                payload = list_cases(
                    connection,
                    query=args.query,
                    source_work=args.source_work,
                    machine_status=args.machine_status,
                    page=args.page,
                    page_size=args.page_size,
                )
            else:
                payload = get_case(connection, args.case_id or "")
                if payload is None:
                    payload = {"ok": False, "message": "V2 case not found"}
                else:
                    payload["ok"] = True
        finally:
            connection.close()
        print(json.dumps(payload, ensure_ascii=False))
        return 0
    except Exception as error:
        print(json.dumps({"ok": False, "message": str(error)}, ensure_ascii=False))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
