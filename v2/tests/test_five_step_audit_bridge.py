import sqlite3
import tempfile
import unittest
from pathlib import Path
import sys

V2_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(V2_ROOT / "scripts"))
from v2_five_step_audit_bridge import (
    delete_record,
    get_record,
    list_records,
    restore_record,
    save_record,
    save_revision,
)


STEP_FIELDS = [
    "problem_discovery",
    "research_question",
    "evidence_collection",
    "reasoning",
    "conclusion",
]


def sample_payload(operation_id="audit-op-1"):
    steps = [{"field": field, "text": field, "evidence_refs": [], "review_questions": []} for field in STEP_FIELDS]
    reviewed = [{"field": field, "status": "accepted", "text": field, "comment": ""} for field in STEP_FIELDS]
    return {
        "case_id": "case-1",
        "reviewer": "reviewer-1",
        "operation_id": operation_id,
        "model_requested": "deepseek-flash",
        "model_returned": "deepseek-flash",
        "reasoning_effort": "high",
        "prompt_version": "v2-five-step-audit.v1",
        "case_fingerprint": "a" * 64,
        "generated_at": "2026-09-15T00:00:00.000Z",
        "audit_json": {
            "overall_decision": "reviewed",
            "overall_note": "checked",
            "ai_draft": steps,
            "reviewed_steps": reviewed,
        },
    }


class FiveStepAuditBridgeTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.database_path = Path(self.temp_dir.name) / "annotation_v2.db"
        connection = sqlite3.connect(self.database_path)
        connection.execute(
            "CREATE TABLE annotation_cases (case_id TEXT PRIMARY KEY, human_status TEXT NOT NULL)"
        )
        connection.execute(
            "CREATE TABLE annotation_evidences (case_id TEXT NOT NULL, evidence_index INTEGER NOT NULL)"
        )
        connection.execute(
            "INSERT INTO annotation_cases(case_id, human_status) VALUES ('case-1', 'pending')"
        )
        connection.commit()
        connection.close()

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_save_is_append_only_and_idempotent(self):
        first = save_record(self.database_path, sample_payload())
        retry = save_record(self.database_path, sample_payload())
        self.assertEqual(first["audit_id"], retry["audit_id"])
        self.assertTrue(retry["idempotent"])

        connection = sqlite3.connect(self.database_path)
        self.assertEqual(connection.execute("SELECT COUNT(*) FROM five_step_audit_records").fetchone()[0], 1)
        self.assertEqual(connection.execute("SELECT human_status FROM annotation_cases WHERE case_id='case-1'").fetchone()[0], "pending")
        connection.close()

    def test_list_returns_saved_model_and_review_payload(self):
        save_record(self.database_path, sample_payload())
        result = list_records(self.database_path, "case-1")
        self.assertEqual(len(result["records"]), 1)
        self.assertEqual(result["records"][0]["model_requested"], "deepseek-flash")
        self.assertEqual(result["records"][0]["reasoning_effort"], "high")
        self.assertEqual(len(result["records"][0]["audit"]["reviewed_steps"]), 5)

    def test_rejects_unsupported_model(self):
        payload = sample_payload()
        payload["model_requested"] = "deepseek-v4-flash"
        with self.assertRaisesRegex(ValueError, "model_not_allowed"):
            save_record(self.database_path, payload)

    def test_revision_delete_and_restore_preserve_history(self):
        first = save_record(self.database_path, sample_payload())
        revision = save_revision(
            self.database_path,
            {
                "source_audit_id": first["audit_id"],
                "case_id": "case-1",
                "reviewer": "reviewer-2",
                "operation_id": "revision-op-1",
                "case_fingerprint": first["case_fingerprint"],
                "reviewed_steps": [
                    {"field": field, "status": "edited", "text": f"{field} revised", "comment": "changed"}
                    for field in STEP_FIELDS
                ],
                "overall_decision": "needs_revision",
                "overall_note": "revision note",
            },
        )
        self.assertEqual(revision["record_version"], 2)
        self.assertEqual(revision["supersedes_audit_id"], first["audit_id"])
        self.assertEqual(get_record(self.database_path, first["audit_id"])["record"]["record_state"], "superseded")

        deleted = delete_record(
            self.database_path,
            {
                "audit_id": revision["audit_id"],
                "deleted_by": "reviewer-2",
                "operation_id": "delete-op-1",
                "delete_reason": "duplicate draft",
            },
        )
        self.assertEqual(deleted["record_state"], "deleted")
        restored = restore_record(
            self.database_path,
            {
                "audit_id": revision["audit_id"],
                "restored_by": "reviewer-2",
                "operation_id": "restore-op-1",
            },
        )
        self.assertEqual(restored["record_state"], "active")
        self.assertEqual(len(list_records(self.database_path, "case-1")["records"]), 2)


if __name__ == "__main__":
    unittest.main()
