"""Conexión SQLite (una conexión por operación, segura entre hilos)."""
from __future__ import annotations

import sqlite3
import threading
from contextlib import contextmanager
from pathlib import Path

SCHEMA_VERSION = 1
SCHEMA_FILE = Path(__file__).resolve().parent / "schema.sql"


class Database:
    def __init__(self, path: Path | str):
        self.path = str(path)
        if self.path != ":memory:":
            Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        self._write_lock = threading.Lock()
        self._memory_conn = sqlite3.connect(":memory:", check_same_thread=False) if self.path == ":memory:" else None
        self.initialize()

    def _connect(self) -> sqlite3.Connection:
        if self._memory_conn is not None:
            return self._memory_conn
        conn = sqlite3.connect(self.path, timeout=10)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        return conn

    @contextmanager
    def connection(self, write: bool = False):
        lock = self._write_lock if (write or self._memory_conn is not None) else None
        if lock:
            lock.acquire()
        conn = self._connect()
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            if write:
                conn.commit()
        except Exception:
            if write:
                conn.rollback()
            raise
        finally:
            if self._memory_conn is None:
                conn.close()
            if lock:
                lock.release()

    def initialize(self) -> None:
        with self.connection(write=True) as conn:
            conn.executescript(SCHEMA_FILE.read_text(encoding="utf-8"))
            row = conn.execute("SELECT version FROM SchemaVersion").fetchone()
            if row is None:
                conn.execute("INSERT INTO SchemaVersion (version) VALUES (?)", (SCHEMA_VERSION,))
