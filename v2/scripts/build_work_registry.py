#!/usr/bin/env python3
"""Build the reversible V2 work-identity and alias registry.

This is a deterministic registry pass, not an academic disambiguation pass.
Formatting-equivalent labels may be attached to a known work key.  Labels that
need semantic or edition-level judgment receive an explicit candidate/unknown
identity and remain unresolved in the case data.
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
DEFAULT_REPORT = V2_ROOT / "data/real_runs/work_registry_report.json"

sys.path.insert(0, str(V2_ROOT / "src"))
from erwang_v2.database import open_database  # noqa: E402

CANONICAL_WORKS: dict[str, dict[str, str]] = {
    "dushu_zazhi": {"title": "读书杂志", "author": "王念孙", "type": "王氏四种"},
    "guangya_shuzheng": {"title": "广雅疏证", "author": "王念孙", "type": "王氏四种"},
    "jingzhuan_shici": {"title": "经传释词", "author": "王引之", "type": "王氏四种"},
    "jingyi_shuwen": {"title": "经义述闻", "author": "王引之", "type": "王氏四种"},
}

LEGACY_SOURCE_TITLES = {
    "legacy_dictionary_db_evidence": "旧 dictionary.db 证据派生文本",
    "legacy_guangya_shuzheng_source": "旧 source.txt 机器源文本",
}


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def normalize_label(value: str | None) -> str:
    text = (value or "").strip().strip("《》")
    return " ".join(text.split())


def identity_key(prefix: str, normalized_label: str) -> str:
    return f"{prefix}:{normalized_label}"


def relative_path(value: str | None) -> str | None:
    if not value:
        return None
    path = Path(value)
    try:
        return path.resolve().relative_to(PROJECT_ROOT.resolve()).as_posix()
    except ValueError:
        return str(path)


def json_text(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


class RegistryBuilder:
    def __init__(self, connection: sqlite3.Connection) -> None:
        self.connection = connection
        self.created_identities: set[str] = set()
        self.alias_keys: set[tuple[str, str, str, str]] = set()
        self.canonical_by_label = {
            normalize_label(config["title"]): work_key
            for work_key, config in CANONICAL_WORKS.items()
        }

    def upsert_work(
        self,
        *,
        work_key: str,
        canonical_title: str,
        identity_status: str,
        author: str | None = None,
        work_type: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        timestamp = now()
        self.connection.execute(
            """
            INSERT INTO work_registry(
                work_key, canonical_title, author, work_type, identity_status,
                metadata_json, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(work_key) DO UPDATE SET
                canonical_title = excluded.canonical_title,
                author = COALESCE(excluded.author, work_registry.author),
                work_type = COALESCE(excluded.work_type, work_registry.work_type),
                identity_status = excluded.identity_status,
                metadata_json = excluded.metadata_json,
                updated_at = excluded.updated_at
            """,
            (
                work_key,
                canonical_title,
                author,
                work_type,
                identity_status,
                json_text(metadata or {}),
                timestamp,
                timestamp,
            ),
        )
        self.created_identities.add(work_key)

    def alias(
        self,
        *,
        work_key: str,
        raw_label: str,
        mapping_status: str,
        mapping_method: str,
        confidence: str,
        source_file: str | None = None,
        source_record_id: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> None:
        raw = str(raw_label or "").strip()
        normalized = normalize_label(raw)
        if not raw or not normalized:
            return
        key = (work_key, raw, mapping_method, source_record_id)
        if key in self.alias_keys:
            return
        self.alias_keys.add(key)
        timestamp = now()
        self.connection.execute(
            """
            INSERT INTO work_aliases(
                work_key, raw_label, normalized_label, mapping_status,
                mapping_method, confidence, source_file, source_record_id,
                metadata_json, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(work_key, raw_label, mapping_method, source_record_id)
            DO UPDATE SET
                normalized_label = excluded.normalized_label,
                mapping_status = excluded.mapping_status,
                confidence = excluded.confidence,
                source_file = excluded.source_file,
                metadata_json = excluded.metadata_json,
                updated_at = excluded.updated_at
            """,
            (
                work_key,
                raw,
                normalized,
                mapping_status,
                mapping_method,
                confidence,
                source_file,
                source_record_id,
                json_text(metadata or {}),
                timestamp,
                timestamp,
            ),
        )

    def ensure_unknown_identity(self, raw_label: str, *, prefix: str = "unknown") -> str:
        normalized = normalize_label(raw_label)
        work_key = identity_key(prefix, normalized or "empty")
        self.upsert_work(
            work_key=work_key,
            canonical_title=raw_label or "未命名著作",
            identity_status="unknown",
            work_type="unresolved_label",
            metadata={"raw_label": raw_label, "semantic_resolution": "not_performed"},
        )
        return work_key

    def resolve_label(self, raw_label: str | None) -> tuple[str | None, str, str, str]:
        raw = str(raw_label or "").strip()
        normalized = normalize_label(raw)
        if not normalized:
            return None, "unresolved", "empty_label", "none"
        canonical_key = self.canonical_by_label.get(normalized)
        if canonical_key:
            return canonical_key, "canonical", "exact_title_after_format_normalization", "high"
        return None, "candidate", "not_in_canonical_work_registry", "low"

    def seed_known_identities(self) -> None:
        for work_key, config in CANONICAL_WORKS.items():
            self.upsert_work(
                work_key=work_key,
                canonical_title=config["title"],
                author=config["author"],
                work_type=config["type"],
                identity_status="canonical_active",
                metadata={"registry_source": "V2 canonical source_documents"},
            )
            self.alias(
                work_key=work_key,
                raw_label=config["title"],
                mapping_status="canonical",
                mapping_method="canonical_work_key",
                confidence="high",
                source_file="v2/schemas/annotation_v2.sql",
            )
            self.alias(
                work_key=work_key,
                raw_label=f"《{config['title']}》",
                mapping_status="canonical",
                mapping_method="book_title_wrapper_only",
                confidence="high",
                source_file="v2/schemas/annotation_v2.sql",
            )

    def ingest_source_documents(self) -> None:
        rows = self.connection.execute(
            """
            SELECT work_key, source_kind, source_file, canonical_status,
                   metadata_json
            FROM source_documents
            ORDER BY work_key, source_file
            """
        ).fetchall()
        for row in rows:
            work_key = row["work_key"]
            if work_key in CANONICAL_WORKS:
                continue
            title = LEGACY_SOURCE_TITLES.get(work_key, work_key)
            self.upsert_work(
                work_key=work_key,
                canonical_title=title,
                identity_status="legacy_source",
                work_type="legacy_derived_source",
                metadata={
                    "source_kind": row["source_kind"],
                    "canonical_status": row["canonical_status"],
                },
            )
            self.alias(
                work_key=work_key,
                raw_label=title,
                mapping_status="legacy",
                mapping_method="source_document_work_key",
                confidence="high",
                source_file=relative_path(row["source_file"]),
                source_record_id=work_key,
            )

    def ingest_catalog_works(self) -> None:
        rows = self.connection.execute(
            """
            SELECT legacy_work_id, title, author, work_type, source_file
            FROM legacy_catalog_works
            ORDER BY legacy_work_id
            """
        ).fetchall()
        for row in rows:
            work_key = f"legacy_catalog:{row['legacy_work_id']}"
            self.upsert_work(
                work_key=work_key,
                canonical_title=row["title"] or "未命名著作",
                author=row["author"],
                work_type=row["work_type"] or "legacy_catalog",
                identity_status="legacy_catalog",
                metadata={"legacy_work_id": row["legacy_work_id"]},
            )
            self.alias(
                work_key=work_key,
                raw_label=row["title"] or "未命名著作",
                mapping_status="legacy",
                mapping_method="legacy_catalog_row",
                confidence="high",
                source_file=relative_path(row["source_file"]),
                source_record_id=f"legacy_work:{row['legacy_work_id']}",
            )

    def ingest_referenced_legacy_works(self) -> dict[str, int]:
        """Register referenced dictionary works as candidate identities.

        ``legacy_dictionary_works`` is an inventory boundary, not a canonical
        edition registry.  Referenced rows can safely improve target-label
        traceability, while catalog-only rows remain represented only by
        ``legacy_catalog_works``.  Exact title matching is the only mapping
        performed here; chapter/section labels remain unresolved.
        """

        stats: Counter[str] = Counter()
        rows = self.connection.execute(
            """
            SELECT legacy_work_id, title, author, work_type, source_file,
                   usage_status
            FROM legacy_dictionary_works
            WHERE usage_status = 'referenced'
            ORDER BY legacy_work_id
            """
        ).fetchall()
        for row in rows:
            raw_label = str(row["title"] or "").strip()
            normalized = normalize_label(raw_label)
            if not normalized:
                stats["empty_label"] += 1
                continue

            canonical_key = self.canonical_by_label.get(normalized)
            if canonical_key:
                work_key = canonical_key
                mapping_status = "canonical"
                mapping_method = "legacy_dictionary_work_exact_canonical_title"
                confidence = "high"
                stats["canonical_alias"] += 1
            else:
                existing = self.connection.execute(
                    """
                    SELECT work_key, mapping_status
                    FROM work_aliases
                    WHERE normalized_label = ?
                      AND mapping_status IN ('canonical', 'candidate')
                    ORDER BY CASE mapping_status WHEN 'canonical' THEN 0 ELSE 1 END,
                             work_key
                    LIMIT 1
                    """,
                    (normalized,),
                ).fetchone()
                if existing is not None:
                    work_key = str(existing["work_key"])
                    mapping_status = str(existing["mapping_status"])
                    mapping_method = "legacy_dictionary_work_alias_to_existing_identity"
                    confidence = "medium" if mapping_status == "candidate" else "high"
                    stats["existing_identity_alias"] += 1
                else:
                    work_key = identity_key("legacy_candidate", normalized)
                    self.upsert_work(
                        work_key=work_key,
                        canonical_title=raw_label,
                        author=row["author"],
                        work_type=row["work_type"] or "legacy_dictionary_work_reference",
                        identity_status="unknown",
                        metadata={
                            "legacy_work_id": row["legacy_work_id"],
                            "usage_status": row["usage_status"],
                            "source_file": relative_path(row["source_file"]),
                            "identity_class": "legacy_dictionary_work_reference",
                            "semantic_resolution": "not_performed",
                            "edition_resolution": "not_performed",
                        },
                    )
                    mapping_status = "candidate"
                    mapping_method = "legacy_dictionary_work_reference"
                    confidence = "low"
                    stats["new_legacy_candidate_identity"] += 1

            self.alias(
                work_key=work_key,
                raw_label=raw_label,
                mapping_status=mapping_status,
                mapping_method=mapping_method,
                confidence=confidence,
                source_file=relative_path(row["source_file"]),
                source_record_id=f"legacy_work:{row['legacy_work_id']}",
                metadata={
                    "legacy_work_id": row["legacy_work_id"],
                    "usage_status": row["usage_status"],
                    "identity_class": "legacy_dictionary_work_reference" if mapping_status != "canonical" else "canonical_title_identity_from_legacy_reference",
                    "semantic_resolution": "not_performed" if mapping_status != "canonical" else "canonical_title_identity_only",
                },
            )
        return dict(stats)

    def ingest_case_labels(self) -> dict[str, int]:
        stats: Counter[str] = Counter()
        rows = self.connection.execute(
            """
            SELECT case_id, source_work, target_work, origin
            FROM annotation_cases
            ORDER BY case_id
            """
        ).fetchall()
        for row in rows:
            for field_name in ("source_work", "target_work"):
                raw = row[field_name] or ""
                if not raw:
                    stats[f"{field_name}:empty"] += 1
                    continue
                resolved_key, status, method, confidence = self.resolve_label(raw)
                if resolved_key is None:
                    resolved_key = self.ensure_unknown_identity(raw, prefix="candidate")
                self.alias(
                    work_key=resolved_key,
                    raw_label=raw,
                    mapping_status=status,
                    mapping_method=f"case_{field_name}:{method}",
                    confidence=confidence,
                    source_file=f"annotation_cases:{row['origin']}",
                    source_record_id=f"{row['case_id']}:{field_name}",
                    metadata={"case_id": row["case_id"], "field": field_name},
                )
                stats[f"{field_name}:{status}"] += 1
        return dict(stats)

    def ingest_external_sources(self) -> dict[str, int]:
        stats: Counter[str] = Counter()
        rows = self.connection.execute(
            """
            SELECT external_source_id, cited_work, normalized_work, status
            FROM external_source_registry
            ORDER BY external_source_id
            """
        ).fetchall()
        for row in rows:
            resolved_key, status, method, confidence = self.resolve_label(row["cited_work"])
            if resolved_key is None:
                resolved_key = identity_key("external", row["normalized_work"])
                self.upsert_work(
                    work_key=resolved_key,
                    canonical_title=row["cited_work"] or row["normalized_work"],
                    identity_status="external_pending",
                    work_type="external_citation",
                    metadata={
                        "external_source_id": row["external_source_id"],
                        "registry_status": row["status"],
                    },
                )
                status = "candidate"
                method = "external_registry_label_not_canonicalized"
                confidence = "low"
            self.alias(
                work_key=resolved_key,
                raw_label=row["cited_work"],
                mapping_status=status,
                mapping_method=method,
                confidence=confidence,
                source_file="external_source_registry",
                source_record_id=row["external_source_id"],
                metadata={"normalized_work": row["normalized_work"], "status": row["status"]},
            )
            stats[status] += 1
        return dict(stats)

    def build(self) -> dict[str, Any]:
        self.seed_known_identities()
        self.ingest_source_documents()
        self.ingest_catalog_works()
        legacy_work_stats = self.ingest_referenced_legacy_works()
        case_stats = self.ingest_case_labels()
        external_stats = self.ingest_external_sources()
        self.connection.commit()
        work_counts = {
            row["identity_status"]: row["count"]
            for row in self.connection.execute(
                "SELECT identity_status, COUNT(*) AS count FROM work_registry GROUP BY identity_status"
            )
        }
        alias_counts = {
            row["mapping_status"]: row["count"]
            for row in self.connection.execute(
                "SELECT mapping_status, COUNT(*) AS count FROM work_aliases GROUP BY mapping_status"
            )
        }
        unresolved = [
            dict(row)
            for row in self.connection.execute(
                """
                SELECT work_key, canonical_title, identity_status
                FROM work_registry
                WHERE identity_status IN ('unknown', 'external_pending')
                ORDER BY identity_status, canonical_title
                LIMIT 200
                """
            )
        ]
        return {
            "report_version": "work_registry.v1",
            "generated_at": now(),
            "status": "completed_with_explicit_unresolved_identities",
            "database": relative_path(str(DEFAULT_DATABASE)),
            "policy": {
                "semantic_disambiguation_performed": False,
                "format_only_normalization": "strip outer book-title marks and compress whitespace",
                "unresolved_target_labels_remain_candidates": True,
            },
            "counts": {
                "work_registry": sum(work_counts.values()),
                "work_aliases": sum(alias_counts.values()),
                "canonical_active_works": work_counts.get("canonical_active", 0),
                "external_pending_works": work_counts.get("external_pending", 0),
                "unknown_works": work_counts.get("unknown", 0),
            },
            "identity_status_counts": work_counts,
            "alias_mapping_status_counts": alias_counts,
            "case_label_mapping": case_stats,
            "legacy_work_mapping": legacy_work_stats,
            "external_label_mapping": external_stats,
            "unresolved_identity_examples": unresolved,
        }


def build_registry(database_path: Path = DEFAULT_DATABASE) -> dict[str, Any]:
    with open_database(database_path) as connection:
        report = RegistryBuilder(connection).build()
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", type=Path, default=DEFAULT_DATABASE)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    args = parser.parse_args()
    report = build_registry(args.database)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report["counts"], ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
