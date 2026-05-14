-- 02-数据库/main/schema.sql
-- 主库（dictionary.db）DDL — 古汉语考据知识库 · 五表结构
-- 来源：原 database.py _SCHEMA 常量

-- 著作表：所有被引用的典籍
CREATE TABLE IF NOT EXISTS works (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    title      TEXT NOT NULL UNIQUE,
    author     TEXT,
    work_type  TEXT CHECK(work_type IN ('二王著作','原始经典')),
    dynasty    TEXT,
    time_note  TEXT,
    notes      TEXT
);

-- 文本片段表：二王论述段落
CREATE TABLE IF NOT EXISTS passages (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    work_id          INTEGER REFERENCES works(id),
    juan             TEXT,
    chapter          TEXT,
    location_note    TEXT,
    raw_text         TEXT NOT NULL,
    normalized_text  TEXT,
    passage_type     TEXT CHECK(passage_type IN ('二王论述','原始经典'))
);

-- 词条表：每个字/词独立一行，无重复
CREATE TABLE IF NOT EXISTS terms (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    term        TEXT NOT NULL,
    term_type   TEXT CHECK(term_type IN ('术语','词','字')),
    category    TEXT,
    aliases     TEXT,
    notes       TEXT,
    core_meaning TEXT,
    case_ids    TEXT,
    UNIQUE(term)
);

-- 考据案例表：整条考证为一个 case
CREATE TABLE IF NOT EXISTS cases (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    title               TEXT NOT NULL,
    section_title       TEXT,
    volume_title        TEXT,
    term_ids            TEXT,
    erwang_passage_id   INTEGER REFERENCES passages(id),
    target_passage_id   INTEGER REFERENCES passages(id),
    problem             TEXT,
    method              TEXT,
    process_text        TEXT,
    conclusion          TEXT,
    certainty           TEXT CHECK(certainty IN ('确定','可疑','待核')),
    status              TEXT CHECK(status IN ('草稿','已校对','已审核'))
);

-- 证据表：每个证据关联到特定字（term），独立一行
CREATE TABLE IF NOT EXISTS evidences (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    case_id             INTEGER REFERENCES cases(id),
    term_id             INTEGER REFERENCES terms(id),
    source_passage_id   INTEGER REFERENCES passages(id),
    work_id             INTEGER REFERENCES works(id),
    evidence_type       TEXT CHECK(evidence_type IN ('书证','声训','义证','形证','语法证据','异文')),
    quote_text          TEXT,
    core_snippet        TEXT,
    note                TEXT
);

-- FTS5 全文索引
CREATE VIRTUAL TABLE IF NOT EXISTS terms_fts USING fts5(
    term, category, aliases, notes, core_meaning
);
CREATE VIRTUAL TABLE IF NOT EXISTS passages_fts USING fts5(
    raw_text, normalized_text
);
CREATE VIRTUAL TABLE IF NOT EXISTS evidences_fts USING fts5(
    quote_text, core_snippet, note
);
