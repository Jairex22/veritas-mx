"""Repositorios operativos: consultas, feedback, Q&A, incidentes, configuración, evaluaciones y errores."""
from __future__ import annotations

import json
from typing import Any

from core.logging_setup import redact
from core.text import truncate
from core.utils import new_id, now_iso
from repositories.base import BaseRepository


class QueryLogRepository(BaseRepository):
    table = "query_log"

    def insert(self, record: dict[str, Any], sources: list[dict[str, Any]]) -> str:
        query_id = record.get("id") or new_id("qry-")
        record = {**record, "id": query_id, "created_at": now_iso()}
        with self.db.transaction() as conn:
            cols = list(record)
            conn.execute(f"INSERT INTO query_log ({', '.join(cols)}) VALUES ({','.join('?' for _ in cols)})",
                         list(record.values()))
            for src in sources:
                conn.execute("INSERT INTO answer_sources (id, query_id, chunk_id, version_id, document_id, rank, "
                             "score) VALUES (?, ?, ?, ?, ?, ?, ?)",
                             (new_id("as-"), query_id, src["chunk_id"], src["version_id"], src["document_id"],
                              src["rank"], src["score"]))
        return query_id

    def get(self, query_id: str) -> dict[str, Any] | None:
        return self.db.query_one("SELECT * FROM query_log WHERE id = ?", (query_id,))

    def purge_expired_sentiment(self, now: str) -> int:
        return self.db.execute("UPDATE query_log SET sentiment_label = NULL, sentiment_expires_at = NULL "
                               "WHERE sentiment_expires_at IS NOT NULL AND sentiment_expires_at <= ?", (now,))

    def sources_for_query(self, query_id: str) -> list[dict[str, Any]]:
        return self.db.query("SELECT a.*, d.doc_code, d.title, v.version_label FROM answer_sources a "
                             "LEFT JOIN documents d ON d.id = a.document_id "
                             "LEFT JOIN document_versions v ON v.id = a.version_id WHERE a.query_id = ? "
                             "ORDER BY a.rank", (query_id,))


class FeedbackRepository(BaseRepository):
    table = "feedback"
    updatable = frozenset({"status", "reviewed_by", "reviewed_at", "review_note"})

    def create(self, **data: Any) -> str:
        fid = new_id("fb-")
        record = {"id": fid, "created_at": now_iso(), **data}
        cols = list(record)
        self.db.execute(f"INSERT INTO feedback ({', '.join(cols)}) VALUES ({','.join('?' for _ in cols)})",
                        list(record.values()))
        return fid

    def get(self, fid: str) -> dict[str, Any] | None:
        return self.db.query_one("SELECT * FROM feedback WHERE id = ?", (fid,))

    def list(self, status: str = "", corrections_only: bool = False) -> list[dict[str, Any]]:
        sql = "SELECT * FROM feedback WHERE 1=1"
        params: list[Any] = []
        if status:
            sql += " AND status = ?"
            params.append(status)
        if corrections_only:
            sql += " AND is_correction = 1"
        return self.db.query(sql + " ORDER BY created_at DESC", params)

    def update(self, fid: str, **fields: Any) -> None:
        self._update(fid, fields)


class QARepository(BaseRepository):
    table = "qa_pairs"
    updatable = frozenset({"status", "decided_by", "decided_at", "decision_reason", "document_id", "answer",
                           "question"})

    def create(self, **data: Any) -> str:
        qid = new_id("qa-")
        record = {"id": qid, "created_at": now_iso(), **data}
        cols = list(record)
        self.db.execute(f"INSERT INTO qa_pairs ({', '.join(cols)}) VALUES ({','.join('?' for _ in cols)})",
                        list(record.values()))
        return qid

    def get(self, qid: str) -> dict[str, Any] | None:
        return self.db.query_one("SELECT * FROM qa_pairs WHERE id = ?", (qid,))

    def list(self, status: str = "") -> list[dict[str, Any]]:
        if status:
            return self.db.query("SELECT * FROM qa_pairs WHERE status = ? ORDER BY created_at DESC", (status,))
        return self.db.query("SELECT * FROM qa_pairs ORDER BY created_at DESC")

    def update(self, qid: str, **fields: Any) -> None:
        self._update(qid, fields)


class IncidentRepository(BaseRepository):
    table = "incidents"
    updatable = frozenset({"status", "notes", "updated_at", "updated_by", "suggested_area", "urgency",
                           "preliminary_diagnosis"})

    def create(self, **data: Any) -> tuple[str, str]:
        iid = new_id("inc-")
        seq = int(self.db.scalar("SELECT COUNT(*) FROM incidents", default=0)) + 1
        code = f"INC-{now_iso()[:10].replace('-', '')}-{seq:04d}"
        ts = now_iso()
        record = {"id": iid, "code": code, "created_at": ts, "updated_at": ts, **data}
        cols = list(record)
        self.db.execute(f"INSERT INTO incidents ({', '.join(cols)}) VALUES ({','.join('?' for _ in cols)})",
                        list(record.values()))
        return iid, code

    def get(self, iid: str) -> dict[str, Any] | None:
        return self.db.query_one("SELECT * FROM incidents WHERE id = ?", (iid,))

    def list(self, status: str = "", created_by: str = "") -> list[dict[str, Any]]:
        sql = "SELECT * FROM incidents WHERE 1=1"
        params: list[Any] = []
        if status:
            sql += " AND status = ?"
            params.append(status)
        if created_by:
            sql += " AND created_by = ?"
            params.append(created_by)
        return self.db.query(sql + " ORDER BY created_at DESC", params)

    def update(self, iid: str, **fields: Any) -> None:
        fields["updated_at"] = now_iso()
        self._update(iid, fields)


class SettingsRepository(BaseRepository):
    table = "app_settings"

    def all(self) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for row in self.db.query("SELECT key, value FROM app_settings"):
            try:
                result[row["key"]] = json.loads(row["value"])
            except json.JSONDecodeError:
                result[row["key"]] = row["value"]
        return result

    def put(self, key: str, value: Any, user: str) -> None:
        self.db.execute("INSERT INTO app_settings (key, value, updated_by, updated_at) VALUES (?, ?, ?, ?) "
                        "ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_by = excluded.updated_by, "
                        "updated_at = excluded.updated_at", (key, json.dumps(value), user, now_iso()))


class EvaluationRepository(BaseRepository):
    table = "evaluation_runs"

    def save(self, started_at: str, run_by: str, summary: dict[str, Any], details: list[dict[str, Any]]) -> str:
        rid = new_id("eval-")
        self.db.execute("INSERT INTO evaluation_runs (id, started_at, finished_at, run_by, summary, details) "
                        "VALUES (?, ?, ?, ?, ?, ?)",
                        (rid, started_at, now_iso(), run_by, json.dumps(summary), json.dumps(details)))
        return rid

    def list(self, limit: int = 20) -> list[dict[str, Any]]:
        rows = self.db.query("SELECT * FROM evaluation_runs ORDER BY finished_at DESC LIMIT ?", (limit,))
        for row in rows:
            row["summary"] = json.loads(row["summary"])
            row["details"] = json.loads(row["details"])
        return rows


class ErrorRepository(BaseRepository):
    table = "system_errors"

    def record(self, component: str, error: BaseException | str, correlation_id: str = "") -> None:
        error_type = type(error).__name__ if isinstance(error, BaseException) else "Error"
        self.db.execute("INSERT INTO system_errors (id, ts, component, error_type, message, correlation_id) "
                        "VALUES (?, ?, ?, ?, ?, ?)",
                        (new_id("err-"), now_iso(), component, error_type, truncate(redact(str(error)), 400),
                         correlation_id))

    def list(self, limit: int = 200) -> list[dict[str, Any]]:
        return self.db.query("SELECT * FROM system_errors ORDER BY ts DESC LIMIT ?", (limit,))
