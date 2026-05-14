# -*- coding: utf-8 -*-
"""
annotation_bridge.py

将 02-数据库/data/annotations.db 导出为网站 JSON 快照。
使用 02-数据库/lib/ 共享工具层。
独立于主库桥接脚本，专用于人工标注灰度库。
"""
import argparse
import json
import sys
from pathlib import Path

WORKSPACE_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(WORKSPACE_ROOT / "02-数据库"))

from lib.connection import connect, fetch_all
from lib.snapshot import write_json, loads_json

ANNOTATION_DB_FILE = WORKSPACE_ROOT / "02-数据库" / "data" / "annotations.db"
SNAPSHOT_FILE = WORKSPACE_ROOT / "03-项目网站" / "data" / "annotation-snapshot.json"


def build_snapshot(db_file):
    if not db_file.exists():
        raise FileNotFoundError(f"Annotation database not found: {db_file}")

    conn = connect(db_file)

    meta = {row["key"]: row["value"] for row in fetch_all(conn, "SELECT key, value FROM meta")}
    documents = fetch_all(conn, "SELECT * FROM source_documents ORDER BY id")
    cases = fetch_all(conn, "SELECT * FROM annotation_cases ORDER BY id")
    terms = fetch_all(conn, "SELECT * FROM annotation_terms ORDER BY id")
    evidences = fetch_all(conn, "SELECT * FROM annotation_evidences ORDER BY id")
    steps = fetch_all(conn, "SELECT * FROM annotation_process_steps ORDER BY case_id, step_order, id")

    terms_by_case = {}
    for term in terms:
        term["source_paragraph_indexes"] = loads_json(term.pop("source_paragraph_indexes_json", ""), [])
        term["source_comment_ids"] = loads_json(term.pop("source_comment_ids_json", ""), [])
        term["raw"] = loads_json(term.pop("raw_term_json", ""), {})
        terms_by_case.setdefault(term["case_id"], []).append(term)

    evidences_by_case = {}
    for evidence in evidences:
        evidence["source_paragraph_indexes"] = loads_json(evidence.pop("source_paragraph_indexes_json", ""), [])
        evidence["source_comment_ids"] = loads_json(evidence.pop("source_comment_ids_json", ""), [])
        evidence["raw"] = loads_json(evidence.pop("raw_evidence_json", ""), {})
        evidences_by_case.setdefault(evidence["case_id"], []).append(evidence)

    steps_by_case = {}
    for step in steps:
        step["source_paragraph_indexes"] = loads_json(step.pop("source_paragraph_indexes_json", ""), [])
        step["source_comment_ids"] = loads_json(step.pop("source_comment_ids_json", ""), [])
        step["raw"] = loads_json(step.pop("raw_step_json", ""), {})
        steps_by_case.setdefault(step["case_id"], []).append(step)

    document_map = {doc["id"]: doc for doc in documents}
    method_counts = {}
    document_counts = {}

    for case in cases:
        case["method_tags"] = loads_json(case.pop("method_tags_json", ""), [])
        case["raw"] = loads_json(case.pop("raw_case_json", ""), {})
        case["terms"] = terms_by_case.get(case["id"], [])
        case["evidences"] = evidences_by_case.get(case["id"], [])
        case["process_steps"] = steps_by_case.get(case["id"], [])
        case["source_document"] = document_map.get(case.get("source_document_id"))

        doc_name = case["source_document"]["source_file_name"] if case.get("source_document") else "未标注文档"
        document_counts[doc_name] = document_counts.get(doc_name, 0) + 1
        for tag in case["method_tags"] or ["未标注方法"]:
            method_counts[tag] = method_counts.get(tag, 0) + 1

    conn.close()

    return {
        "schemaVersion": "annotation_snapshot_v1",
        "source": "annotation_db",
        "sourceLabel": "人工标注灰度库",
        "description": "人工标注与 AI 整理结果暂存库，独立于主库，位于 02-数据库/data/annotations.db。",
        "dbFile": str(db_file.relative_to(WORKSPACE_ROOT)),
        "meta": meta,
        "counts": {
            "documents": len(documents),
            "cases": len(cases),
            "terms": len(terms),
            "evidences": len(evidences),
            "processSteps": len(steps),
        },
        "documents": documents,
        "methodCounts": method_counts,
        "documentCounts": document_counts,
        "cases": cases,
    }


def export_snapshot(db_file=ANNOTATION_DB_FILE, output_file=SNAPSHOT_FILE):
    snapshot = build_snapshot(db_file)
    write_json(output_file, snapshot)
    return snapshot


def main():
    parser = argparse.ArgumentParser(description="Export annotation database snapshot for website")
    parser.add_argument("command", nargs="?", default="export", choices=["export"])
    parser.add_argument("--db", type=Path, default=ANNOTATION_DB_FILE)
    parser.add_argument("--out", type=Path, default=SNAPSHOT_FILE)
    args = parser.parse_args()

    snapshot = export_snapshot(args.db, args.out)
    print(f"Exported {snapshot['counts']['cases']} annotation cases to {args.out}")


if __name__ == "__main__":
    main()
