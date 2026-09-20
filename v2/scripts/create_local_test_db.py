"""Create the small editable V2 database used by local website testing.

The production Railway database is never touched by this script.  The default
output is ignored by Git and is rebuilt from the tracked fixture passages and
cases when needed.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path


V2_ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = V2_ROOT.parent
DEFAULT_DATABASE = V2_ROOT / "data" / "local_test" / "annotation_v2.local.db"
FIXTURE_PASSAGES = V2_ROOT / "data" / "fixtures" / "passages.jsonl"
FIXTURE_CASES = V2_ROOT / "data" / "fixtures" / "cases"
sys.path.insert(0, str(V2_ROOT / "src"))

from erwang_v2.database import ingest_case, ingest_passages, open_database  # noqa: E402
from erwang_v2.validate_annotation_case import load_passages_jsonl  # noqa: E402


def load_fixture_cases() -> list[dict]:
    cases = []
    for path in sorted(FIXTURE_CASES.glob("*.annotation.json")):
        case = json.loads(path.read_text(encoding="utf-8"))
        case["submitted_by"] = "local-test-fixture"
        case["machine_result"] = {
            **(case.get("machine_result") or {}),
            "status": "draft",
            "validation_state": "local_fixture",
        }
        case["human_review"] = {
            **(case.get("human_review") or {}),
            "status": "pending",
        }
        case["_migration"] = {
            "source_format": "local_fixture",
            "source_layer": "local_test",
            "transformation_kind": "fixture_ingress",
            "provenance": {
                "source_file": str(path.relative_to(PROJECT_ROOT)).replace("\\", "/"),
                "source_passage_id": case.get("source_passage_id"),
            },
        }
        cases.append(case)
    return cases


def build_database(database_path: Path) -> dict[str, int | str]:
    passages = list(load_passages_jsonl(FIXTURE_PASSAGES).values())
    by_work: dict[str, list[dict]] = defaultdict(list)
    for passage in passages:
        by_work[str(passage.get("work_key") or "unknown")].append(passage)

    database_path.parent.mkdir(parents=True, exist_ok=True)
    if database_path.exists():
        database_path.unlink()

    cases = load_fixture_cases()
    with open_database(database_path) as connection:
        for work_passages in by_work.values():
            ingest_passages(connection, work_passages, source_kind="markdown")
        for case in cases:
            ingest_case(connection, case, origin="local_test_fixture")
        connection.commit()

    return {
        "database": str(database_path),
        "passages": len(passages),
        "cases": len(cases),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", type=Path, default=DEFAULT_DATABASE)
    args = parser.parse_args()
    result = build_database(args.database.resolve())
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
