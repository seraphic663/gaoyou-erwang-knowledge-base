"""Append selected case Markdown to JSONL and import it without hashes or copies."""
from __future__ import annotations

import argparse
import importlib.util
import json
import re
import sqlite3
import sys
from collections import Counter, OrderedDict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[3]
BASE = ROOT / "data" / "D-标注"
JSONL = BASE / "04-案例JSONL/manual_annotation_cases.annotation_case.v1.candidates.jsonl"
REPORT = BASE / "04-案例JSONL/manual_annotation_conversion_report.json"
DATABASE = BASE / "05-数据库/annotations.db"


STEP_FIELDS = (
    ("problem_discovery", "发疑"),
    ("research_question", "立论"),
    ("evidence_collection", "取证"),
    ("reasoning", "释理"),
    ("conclusion", "结论"),
)

EVIDENCE_ROLE = "从标注 Markdown 的引文中自动抽取；底本和版本未核。"


def module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    result = importlib.util.module_from_spec(spec)
    sys.modules[name] = result
    spec.loader.exec_module(result)
    return result



def json_text(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))

def read_json(raw: str | None) -> Any:
    try:
        return json.loads(raw or "")
    except (TypeError, json.JSONDecodeError):
        return {}

def existing_case_keys(conn: sqlite3.Connection) -> dict[str, int]:
    result: dict[str, int] = {}
    for case_id, raw_case_json in conn.execute(
        "SELECT id, raw_case_json FROM annotation_cases"
    ):
        raw = read_json(raw_case_json)
        for key in (
            raw.get("manual_case_key"),
            raw.get("case_id"),
            (raw.get("annotation_case_v1") or {}).get("case_id"),
        ):
            if key:
                result[str(key)] = int(case_id)
    return result

def archive_path(
    candidate: dict[str, Any], workspace_root: Path, archive_dir: Path
) -> tuple[Path, str]:
    migration = candidate.get("_migration") or {}
    raw_path = str(migration.get("archive_markdown_file") or "").replace("\\", "/")
    if not raw_path:
        raise RuntimeError(f"{candidate['case_id']} has no archive_markdown_file")
    candidate_path = Path(raw_path)
    if candidate_path.is_absolute():
        resolved = candidate_path
    else:
        resolved = workspace_root / Path(raw_path)
    if not resolved.is_file():
        resolved = archive_dir / Path(raw_path).name
    if not resolved.is_file():
        raise FileNotFoundError(
            f"{candidate['case_id']} archive source not found: {raw_path}"
        )
    try:
        relative = resolved.relative_to(workspace_root).as_posix()
    except ValueError:
        relative = raw_path
    return resolved, relative

def source_document_id(
    conn: sqlite3.Connection,
    candidate: dict[str, Any],
    workspace_root: Path,
    archive_dir: Path,
) -> tuple[int, bool]:
    resolved, relative = archive_path(candidate, workspace_root, archive_dir)
    source_name = resolved.name
    existing = conn.execute(
        "SELECT id FROM source_documents WHERE source_file_name=?",
        (source_name,),
    ).fetchone()
    if existing:
        return int(existing[0]), False

    lines = resolved.read_text(encoding="utf-8").splitlines()
    conn.execute(
        """
        INSERT INTO source_documents(
            source_file_name, source_file_path, full_json_file, ai_json_file,
            doc_type, paragraph_count, comment_count, anchored_comment_count
        ) VALUES(?,?,?,?,?,?,?,?)
        """,
        (
            source_name,
            relative,
            None,
            None,
            "markdown_manual_annotation",
            sum(bool(line.strip()) for line in lines),
            0,
            0,
        ),
    )
    row = conn.execute(
        "SELECT id FROM source_documents WHERE source_file_name=?",
        (source_name,),
    ).fetchone()
    if not row:
        raise RuntimeError(f"source document insert did not resolve: {source_name}")
    return int(row[0]), True

def evidence_work(item: dict[str, Any], candidate: dict[str, Any]) -> str:
    context = str(item.get("citation_context") or "")
    match = re.search(r"《([^》]+)》", context)
    if match:
        return match.group(1)
    return str(item.get("source_work") or candidate.get("source_work") or "")

def method_tags(candidate: dict[str, Any]) -> list[str]:
    tags: list[str] = []
    for item in candidate.get("term_relations") or []:
        relation = str(item.get("relation_type") or "").strip()
        if relation and relation not in tags:
            tags.append(relation)
    return tags

def first_nonempty(candidate: dict[str, Any], *keys: str) -> str:
    for key in keys:
        value = candidate.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""

def candidate_case_row(
    candidate: dict[str, Any],
    source_id: int,
    source_jsonl_relative: str,
    source_jsonl_sha256: str,
) -> tuple[tuple[Any, ...], dict[str, Any]]:
    case_id = str(candidate["case_id"])
    short_id = case_id.removeprefix("manual_md:")
    migration = candidate.get("_migration") or {}
    target_scope = candidate.get("target_scope") or {}
    target_work = first_nonempty(
        candidate,
        "target_work",
    ) or first_nonempty(
        migration,
        "target_label_from_filename",
    )
    claim = first_nonempty(
        candidate.get("method_profile") or {},
        "claim_text",
    ) or first_nonempty(candidate, "research_question", "reasoning", "conclusion")
    problem = first_nonempty(candidate, "problem_discovery")
    conclusion = first_nonempty(candidate, "conclusion") or claim
    raw_case = OrderedDict(
        [
            ("annotation_case_v1", candidate),
            ("archive_markdown_sha256", migration.get("archive_markdown_sha256")),
            (
                "legacy_projection",
                {
                    "certainty": "待核",
                    "evidence_quotes_unverified": True,
                    "status": "草稿",
                    "target_scope_status": target_scope.get("status")
                    or "candidate_only",
                    "target_work_raw_label": migration.get("target_label_from_filename")
                    or target_work,
                },
            ),
            ("manual_case_key", case_id),
            ("source_jsonl", source_jsonl_relative),
            ("source_jsonl_sha256", source_jsonl_sha256),
            (
                "source_markdown_sha256",
                migration.get("source_markdown_sha256")
                or migration.get("source_sha256"),
            ),
        ]
    )
    row = (
        source_id,
        f"{short_id} · {candidate.get('case_title') or short_id}",
        candidate.get("source_work") or "",
        target_work,
        candidate.get("target_text") or candidate.get("case_title") or short_id,
        problem or None,
        claim or None,
        json_text(method_tags(candidate)),
        conclusion,
        "待核",
        "草稿",
        json_text(raw_case),
    )
    return row, raw_case

def insert_children(
    conn: sqlite3.Connection, case_db_id: int, candidate: dict[str, Any], case_id: str
) -> tuple[int, int, int]:
    term_count = 0
    evidence_count = 0
    step_count = 0

    for index, item in enumerate(candidate.get("term_relations") or []):
        relation = dict(item)
        conn.execute(
            """
            INSERT INTO annotation_terms(
                case_id, term, term_type, relation_type, related_term, note,
                source_paragraph_indexes_json, source_comment_ids_json, raw_term_json
            ) VALUES(?,?,?,?,?,?,?,?,?)
            """,
            (
                case_db_id,
                relation.get("source_term") or "",
                "字词",
                relation.get("relation_type") or "",
                relation.get("target_term") or "",
                relation.get("relation_note")
                or relation.get("_source_line")
                or "",
                "[]",
                "[]",
                json_text(
                    {
                        "manual_case_key": case_id,
                        "term_index": index,
                        "v2_term_relation": relation,
                    }
                ),
            ),
        )
        term_count += 1

    for index, item in enumerate(candidate.get("evidences") or []):
        evidence = dict(item)
        raw_evidence = {
            "evidence_index": index,
            "manual_case_key": case_id,
            "quote_check": evidence.get("quote_check") or "unchecked",
            "source_resolution": evidence.get("source_resolution")
            or "external_source_pending",
            "v2_evidence": evidence,
        }
        conn.execute(
            """
            INSERT INTO annotation_evidences(
                case_id, evidence_type, work, quote, role, term,
                source_paragraph_indexes_json, source_comment_ids_json, raw_evidence_json
            ) VALUES(?,?,?,?,?,?,?,?,?)
            """,
            (
                case_db_id,
                "书证",
                evidence_work(evidence, candidate),
                evidence.get("quote") or "",
                evidence.get("evidence_role") or EVIDENCE_ROLE,
                "",
                "[]",
                "[]",
                json_text(raw_evidence),
            ),
        )
        evidence_count += 1

    source_spans = (candidate.get("_migration") or {}).get("source_section_spans") or {}
    for field_name, step_type in STEP_FIELDS:
        text = candidate.get(field_name)
        if not isinstance(text, str) or not text.strip():
            continue
        raw_step = {
            "field_name": field_name,
            "manual_case_key": case_id,
            "source_spans": source_spans.get("conclusion", [])
            if field_name == "conclusion"
            else [],
            "text": text.strip(),
        }
        conn.execute(
            """
            INSERT INTO annotation_process_steps(
                case_id, step_order, step_type, text,
                source_paragraph_indexes_json, source_comment_ids_json, raw_step_json
            ) VALUES(?,?,?,?,?,?,?)
            """,
            (
                case_db_id,
                step_count + 1,
                step_type,
                text.strip(),
                "[]",
                "[]",
                json_text(raw_step),
            ),
        )
        step_count += 1
    return term_count, evidence_count, step_count


def run(phase: str, ids: list[str]) -> None:
    selected_ids = set(ids)
    records = [json.loads(line) for line in JSONL.read_text(encoding="utf-8").splitlines() if line.strip()]
    if phase == "convert":
        converter = module("manual_converter", ROOT / "v2/scripts/convert_manual_annotation_markdown.py")
        sys.path.insert(0, str(ROOT / "v2/src"))
        by_work, existing_v2_ids = converter.load_canonical_passages(converter.DEFAULT_DATABASE)
        existing = {row["case_id"] for row in records}
        reports = []
        additions = []
        for case_id in ids:
            matches = list((BASE / "03-案例Markdown").glob(f"{case_id}-*.md"))
            if len(matches) != 1:
                raise RuntimeError(f"{case_id}: expected one case Markdown, found {len(matches)}")
            if f"manual_md:{case_id}" in existing:
                continue
            record, report = converter.build_record(matches[0], BASE / "03-案例Markdown", BASE / "02-文档Markdown", by_work, existing_v2_ids, compute_hashes=False)
            if report["schema_errors"]:
                raise RuntimeError(f"{case_id}: {report['schema_errors']}")
            additions.append(record)
            reports.append(report)
        with JSONL.open("a", encoding="utf-8", newline="\n") as handle:
            for record in additions:
                handle.write(json.dumps(record, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n")
        report_document = json.loads(REPORT.read_text(encoding="utf-8"))
        report_document["cases"].extend(reports)
        report_document["case_count"] = len(records) + len(additions)
        all_reports = report_document["cases"]
        summary = report_document["summary"]
        summary.update({
            "schema_valid_cases": sum(r["schema_valid"] for r in all_reports),
            "source_passage_matched_cases": sum(bool(r["source_passage_match"].get("passage_id")) for r in all_reports),
            "cases_with_evidence_quotes": sum(r["evidence_quote_count"] > 0 for r in all_reports),
            "all_evidence_quotes_unverified": sum(r["evidence_quote_count"] for r in all_reports),
            "word_comment_count": sum(r["word_comments_count"] for r in all_reports),
            "term_relation_placeholder_cases": sum(r["term_relation_placeholder"] for r in all_reports),
            "source_passage_ambiguous_cases": sum(r["source_passage_match"].get("status") == "ambiguous" for r in all_reports),
            "cases_with_unparsed_evidence_lines": sum(r["unparsed_evidence_line_count"] > 0 for r in all_reports),
            "existing_case_id_collisions": sum(r["case_id_collision"] for r in all_reports),
            "draft_ingest_candidates": sum(r["draft_ingest_candidate"] for r in all_reports),
            "blocker_counts": dict(sorted(Counter(flag for r in all_reports for flag in r["blockers"]).items())),
        })
        REPORT.write_text(json.dumps(report_document, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(json.dumps({"appended": len(additions), "total": len(records) + len(additions), "cases": [{"id": r["case_id"], "matched": r["source_passage_match"].get("passage_id"), "evidences": r["evidence_quote_count"], "missing_process": r["process_fields_missing"], "conclusion": r["blockers"]} for r in reports]}, ensure_ascii=False))
        return

    chosen = [row for row in records if row["case_id"].removeprefix("manual_md:") in selected_ids]
    if {row["case_id"].removeprefix("manual_md:") for row in chosen} != selected_ids:
        raise RuntimeError("Selected JSONL case set is incomplete")
    inserted = []
    with sqlite3.connect(DATABASE) as conn:
        conn.execute("PRAGMA foreign_keys=ON")
        existing = existing_case_keys(conn)
        for candidate in chosen:
            key = candidate["case_id"]
            if key in existing:
                continue
            source_id, _ = source_document_id(conn, candidate, ROOT, BASE / "02-文档Markdown")
            row, _ = candidate_case_row(candidate, source_id, JSONL.relative_to(ROOT).as_posix(), None)
            cursor = conn.execute("""INSERT INTO annotation_cases(source_document_id,case_title,source_work,target_work,target_text,problem,claim,method_tags_json,conclusion,certainty,status,raw_case_json) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""", row)
            insert_children(conn, cursor.lastrowid, candidate, key)
            existing[key] = cursor.lastrowid
            inserted.append(key)
        for key, value in {
            "manual_import_source": JSONL.relative_to(ROOT).as_posix(),
            "manual_import_source_case_count": str(len(records)),
            "manual_imported_at_utc": datetime.now(timezone.utc).isoformat(),
            "manual_import_status_mapping": "machine draft + human pending -> 草稿/待核",
        }.items():
            conn.execute("INSERT INTO meta(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", (key, value))
        conn.execute("DELETE FROM meta WHERE key='manual_import_source_sha256'")
        if conn.execute("PRAGMA foreign_key_check").fetchone() is not None:
            raise RuntimeError("Foreign key error; import rolled back")
        counts = {table: conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] for table in ["source_documents", "annotation_cases", "annotation_terms", "annotation_evidences", "annotation_process_steps"]}
    print(json.dumps({"inserted": inserted, "counts": counts}, ensure_ascii=False))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("phase", choices=["convert", "import"])
    parser.add_argument("--ids", nargs="+", required=True)
    args = parser.parse_args()
    run(args.phase, args.ids)
