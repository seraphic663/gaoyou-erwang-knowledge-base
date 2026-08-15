#!/usr/bin/env python3
"""Build a read-only coverage map for the V2 annotation workflow.

The database deliberately contains both formal machine cases and original-text
candidate shells.  A raw ``annotation_cases`` count therefore hides an
important boundary.  This report maps the eleven workflow stages to concrete
artifacts, counts, and unresolved gates without changing the database.
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
DEFAULT_OUTPUT = V2_ROOT / "data/real_runs/workflow_coverage_report.v1.json"
DEFAULT_VALIDATION = V2_ROOT / "data/real_runs/v2_validation_report.json"
DEFAULT_SOURCE_INVENTORY = V2_ROOT / "data/real_runs/source_inventory.v1.json"
DEFAULT_LEGACY_AUDIT = V2_ROOT / "data/real_runs/legacy_dictionary_field_audit.json"
DEFAULT_TARGET_PACKET_REPORT = V2_ROOT / "data/real_runs/target_work_resolution_packets_report.json"
DEFAULT_TARGET_PROPOSAL_REPORT = V2_ROOT / "data/real_runs/target_work_resolution_proposals_report.json"
DEFAULT_EXTERNAL_PACKET_REPORT = V2_ROOT / "data/real_runs/external_evidence_packets_report.json"
DEFAULT_REVIEW_MANIFEST = V2_ROOT / "data/real_runs/review_tasks/review_task_manifest.review.v1.json"


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def relative_path(value: str | Path) -> str:
    path = Path(value)
    try:
        return path.resolve().relative_to(PROJECT_ROOT.resolve()).as_posix()
    except ValueError:
        return path.as_posix()


def load_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return value if isinstance(value, dict) else {}


def connect_read_only(database_path: Path) -> sqlite3.Connection:
    connection = sqlite3.connect(f"file:{database_path.resolve()}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA query_only = ON")
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def grouped(connection: sqlite3.Connection, query: str) -> dict[str, int]:
    return {
        str(row["value"] if row["value"] is not None else "<null>"): int(row["count"])
        for row in connection.execute(query)
    }


def scalar(connection: sqlite3.Connection, query: str) -> int:
    return int(connection.execute(query).fetchone()[0])


def build_report(
    *,
    database_path: Path = DEFAULT_DATABASE,
    validation_path: Path = DEFAULT_VALIDATION,
    source_inventory_path: Path = DEFAULT_SOURCE_INVENTORY,
    legacy_audit_path: Path = DEFAULT_LEGACY_AUDIT,
    target_packet_report_path: Path = DEFAULT_TARGET_PACKET_REPORT,
    target_proposal_report_path: Path = DEFAULT_TARGET_PROPOSAL_REPORT,
    external_packet_report_path: Path = DEFAULT_EXTERNAL_PACKET_REPORT,
    review_manifest_path: Path = DEFAULT_REVIEW_MANIFEST,
) -> dict[str, Any]:
    database_path = Path(database_path).resolve()
    with connect_read_only(database_path) as connection:
        integrity = connection.execute("PRAGMA integrity_check").fetchone()[0]
        foreign_keys = [tuple(row) for row in connection.execute("PRAGMA foreign_key_check")]

        source_documents = {
            "total": scalar(connection, "SELECT COUNT(*) FROM source_documents"),
            "by_kind_and_status": [
                dict(row)
                for row in connection.execute(
                    """
                    SELECT source_kind, canonical_status, COUNT(*) AS count
                    FROM source_documents
                    GROUP BY source_kind, canonical_status
                    ORDER BY source_kind, canonical_status
                    """
                )
            ],
            "canonical_active_count": scalar(
                connection, "SELECT COUNT(*) FROM source_documents WHERE canonical_status='canonical_active'"
            ),
            "canonical_active_passage_count": scalar(
                connection,
                """
                SELECT COUNT(*) FROM passages p
                JOIN source_documents sd USING(source_document_id)
                WHERE sd.canonical_status='canonical_active'
                """,
            ),
            "active_versions": [
                dict(row)
                for row in connection.execute(
                    """
                    SELECT work_key, source_file, source_file_sha256, canonical_status
                    FROM source_documents
                    WHERE canonical_status='canonical_active'
                    ORDER BY work_key
                    """
                )
            ],
        }

        candidates = {
            "candidate_item_count": scalar(connection, "SELECT COUNT(*) FROM candidate_items"),
            "candidate_output_link_count": scalar(
                connection, "SELECT COUNT(*) FROM candidate_items WHERE output_case_id IS NOT NULL"
            ),
            "candidate_status_counts": grouped(
                connection,
                "SELECT candidate_status AS value, COUNT(*) AS count FROM candidate_items GROUP BY candidate_status",
            ),
            "case_origin_counts": grouped(
                connection,
                "SELECT origin AS value, COUNT(*) AS count FROM annotation_cases GROUP BY origin",
            ),
        }

        cases = {
            "total": scalar(connection, "SELECT COUNT(*) FROM annotation_cases"),
            "source_passage_links": scalar(
                connection, "SELECT COUNT(*) FROM annotation_cases WHERE source_passage_id IS NOT NULL"
            ),
            "target_passage_links": scalar(
                connection, "SELECT COUNT(*) FROM annotation_cases WHERE target_passage_id IS NOT NULL"
            ),
            "target_work_nonempty": scalar(
                connection, "SELECT COUNT(*) FROM annotation_cases WHERE TRIM(target_work)<>''"
            ),
            "target_work_empty": scalar(
                connection, "SELECT COUNT(*) FROM annotation_cases WHERE TRIM(target_work)=''"
            ),
            "process_text_nonempty": scalar(
                connection, "SELECT COUNT(*) FROM annotation_cases WHERE TRIM(process_text)<>''"
            ),
            "origin_target_summary": [
                dict(row)
                for row in connection.execute(
                    """
                    SELECT origin,
                           COUNT(*) AS cases,
                           SUM(source_passage_id IS NOT NULL) AS source_passage_links,
                           SUM(target_passage_id IS NOT NULL) AS target_passage_links,
                           SUM(TRIM(target_work)<>'') AS target_work_nonempty,
                           SUM(TRIM(process_text)<>'') AS process_text_nonempty
                    FROM annotation_cases
                    GROUP BY origin
                    ORDER BY cases DESC, origin
                    """
                )
            ],
        }

        target_resolution = {
            "queue_count": scalar(connection, "SELECT COUNT(*) FROM target_work_resolution_queue"),
            "queue_status_counts": grouped(
                connection,
                "SELECT queue_status AS value, COUNT(*) AS count FROM target_work_resolution_queue GROUP BY queue_status",
            ),
            "pending_case_count": scalar(
                connection,
                """
                SELECT COUNT(DISTINCT case_id) FROM target_work_resolution_queue
                WHERE queue_status IN ('pending','needs_context','uncertain')
                """,
            ),
            "empty_label_count": scalar(
                connection,
                "SELECT COUNT(*) FROM target_work_resolution_queue WHERE TRIM(raw_label)=''",
            ),
            "machine_work_key_count": scalar(
                connection,
                "SELECT COUNT(*) FROM target_work_resolution_queue WHERE machine_candidate_work_key IS NOT NULL",
            ),
            "candidate_location_count": scalar(
                connection, "SELECT COUNT(*) FROM candidate_target_locations"
            ),
            "candidate_location_match_count": scalar(
                connection,
                """
                SELECT COUNT(*) FROM candidate_target_locations
                WHERE target_passage_match_status='candidate_match'
                """,
            ),
            "candidate_location_identity_counts": grouped(
                connection,
                "SELECT work_identity_status AS value, COUNT(*) AS count FROM candidate_target_locations GROUP BY work_identity_status",
            ),
            "automatic_promotion_count": scalar(
                connection,
                """
                SELECT COUNT(*) FROM candidate_target_locations
                WHERE machine_status <> 'candidate_only' OR human_status <> 'pending'
                """,
            ),
            "canonical_target_passage_links": scalar(
                connection,
                """
                SELECT COUNT(*) FROM annotation_cases ac
                JOIN passages p ON p.passage_id=ac.target_passage_id
                JOIN source_documents sd USING(source_document_id)
                WHERE sd.canonical_status='canonical_active'
                """,
            ),
        }

        process = {
            "row_count": scalar(connection, "SELECT COUNT(*) FROM annotation_process_steps"),
            "field_case_counts": grouped(
                connection,
                "SELECT field_name AS value, COUNT(DISTINCT case_id) AS count FROM annotation_process_steps GROUP BY field_name",
            ),
            "five_step_case_count": scalar(
                connection,
                """
                SELECT COUNT(*) FROM (
                    SELECT case_id FROM annotation_process_steps
                    WHERE field_name IN ('problem_discovery','research_question',
                                         'evidence_collection','reasoning','conclusion')
                    GROUP BY case_id
                    HAVING COUNT(DISTINCT field_name)=5
                )
                """,
            ),
            "five_step_case_counts_by_origin": [
                dict(row)
                for row in connection.execute(
                    """
                    SELECT ac.origin, COUNT(*) AS count
                    FROM annotation_cases ac
                    WHERE (
                        SELECT COUNT(DISTINCT ps.field_name)
                        FROM annotation_process_steps ps
                        WHERE ps.case_id=ac.case_id
                          AND ps.field_name IN ('problem_discovery','research_question',
                                                'evidence_collection','reasoning','conclusion')
                          AND TRIM(ps.step_text)<>''
                    )=5
                    GROUP BY ac.origin
                    ORDER BY count DESC, ac.origin
                    """
                )
            ],
        }

        evidence = {
            "total": scalar(connection, "SELECT COUNT(*) FROM annotation_evidences"),
            "passage_links": scalar(
                connection, "SELECT COUNT(*) FROM annotation_evidences WHERE passage_id IS NOT NULL"
            ),
            "unlinked_count": scalar(
                connection, "SELECT COUNT(*) FROM annotation_evidences WHERE passage_id IS NULL"
            ),
            "source_resolution_counts": grouped(
                connection,
                """
                SELECT COALESCE(json_extract(evidence_json,'$.source_resolution'), '<null>') AS value,
                       COUNT(*) AS count
                FROM annotation_evidences GROUP BY value
                """,
            ),
            "quote_check_counts": grouped(
                connection,
                "SELECT COALESCE(quote_check,'<null>') AS value, COUNT(*) AS count FROM annotation_evidences GROUP BY value",
            ),
            "canonical_wang_passed_count": scalar(
                connection,
                """
                SELECT COUNT(*) FROM annotation_evidences ae
                JOIN passages p ON p.passage_id=ae.passage_id
                JOIN source_documents sd USING(source_document_id)
                WHERE ae.quote_check='passed' AND sd.canonical_status='canonical_active'
                """,
            ),
            "external_canonical_passed_count": scalar(
                connection,
                """
                SELECT COUNT(*) FROM annotation_evidences ae
                JOIN passages p ON p.passage_id=ae.passage_id
                JOIN source_documents sd USING(source_document_id)
                WHERE ae.quote_check='passed' AND sd.source_kind='external_public_candidate'
                """,
            ),
        }

        external = {
            "source_registry_count": scalar(connection, "SELECT COUNT(*) FROM external_source_registry"),
            "source_registry_status_counts": grouped(
                connection,
                "SELECT status AS value, COUNT(*) AS count FROM external_source_registry GROUP BY status",
            ),
            "source_queue_count": scalar(connection, "SELECT COUNT(*) FROM external_source_resolution_queue"),
            "source_queue_status_counts": grouped(
                connection,
                "SELECT queue_status AS value, COUNT(*) AS count FROM external_source_resolution_queue GROUP BY queue_status",
            ),
            "passage_queue_count": scalar(connection, "SELECT COUNT(*) FROM external_passage_resolution_queue"),
            "passage_queue_status_counts": grouped(
                connection,
                "SELECT queue_status AS value, COUNT(*) AS count FROM external_passage_resolution_queue GROUP BY queue_status",
            ),
            "candidate_passage_count": scalar(
                connection,
                """
                SELECT COUNT(*) FROM passages p
                JOIN source_documents sd USING(source_document_id)
                WHERE sd.source_kind='external_public_candidate'
                """,
            ),
            "canonical_external_document_count": scalar(
                connection,
                """
                SELECT COUNT(*) FROM source_documents
                WHERE source_kind NOT IN ('markdown','markdown_core','legacy_source_txt','legacy_derived_quote',
                                          'external_public_candidate')
                  AND canonical_status='canonical_active'
                """,
            ),
        }

        states = {
            "machine_status_counts": grouped(
                connection, "SELECT machine_status AS value, COUNT(*) AS count FROM annotation_cases GROUP BY machine_status"
            ),
            "human_status_counts": grouped(
                connection, "SELECT human_status AS value, COUNT(*) AS count FROM annotation_cases GROUP BY human_status"
            ),
            "lifecycle_counts": grouped(
                connection, "SELECT lifecycle AS value, COUNT(*) AS count FROM annotation_cases GROUP BY lifecycle"
            ),
            "review_event_count": scalar(connection, "SELECT COUNT(*) FROM review_events"),
            "resolution_event_count": scalar(connection, "SELECT COUNT(*) FROM resolution_events"),
        }

        legacy = {
            "term_rows": scalar(connection, "SELECT COUNT(*) FROM legacy_dictionary_terms"),
            "referenced_term_rows": scalar(
                connection, "SELECT COUNT(*) FROM legacy_dictionary_terms WHERE usage_status='referenced'"
            ),
            "catalog_only_term_rows": scalar(connection, "SELECT COUNT(*) FROM legacy_catalog_terms"),
            "work_rows": scalar(connection, "SELECT COUNT(*) FROM legacy_dictionary_works"),
            "referenced_work_rows": scalar(
                connection, "SELECT COUNT(*) FROM legacy_dictionary_works WHERE usage_status='referenced'"
            ),
            "catalog_only_work_rows": scalar(connection, "SELECT COUNT(*) FROM legacy_catalog_works"),
            "term_case_link_rows": scalar(connection, "SELECT COUNT(*) FROM legacy_term_case_links"),
            "work_evidence_link_rows": scalar(connection, "SELECT COUNT(*) FROM legacy_work_evidence_links"),
        }

    validation = load_json(Path(validation_path))
    source_inventory = load_json(Path(source_inventory_path))
    legacy_audit = load_json(Path(legacy_audit_path))
    target_packet = load_json(Path(target_packet_report_path))
    target_proposal = load_json(Path(target_proposal_report_path))
    external_packet = load_json(Path(external_packet_report_path))
    review_manifest = load_json(Path(review_manifest_path))
    edition_candidate_validation = external_packet.get(
        "edition_candidate_manifest_validation", {}
    )

    canonical_policy_ok = (
        source_documents["canonical_active_count"] == 4
        and any(
            row.get("work_key") == "dushu_zazhi"
            and str(row.get("source_file_sha256", "")).startswith("1460a906825998bf")
            for row in source_documents["active_versions"]
        )
    )
    case_count = cases["total"]
    candidate_count = candidates["candidate_item_count"]
    case_origin_counts = candidates["case_origin_counts"]
    validation_ok = validation.get("status") == "passed" and all(
        bool(value) for value in (validation.get("checks") or {}).values()
    )

    workflow_steps = [
        {
            "step": 1,
            "name": "清点输入源、字段、数量、来源链和 canonical hash",
            "status": "completed" if source_inventory and canonical_policy_ok else "needs_refresh",
            "artifacts": [relative_path(source_inventory_path), relative_path(legacy_audit_path)],
            "counts": {
                "canonical_active_documents": source_documents["canonical_active_count"],
                "canonical_active_passages": source_documents["canonical_active_passage_count"],
                "candidate_items": candidate_count,
                "legacy_terms": legacy["term_rows"],
                "legacy_works": legacy["work_rows"],
            },
            "boundary": "旧主库实际为 SQLite dictionary.db；source.txt/parser/importer 链路仍标为 legacy machine source，不是原典核验。",
        },
        {
            "step": 2,
            "name": "建立四部原典 source_documents 和 passages",
            "status": "completed" if canonical_policy_ok and source_documents["canonical_active_passage_count"] > 0 else "incomplete",
            "artifacts": [relative_path(database_path)],
            "counts": {
                "canonical_documents": source_documents["canonical_active_count"],
                "canonical_passages": source_documents["canonical_active_passage_count"],
            },
            "boundary": "读书杂志 active hash 使用 1460a906825998bf…；旧 hash 只保留历史策略，不进入 active passages。",
        },
        {
            "step": 3,
            "name": "从旧机器库、旧 AI JSON、四部原典提取候选",
            "status": "completed" if candidate_count > 0 and legacy["term_rows"] > 0 else "incomplete",
            "artifacts": [relative_path(database_path)],
            "counts": {
                "original_markdown_candidate_items": candidate_count,
                "legacy_dictionary_cases": case_origin_counts.get(
                    "legacy_dictionary_db_reprocessing", 0
                ),
                "legacy_dictionary_terms": legacy["term_rows"],
                "external_source_queue": external["source_queue_count"],
            },
            "boundary": "旧 AI JSON 仍是迁移线索；四部原典抽取结果先进入 candidate_item.v1。",
        },
        {
            "step": 4,
            "name": "候选统一转换为 annotation_case.v1",
            "status": "completed" if candidates["candidate_output_link_count"] == candidate_count else "incomplete",
            "artifacts": [relative_path(database_path)],
            "counts": {
                "candidate_items": candidate_count,
                "candidate_output_links": candidates["candidate_output_link_count"],
                "annotation_cases": case_count,
                "case_origins": candidates["case_origin_counts"],
            },
            "boundary": "6,745 个原典记录是 machine-only candidate shell；其结构化存在不代表已经形成学术结论。",
        },
        {
            "step": 5,
            "name": "自动定位 source passage、target passage、target work 和 target location",
            "status": "machine_ready_with_resolution_queue",
            "artifacts": [
                relative_path(target_packet_report_path),
                relative_path(target_proposal_report_path),
                "v2/data/real_runs/candidate_target_location_report.json",
            ],
            "counts": {
                "case_source_passage_links": cases["source_passage_links"],
                "case_target_passage_links": cases["target_passage_links"],
                "canonical_target_passage_links": target_resolution["canonical_target_passage_links"],
                "target_work_queue": target_resolution["queue_count"],
                "target_work_pending_cases": target_resolution["pending_case_count"],
                "target_location_candidates": target_resolution["candidate_location_count"],
                "target_location_candidate_matches": target_resolution["candidate_location_match_count"],
                "target_location_automatic_promotions": target_resolution["automatic_promotion_count"],
                "target_resolution_proposals": target_proposal.get("counts", {}).get("pending_queue_count"),
                "target_resolution_proposal_candidate_passage_refs": target_proposal.get("counts", {}).get("candidate_passage_refs_embedded"),
            },
            "boundary": "不安全的目标著作身份、篇章或版本不写入 annotation_cases.target_work/target_passage_id；当前 815 个 target passage 是 legacy-derived、未核验材料。",
        },
        {
            "step": 6,
            "name": "自动补齐 process_text 和五步过程字段",
            "status": "completed_structurally",
            "artifacts": [relative_path(database_path)],
            "counts": {
                "process_rows": process["row_count"],
                "five_step_cases": process["five_step_case_count"],
                "five_step_cases_by_origin": process["five_step_case_counts_by_origin"],
            },
            "boundary": "旧机器案例的过程是机器迁移规则；candidate shell 的五步是待研究占位文本，均保持 machine draft/human pending。",
        },
        {
            "step": 7,
            "name": "证据绑定 passage、quote、location、来源文件/行号/hash/匹配模式",
            "status": "machine_ready_with_unresolved_external",
            "artifacts": [
                relative_path(database_path),
                relative_path(external_packet_report_path),
            ],
            "counts": {
                "evidence_rows": evidence["total"],
                "evidence_passage_links": evidence["passage_links"],
                "evidence_unlinked": evidence["unlinked_count"],
                "canonical_wang_quote_machine_passed": evidence["canonical_wang_passed_count"],
                "external_candidate_quote_passed": evidence["external_canonical_passed_count"],
                "quote_check_counts": evidence["quote_check_counts"],
            },
            "boundary": "secondary citation、legacy derived quote、external pending 均不能冒充被引原典 canonical quote；外部候选仍需独立底本/版本与人工图文核验。",
        },
        {
            "step": 8,
            "name": "运行结构、外键、引用、quote、hash、来源状态校验",
            "status": "completed" if validation_ok and integrity == "ok" and not foreign_keys else "failed",
            "artifacts": [relative_path(validation_path)],
            "counts": {
                "integrity_check": integrity,
                "foreign_key_violations": len(foreign_keys),
                "validation_status": validation.get("status"),
                "validation_checks": len(validation.get("checks") or {}),
            },
            "boundary": "通过表示结构和来源边界通过，不表示人工学术结论通过。",
        },
        {
            "step": 9,
            "name": "通过本地验收网站检查数据库结果",
            "status": "artifact_ready",
            "artifacts": [
                "03-项目网站/web/v2-database.html",
                "03-项目网站/web/v2-acceptance.html",
                "03-项目网站/src/http-server.js",
            ],
            "counts": {"read_only_database": True, "validation_bridge_present": True},
            "boundary": "本报告不把网页是否当前运行冒充数据库验证；网站只读展示和任务分批不改变机器/人工状态。",
        },
        {
            "step": 10,
            "name": "机器结果保留 machine draft，人工保持 pending",
            "status": "completed" if states["review_event_count"] == 0 and states["resolution_event_count"] == 0 else "needs_review_audit",
            "artifacts": [relative_path(database_path), relative_path(review_manifest_path)],
            "counts": {
                "machine_status": states["machine_status_counts"],
                "human_status": states["human_status_counts"],
                "lifecycle": states["lifecycle_counts"],
                "review_events": states["review_event_count"],
                "resolution_events": states["resolution_event_count"],
            },
            "boundary": "当前没有 gold；target/source/passage resolution 也不自动晋级 gold。",
        },
        {
            "step": 11,
            "name": "更新报告、README、验收数据和测试",
            "status": (
                "completed"
                if target_packet
                and target_proposal
                and external_packet
                and review_manifest
                and external_packet.get("valid", False)
                and edition_candidate_validation.get("valid", False)
                else "needs_refresh"
            ),
            "artifacts": [
                relative_path(DEFAULT_OUTPUT),
                relative_path(target_packet_report_path),
                relative_path(target_proposal_report_path),
                relative_path(external_packet_report_path),
                str(
                    external_packet.get("edition_candidate_manifest", {}).get(
                        "path", "v2/data/real_runs/external_edition_candidate_manifest.v1.json"
                    )
                ),
                relative_path(review_manifest_path),
            ],
            "counts": {
                "target_packet_valid": bool(target_packet.get("valid", False)),
                "target_proposal_report_present": bool(target_proposal),
                "external_packet_valid": bool(external_packet.get("valid", False)),
                "external_edition_candidate_manifest_valid": bool(
                    edition_candidate_validation.get("valid", False)
                ),
                "external_edition_candidate_counts": edition_candidate_validation.get(
                    "counts", {}
                ),
                "review_manifest_present": bool(review_manifest),
            },
            "boundary": "人工审校不在自动化完成范围；报告只登记待办，不伪造审校结果。",
        },
    ]

    report = {
        "report_version": "workflow-coverage-report.v1",
        "generated_at": now(),
        "database": relative_path(database_path),
        "current_round_focus": {
            "workflow_steps": [5, 7, 8, 10, 11],
            "description": "目标典籍解析、外部底本候选、证据边界、机器/人工分离和可验收任务包；没有把网站展示层当作数据完成。",
            "off_track_check": {
                "source_chain_preserved": True,
                "canonical_dushu_hash_policy_preserved": canonical_policy_ok,
                "human_review_performed": states["review_event_count"] > 0,
                "gold_promotion_performed": states["lifecycle_counts"].get("gold", 0) > 0,
            },
        },
        "workflow_steps": workflow_steps,
        "inventory": {
            "source_documents": source_documents,
            "candidates": candidates,
            "cases": cases,
            "target_resolution": target_resolution,
            "process": process,
            "evidence": evidence,
            "external": external,
            "legacy": legacy,
            "states": states,
        },
        "machine_ready": {
            "source_passage_coverage": cases["source_passage_links"] == case_count,
            "process_five_step_coverage": process["five_step_case_count"] == case_count,
            "candidate_output_coverage": candidates["candidate_output_link_count"] == candidate_count,
            "validation_passed": validation_ok,
            "target_packet_report": target_packet.get("counts", {}),
            "target_proposal_report": target_proposal.get("counts", {}),
            "external_packet_report": external_packet.get("counts", {}),
            "external_edition_candidate_manifest": edition_candidate_validation,
        },
        "remaining_boundaries": {
            "target_work_empty_cases": cases["target_work_empty"],
            "target_passage_missing_cases": case_count - cases["target_passage_links"],
            "external_canonical_documents": external["canonical_external_document_count"],
            "external_candidate_passage_documents": external["candidate_passage_count"],
            "external_edition_candidate_files": edition_candidate_validation.get(
                "counts", {}
            ).get("complete_file_count", 0),
            "legacy_unverified_evidence": evidence["source_resolution_counts"].get("legacy_derived_passage", 0),
            "human_pending_cases": states["human_status_counts"].get("pending", 0),
            "gold_cases": states["lifecycle_counts"].get("gold", 0),
            "reason": [
                "目标著作/篇章/版本需要逐条身份判断，不能由空标签或模糊引文自动猜测。",
                "旧机器 quote 和外部公开转录不能代替被引原典的独立 canonical 底本。",
                "人工审校、版本选择和学术结论确认尚未执行。",
            ],
        },
        "valid": all(step["status"] != "failed" for step in workflow_steps)
        and integrity == "ok"
        and not foreign_keys,
        "validation_source": relative_path(validation_path),
        "source_inventory_source": relative_path(source_inventory_path),
        "legacy_audit_source": relative_path(legacy_audit_path),
    }
    return report


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--database", type=Path, default=DEFAULT_DATABASE)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--validation", type=Path, default=DEFAULT_VALIDATION)
    parser.add_argument("--source-inventory", type=Path, default=DEFAULT_SOURCE_INVENTORY)
    parser.add_argument("--legacy-audit", type=Path, default=DEFAULT_LEGACY_AUDIT)
    parser.add_argument("--target-packet-report", type=Path, default=DEFAULT_TARGET_PACKET_REPORT)
    parser.add_argument("--target-proposal-report", type=Path, default=DEFAULT_TARGET_PROPOSAL_REPORT)
    parser.add_argument("--external-packet-report", type=Path, default=DEFAULT_EXTERNAL_PACKET_REPORT)
    parser.add_argument("--review-manifest", type=Path, default=DEFAULT_REVIEW_MANIFEST)
    args = parser.parse_args()
    report = build_report(
        database_path=args.database,
        validation_path=args.validation,
        source_inventory_path=args.source_inventory,
        legacy_audit_path=args.legacy_audit,
        target_packet_report_path=args.target_packet_report,
        target_proposal_report_path=args.target_proposal_report,
        external_packet_report_path=args.external_packet_report,
        review_manifest_path=args.review_manifest,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"ok": report["valid"], "output": relative_path(args.output)}, ensure_ascii=False))
    return 0 if report["valid"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
