#!/usr/bin/env python3
"""Build a read-only inventory of V2 inputs and source boundaries.

The inventory is explicit about the missing MySQL10 claim. A SQLite database
or a website JSON snapshot is not relabelled as MySQL10. The report records
files that are present in this project tree and leaves any external or
unmounted source outside the claim boundary.
"""

from __future__ import annotations

import argparse
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[2]
V2_ROOT = PROJECT_ROOT / "v2"
DEFAULT_OUTPUT = V2_ROOT / "data/real_runs/source_inventory.v1.json"
V2_DATABASE = V2_ROOT / "data/real_runs/annotation_v2.db"

CANONICAL_MARKDOWN = {
    "dushu_zazhi": PROJECT_ROOT / "04-项目文献/A-原著原典/读书杂志_王念孙.md",
    "guangya_shuzheng": PROJECT_ROOT / "04-项目文献/A-原著原典/广雅疏证_王念孙.md",
    "jingyi_shuwen": PROJECT_ROOT / "04-项目文献/A-原著原典/经义述闻_王引之.md",
    "jingzhuan_shici": PROJECT_ROOT / "04-项目文献/A-原著原典/经传释词_王引之.md",
}

LEGACY_ROUTE = {
    "dictionary_db": PROJECT_ROOT / "02-数据库/data/dictionary.db",
    "source_txt": PROJECT_ROOT / "02-数据库/main/source.txt",
    "parser_py": PROJECT_ROOT / "02-数据库/main/parser.py",
    "importer_py": PROJECT_ROOT / "02-数据库/main/importer.py",
}

AI_JSON_DIR = PROJECT_ROOT / "04-项目文献/D-标注/json/ai_json"
FULL_JSON_DIR = PROJECT_ROOT / "04-项目文献/D-标注/json/full_json"
WEBSITE_SNAPSHOTS = {
    "sqlite_snapshot": PROJECT_ROOT / "03-项目网站/data/sqlite-snapshot.json",
    "annotation_snapshot": PROJECT_ROOT / "03-项目网站/data/annotation-snapshot.json",
}


def file_record(path: Path, *, role: str) -> dict[str, Any]:
    record: dict[str, Any] = {
        "path": path.resolve().relative_to(PROJECT_ROOT.resolve()).as_posix(),
        "role": role,
        "exists": path.is_file(),
    }
    if path.is_file():
        record["size_bytes"] = path.stat().st_size
    return record


def discover_mysql_named_files() -> list[dict[str, Any]]:
    """Find names that could be mistaken for a MySQL10 snapshot."""

    records: list[dict[str, Any]] = []
    pattern = re.compile(r"mysql", re.IGNORECASE)
    for path in PROJECT_ROOT.rglob("*"):
        if not path.is_file() or ".git" in path.parts:
            continue
        if pattern.search(path.name) or path.suffix.lower() in {".sql", ".dump", ".bak"}:
            records.append(
                {
                    **file_record(path, role="possible_mysql_or_dump_artifact"),
                    "classification": (
                        "mysql_named_artifact"
                        if pattern.search(path.name)
                        else "schema_or_dump_extension_only"
                    ),
                }
            )
    return sorted(records, key=lambda item: item["path"])


def sqlite_counts(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {"exists": False}
    import sqlite3

    connection = sqlite3.connect(f"file:{path.resolve()}?mode=ro", uri=True)
    try:
        tables = {}
        for table in ("works", "terms", "cases", "evidences", "passages"):
            try:
                tables[table] = int(connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])
            except sqlite3.Error:
                tables[table] = None
        return {"exists": True, "database_type": "SQLite", "table_counts": tables}
    finally:
        connection.close()


def load_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return value if isinstance(value, dict) else {}


def build_report() -> dict[str, Any]:
    canonical = [
        file_record(path, role="canonical_wang_work_markdown") | {"work_key": work_key}
        for work_key, path in CANONICAL_MARKDOWN.items()
    ]
    legacy = [
        file_record(path, role="legacy_machine_route_input") | {"name": name}
        for name, path in LEGACY_ROUTE.items()
    ]
    ai_files = (
        [file_record(path, role="legacy_ai_json") for path in sorted(AI_JSON_DIR.glob("*.json"))]
        if AI_JSON_DIR.is_dir()
        else []
    )
    full_files = (
        [
            file_record(path, role="legacy_full_json_context")
            for path in sorted(FULL_JSON_DIR.glob("*.json"))
            if path.name != "_report.json"
        ]
        if FULL_JSON_DIR.is_dir()
        else []
    )
    snapshots = [
        file_record(path, role="legacy_website_derived_snapshot") | {"name": name}
        for name, path in WEBSITE_SNAPSHOTS.items()
    ]
    possible_mysql_files = discover_mysql_named_files()
    mysql_named = [
        item for item in possible_mysql_files if item["classification"] == "mysql_named_artifact"
    ]
    dump_like = [
        item for item in possible_mysql_files if item["classification"] == "schema_or_dump_extension_only"
    ]
    unified = load_json(V2_ROOT / "data/real_runs/unified_ingress_report.json")
    validation = load_json(V2_ROOT / "data/real_runs/v2_validation_report.json")
    audit = load_json(V2_ROOT / "data/real_runs/legacy_dictionary_field_audit.json")

    return {
        "report_version": "source_inventory.v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "scope": {
            "project_root": PROJECT_ROOT.resolve().as_posix(),
            "read_only": True,
            "external_or_unmounted_sources": "not assessed; provide a path to add them",
        },
        "canonical_wang_markdown": canonical,
        "legacy_machine_route": {
            "chain": [
                "02-数据库/main/source.txt",
                "02-数据库/main/parser.py",
                "02-数据库/main/importer.py",
                "02-数据库/data/dictionary.db",
            ],
            "files": legacy,
            "dictionary_db_observed": sqlite_counts(LEGACY_ROUTE["dictionary_db"]),
        },
        "legacy_ai_json": {
            "directory": AI_JSON_DIR.resolve().relative_to(PROJECT_ROOT.resolve()).as_posix(),
            "files": ai_files,
            "file_count": len(ai_files),
            "reported_case_count": ((unified.get("legacy_ai_json_route") or {}).get("summary") or {}).get("case_count"),
            "full_json_context": {
                "directory": FULL_JSON_DIR.resolve().relative_to(PROJECT_ROOT.resolve()).as_posix(),
                "files": full_files,
                "file_count": len(full_files),
                "reported_matches": ((unified.get("legacy_ai_json_route") or {}).get("summary") or {}).get("full_json_context_counts", {}),
                "boundary": "migration clue only; never canonical evidence or gold",
            },
        },
        "legacy_website_snapshots": snapshots,
        "mysql10_snapshot_search": {
            "status": "not_found_in_project_tree" if not mysql_named else "mysql_named_files_found_needs_inspection",
            "searched_roots": [PROJECT_ROOT.resolve().as_posix()],
            "filename_rule": "case-insensitive mysql in filename; plus .sql/.dump/.bak for manual classification",
            "mysql_named_files": mysql_named,
            "schema_or_dump_extension_files": dump_like,
            "conclusion": (
                "No file named as a MySQL/MySQL10 artifact was found in the current project tree. "
                "The present old machine database is SQLite dictionary.db; website JSON snapshots are derived data."
                if not mysql_named
                else "A MySQL-named file exists and must be inspected before claiming it is a MySQL10 snapshot."
            ),
        },
        "actual_v2_use": {
            "database": V2_DATABASE.resolve().relative_to(PROJECT_ROOT.resolve()).as_posix(),
            "counts": validation.get("counts", {}),
            "legacy_inventory_coverage": (audit.get("v2_representation") or {}).get("legacy_inventory_coverage", {}),
            "route_counts": {
                "legacy_ai_json_cases": ((unified.get("legacy_ai_json_route") or {}).get("summary") or {}).get("case_count"),
                "legacy_dictionary_cases": ((unified.get("legacy_dictionary_db_route") or {}).get("case_count")),
                "original_markdown_candidates": ((unified.get("original_markdown_route") or {}).get("candidate_count")),
            },
            "canonical_hash_policy": {
                "dushu_active": "1460a906825998bf8a4bf3c51d4525fe19b8b79f377fb6d25ccdad4dc698e19e",
                "dushu_historical_superseded": "1534084959961a160ddc93b5d7523ec2565bb01f0c079523f53442ef61fa37b2",
            },
        },
        "interpretation": {
            "used_now": [
                "old SQLite dictionary.db inventory and relationships",
                "source.txt legacy passages and legacy derived evidence passages",
                "three legacy AI JSON files plus full JSON context where available",
                "four canonical Wang Markdown files and their passages/candidates",
                "website snapshots only as legacy derived display artifacts, not canonical input",
            ],
            "not_available": [
                "an independently identifiable MySQL10 runtime or dump in this project tree",
            ],
            "next_import_condition": "If a MySQL10 snapshot is supplied by path, inventory it as a new source and compare fields before migration; do not merge it into dictionary.db silently.",
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    report = build_report()
    args.output.resolve().parent.mkdir(parents=True, exist_ok=True)
    args.output.resolve().write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"ok": True, "output": str(args.output), "report_version": report["report_version"]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
