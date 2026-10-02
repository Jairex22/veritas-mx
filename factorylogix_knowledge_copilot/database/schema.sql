-- FactoryLogix Knowledge Copilot - esquema SQLite (v1)
-- Tipos y SQL estándar para facilitar la migración a SQL Server (ver docs/ESQUEMA_BASE_DATOS.md).

CREATE TABLE IF NOT EXISTS schema_version (
    version     INTEGER NOT NULL,
    applied_at  TEXT    NOT NULL
);

CREATE TABLE IF NOT EXISTS users (
    id                    TEXT PRIMARY KEY,
    username              TEXT NOT NULL UNIQUE COLLATE NOCASE,
    display_name          TEXT NOT NULL,
    role                  TEXT NOT NULL,
    password_hash         TEXT NOT NULL,
    must_change_password  INTEGER NOT NULL DEFAULT 1,
    is_active             INTEGER NOT NULL DEFAULT 1,
    failed_attempts       INTEGER NOT NULL DEFAULT 0,
    locked_until          TEXT,
    auth_source           TEXT NOT NULL DEFAULT 'local',
    preferred_language    TEXT NOT NULL DEFAULT 'es',
    is_demo               INTEGER NOT NULL DEFAULT 0,
    created_at            TEXT NOT NULL,
    updated_at            TEXT NOT NULL,
    last_login_at         TEXT,
    password_changed_at   TEXT
);

CREATE TABLE IF NOT EXISTS sessions (
    id            TEXT PRIMARY KEY,
    user_id       TEXT NOT NULL REFERENCES users(id),
    started_at    TEXT NOT NULL,
    last_seen_at  TEXT NOT NULL,
    ended_at      TEXT,
    end_reason    TEXT
);

CREATE TABLE IF NOT EXISTS documents (
    id                    TEXT PRIMARY KEY,
    doc_code              TEXT NOT NULL UNIQUE,
    title                 TEXT NOT NULL,
    description           TEXT NOT NULL DEFAULT '',
    source_type           TEXT NOT NULL,
    owner                 TEXT NOT NULL DEFAULT '',
    approver              TEXT NOT NULL DEFAULT '',
    area                  TEXT NOT NULL DEFAULT '',
    customer              TEXT NOT NULL DEFAULT '',
    product               TEXT NOT NULL DEFAULT '',
    line                  TEXT NOT NULL DEFAULT '',
    process               TEXT NOT NULL DEFAULT '',
    station               TEXT NOT NULL DEFAULT '',
    fl_module             TEXT NOT NULL DEFAULT '',
    classification        TEXT NOT NULL,
    retention_policy      TEXT NOT NULL,
    tags                  TEXT NOT NULL DEFAULT '',
    language              TEXT NOT NULL DEFAULT 'es',
    is_demo               INTEGER NOT NULL DEFAULT 0,
    is_active             INTEGER NOT NULL DEFAULT 1,
    published_version_id  TEXT,
    created_by            TEXT NOT NULL,
    created_at            TEXT NOT NULL,
    updated_at            TEXT NOT NULL,
    deleted_at            TEXT,
    deleted_reason        TEXT
);

CREATE TABLE IF NOT EXISTS document_versions (
    id                TEXT PRIMARY KEY,
    document_id       TEXT NOT NULL REFERENCES documents(id),
    version_no        INTEGER NOT NULL,
    version_label     TEXT NOT NULL,
    status            TEXT NOT NULL,
    content_hash      TEXT NOT NULL,
    file_hash         TEXT,
    file_name         TEXT,
    stored_path       TEXT,
    file_kind         TEXT,
    size_bytes        INTEGER,
    page_count        INTEGER,
    extracted_text    TEXT NOT NULL,
    injection_flags   TEXT NOT NULL DEFAULT '',
    injection_ack_by  TEXT,
    duplicate_of      TEXT,
    effective_date    TEXT,
    review_date       TEXT,
    expiration_date   TEXT,
    change_note       TEXT NOT NULL DEFAULT '',
    created_by        TEXT NOT NULL,
    created_at        TEXT NOT NULL,
    submitted_by      TEXT,
    submitted_at      TEXT,
    decided_by        TEXT,
    decided_at        TEXT,
    decision_reason   TEXT,
    ever_approved     INTEGER NOT NULL DEFAULT 0,
    published_at      TEXT,
    archived_at       TEXT,
    UNIQUE (document_id, version_no)
);

CREATE TABLE IF NOT EXISTS chunks (
    id               TEXT PRIMARY KEY,
    version_id       TEXT NOT NULL REFERENCES document_versions(id),
    document_id      TEXT NOT NULL REFERENCES documents(id),
    chunk_index      INTEGER NOT NULL,
    section          TEXT NOT NULL DEFAULT '',
    page             INTEGER,
    text             TEXT NOT NULL,
    char_count       INTEGER NOT NULL,
    embedding        BLOB,
    embedding_model  TEXT,
    injection_flag   INTEGER NOT NULL DEFAULT 0,
    created_at       TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_chunks_version ON chunks(version_id);
CREATE INDEX IF NOT EXISTS ix_versions_doc ON document_versions(document_id);

CREATE TABLE IF NOT EXISTS metadata_changes (
    id           TEXT PRIMARY KEY,
    document_id  TEXT NOT NULL,
    field        TEXT NOT NULL,
    old_value    TEXT,
    new_value    TEXT,
    changed_by   TEXT NOT NULL,
    changed_at   TEXT NOT NULL,
    reason       TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS approvals (
    id          TEXT PRIMARY KEY,
    version_id  TEXT NOT NULL,
    document_id TEXT NOT NULL,
    action      TEXT NOT NULL,
    actor       TEXT NOT NULL,
    at          TEXT NOT NULL,
    reason      TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS query_log (
    id                    TEXT PRIMARY KEY,
    user_id               TEXT NOT NULL,
    role                  TEXT NOT NULL,
    correlation_id        TEXT NOT NULL,
    question              TEXT NOT NULL,
    language              TEXT NOT NULL,
    answered              INTEGER NOT NULL,
    confidence            REAL,
    confidence_level      TEXT,
    latency_ms            INTEGER NOT NULL,
    mode                  TEXT NOT NULL,
    conflict              INTEGER NOT NULL DEFAULT 0,
    topic                 TEXT NOT NULL DEFAULT '',
    filters               TEXT NOT NULL DEFAULT '',
    sentiment_label       TEXT,
    sentiment_expires_at  TEXT,
    created_at            TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_query_created ON query_log(created_at);

CREATE TABLE IF NOT EXISTS answer_sources (
    id           TEXT PRIMARY KEY,
    query_id     TEXT NOT NULL,
    chunk_id     TEXT NOT NULL,
    version_id   TEXT NOT NULL,
    document_id  TEXT NOT NULL,
    rank         INTEGER NOT NULL,
    score        REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_answer_sources_doc ON answer_sources(document_id);

CREATE TABLE IF NOT EXISTS feedback (
    id               TEXT PRIMARY KEY,
    query_id         TEXT,
    user_id          TEXT NOT NULL,
    rating           TEXT NOT NULL,
    comment          TEXT NOT NULL DEFAULT '',
    is_correction    INTEGER NOT NULL DEFAULT 0,
    question         TEXT NOT NULL DEFAULT '',
    original_answer  TEXT NOT NULL DEFAULT '',
    proposed_answer  TEXT NOT NULL DEFAULT '',
    status           TEXT NOT NULL,
    reviewed_by      TEXT,
    reviewed_at      TEXT,
    review_note      TEXT,
    created_at       TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS qa_pairs (
    id                  TEXT PRIMARY KEY,
    question            TEXT NOT NULL,
    answer              TEXT NOT NULL,
    fl_module           TEXT NOT NULL DEFAULT '',
    classification      TEXT NOT NULL,
    language            TEXT NOT NULL DEFAULT 'es',
    status              TEXT NOT NULL,
    created_by          TEXT NOT NULL,
    created_at          TEXT NOT NULL,
    decided_by          TEXT,
    decided_at          TEXT,
    decision_reason     TEXT,
    document_id         TEXT,
    source_feedback_id  TEXT
);

CREATE TABLE IF NOT EXISTS incidents (
    id                     TEXT PRIMARY KEY,
    code                   TEXT NOT NULL UNIQUE,
    created_by             TEXT NOT NULL,
    created_by_role        TEXT NOT NULL,
    created_at             TEXT NOT NULL,
    question               TEXT NOT NULL DEFAULT '',
    answer                 TEXT NOT NULL DEFAULT '',
    work_order             TEXT NOT NULL DEFAULT '',
    serial_number          TEXT NOT NULL DEFAULT '',
    assembly               TEXT NOT NULL DEFAULT '',
    station                TEXT NOT NULL DEFAULT '',
    operation              TEXT NOT NULL DEFAULT '',
    error_message          TEXT NOT NULL DEFAULT '',
    attachment_path        TEXT,
    sources                TEXT NOT NULL DEFAULT '',
    preliminary_diagnosis  TEXT NOT NULL DEFAULT '',
    urgency                TEXT NOT NULL,
    suggested_area         TEXT NOT NULL DEFAULT '',
    status                 TEXT NOT NULL,
    notes                  TEXT NOT NULL DEFAULT '',
    updated_at             TEXT NOT NULL,
    updated_by             TEXT NOT NULL
);

-- Auditoría: append-only con cadena de hashes. UPDATE/DELETE bloqueados por triggers.
CREATE TABLE IF NOT EXISTS audit_log (
    seq             INTEGER PRIMARY KEY AUTOINCREMENT,
    id              TEXT NOT NULL UNIQUE,
    ts              TEXT NOT NULL,
    username        TEXT NOT NULL,
    role            TEXT NOT NULL,
    action          TEXT NOT NULL,
    object_type     TEXT NOT NULL,
    object_id       TEXT NOT NULL,
    result          TEXT NOT NULL,
    reason          TEXT NOT NULL DEFAULT '',
    correlation_id  TEXT NOT NULL,
    details         TEXT NOT NULL DEFAULT '',
    prev_hash       TEXT NOT NULL,
    hash            TEXT NOT NULL
);
CREATE TRIGGER IF NOT EXISTS audit_no_update BEFORE UPDATE ON audit_log
BEGIN SELECT RAISE(ABORT, 'audit_log is append-only'); END;
CREATE TRIGGER IF NOT EXISTS audit_no_delete BEFORE DELETE ON audit_log
BEGIN SELECT RAISE(ABORT, 'audit_log is append-only'); END;

CREATE TABLE IF NOT EXISTS app_settings (
    key         TEXT PRIMARY KEY,
    value       TEXT NOT NULL,
    updated_by  TEXT NOT NULL,
    updated_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS evaluation_runs (
    id           TEXT PRIMARY KEY,
    started_at   TEXT NOT NULL,
    finished_at  TEXT NOT NULL,
    run_by       TEXT NOT NULL,
    summary      TEXT NOT NULL,
    details      TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS system_errors (
    id              TEXT PRIMARY KEY,
    ts              TEXT NOT NULL,
    component       TEXT NOT NULL,
    error_type      TEXT NOT NULL,
    message         TEXT NOT NULL,
    correlation_id  TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS index_state (
    key    TEXT PRIMARY KEY,
    value  TEXT NOT NULL
);
