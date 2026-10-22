"""Read-only SQLite baseline and recoverable backup for website changes."""
from contextlib import closing
import argparse
import hashlib
import json
import sqlite3
from pathlib import Path

def inspect(db):
    with closing(sqlite3.connect(Path(db).resolve().as_uri()+"?mode=ro", uri=True)) as con:
        con.execute("PRAGMA query_only=ON")
        con.execute("BEGIN")
        integrity = [r[0] for r in con.execute("PRAGMA integrity_check")]
        foreign_keys = list(con.execute("PRAGMA foreign_key_check"))
        tables = {}
        for (name,) in con.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"):
            quoted = '"' + name.replace('"','""') + '"'
            rows = []
            for row in con.execute("SELECT * FROM "+quoted):
                value=json.dumps(row,ensure_ascii=False,default=lambda v:{"bytes":v.hex()},separators=(',',':'))
                rows.append(hashlib.sha256(value.encode()).digest())
            tables[name]={"count":len(rows),"digest":hashlib.sha256(b"".join(sorted(rows))).hexdigest()}
        return {"integrity":integrity,"foreign_keys":foreign_keys,"tables":tables}

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--db",required=True)
    parser.add_argument("--backup")
    parser.add_argument("--baseline")
    parser.add_argument("--output",required=True)
    args=parser.parse_args()
    report=inspect(args.db)
    if args.backup:
        dest=Path(args.backup)
        if dest.exists(): raise FileExistsError(dest)
        dest.parent.mkdir(parents=True,exist_ok=True)
        with closing(sqlite3.connect(Path(args.db).resolve().as_uri()+"?mode=ro",uri=True)) as source, closing(sqlite3.connect(dest)) as target:
            source.backup(target)
        if inspect(dest)!=report: raise RuntimeError("backup_content_mismatch")
    if args.baseline:
        report["matches_baseline"]=report==json.loads(Path(args.baseline).read_text(encoding="utf-8"))
    Path(args.output).parent.mkdir(parents=True,exist_ok=True)
    Path(args.output).write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8")
    print(json.dumps({"integrity":report["integrity"],"foreign_key_errors":len(report["foreign_keys"]),"tables":len(report["tables"]),"matches_baseline":report.get("matches_baseline")}))
    if report["integrity"]!=["ok"] or report["foreign_keys"] or report.get("matches_baseline") is False: raise SystemExit(1)

if __name__=="__main__":main()
