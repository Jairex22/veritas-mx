"""Auditoría de consultas, salud de conexión, historial y resultados de análisis."""
from __future__ import annotations

import json
from datetime import datetime, timezone

from database.db import Database
from models.results import ODataStatus, QueryResult


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class AuditRepository:
    def __init__(self, db: Database):
        self.db = db

    def record_query(self, r: QueryResult) -> None:
        with self.db.connection(write=True) as conn:
            conn.execute(
                """INSERT INTO QueryAudit (ts, data_source, entity, query, status, http_status, elapsed_ms,
                   wait_headers_ms, download_ms, parse_ms, attempts, rows, error)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (_now(), r.data_source, r.entity, r.query_description[:500], r.status.value, r.http_status,
                 round(r.elapsed_ms, 1), r.timings.get("wait_headers_ms"), r.timings.get("download_ms"),
                 r.timings.get("parse_ms"), r.attempts, len(r.rows), (r.error or "")[:500]))
            if r.status in (ODataStatus.VALIDATION_ERROR, ODataStatus.NOT_REQUESTED):
                return
            ok = r.ok
            conn.execute(
                """INSERT INTO ConnectionHealth (entity, data_source, last_status, last_http, last_elapsed_ms,
                   last_checked_at, last_success_at, last_error_at, last_error, consecutive_failures)
                   VALUES (?,?,?,?,?,?,?,?,?,?)
                   ON CONFLICT(entity, data_source) DO UPDATE SET
                     last_status=excluded.last_status, last_http=excluded.last_http,
                     last_elapsed_ms=excluded.last_elapsed_ms, last_checked_at=excluded.last_checked_at,
                     last_success_at=COALESCE(excluded.last_success_at, ConnectionHealth.last_success_at),
                     last_error_at=COALESCE(excluded.last_error_at, ConnectionHealth.last_error_at),
                     last_error=COALESCE(excluded.last_error, ConnectionHealth.last_error),
                     consecutive_failures=CASE WHEN ? THEN 0 ELSE ConnectionHealth.consecutive_failures + 1 END""",
                (r.entity, r.data_source, r.status.value, r.http_status, round(r.elapsed_ms, 1), _now(),
                 _now() if ok else None, None if ok else _now(), None if ok else (r.error or r.status.value)[:500],
                 0 if ok else 1, 1 if ok else 0))

    def health(self, data_source: str) -> list[dict]:
        with self.db.connection() as conn:
            return [dict(r) for r in conn.execute(
                "SELECT * FROM ConnectionHealth WHERE data_source=? ORDER BY entity", (data_source,))]

    def recent_queries(self, limit: int = 50) -> list[dict]:
        with self.db.connection() as conn:
            return [dict(r) for r in conn.execute("SELECT * FROM QueryAudit ORDER BY id DESC LIMIT ?", (limit,))]

    def add_search(self, data_source: str, module: str, term: str, summary: str) -> None:
        with self.db.connection(write=True) as conn:
            conn.execute("INSERT INTO SearchHistory (ts, data_source, module, term, summary) VALUES (?,?,?,?,?)",
                         (_now(), data_source, module, term[:200], summary[:300]))

    def searches(self, limit: int = 100) -> list[dict]:
        with self.db.connection() as conn:
            return [dict(r) for r in conn.execute("SELECT * FROM SearchHistory ORDER BY id DESC LIMIT ?", (limit,))]

    def clear_searches(self) -> None:
        with self.db.connection(write=True) as conn:
            conn.execute("DELETE FROM SearchHistory")

    def save_analysis(self, data_source: str, kind: str, subject: str, result: dict) -> None:
        with self.db.connection(write=True) as conn:
            conn.execute("INSERT INTO AnalysisResults (ts, data_source, kind, subject, result_json) VALUES (?,?,?,?,?)",
                         (_now(), data_source, kind, subject, json.dumps(result, ensure_ascii=False, default=str)))

    def latest_analysis(self, data_source: str, kind: str, subject: str) -> dict | None:
        with self.db.connection() as conn:
            row = conn.execute("SELECT result_json FROM AnalysisResults WHERE data_source=? AND kind=? AND subject=? "
                               "ORDER BY id DESC LIMIT 1", (data_source, kind, subject)).fetchone()
        return json.loads(row["result_json"]) if row else None
