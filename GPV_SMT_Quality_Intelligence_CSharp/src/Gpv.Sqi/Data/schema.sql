-- GPV SMT Quality Intelligence - esquema SQLite
-- Nunca se almacenan contraseñas ni cabeceras de autenticación.
-- data_source separa estrictamente 'live' de 'demo' para no mezclar datos.

PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS SchemaVersion (version INTEGER NOT NULL);

-- dedup_key: 'key:<ODataKey>' si ODataKey es un GUID no vacío; en otro caso
-- 'hash:<sha256 del registro canónico>'. Nunca se asume único el GUID vacío.
CREATE TABLE IF NOT EXISTS CachedSMTEvents (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    dedup_key     TEXT NOT NULL,
    data_source   TEXT NOT NULL CHECK (data_source IN ('live','demo')),
    identifier    TEXT,
    batch         TEXT,
    assembly      TEXT,
    customer      TEXT,
    operation     TEXT,
    event_date    TEXT,
    event_utc     TEXT,
    odata_key     TEXT,
    raw_json      TEXT NOT NULL,
    first_seen_at TEXT NOT NULL,
    last_seen_at  TEXT NOT NULL,
    UNIQUE (data_source, dedup_key)
);
CREATE INDEX IF NOT EXISTS ix_smt_identifier ON CachedSMTEvents (data_source, identifier);
CREATE INDEX IF NOT EXISTS ix_smt_batch ON CachedSMTEvents (data_source, batch);
CREATE INDEX IF NOT EXISTS ix_smt_event_utc ON CachedSMTEvents (data_source, event_utc);

CREATE TABLE IF NOT EXISTS CachedQualityDefects (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    dedup_key     TEXT NOT NULL,
    data_source   TEXT NOT NULL CHECK (data_source IN ('live','demo')),
    defect_id     TEXT,
    identifier    TEXT,
    batch         TEXT,
    assembly      TEXT,
    defect_status TEXT,
    line          TEXT,
    date_created  TEXT,
    created_utc   TEXT,
    odata_key     TEXT,
    raw_json      TEXT NOT NULL,
    first_seen_at TEXT NOT NULL,
    last_seen_at  TEXT NOT NULL,
    UNIQUE (data_source, dedup_key)
);
CREATE INDEX IF NOT EXISTS ix_qd_identifier ON CachedQualityDefects (data_source, identifier);
CREATE INDEX IF NOT EXISTS ix_qd_defect ON CachedQualityDefects (data_source, defect_id);
CREATE INDEX IF NOT EXISTS ix_qd_batch ON CachedQualityDefects (data_source, batch);
CREATE INDEX IF NOT EXISTS ix_qd_created ON CachedQualityDefects (data_source, created_utc);

-- Varias filas pueden compartir DefectID: la clave hash incluye hora, estado,
-- operación, estación, operador y comentario, de modo que nunca se sobrescriben.
CREATE TABLE IF NOT EXISTS CachedQualityHistory (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    dedup_key      TEXT NOT NULL,
    data_source    TEXT NOT NULL CHECK (data_source IN ('live','demo')),
    defect_id      TEXT,
    identifier     TEXT,
    history_time   TEXT,
    history_utc    TEXT,
    history_status TEXT,
    operation      TEXT,
    odata_key      TEXT,
    raw_json       TEXT NOT NULL,
    first_seen_at  TEXT NOT NULL,
    last_seen_at   TEXT NOT NULL,
    UNIQUE (data_source, dedup_key)
);
CREATE INDEX IF NOT EXISTS ix_qh_defect ON CachedQualityHistory (data_source, defect_id);
CREATE INDEX IF NOT EXISTS ix_qh_identifier ON CachedQualityHistory (data_source, identifier);
CREATE INDEX IF NOT EXISTS ix_qh_time ON CachedQualityHistory (data_source, history_utc);

CREATE TABLE IF NOT EXISTS QueryAudit (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    ts            TEXT NOT NULL,
    data_source   TEXT NOT NULL,
    entity        TEXT NOT NULL,
    query         TEXT,
    status        TEXT NOT NULL,
    http_status   INTEGER,
    elapsed_ms    REAL,
    wait_headers_ms REAL,
    download_ms   REAL,
    parse_ms      REAL,
    attempts      INTEGER,
    rows          INTEGER,
    error         TEXT
);
CREATE INDEX IF NOT EXISTS ix_audit_ts ON QueryAudit (ts);

-- Historial de búsquedas del usuario (módulos).
CREATE TABLE IF NOT EXISTS SearchHistory (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    ts          TEXT NOT NULL,
    data_source TEXT NOT NULL,
    module      TEXT NOT NULL,
    term        TEXT NOT NULL,
    summary     TEXT
);
CREATE INDEX IF NOT EXISTS ix_search_ts ON SearchHistory (ts);

CREATE TABLE IF NOT EXISTS ConnectionHealth (
    entity          TEXT NOT NULL,
    data_source     TEXT NOT NULL,
    last_status     TEXT,
    last_http       INTEGER,
    last_elapsed_ms REAL,
    last_checked_at TEXT,
    last_success_at TEXT,
    last_error_at   TEXT,
    last_error      TEXT,
    consecutive_failures INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (entity, data_source)
);

CREATE TABLE IF NOT EXISTS AnalysisResults (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    ts          TEXT NOT NULL,
    data_source TEXT NOT NULL,
    kind        TEXT NOT NULL,
    subject     TEXT NOT NULL,
    result_json TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_analysis_subject ON AnalysisResults (data_source, kind, subject, ts);

CREATE TABLE IF NOT EXISTS ApplicationSettings (
    key        TEXT PRIMARY KEY,
    value_json TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
