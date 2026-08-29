-- 02-数据库/annotation/schema.sql
-- 人工标注灰度库（annotations.db）DDL
-- 来源：原 run.py ANNOTATION_SCHEMA 常量，表名保持不变
-- 定位：独立于主库的工作稿，annotation_ 前缀区分两个库的核心表

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
