PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS schema_meta (
    meta_key TEXT PRIMARY KEY,
    meta_value TEXT NOT NULL
);

INSERT INTO schema_meta(meta_key, meta_value)
VALUES ('schema_version', 'annotation_db_v2')
ON CONFLICT(meta_key) DO UPDATE SET meta_value = excluded.meta_value;

CREATE TABLE IF NOT EXISTS source_documents (
    source_document_id TEXT PRIMARY KEY,
    work_key TEXT NOT NULL,
    source_kind TEXT NOT NULL,
    source_file TEXT NOT NULL,
    source_file_sha256 TEXT NOT NULL,
    metadata_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS passages (
    passage_id TEXT PRIMARY KEY,
    source_document_id TEXT NOT NULL,
    work_key TEXT NOT NULL,
    document_title TEXT,
    section_title TEXT,
    entry_title TEXT,
    entry_kind TEXT,
    local_ordinal INTEGER NOT NULL,
    md_line_start INTEGER,
    md_line_end INTEGER,
    raw_text TEXT NOT NULL,
    plain_text TEXT NOT NULL,
    normalized_text TEXT NOT NULL,
    raw_text_sha256 TEXT,
    normalized_text_sha256 TEXT,
    inline_notes_json TEXT NOT NULL DEFAULT '[]',
    FOREIGN KEY(source_document_id) REFERENCES source_documents(source_document_id)
);

CREATE INDEX IF NOT EXISTS idx_passages_work_title
    ON passages(work_key, document_title, section_title, entry_title);

CREATE TABLE IF NOT EXISTS annotation_cases (
    case_id TEXT PRIMARY KEY,
    schema_version TEXT NOT NULL,
    case_title TEXT NOT NULL,
    submitted_by TEXT NOT NULL,
    source_work TEXT NOT NULL,
    target_work TEXT NOT NULL,
    target_works_json TEXT NOT NULL DEFAULT '[]',
    target_scope_json TEXT NOT NULL DEFAULT '{}',
    target_text TEXT NOT NULL,
    evidence_state TEXT NOT NULL DEFAULT 'present',
    source_passage_id TEXT,
    origin TEXT NOT NULL,
    lifecycle TEXT NOT NULL CHECK(lifecycle IN ('machine_draft', 'human_review', 'gold', 'rejected')),
    machine_status TEXT NOT NULL CHECK(machine_status IN ('pending', 'draft', 'approved', 'rejected')),
    human_status TEXT NOT NULL CHECK(human_status IN ('pending', 'approved', 'rejected', 'uncertain')),
    review_status TEXT NOT NULL CHECK(review_status IN ('pending', 'approved', 'rejected', 'uncertain')),
    machine_result_json TEXT NOT NULL,
    human_review_json TEXT NOT NULL,
    case_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY(source_passage_id) REFERENCES passages(passage_id)
);

CREATE INDEX IF NOT EXISTS idx_annotation_cases_work_state
    ON annotation_cases(source_work, lifecycle, machine_status, human_status);

CREATE TABLE IF NOT EXISTS annotation_terms (
    case_id TEXT NOT NULL,
    term_index INTEGER NOT NULL,
    source_term TEXT NOT NULL,
    target_term TEXT NOT NULL,
    relation_type TEXT,
    relation_subtype TEXT,
    relation_note TEXT,
    term_json TEXT NOT NULL,
    PRIMARY KEY(case_id, term_index),
    FOREIGN KEY(case_id) REFERENCES annotation_cases(case_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS annotation_evidences (
    case_id TEXT NOT NULL,
    evidence_index INTEGER NOT NULL,
    passage_id TEXT,
    source_work TEXT,
    quote TEXT NOT NULL,
    quote_sha256 TEXT,
    quote_check TEXT,
    evidence_json TEXT NOT NULL,
    PRIMARY KEY(case_id, evidence_index),
    FOREIGN KEY(case_id) REFERENCES annotation_cases(case_id) ON DELETE CASCADE,
    FOREIGN KEY(passage_id) REFERENCES passages(passage_id)
);

CREATE INDEX IF NOT EXISTS idx_annotation_evidences_passage
    ON annotation_evidences(passage_id);

CREATE TABLE IF NOT EXISTS external_source_registry (
    external_source_id TEXT PRIMARY KEY,
    cited_work TEXT NOT NULL,
    normalized_work TEXT NOT NULL UNIQUE,
    source_kind TEXT NOT NULL DEFAULT 'external_citation',
    status TEXT NOT NULL CHECK(status IN ('pending', 'registered', 'verified')),
    source_file TEXT,
    source_file_sha256 TEXT,
    edition TEXT,
    location_note TEXT,
    metadata_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS annotation_evidence_external_sources (
    case_id TEXT NOT NULL,
    evidence_index INTEGER NOT NULL,
    external_source_id TEXT NOT NULL,
    PRIMARY KEY(case_id, evidence_index),
    FOREIGN KEY(case_id, evidence_index)
        REFERENCES annotation_evidences(case_id, evidence_index) ON DELETE CASCADE,
    FOREIGN KEY(external_source_id)
        REFERENCES external_source_registry(external_source_id)
);

CREATE INDEX IF NOT EXISTS idx_external_source_registry_status
    ON external_source_registry(status, normalized_work);

CREATE TABLE IF NOT EXISTS annotation_process_steps (
    case_id TEXT NOT NULL,
    step_index INTEGER NOT NULL,
    field_name TEXT NOT NULL CHECK(field_name IN ('problem_discovery', 'research_question', 'evidence_collection', 'reasoning', 'conclusion')),
    step_text TEXT,
    step_json TEXT NOT NULL,
    PRIMARY KEY(case_id, step_index),
    UNIQUE(case_id, field_name),
    FOREIGN KEY(case_id) REFERENCES annotation_cases(case_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS review_events (
    review_event_id INTEGER PRIMARY KEY AUTOINCREMENT,
    case_id TEXT NOT NULL,
    reviewer TEXT,
    review_status TEXT NOT NULL CHECK(review_status IN ('pending', 'approved', 'rejected', 'uncertain')),
    review_note TEXT,
    review_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL,
    FOREIGN KEY(case_id) REFERENCES annotation_cases(case_id) ON DELETE CASCADE
);

CREATE VIEW IF NOT EXISTS v_machine_cases AS
SELECT * FROM annotation_cases
WHERE lifecycle = 'machine_draft';

CREATE VIEW IF NOT EXISTS v_human_review_queue AS
SELECT * FROM annotation_cases
WHERE human_status IN ('pending', 'uncertain');

CREATE VIEW IF NOT EXISTS v_gold_cases AS
SELECT * FROM annotation_cases
WHERE lifecycle = 'gold' AND human_status = 'approved';
