from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path


V2_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(V2_ROOT / "src"))

from erwang_v2.database import database_counts, ingest_case, ingest_passages, open_database
from erwang_v2.validate_annotation_case import load_passages_jsonl


class UnifiedDatabaseTest(unittest.TestCase):
    def test_machine_case_enters_shared_db_without_becoming_gold(self) -> None:
        passages = list(load_passages_jsonl(V2_ROOT / "data/fixtures/passages.jsonl").values())
        case = json.loads(
            (V2_ROOT / "data/fixtures/cases/造舟于河.annotation.json").read_text(
                encoding="utf-8"
            )
        )

        with tempfile.TemporaryDirectory() as directory:
            database_path = Path(directory) / "annotation_v2.db"
            with open_database(database_path) as connection:
                ingest_passages(connection, passages)
                stored = ingest_case(connection, case, origin="candidate_ai")
                connection.commit()

                self.assertEqual(stored["origin"], "candidate_ai")
                self.assertEqual(stored["lifecycle"], "machine_draft")
                self.assertEqual(stored["machine_status"], "pending")
                self.assertEqual(stored["human_status"], "pending")
                self.assertEqual(database_counts(connection)["annotation_cases"], 1)
                self.assertEqual(connection.execute("SELECT COUNT(*) FROM v_gold_cases").fetchone()[0], 0)


if __name__ == "__main__":
    unittest.main()
