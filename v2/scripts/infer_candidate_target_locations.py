#!/usr/bin/env python3
"""Infer conservative target-work/location candidates from original text.

This pass is deliberately below the human-resolution boundary.  It extracts
explicit book-title marks from each original candidate, maps only exact title
variants to the four canonical work keys, and searches the canonical passage
corpus for the cited label or an exact quoted fragment.  It never writes
annotation_cases.target_work or target_passage_id and never changes review or
gold state.
"""

from __future__ import annotations

import argparse
import json
import re
import sqlite3
import unicodedata
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


V2_ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = V2_ROOT.parent
DEFAULT_DATABASE = V2_ROOT / "data/real_runs/annotation_v2.db"
DEFAULT_REPORT = V2_ROOT / "data/real_runs/candidate_target_location_report.json"

BOOK_TITLE_RE = re.compile(r"《[^》]{1,120}》")
QUOTE_PATTERNS = (
    re.compile(r"「([^」]{2,240})」"),
    re.compile(r"『([^』]{2,240})』"),
    re.compile(r"“([^”]{2,240})”"),
    re.compile(r"‘([^’]{2,240})’"),
)
CANONICAL_TITLES = {
    "读书杂志": "dushu_zazhi",
    "讀書雜志": "dushu_zazhi",
    "讀書雜誌": "dushu_zazhi",
    "广雅疏证": "guangya_shuzheng",
    "廣雅疏證": "guangya_shuzheng",
    "经传释词": "jingzhuan_shici",
    "經傳釋詞": "jingzhuan_shici",
    "经义述闻": "jingyi_shuwen",
    "經義述聞": "jingyi_shuwen",
}


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def relative_path(value: str | Path) -> str:
    path = Path(value)
    try:
        return path.resolve().relative_to(PROJECT_ROOT.resolve()).as_posix()
    except ValueError:
        return str(path)


def compact(value: str) -> str:
    return "".join(str(value or "").split())


def normalize_label(value: str) -> str:
    text = unicodedata.normalize("NFKC", str(value or "")).strip().strip("《》")
    return " ".join(text.split())


def canonical_work_for_label(normalized_label: str) -> tuple[str | None, str]:
    """Map only an exact four-work title or an explicit title suffix."""

    for title, work_key in CANONICAL_TITLES.items():
        if normalized_label == title:
            return work_key, "explicit_book_title_mark_canonical_work"
        if normalized_label.startswith(title) and normalized_label[len(title) :].startswith(
            ("·", "・", "-", "—", " ")
        ):
            return work_key, "explicit_book_title_mark_canonical_work_with_scope"
    return None, "explicit_book_title_mark"


def extract_book_labels(text: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for match in BOOK_TITLE_RE.finditer(text or ""):
        raw = match.group(0)
        inner = raw[1:-1]
        normalized = normalize_label(inner)
        if not normalized:
            continue
        canonical_key, label_match = canonical_work_for_label(normalized)
        # A chapter/section suffix is retained as a candidate label but is not
        # silently mapped to a whole canonical work.
        identity_status = "canonical" if canonical_key else "candidate"
        rows.append(
            {
                "raw_label": raw,
                "normalized_label": normalized,
                "candidate_work_key": canonical_key,
                "work_identity_status": identity_status,
                "label_start_char": match.start(),
                "label_end_char": match.end(),
                "label_match": label_match,
            }
        )
    return rows


def extract_quote_fragments(text: str) -> list[str]:
    fragments: list[str] = []
    for pattern in QUOTE_PATTERNS:
        for match in pattern.findall(text or ""):
            value = compact(match)
            if len(value) >= 6 and value not in fragments:
                fragments.append(value)
    return fragments[:12]


def build_location_candidates(database_path: Path) -> dict[str, Any]:
    connection = sqlite3.connect(database_path)
    connection.row_factory = sqlite3.Row
    try:
        canonical_passages = connection.execute(
            """
            SELECT p.passage_id, p.work_key, p.plain_text, p.raw_text,
                   p.md_line_start, p.md_line_end, p.document_title,
                   p.section_title, p.entry_title, sd.source_file
            FROM passages p
            JOIN source_documents sd ON sd.source_document_id=p.source_document_id
            WHERE sd.canonical_status='canonical_active'
            ORDER BY p.work_key, p.local_ordinal
            """
        ).fetchall()
        passages_by_work: dict[str, list[sqlite3.Row]] = {}
        for row in canonical_passages:
            passages_by_work.setdefault(row["work_key"], []).append(row)
        cases = connection.execute(
            """
            SELECT ci.candidate_id, ci.source_work, ci.candidate_text,
                   ci.passage_id, ci.output_case_id, ac.case_id
            FROM candidate_items ci
            LEFT JOIN annotation_cases ac ON ac.case_id=ci.output_case_id
            WHERE ci.origin='original_markdown_machine_extraction'
              AND ci.output_case_id IS NOT NULL
            ORDER BY ci.candidate_id
            """
        ).fetchall()

        connection.execute("BEGIN IMMEDIATE")
        connection.execute("DELETE FROM candidate_target_locations")
        counts: Counter[str] = Counter()
        label_counts: Counter[str] = Counter()
        candidate_rows = 0
        for candidate in cases:
            candidate_rows += 1
            text = candidate["candidate_text"] or ""
            labels = extract_book_labels(text)
            quotes = extract_quote_fragments(text)
            for label in labels:
                candidate_key = label["candidate_work_key"]
                search_passages = passages_by_work.get(candidate_key, []) if candidate_key else []
                fragment_matches: list[sqlite3.Row] = []
                for fragment in quotes:
                    for passage in search_passages:
                        if fragment in (passage["plain_text"] or "") or fragment in (passage["raw_text"] or ""):
                            fragment_matches.append(passage)
                    if fragment_matches:
                        break
                unique_matches = {row["passage_id"]: row for row in fragment_matches}
                other_matches = {
                    passage_id: passage
                    for passage_id, passage in unique_matches.items()
                    if passage_id != candidate["passage_id"]
                }
                if not candidate_key:
                    match_status = "not_searched"
                    target_candidate = None
                elif not other_matches and unique_matches:
                    match_status = "same_source_only"
                    target_candidate = None
                elif not other_matches:
                    match_status = "no_match"
                    target_candidate = None
                elif len(other_matches) == 1:
                    match_status = "candidate_match"
                    target_candidate = next(iter(other_matches.values()))
                else:
                    match_status = "candidate_match"
                    target_candidate = None
                candidate_target_id = (
                    f"candidate-target:{candidate['candidate_id']}:"
                    f"{label['label_start_char']}:{label['label_end_char']}"
                )
                provenance = {
                    "inference_version": "candidate_target_location.v1",
                    "candidate_id": candidate["candidate_id"],
                    "case_id": candidate["case_id"],
                    "source_passage_id": candidate["passage_id"],
                    "source_file": "v2/data/real_runs/unified_ingress/original_text_candidate_items.candidate_item.v1.jsonl",
                    "source_quote_fragments": quotes,
                    "canonical_search_work_key": candidate_key,
                    "canonical_search_policy": "exact compact quote fragment in canonical raw/plain passage; no semantic inference",
                    "target_resolution": "candidate_only",
                }
                connection.execute(
                    """
                    INSERT INTO candidate_target_locations(
                        candidate_target_id, candidate_id, case_id, raw_label,
                        normalized_label, candidate_work_key, work_identity_status,
                        label_start_char, label_end_char, label_match,
                        source_passage_id, target_passage_candidate_id,
                        target_passage_match_status, target_passage_candidate_count,
                        evidence_indexes_json, machine_status, human_status,
                        provenance_json, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'candidate_only', 'pending', ?, ?, ?)
                    """,
                    (
                        candidate_target_id,
                        candidate["candidate_id"],
                        candidate["case_id"],
                        label["raw_label"],
                        label["normalized_label"],
                        candidate_key,
                        label["work_identity_status"],
                        label["label_start_char"],
                        label["label_end_char"],
                        label["label_match"],
                        candidate["passage_id"],
                        target_candidate["passage_id"] if target_candidate else None,
                        match_status,
                        len(unique_matches),
                        "[]",
                        json.dumps(provenance, ensure_ascii=False, sort_keys=True),
                        now(),
                        now(),
                    ),
                )
                counts["rows"] += 1
                counts[f"identity:{label['work_identity_status']}"] += 1
                counts[f"passage:{match_status}"] += 1
                label_counts[label["normalized_label"]] += 1
        connection.commit()
        result = {
            "report_version": "candidate_target_location.v1",
            "generated_at": now(),
            "database": relative_path(database_path),
            "policy": {
                "target_work_written": False,
                "target_passage_written": False,
                "machine_status_changed": False,
                "human_status_changed": False,
                "gold_promotion_performed": False,
                "canonical_passage_search_is_not_quote_verification": True,
            },
            "counts": {
                "candidate_rows_scanned": candidate_rows,
                "candidate_target_location_rows": counts["rows"],
                "canonical_identity_labels": counts["identity:canonical"],
                "unresolved_identity_labels": counts["identity:candidate"],
                "canonical_candidate_passage_matches": counts["passage:candidate_match"],
                "canonical_identity_without_passage_match": counts["passage:no_match"],
                "canonical_identity_same_source_only": counts["passage:same_source_only"],
                "unresolved_identity_not_searched": counts["passage:not_searched"],
                "unique_labels": len(label_counts),
            },
            "top_labels": [
                {"normalized_label": label, "count": count}
                for label, count in label_counts.most_common(100)
            ],
        }
        return result
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", type=Path, default=DEFAULT_DATABASE)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    args = parser.parse_args()
    report = build_location_candidates(args.database)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report["counts"], ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
