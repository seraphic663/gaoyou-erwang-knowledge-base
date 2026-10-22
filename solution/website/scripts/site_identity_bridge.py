"""Read-only navigation mapping. Never infer identities from titles."""
from contextlib import closing
import argparse
import base64
import json
import sqlite3
from pathlib import Path

def audit_targets(db, source, ids):
    if source == "annotation":
        return {str(i): [] for i in ids}
    uri = Path(db).resolve().as_uri() + "?mode=ro"
    with closing(sqlite3.connect(uri, uri=True)) as connection:
        connection.execute("PRAGMA query_only=ON")
        result = {str(i): [] for i in ids}
        if not ids:
            return result
        placeholders = ",".join("?" for _ in ids)
        if source == "main":
            exists = connection.execute("SELECT 1 FROM sqlite_master WHERE name='legacy_term_case_links'").fetchone()
            if not exists:
                return result
            rows = connection.execute(
                f"SELECT DISTINCT l.legacy_case_id, l.v2_case_id FROM legacy_term_case_links l JOIN annotation_cases c ON c.case_id=l.v2_case_id WHERE CAST(l.legacy_case_id AS TEXT) IN ({placeholders}) ORDER BY l.v2_case_id", ids
            )
        elif source == "v2":
            rows = connection.execute(f"SELECT case_id, case_id FROM annotation_cases WHERE case_id IN ({placeholders})", ids)
        else:
            raise ValueError("invalid_source")
        for old, new in rows:
            result[str(old)].append(new)
        return result

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["map"])
    parser.add_argument("--db", required=True)
    parser.add_argument("--payload-base64", required=True)
    args = parser.parse_args()
    payload = json.loads(base64.b64decode(args.payload_base64))
    print(json.dumps({"ok": True, "targets": audit_targets(args.db, payload["source"], [str(i) for i in payload["ids"]])}, ensure_ascii=False))
