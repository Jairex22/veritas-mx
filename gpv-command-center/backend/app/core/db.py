"""Base de datos propia de la aplicación (SQLite).

Separada por completo de FactoryLogix: sólo almacena sesiones, auditoría,
idempotencia y trabajos de impresión. Nunca se escribe en tablas de FactoryLogix.
"""
from __future__ import annotations

import sqlite3
import threading
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

SCHEMA = """
CREATE TABLE IF NOT EXISTS sessions (
    token_hash   TEXT PRIMARY KEY,
    username     TEXT NOT NULL,
    display_name TEXT NOT NULL,
    role         TEXT NOT NULL,
    provider     TEXT NOT NULL,
    csrf_token   TEXT NOT NULL,
    created_at   TEXT NOT NULL,
    expires_at   TEXT NOT NULL,
    last_seen_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS audit_log (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    ts             TEXT NOT NULL,
    correlation_id TEXT,
    username       TEXT,
    role           TEXT,
    mode           TEXT NOT NULL,
    category       TEXT NOT NULL,
    action         TEXT NOT NULL,
    target         TEXT,
    outcome        TEXT NOT NULL,
    details        TEXT,
    prev_hash      TEXT NOT NULL,
    hash           TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_audit_ts ON audit_log(ts);
CREATE TABLE IF NOT EXISTS access_log (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    ts             TEXT NOT NULL,
    correlation_id TEXT,
    username       TEXT,
    method         TEXT NOT NULL,
    path           TEXT NOT NULL,
    status         INTEGER NOT NULL,
    duration_ms    REAL NOT NULL,
    client_ip      TEXT
);
CREATE TABLE IF NOT EXISTS idempotency (
    key          TEXT PRIMARY KEY,
    username     TEXT NOT NULL,
    action_id    TEXT NOT NULL,
    request_hash TEXT NOT NULL,
    status       TEXT NOT NULL,
    response     TEXT,
    created_at   TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS print_jobs (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    ts           TEXT NOT NULL,
    username     TEXT NOT NULL,
    printer_id   TEXT NOT NULL,
    template_id  TEXT NOT NULL,
    serial       TEXT,
    is_reprint   INTEGER NOT NULL,
    reason       TEXT,
    mode         TEXT NOT NULL,
    outcome      TEXT NOT NULL,
    message      TEXT,
    correlation_id TEXT
);
"""


class Database:
    def __init__(self, path: Path | str):
        self.path = str(path)
        if self.path != ":memory:":
            Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(self.path, check_same_thread=False, isolation_level=None)
        self._conn.row_factory = sqlite3.Row
        self._lock = threading.RLock()
        with self._lock:
            self._conn.execute("PRAGMA journal_mode=WAL" if self.path != ":memory:" else "PRAGMA journal_mode=MEMORY")
            self._conn.executescript(SCHEMA)

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        with self._lock:
            self._conn.execute("BEGIN IMMEDIATE")
            try:
                yield self._conn
                self._conn.execute("COMMIT")
            except Exception:
                self._conn.execute("ROLLBACK")
                raise

    def query(self, sql: str, params: tuple = ()) -> list[sqlite3.Row]:
        with self._lock:
            return list(self._conn.execute(sql, params).fetchall())

    def execute(self, sql: str, params: tuple = ()) -> sqlite3.Cursor:
        with self._lock:
            return self._conn.execute(sql, params)

    def close(self) -> None:
        with self._lock:
            self._conn.close()
