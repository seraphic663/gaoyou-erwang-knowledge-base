from __future__ import annotations

"""Convert the legacy machine dictionary database into the V2 work database.

This route is intentionally separate from the original-Markdown AI route. It
does not call an external model. The legacy database is opened read-only for
profiling and is mechanically re-ingested as ``annotation_case.v1`` machine
records with explicit provenance and unresolved-field boundaries.
"""

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
sys.path.insert(0, str(V2_ROOT / "src"))

from erwang_v2.database import ingest_case, ingest_legacy_catalog, ingest_passages, open_database
from erwang_v2.legacy_dictionary_adapter import load_legacy_dictionary_material


SOURCE_DATABASE = PROJECT_ROOT / "02-数据库/data/dictionary.db"
SOURCE_TEXT = PROJECT_ROOT / "02-数据库/main/source.txt"
SOURCE_PARSER = PROJECT_ROOT / "02-数据库/main/parser.py"
TARGET_DATABASE = V2_ROOT / "data/real_runs/annotation_v2.db"
OUTPUT_DIR = V2_ROOT / "data/real_runs/legacy_machine_conversion"
REPORT_FILE = V2_ROOT / "data/real_runs/legacy_machine_conversion_report.json"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _write_jsonl(path: Path, values: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for value in values:
            handle.write(json.dumps(value, ensure_ascii=False, separators=(",", ":")) + "\n")


def _source_profile(connection: sqlite3.Connection) -> dict[str, Any]:
    counts = {
        table: connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        for table in ("works", "terms", "cases", "evidences", "passages")
    }
    counts.update(
        {
            "cases_without_source_passage": connection.execute(
                "SELECT COUNT(*) FROM cases WHERE erwang_passage_id IS NULL"
            ).fetchone()[0],
            "cases_without_target_passage": connection.execute(
                "SELECT COUNT(*) FROM cases WHERE target_passage_id IS NULL"
            ).fetchone()[0],
            "cases_without_process_text": connection.execute(
                "SELECT COUNT(*) FROM cases WHERE process_text IS NULL OR trim(process_text) = ''"
            ).fetchone()[0],
            "evidences_without_source_passage": connection.execute(
                "SELECT COUNT(*) FROM evidences WHERE source_passage_id IS NULL"
            ).fetchone()[0],
        }
    )
    term_ids: set[int] = set()
    for row in connection.execute("SELECT term_ids FROM cases"):
        try:
            values = json.loads(row[0] or "[]")
        except (TypeError, ValueError):
            values = []
        term_ids.update(int(value) for value in values if str(value).isdigit())
    all_terms = {
        int(row["id"]): row["term"]
        for row in connection.execute("SELECT id, term FROM terms")
    }
    used_work_ids = {
        int(row[0])
        for row in connection.execute(
            "SELECT DISTINCT work_id FROM evidences WHERE work_id IS NOT NULL"
        )
    }
    all_works = {
        int(row["id"]): row["title"]
        for row in connection.execute("SELECT id, title FROM works")
    }
    return {
        "counts": counts,
        "unreferenced_terms": [
            {"id": term_id, "term": all_terms[term_id]}
            for term_id in sorted(set(all_terms) - term_ids)
        ],
        "unreferenced_works": [
            {"id": work_id, "title": all_works[work_id]}
            for work_id in sorted(set(all_works) - used_work_ids)
        ],
    }


def _schema_error_count(cases: list[dict[str, Any]]) -> int:
    try:
        from jsonschema import Draft202012Validator
    except ImportError:
        return -1
    schema = json.loads(
        (V2_ROOT / "schemas/annotation_case.v1.schema.json").read_text(encoding="utf-8")
    )
    validator = Draft202012Validator(schema)
    return sum(sum(1 for _ in validator.iter_errors(case)) for case in cases)


def run_conversion(
    *,
    source_database: Path = SOURCE_DATABASE,
    source_text: Path = SOURCE_TEXT,
    source_parser: Path = SOURCE_PARSER,
    target_database: Path = TARGET_DATABASE,
    output_dir: Path = OUTPUT_DIR,
    report_path: Path = REPORT_FILE,
) -> dict[str, Any]:
    source_database = source_database.resolve()
    source_text = source_text.resolve()
    source_parser = source_parser.resolve()
    target_database = target_database.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    source_connection = sqlite3.connect(f"file:{source_database}?mode=ro", uri=True)
    source_connection.row_factory = sqlite3.Row
    try:
        source_profile = _source_profile(source_connection)
        source_integrity = source_connection.execute("PRAGMA integrity_check").fetchone()[0]
        source_foreign_keys = source_connection.execute("PRAGMA foreign_key_check").fetchall()
    finally:
        source_connection.close()

    cases, source_passages, target_passages, material = load_legacy_dictionary_material(
        source_database,
        source_text_path=source_text,
        parser_path=source_parser,
    )
    adapter_report = material["report"]
    output_jsonl = output_dir / "legacy_dictionary_cases.annotation_case.v1.jsonl"
    _write_jsonl(output_jsonl, cases)
    _write_jsonl(output_dir / "legacy_source_passages.passage.v1.jsonl", source_passages)
    _write_jsonl(output_dir / "legacy_derived_evidence_passages.passage.v1.jsonl", target_passages)

    with open_database(target_database) as connection:
        source_document_id = ingest_passages(
            connection,
            source_passages,
            source_kind="legacy_source_txt",
            metadata={
                "canonical_status": "legacy_unverified",
                "source_role": "legacy_source",
                "source_version_reason": "source.txt is upstream parser input, not an original-canonical edition",
            },
        )
        target_document_id = ingest_passages(
            connection,
            target_passages,
            source_kind="legacy_derived_quote",
            metadata={
                "canonical_status": "legacy_unverified",
                "source_role": "legacy_derived",
                "source_version_reason": "quote text was derived from dictionary.db evidence rows and is not a cited-work canonical edition",
            },
        )
        catalog_counts = ingest_legacy_catalog(
            connection,
            terms=material["catalog_terms"],
            works=material["catalog_works"],
            source_file=str(source_database.relative_to(PROJECT_ROOT)),
            source_file_sha256=material["database_sha256"],
        )
        for case in cases:
            ingest_case(connection, case, origin="legacy_dictionary_db_reprocessing")
        connection.commit()

        case_ids = {
            row[0]
            for row in connection.execute(
                "SELECT case_id FROM annotation_cases WHERE origin = 'legacy_dictionary_db_reprocessing'"
            )
        }
        expected_case_ids = {f"legacy-dictionary:{index}" for index in range(1, len(cases) + 1)}
        target_profile = {
            "cases": len(case_ids),
            "term_relations": connection.execute(
                "SELECT COUNT(*) FROM annotation_terms WHERE case_id LIKE 'legacy-dictionary:%'"
            ).fetchone()[0],
            "evidences": connection.execute(
                "SELECT COUNT(*) FROM annotation_evidences WHERE case_id LIKE 'legacy-dictionary:%'"
            ).fetchone()[0],
            "process_steps": connection.execute(
                "SELECT COUNT(*) FROM annotation_process_steps WHERE case_id LIKE 'legacy-dictionary:%'"
            ).fetchone()[0],
            "evidence_passage_links": connection.execute(
                "SELECT COUNT(*) FROM annotation_evidences WHERE case_id LIKE 'legacy-dictionary:%' AND passage_id IS NOT NULL"
            ).fetchone()[0],
            "legacy_evidence_canonical_passage_links": connection.execute(
                """
                SELECT COUNT(*)
                FROM annotation_evidences ae
                JOIN passages p ON p.passage_id = ae.passage_id
                JOIN source_documents sd ON sd.source_document_id = p.source_document_id
                WHERE ae.case_id LIKE 'legacy-dictionary:%'
                  AND sd.canonical_status = 'canonical_active'
                """
            ).fetchone()[0],
            "evidence_unchecked": connection.execute(
                "SELECT COUNT(*) FROM annotation_evidences WHERE case_id LIKE 'legacy-dictionary:%' AND quote_check = 'unchecked'"
            ).fetchone()[0],
            "case_source_passage_links": connection.execute(
                "SELECT COUNT(*) FROM annotation_cases WHERE case_id LIKE 'legacy-dictionary:%' AND source_passage_id IS NOT NULL"
            ).fetchone()[0],
            "case_target_passage_links": connection.execute(
                "SELECT COUNT(*) FROM annotation_cases WHERE case_id LIKE 'legacy-dictionary:%' AND target_passage_id IS NOT NULL"
            ).fetchone()[0],
            "process_text_count": connection.execute(
                "SELECT COUNT(*) FROM annotation_cases WHERE case_id LIKE 'legacy-dictionary:%' AND trim(process_text) <> ''"
            ).fetchone()[0],
            "complete_process_case_count": connection.execute(
                """
                SELECT COUNT(*)
                FROM annotation_cases
                WHERE case_id LIKE 'legacy-dictionary:%'
                  AND (SELECT COUNT(*) FROM annotation_process_steps ps
                       WHERE ps.case_id = annotation_cases.case_id
                         AND ps.step_text IS NOT NULL
                         AND trim(ps.step_text) <> '') = 5
                """
            ).fetchone()[0],
            "source_passage_count": connection.execute(
                "SELECT COUNT(*) FROM passages WHERE source_document_id = ?",
                (source_document_id,),
            ).fetchone()[0],
            "target_passage_count": connection.execute(
                "SELECT COUNT(*) FROM passages WHERE source_document_id = ?",
                (target_document_id,),
            ).fetchone()[0],
            "catalog_only_terms": connection.execute(
                "SELECT COUNT(*) FROM legacy_catalog_terms WHERE catalog_status = 'catalog_only'"
            ).fetchone()[0],
            "catalog_only_works": connection.execute(
                "SELECT COUNT(*) FROM legacy_catalog_works WHERE catalog_status = 'catalog_only'"
            ).fetchone()[0],
            "human_pending": connection.execute(
                "SELECT COUNT(*) FROM annotation_cases WHERE origin = 'legacy_dictionary_db_reprocessing' AND human_status = 'pending'"
            ).fetchone()[0],
            "gold": connection.execute(
                "SELECT COUNT(*) FROM annotation_cases WHERE origin = 'legacy_dictionary_db_reprocessing' AND lifecycle = 'gold'"
            ).fetchone()[0],
        }
        target_integrity = connection.execute("PRAGMA integrity_check").fetchone()[0]
        target_foreign_keys = connection.execute("PRAGMA foreign_key_check").fetchall()

    source_counts = source_profile["counts"]
    checks = {
        "source_integrity": source_integrity == "ok",
        "source_foreign_keys": not source_foreign_keys,
        "case_count": target_profile["cases"] == source_counts["cases"],
        "case_id_coverage": case_ids == expected_case_ids,
        "term_relation_count": target_profile["term_relations"] == adapter_report["term_relation_count"],
        "evidence_count": target_profile["evidences"] == source_counts["evidences"],
        "five_process_rows_per_case": target_profile["process_steps"] == source_counts["cases"] * 5,
        "source_passage_count": target_profile["source_passage_count"] == source_counts["cases"],
        "target_passage_count": target_profile["target_passage_count"] == source_counts["evidences"],
        "case_source_passage_links": target_profile["case_source_passage_links"] == source_counts["cases"],
        "case_target_passage_links": target_profile["case_target_passage_links"] == source_counts["cases"],
        "process_text_count": target_profile["process_text_count"] == source_counts["cases"],
        "complete_process_case_count": target_profile["complete_process_case_count"] == source_counts["cases"],
        "catalog_only_term_count": target_profile["catalog_only_terms"] == len(material["catalog_terms"]),
        "catalog_only_work_count": target_profile["catalog_only_works"] == len(material["catalog_works"]),
        "schema_error_count": _schema_error_count(cases) == 0,
        "target_integrity": target_integrity == "ok",
        "target_foreign_keys": not target_foreign_keys,
        "no_unverified_passage_claim": (
            target_profile["legacy_evidence_canonical_passage_links"] == 0
            and target_profile["evidence_passage_links"] == source_counts["evidences"]
        ),
        "no_gold_promotion": target_profile["gold"] == 0,
        "all_human_pending": target_profile["human_pending"] == source_counts["cases"],
    }
    report = {
        "report_version": "legacy-machine-conversion.v2",
        "generated_at": _now(),
        "status": "completed_with_explicit_boundaries" if all(checks.values()) else "completed_with_failures",
        "source_lineage": {
            "database": "02-数据库/data/dictionary.db",
            "database_sha256": _sha256(source_database),
            "upstream_text": "02-数据库/main/source.txt",
            "upstream_text_sha256": _sha256(source_text),
            "parser": "02-数据库/main/parser.py",
            "parser_sha256": _sha256(source_parser),
            "importer": "02-数据库/main/importer.py",
            "source_kind": "legacy_machine_parser_output",
            "ai_model_called": False,
        },
        "conversion": {
            "origin": "legacy_dictionary_db_reprocessing",
            "transformation_kind": "machine_output_reprocessing",
            "output_schema": "annotation_case.v1",
            "output_jsonl": str(output_jsonl.relative_to(PROJECT_ROOT)),
            "source_passage_jsonl": str((output_dir / "legacy_source_passages.passage.v1.jsonl").relative_to(PROJECT_ROOT)),
            "target_passage_jsonl": str((output_dir / "legacy_derived_evidence_passages.passage.v1.jsonl").relative_to(PROJECT_ROOT)),
            "field_policy": "mechanical_mapping plus traceable legacy source/derived passage materialization; no canonical quote or semantic conclusion inference",
            "source_records_are_not_human_gold": True,
            "source_document_ids": {
                "legacy_source": source_document_id,
                "legacy_derived": target_document_id,
            },
            "catalog_counts": catalog_counts,
        },
        "source_profile": source_profile,
        "adapter_profile": adapter_report,
        "target_profile": target_profile,
        "checks": checks,
        "unresolved_boundaries": {
            "all_source_cases_have_no_erwang_passage": source_counts["cases_without_source_passage"] == source_counts["cases"],
            "all_source_cases_have_no_target_passage": source_counts["cases_without_target_passage"] == source_counts["cases"],
            "all_source_cases_have_no_process_text": source_counts["cases_without_process_text"] == source_counts["cases"],
            "all_source_evidences_have_no_passage": source_counts["evidences_without_source_passage"] == source_counts["evidences"],
            "source_txt_passages_are_legacy_unverified": True,
            "derived_quote_passages_are_not_canonical": True,
            "all_legacy_evidence_quote_checks_remain_unchecked": target_profile["evidence_unchecked"] == source_counts["evidences"],
            "unreferenced_terms_preserved_in_report_only": source_profile["unreferenced_terms"],
            "unreferenced_works_preserved_in_report_only": source_profile["unreferenced_works"],
        },
    }
    _write_json(report_path, report)
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description="Convert dictionary.db machine output into V2.")
    parser.add_argument("--source-database", type=Path, default=SOURCE_DATABASE)
    parser.add_argument("--source-text", type=Path, default=SOURCE_TEXT)
    parser.add_argument("--source-parser", type=Path, default=SOURCE_PARSER)
    parser.add_argument("--target-database", type=Path, default=TARGET_DATABASE)
    parser.add_argument("--output-dir", type=Path, default=OUTPUT_DIR)
    parser.add_argument("--report", type=Path, default=REPORT_FILE)
    args = parser.parse_args()
    report = run_conversion(
        source_database=args.source_database,
        source_text=args.source_text,
        source_parser=args.source_parser,
        target_database=args.target_database,
        output_dir=args.output_dir,
        report_path=args.report,
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["status"] == "completed_with_explicit_boundaries" else 1


if __name__ == "__main__":
    raise SystemExit(main())
