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
    canonical_status TEXT NOT NULL DEFAULT 'unknown',
    supersedes_source_document_id TEXT,
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
    target_passage_id TEXT,
    target_location_json TEXT NOT NULL DEFAULT '{}',
    process_text TEXT NOT NULL DEFAULT '',
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
    FOREIGN KEY(source_passage_id) REFERENCES passages(passage_id),
    FOREIGN KEY(target_passage_id) REFERENCES passages(passage_id)
);

CREATE INDEX IF NOT EXISTS idx_annotation_cases_work_state
    ON annotation_cases(source_work, lifecycle, machine_status, human_status);

CREATE TABLE IF NOT EXISTS source_version_registry (
    source_version_id TEXT PRIMARY KEY,
    work_key TEXT NOT NULL,
    source_file TEXT NOT NULL,
    source_file_sha256 TEXT NOT NULL,
    canonical_status TEXT NOT NULL CHECK(canonical_status IN ('canonical_active', 'historical_superseded', 'legacy_unverified', 'rejected_not_loaded', 'unknown')),
    superseded_by_sha256 TEXT,
    reason TEXT NOT NULL,
    metadata_json TEXT NOT NULL DEFAULT '{}',
    recorded_at TEXT NOT NULL,
    UNIQUE(work_key, source_file, source_file_sha256)
);

CREATE INDEX IF NOT EXISTS idx_source_version_registry_work
    ON source_version_registry(work_key, source_file, canonical_status);

-- Work identity is deliberately separate from source editions and passages.
-- A raw citation label may be retained as an alias without silently resolving
-- an ambiguous target to a canonical work.
CREATE TABLE IF NOT EXISTS work_registry (
    work_key TEXT PRIMARY KEY,
    canonical_title TEXT NOT NULL,
    author TEXT,
    work_type TEXT,
    identity_status TEXT NOT NULL CHECK(identity_status IN (
        'canonical_active', 'legacy_source', 'legacy_catalog',
        'external_pending', 'unknown'
    )),
    metadata_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS work_aliases (
    work_alias_id INTEGER PRIMARY KEY AUTOINCREMENT,
    work_key TEXT NOT NULL,
    raw_label TEXT NOT NULL,
    normalized_label TEXT NOT NULL,
    mapping_status TEXT NOT NULL CHECK(mapping_status IN (
        'canonical', 'legacy', 'candidate', 'unresolved'
    )),
    mapping_method TEXT NOT NULL,
    confidence TEXT NOT NULL CHECK(confidence IN ('high', 'medium', 'low', 'none')),
    source_file TEXT,
    source_record_id TEXT NOT NULL DEFAULT '',
    metadata_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE(work_key, raw_label, mapping_method, source_record_id),
    FOREIGN KEY(work_key) REFERENCES work_registry(work_key)
);

CREATE INDEX IF NOT EXISTS idx_work_aliases_normalized
    ON work_aliases(normalized_label, mapping_status);

CREATE INDEX IF NOT EXISTS idx_work_aliases_work
    ON work_aliases(work_key, mapping_status);

CREATE TABLE IF NOT EXISTS target_work_resolution_queue (
    queue_item_id TEXT PRIMARY KEY,
    case_id TEXT NOT NULL,
    raw_label TEXT NOT NULL DEFAULT '',
    normalized_label TEXT NOT NULL DEFAULT '',
    machine_candidate_work_key TEXT,
    machine_inference_status TEXT NOT NULL CHECK(machine_inference_status IN (
        'machine_inferred', 'unresolved'
    )),
    queue_status TEXT NOT NULL CHECK(queue_status IN (
        'pending', 'needs_context', 'resolved', 'uncertain', 'rejected'
    )),
    evidence_indexes_json TEXT NOT NULL DEFAULT '[]',
    context_json TEXT NOT NULL DEFAULT '{}',
    priority INTEGER NOT NULL DEFAULT 50,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE(case_id, raw_label),
    FOREIGN KEY(case_id) REFERENCES annotation_cases(case_id) ON DELETE CASCADE,
    FOREIGN KEY(machine_candidate_work_key) REFERENCES work_registry(work_key)
);

CREATE INDEX IF NOT EXISTS idx_target_work_queue_status
    ON target_work_resolution_queue(queue_status, priority DESC, case_id);

CREATE TABLE IF NOT EXISTS external_source_resolution_queue (
    queue_item_id TEXT PRIMARY KEY,
    external_source_id TEXT NOT NULL UNIQUE,
    cited_work TEXT NOT NULL,
    registry_status TEXT NOT NULL,
    queue_status TEXT NOT NULL CHECK(queue_status IN (
        'pending', 'candidate_available', 'no_public_match', 'verified', 'rejected'
    )),
    edition_status TEXT NOT NULL CHECK(edition_status IN (
        'missing', 'candidate_registered', 'selected_pending', 'verified', 'rejected'
    )),
    evidence_count INTEGER NOT NULL DEFAULT 0,
    pending_evidence_count INTEGER NOT NULL DEFAULT 0,
    candidate_evidence_count INTEGER NOT NULL DEFAULT 0,
    context_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY(external_source_id) REFERENCES external_source_registry(external_source_id)
);

CREATE INDEX IF NOT EXISTS idx_external_source_queue_status
    ON external_source_resolution_queue(queue_status, edition_status, cited_work);

CREATE TABLE IF NOT EXISTS external_passage_resolution_queue (
    queue_item_id TEXT PRIMARY KEY,
    external_source_id TEXT NOT NULL,
    case_id TEXT NOT NULL,
    evidence_index INTEGER NOT NULL,
    cited_work TEXT NOT NULL,
    quote TEXT NOT NULL,
    source_resolution TEXT NOT NULL,
    quote_check TEXT,
    queue_status TEXT NOT NULL CHECK(queue_status IN (
        'pending', 'candidate_available', 'no_public_match', 'verified', 'rejected'
    )),
    edition_status TEXT NOT NULL CHECK(edition_status IN (
        'missing', 'candidate_registered', 'selected_pending', 'verified', 'rejected'
    )),
    passage_status TEXT NOT NULL CHECK(passage_status IN (
        'missing', 'search_hit_only', 'candidate_match', 'verified', 'rejected'
    )),
    candidate_manifest_path TEXT,
    candidate_manifest_sha256 TEXT,
    selected_passage_id TEXT,
    candidate_passage_ids_json TEXT NOT NULL DEFAULT '[]',
    candidate_refs_json TEXT NOT NULL DEFAULT '[]',
    context_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE(case_id, evidence_index),
    FOREIGN KEY(external_source_id) REFERENCES external_source_registry(external_source_id),
    FOREIGN KEY(case_id, evidence_index)
        REFERENCES annotation_evidences(case_id, evidence_index) ON DELETE CASCADE,
    FOREIGN KEY(selected_passage_id) REFERENCES passages(passage_id)
);

CREATE INDEX IF NOT EXISTS idx_external_passage_queue_status
    ON external_passage_resolution_queue(queue_status, edition_status, passage_status);

CREATE INDEX IF NOT EXISTS idx_external_passage_queue_selected_passage
    ON external_passage_resolution_queue(selected_passage_id);

CREATE TABLE IF NOT EXISTS candidate_items (
    candidate_id TEXT PRIMARY KEY,
    source_document_id TEXT NOT NULL,
    passage_id TEXT NOT NULL,
    work_key TEXT NOT NULL,
    source_work TEXT NOT NULL,
    candidate_text TEXT NOT NULL,
    rule_hits_json TEXT NOT NULL DEFAULT '[]',
    risk_flags_json TEXT NOT NULL DEFAULT '[]',
    candidate_status TEXT NOT NULL CHECK(candidate_status IN ('approved', 'rejected', 'pending')),
    origin TEXT NOT NULL,
    output_case_id TEXT,
    provenance_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY(source_document_id) REFERENCES source_documents(source_document_id),
    FOREIGN KEY(passage_id) REFERENCES passages(passage_id),
    FOREIGN KEY(output_case_id) REFERENCES annotation_cases(case_id)
);

CREATE INDEX IF NOT EXISTS idx_candidate_items_work_status
    ON candidate_items(work_key, candidate_status, origin);

CREATE INDEX IF NOT EXISTS idx_candidate_items_output_case
    ON candidate_items(output_case_id);

-- Deterministic machine-only target-location candidates.  These rows are
-- review input, not resolved target_work/target_passage values: a citation
-- label can identify a possible work without proving the intended edition or
-- the semantic target of the Wang passage.
CREATE TABLE IF NOT EXISTS candidate_target_locations (
    candidate_target_id TEXT PRIMARY KEY,
    candidate_id TEXT NOT NULL,
    case_id TEXT NOT NULL,
    raw_label TEXT NOT NULL,
    normalized_label TEXT NOT NULL,
    candidate_work_key TEXT,
    work_identity_status TEXT NOT NULL CHECK(work_identity_status IN (
        'canonical', 'candidate', 'unknown'
    )),
    label_start_char INTEGER NOT NULL,
    label_end_char INTEGER NOT NULL,
    label_match TEXT NOT NULL,
    source_passage_id TEXT NOT NULL,
    target_passage_candidate_id TEXT,
    target_passage_match_status TEXT NOT NULL CHECK(target_passage_match_status IN (
        'not_searched', 'no_match', 'same_source_only', 'candidate_match'
    )),
    target_passage_candidate_count INTEGER NOT NULL DEFAULT 0,
    evidence_indexes_json TEXT NOT NULL DEFAULT '[]',
    machine_status TEXT NOT NULL DEFAULT 'candidate_only' CHECK(machine_status = 'candidate_only'),
    human_status TEXT NOT NULL DEFAULT 'pending' CHECK(human_status = 'pending'),
    provenance_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE(candidate_id, label_start_char, label_end_char, raw_label),
    FOREIGN KEY(candidate_id) REFERENCES candidate_items(candidate_id) ON DELETE CASCADE,
    FOREIGN KEY(case_id) REFERENCES annotation_cases(case_id) ON DELETE CASCADE,
    FOREIGN KEY(source_passage_id) REFERENCES passages(passage_id),
    FOREIGN KEY(target_passage_candidate_id) REFERENCES passages(passage_id)
);

CREATE INDEX IF NOT EXISTS idx_candidate_target_locations_case
    ON candidate_target_locations(case_id, human_status, work_identity_status);

CREATE INDEX IF NOT EXISTS idx_candidate_target_locations_work
    ON candidate_target_locations(candidate_work_key, target_passage_match_status);

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

CREATE TABLE IF NOT EXISTS legacy_catalog_terms (
    catalog_term_id TEXT PRIMARY KEY,
    legacy_term_id INTEGER NOT NULL UNIQUE,
    term TEXT NOT NULL,
    term_type TEXT,
    category TEXT,
    aliases_json TEXT NOT NULL DEFAULT '[]',
    notes TEXT,
    core_meaning TEXT,
    catalog_status TEXT NOT NULL CHECK(catalog_status = 'catalog_only'),
    evidence_state TEXT NOT NULL CHECK(evidence_state = 'unreferenced'),
    reason TEXT NOT NULL,
    source_file TEXT NOT NULL,
    source_file_sha256 TEXT NOT NULL,
    metadata_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS legacy_catalog_works (
    catalog_work_id TEXT PRIMARY KEY,
    legacy_work_id INTEGER NOT NULL UNIQUE,
    title TEXT NOT NULL,
    author TEXT,
    work_type TEXT,
    dynasty TEXT,
    time_note TEXT,
    notes TEXT,
    catalog_status TEXT NOT NULL CHECK(catalog_status = 'catalog_only'),
    evidence_state TEXT NOT NULL CHECK(evidence_state = 'unreferenced'),
    reason TEXT NOT NULL,
    source_file TEXT NOT NULL,
    source_file_sha256 TEXT NOT NULL,
    metadata_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_legacy_catalog_terms_status
    ON legacy_catalog_terms(catalog_status, evidence_state);

CREATE INDEX IF NOT EXISTS idx_legacy_catalog_works_status
    ON legacy_catalog_works(catalog_status, evidence_state);

-- The legacy catalog-only tables above intentionally contain only rows that
-- have no case/evidence relationship.  These inventory tables preserve every
-- row from dictionary.db, including dialect, sound/loan and synonym metadata,
-- without turning the inventory into canonical evidence or human gold.
CREATE TABLE IF NOT EXISTS legacy_dictionary_terms (
    legacy_term_id INTEGER PRIMARY KEY,
    term TEXT NOT NULL,
    term_type TEXT,
    category TEXT,
    aliases_json TEXT NOT NULL DEFAULT '[]',
    notes TEXT,
    core_meaning TEXT,
    legacy_case_ids_json TEXT NOT NULL DEFAULT '[]',
    usage_status TEXT NOT NULL CHECK(usage_status IN ('referenced', 'catalog_only')),
    case_reference_count INTEGER NOT NULL DEFAULT 0,
    evidence_reference_count INTEGER NOT NULL DEFAULT 0,
    source_file TEXT NOT NULL,
    source_file_sha256 TEXT NOT NULL,
    metadata_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS legacy_dictionary_works (
    legacy_work_id INTEGER PRIMARY KEY,
    title TEXT NOT NULL,
    author TEXT,
    work_type TEXT,
    dynasty TEXT,
    time_note TEXT,
    notes TEXT,
    legacy_case_ids_json TEXT NOT NULL DEFAULT '[]',
    usage_status TEXT NOT NULL CHECK(usage_status IN ('referenced', 'catalog_only')),
    case_reference_count INTEGER NOT NULL DEFAULT 0,
    evidence_reference_count INTEGER NOT NULL DEFAULT 0,
    source_file TEXT NOT NULL,
    source_file_sha256 TEXT NOT NULL,
    metadata_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS legacy_term_case_links (
    legacy_term_id INTEGER NOT NULL,
    legacy_case_id INTEGER NOT NULL,
    v2_case_id TEXT NOT NULL,
    term_position INTEGER NOT NULL,
    source_field TEXT NOT NULL DEFAULT 'cases.term_ids',
    metadata_json TEXT NOT NULL DEFAULT '{}',
    PRIMARY KEY(legacy_term_id, legacy_case_id, term_position),
    FOREIGN KEY(legacy_term_id) REFERENCES legacy_dictionary_terms(legacy_term_id),
    FOREIGN KEY(v2_case_id) REFERENCES annotation_cases(case_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_legacy_term_case_links_case
    ON legacy_term_case_links(v2_case_id, term_position);

CREATE TABLE IF NOT EXISTS legacy_work_evidence_links (
    legacy_work_id INTEGER NOT NULL,
    legacy_evidence_id INTEGER PRIMARY KEY,
    legacy_case_id INTEGER NOT NULL,
    v2_case_id TEXT NOT NULL,
    v2_evidence_index INTEGER NOT NULL,
    legacy_term_id INTEGER,
    evidence_type TEXT,
    quote_sha256 TEXT,
    source_field TEXT NOT NULL DEFAULT 'evidences.work_id',
    metadata_json TEXT NOT NULL DEFAULT '{}',
    FOREIGN KEY(legacy_work_id) REFERENCES legacy_dictionary_works(legacy_work_id),
    FOREIGN KEY(legacy_term_id) REFERENCES legacy_dictionary_terms(legacy_term_id),
    FOREIGN KEY(v2_case_id, v2_evidence_index)
        REFERENCES annotation_evidences(case_id, evidence_index) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_legacy_work_evidence_links_work
    ON legacy_work_evidence_links(legacy_work_id, legacy_case_id);

CREATE INDEX IF NOT EXISTS idx_legacy_dictionary_terms_category
    ON legacy_dictionary_terms(category, term_type, usage_status);

CREATE INDEX IF NOT EXISTS idx_legacy_dictionary_works_usage
    ON legacy_dictionary_works(usage_status, title);

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
    operation_id TEXT,
    event_kind TEXT NOT NULL DEFAULT 'human_review',
    from_lifecycle TEXT,
    from_human_status TEXT,
    to_lifecycle TEXT,
    review_status TEXT NOT NULL CHECK(review_status IN ('pending', 'approved', 'rejected', 'uncertain')),
    review_note TEXT,
    review_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL,
    FOREIGN KEY(case_id) REFERENCES annotation_cases(case_id) ON DELETE CASCADE
);

-- Auxiliary human decisions for queue items that do not belong to one
-- annotation case: external edition/source and external passage resolution.
-- These events are separate from case lifecycle events so one external source
-- shared by many cases is not falsely represented by a single case review.
CREATE TABLE IF NOT EXISTS resolution_events (
    resolution_event_id INTEGER PRIMARY KEY AUTOINCREMENT,
    resolution_kind TEXT NOT NULL CHECK(resolution_kind IN (
        'external_source_resolution', 'external_passage_resolution'
    )),
    queue_item_id TEXT NOT NULL,
    external_source_id TEXT,
    case_id TEXT,
    evidence_index INTEGER,
    reviewer TEXT NOT NULL,
    operation_id TEXT NOT NULL UNIQUE,
    from_queue_status TEXT,
    to_queue_status TEXT NOT NULL,
    resolution_note TEXT,
    resolution_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL,
    FOREIGN KEY(external_source_id) REFERENCES external_source_registry(external_source_id),
    FOREIGN KEY(case_id, evidence_index)
        REFERENCES annotation_evidences(case_id, evidence_index)
        ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_resolution_events_queue_item
    ON resolution_events(resolution_kind, queue_item_id, created_at);

CREATE VIEW IF NOT EXISTS v_machine_cases AS
SELECT * FROM annotation_cases
WHERE lifecycle = 'machine_draft';

CREATE VIEW IF NOT EXISTS v_human_review_queue AS
SELECT * FROM annotation_cases
WHERE human_status IN ('pending', 'uncertain');

CREATE VIEW IF NOT EXISTS v_gold_cases AS
SELECT * FROM annotation_cases
WHERE lifecycle = 'gold' AND human_status = 'approved';
