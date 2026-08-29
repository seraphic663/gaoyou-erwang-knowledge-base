"""
annotation/importer.py — 人工标注灰度库数据库操作

提供标注库的建表、写入接口。
被 04-项目文献/D-标注/json/run.py 调用。
"""

import json
import sys
from pathlib import Path
from typing import Optional, List, Dict, Any

# 确保 02-数据库/ 在 sys.path 中，以便导入 lib/
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib.connection import connect, fetch_all, fetch_one, execute


# ─── 当前标注库路径 ──────────────────────────────────────────────────────────

ANNOTATION_DB_PATH = Path(__file__).resolve().parent.parent / "data" / "annotations.db"


# ─── DDL（与 annotation/schema.sql 保持一致） ─────────────────────────────────

ANNOTATION_SCHEMA = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS meta (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS source_documents (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_file_name TEXT NOT NULL UNIQUE,
    source_file_path TEXT,
    full_json_file TEXT,
    ai_json_file TEXT,
    doc_type TEXT,
    paragraph_count INTEGER DEFAULT 0,
    comment_count INTEGER DEFAULT 0,
    anchored_comment_count INTEGER DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS annotation_cases (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_document_id INTEGER REFERENCES source_documents(id),
    case_title TEXT NOT NULL,
    source_work TEXT,
    target_work TEXT,
    target_text TEXT,
    problem TEXT,
    claim TEXT,
    method_tags_json TEXT,
    conclusion TEXT,
    certainty TEXT CHECK(certainty IN ('确定','可疑','待核')) DEFAULT '待核',
    status TEXT CHECK(status IN ('草稿','已校对','已审核')) DEFAULT '草稿',
    raw_case_json TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS annotation_terms (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    case_id INTEGER NOT NULL REFERENCES annotation_cases(id) ON DELETE CASCADE,
    term TEXT,
    term_type TEXT,
    relation_type TEXT,
    related_term TEXT,
    note TEXT,
    source_paragraph_indexes_json TEXT,
    source_comment_ids_json TEXT,
    raw_term_json TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS annotation_evidences (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    case_id INTEGER NOT NULL REFERENCES annotation_cases(id) ON DELETE CASCADE,
    evidence_type TEXT CHECK(evidence_type IN ('书证','声训','义证','形证','语法证据','异文')),
    work TEXT,
    quote TEXT,
    role TEXT,
    term TEXT,
    source_paragraph_indexes_json TEXT,
    source_comment_ids_json TEXT,
    raw_evidence_json TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS annotation_process_steps (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    case_id INTEGER NOT NULL REFERENCES annotation_cases(id) ON DELETE CASCADE,
    step_order INTEGER NOT NULL,
    step_type TEXT,
    text TEXT,
    source_paragraph_indexes_json TEXT,
    source_comment_ids_json TEXT,
    raw_step_json TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_annotation_cases_source_document_id ON annotation_cases(source_document_id);
CREATE INDEX IF NOT EXISTS idx_annotation_terms_case_id ON annotation_terms(case_id);
CREATE INDEX IF NOT EXISTS idx_annotation_evidences_case_id ON annotation_evidences(case_id);
CREATE INDEX IF NOT EXISTS idx_annotation_process_steps_case_id ON annotation_process_steps(case_id);
"""


# ─── 数据库初始化 ────────────────────────────────────────────────────────────

def init_db(db_path: Path = None) -> Path:
    """创建标注库并初始化 schema，返回数据库路径。"""
    if db_path is None:
        db_path = ANNOTATION_DB_PATH
    db_path.parent.mkdir(parents=True, exist_ok=True)

    conn = connect(db_path)
    try:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        conn.executescript(ANNOTATION_SCHEMA)
        conn.execute(
            "INSERT OR REPLACE INTO meta(key, value) VALUES(?, ?)",
            ("schema_version", "annotation_db_v1"),
        )
        conn.execute(
            "INSERT OR REPLACE INTO meta(key, value) VALUES(?, ?)",
            ("purpose", "人工标注与 AI 整理结果暂存库，不与主库混用"),
        )
        conn.commit()
    finally:
        conn.close()
    return db_path


# ─── 查询辅助 ────────────────────────────────────────────────────────────────

def get_stats(db_path: Path = None) -> Dict[str, int]:
    """返回标注库各表行数统计。"""
    if db_path is None:
        db_path = ANNOTATION_DB_PATH
    if not db_path.exists():
        return {"documents": 0, "cases": 0, "terms": 0, "evidences": 0, "processSteps": 0}

    conn = connect(db_path)
    try:
        return {
            "documents": conn.execute("SELECT COUNT(*) FROM source_documents").fetchone()[0],
            "cases": conn.execute("SELECT COUNT(*) FROM annotation_cases").fetchone()[0],
            "terms": conn.execute("SELECT COUNT(*) FROM annotation_terms").fetchone()[0],
            "evidences": conn.execute("SELECT COUNT(*) FROM annotation_evidences").fetchone()[0],
            "processSteps": conn.execute("SELECT COUNT(*) FROM annotation_process_steps").fetchone()[0],
        }
    finally:
        conn.close()
