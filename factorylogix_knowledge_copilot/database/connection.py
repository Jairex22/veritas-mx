"""Acceso a SQLite con consultas parametrizadas (sin concatenación de entradas de usuario).

La clase `Database` encapsula el dialecto; para SQL Server se implementaría otra clase con la
misma interfaz (`execute`, `query`, `query_one`, `transaction`) usando pyodbc.
"""
from __future__ import annotations

import sqlite3
import threading
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator, Sequence

from core.utils import now_iso

SCHEMA_VERSION = 1
_SCHEMA_FILE = Path(__file__).with_name("schema.sql")


class Database:
    def __init__(self, path: Path | str):
        self.path = str(path)
        self._lock = threading.RLock()
        self._fts5: bool | None = None

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path, timeout=30, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute("PRAGMA busy_timeout=30000")
        return conn

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        with self._lock:
            conn = self._connect()
            try:
                conn.execute("BEGIN IMMEDIATE")
                yield conn
                conn.commit()
            except Exception:
                conn.rollback()
                raise
            finally:
                conn.close()

    def execute(self, sql: str, params: Sequence[Any] = ()) -> int:
        with self.transaction() as conn:
            cur = conn.execute(sql, tuple(params))
            return cur.rowcount

    def query(self, sql: str, params: Sequence[Any] = ()) -> list[dict[str, Any]]:
        with self._lock:
            conn = self._connect()
            try:
                return [dict(r) for r in conn.execute(sql, tuple(params)).fetchall()]
            finally:
                conn.close()

    def query_one(self, sql: str, params: Sequence[Any] = ()) -> dict[str, Any] | None:
        rows = self.query(sql, params)
        return rows[0] if rows else None

    def scalar(self, sql: str, params: Sequence[Any] = (), default: Any = None) -> Any:
        row = self.query_one(sql, params)
        if not row:
            return default
        value = next(iter(row.values()))
        return default if value is None else value

    @property
    def has_fts5(self) -> bool:
        if self._fts5 is None:
            try:
                conn = sqlite3.connect(":memory:")
                conn.execute("CREATE VIRTUAL TABLE t USING fts5(x)")
                conn.close()
                self._fts5 = True
            except sqlite3.OperationalError:
                self._fts5 = False
        return self._fts5

    def disable_fts5(self) -> None:
        """Fuerza el modo de respaldo BM25 en Python (pruebas / SQLite sin FTS5)."""
        self._fts5 = False

    def init_schema(self) -> None:
        Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        script = _SCHEMA_FILE.read_text(encoding="utf-8")
        with self._lock:
            conn = self._connect()
            try:
                conn.execute("PRAGMA journal_mode=WAL")
                conn.executescript(script)
                if self.has_fts5:
                    conn.execute(
                        "CREATE VIRTUAL TABLE IF NOT EXISTS chunks_fts USING fts5("
                        "chunk_id UNINDEXED, title, section, text, tokenize='unicode61 remove_diacritics 2')"
                    )
                current = conn.execute("SELECT MAX(version) FROM schema_version").fetchone()[0]
                if current is None:
                    conn.execute("INSERT INTO schema_version(version, applied_at) VALUES (?, ?)",
                                 (SCHEMA_VERSION, now_iso()))
                conn.commit()
            finally:
                conn.close()

    def integrity_ok(self) -> bool:
        return self.scalar("PRAGMA quick_check") == "ok"
