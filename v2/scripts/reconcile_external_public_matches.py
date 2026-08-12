from __future__ import annotations

"""Reconcile public candidate pages with exact normalized quote spans.

The fetcher intentionally keeps search results separate from quote matches.
This small offline pass looks at the frozen wikitext only.  It upgrades a
manifest entry to ``candidate_found`` only when the full quote (after NFKC,
punctuation/spacing removal, and a small traditional-character map) is a
contiguous substring of the page.  It still never changes V2 quote_check.
"""

import argparse
import hashlib
import json
import sqlite3
import unicodedata
from pathlib import Path
from typing import Any


V2_ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = V2_ROOT.parent
DEFAULT_DATABASE = V2_ROOT / "data/real_runs/annotation_v2.db"
DEFAULT_MANIFEST = V2_ROOT / "data/real_runs/external_public_candidate_manifest.json"


TRADITIONAL = str.maketrans(
    "礼记书传说广雅势义乐乱国声风电与为也说文尔东义仪乡射齐鲁经论语诗击鼓邱齐采苹韩奕说苑慎汉将伤创疥癣旧简标识远举顾忧",
    "禮記書傳說廣雅勢義樂亂國聲風電與為也說文爾東義儀鄉射齊魯經論語詩擊鼓丘齊採蘋韓奕說苑慎漢將傷創疥癬舊簡標識遠舉顧憂",
)


def compact(value: str) -> str:
    value = unicodedata.normalize("NFKC", value or "")
    return "".join(
        char
        for char in value.translate(TRADITIONAL)
        if not unicodedata.category(char).startswith(("P", "Z"))
        and unicodedata.category(char) != "Cf"
    )


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def relative(path: Path) -> str:
    try:
        return path.resolve().relative_to(PROJECT_ROOT.resolve()).as_posix()
    except ValueError:
        return path.as_posix()


def reconcile(manifest_path: Path = DEFAULT_MANIFEST) -> dict[str, Any]:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    statuses: dict[str, int] = {}
    exact_match_count = 0
    for entry in manifest.get("entries", []):
        quote_compact = compact(entry.get("quote", ""))
        candidates = []
        for candidate in entry.get("candidates", []):
            raw_file = PROJECT_ROOT / candidate["raw_file"]
            if not raw_file.exists():
                candidate["offline_match_mode"] = "raw_file_missing"
                candidates.append(candidate)
                continue
            raw = raw_file.read_text(encoding="utf-8")
            raw_compact = compact(raw)
            start = raw_compact.find(quote_compact) if quote_compact else -1
            if start >= 0:
                candidate["offline_match_mode"] = "normalized_contiguous"
                candidate["offline_start_char"] = start
                candidate["offline_end_char"] = start + len(quote_compact)
                exact_match_count += 1
            else:
                candidate["offline_match_mode"] = "not_found"
            candidates.append(candidate)
        entry["candidates"] = candidates
        matched = [
            candidate
            for candidate in candidates
            if candidate.get("offline_match_mode") == "normalized_contiguous"
        ]
        if matched:
            entry["status"] = "candidate_found"
            entry["candidate_match_count"] = len(matched)
        elif candidates:
            entry["status"] = "search_hit_only"
            entry["candidate_match_count"] = 0
        else:
            entry["status"] = "no_public_match"
            entry["candidate_match_count"] = 0
        statuses[entry["status"]] = statuses.get(entry["status"], 0) + 1
    manifest["summary"]["status_counts"] = statuses
    manifest["summary"]["candidate_count"] = sum(
        entry.get("candidate_match_count", 0) for entry in manifest.get("entries", [])
    )
    manifest["summary"]["source_count_with_candidate"] = len(
        {
            entry["external_source_id"]
            for entry in manifest.get("entries", [])
            if entry["status"] == "candidate_found"
        }
    )
    manifest["summary"]["offline_contiguous_match_count"] = exact_match_count
    manifest.pop("manifest_sha256", None)
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    manifest_hash = sha256(manifest_path)
    manifest_path.with_suffix(manifest_path.suffix + ".sha256").write_text(
        f"{manifest_hash}  {manifest_path.name}\n", encoding="utf-8"
    )
    manifest["manifest_sha256"] = manifest_hash
    return manifest


def update_registry(database: Path, manifest_path: Path, manifest: dict[str, Any]) -> None:
    registered_sources = {
        entry["external_source_id"]
        for entry in manifest.get("entries", [])
        if entry.get("status") == "candidate_found"
    }
    connection = sqlite3.connect(database)
    for external_source_id in registered_sources:
        connection.execute(
            "UPDATE external_source_registry SET status='registered', source_file=?, source_file_sha256=?, edition=?, location_note=?, updated_at=datetime('now') WHERE external_source_id=?",
            (
                relative(manifest_path),
                manifest["manifest_sha256"],
                "Wikisource public transcription; edition unresolved",
                "quote matched in frozen wikitext; image/edition verification pending",
                external_source_id,
            ),
        )
    connection.commit()
    connection.close()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--database", type=Path, default=DEFAULT_DATABASE)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    args = parser.parse_args()
    manifest = reconcile(args.manifest)
    update_registry(args.database, args.manifest, manifest)
    print(json.dumps(manifest["summary"], ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
