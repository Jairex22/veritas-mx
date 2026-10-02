"""Repositorio de documentos, versiones, cambios de metadatos y aprobaciones."""
from __future__ import annotations

from typing import Any

from core.utils import new_id, now_iso
from repositories.base import BaseRepository

DOCUMENT_FIELDS = (
    "doc_code", "title", "description", "source_type", "owner", "approver", "area", "customer", "product",
    "line", "process", "station", "fl_module", "classification", "retention_policy", "tags", "language",
)


class DocumentRepository(BaseRepository):
    table = "documents"
    updatable = frozenset(set(DOCUMENT_FIELDS) - {"doc_code"} | {
        "is_active", "published_version_id", "updated_at", "deleted_at", "deleted_reason"})

    # --- documentos ---
    def create(self, meta: dict[str, Any], created_by: str, is_demo: bool = False) -> str:
        doc_id = new_id("doc-")
        ts = now_iso()
        cols = ["id", *DOCUMENT_FIELDS, "is_demo", "is_active", "created_by", "created_at", "updated_at"]
        values = [doc_id, *[meta.get(f, "") for f in DOCUMENT_FIELDS], int(is_demo), 1, created_by, ts, ts]
        self.db.execute(f"INSERT INTO documents ({', '.join(cols)}) VALUES ({','.join('?' for _ in cols)})",
                        values)
        return doc_id

    def get(self, doc_id: str) -> dict[str, Any] | None:
        return self.db.query_one("SELECT * FROM documents WHERE id = ?", (doc_id,))

    def get_by_code(self, doc_code: str) -> dict[str, Any] | None:
        return self.db.query_one("SELECT * FROM documents WHERE doc_code = ?", (doc_code,))

    def update(self, doc_id: str, **fields: Any) -> None:
        fields["updated_at"] = now_iso()
        self._update(doc_id, fields)

    def catalog(self, include_deleted: bool = False) -> list[dict[str, Any]]:
        sql = (
            "SELECT d.*, pv.version_label AS published_version, pv.status AS published_status, "
            "pv.effective_date, pv.review_date, pv.expiration_date, pv.content_hash, "
            "lv.version_label AS latest_version, lv.status AS latest_status, lv.id AS latest_version_id, "
            "(SELECT COUNT(*) FROM chunks c WHERE c.version_id = d.published_version_id) AS chunk_count "
            "FROM documents d "
            "LEFT JOIN document_versions pv ON pv.id = d.published_version_id "
            "LEFT JOIN document_versions lv ON lv.id = (SELECT id FROM document_versions v2 "
            "  WHERE v2.document_id = d.id ORDER BY v2.version_no DESC LIMIT 1) "
        )
        if not include_deleted:
            sql += "WHERE d.deleted_at IS NULL "
        sql += "ORDER BY d.doc_code"
        return self.db.query(sql)

    # --- versiones ---
    def next_version_no(self, doc_id: str) -> int:
        return int(self.db.scalar("SELECT COALESCE(MAX(version_no), 0) + 1 FROM document_versions "
                                  "WHERE document_id = ?", (doc_id,), default=1))

    def create_version(self, doc_id: str, data: dict[str, Any]) -> str:
        version_id = new_id("ver-")
        record = {"id": version_id, "document_id": doc_id, "created_at": now_iso(), **data}
        cols = list(record)
        self.db.execute(
            f"INSERT INTO document_versions ({', '.join(cols)}) VALUES ({','.join('?' for _ in cols)})",
            list(record.values()))
        return version_id

    def get_version(self, version_id: str) -> dict[str, Any] | None:
        return self.db.query_one("SELECT * FROM document_versions WHERE id = ?", (version_id,))

    def list_versions(self, doc_id: str) -> list[dict[str, Any]]:
        return self.db.query("SELECT * FROM document_versions WHERE document_id = ? ORDER BY version_no DESC",
                             (doc_id,))

    def versions_by_status(self, status: str) -> list[dict[str, Any]]:
        return self.db.query(
            "SELECT v.*, d.doc_code, d.title, d.classification, d.owner, d.source_type "
            "FROM document_versions v JOIN documents d ON d.id = v.document_id "
            "WHERE v.status = ? AND d.deleted_at IS NULL ORDER BY v.created_at", (status,))

    def all_versions(self) -> list[dict[str, Any]]:
        return self.db.query(
            "SELECT v.id, v.document_id, v.status, v.version_label, v.effective_date, v.review_date, "
            "v.expiration_date, v.created_at, v.archived_at, v.decided_at, d.doc_code, d.title, "
            "d.retention_policy, d.published_version_id, d.owner, d.deleted_at "
            "FROM document_versions v JOIN documents d ON d.id = v.document_id")

    def update_version(self, version_id: str, conn=None, **fields: Any) -> None:
        allowed = {"status", "submitted_by", "submitted_at", "decided_by", "decided_at", "decision_reason",
                   "published_at", "archived_at", "effective_date", "review_date", "expiration_date",
                   "injection_ack_by", "ever_approved", "extracted_text", "stored_path", "change_note"}
        unknown = set(fields) - allowed
        if unknown:
            raise ValueError(f"Campos de versión no permitidos: {unknown}")
        assignments = ", ".join(f"{c} = ?" for c in fields)
        sql = f"UPDATE document_versions SET {assignments} WHERE id = ?"  # noqa: S608
        params = [*fields.values(), version_id]
        if conn is not None:
            conn.execute(sql, params)
        else:
            self.db.execute(sql, params)

    def find_by_content_hash(self, content_hash: str) -> list[dict[str, Any]]:
        return self.db.query(
            "SELECT v.id, v.version_label, v.status, d.doc_code, d.title FROM document_versions v "
            "JOIN documents d ON d.id = v.document_id WHERE v.content_hash = ? AND d.deleted_at IS NULL",
            (content_hash,))

    # --- registro de cambios y aprobaciones ---
    def log_metadata_change(self, doc_id: str, field: str, old: Any, new: Any, user: str, reason: str) -> None:
        self.db.execute(
            "INSERT INTO metadata_changes (id, document_id, field, old_value, new_value, changed_by, changed_at, "
            "reason) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (new_id("mc-"), doc_id, field, None if old is None else str(old), None if new is None else str(new),
             user, now_iso(), reason))

    def metadata_changes(self, doc_id: str | None = None, limit: int = 500) -> list[dict[str, Any]]:
        if doc_id:
            return self.db.query("SELECT * FROM metadata_changes WHERE document_id = ? ORDER BY changed_at DESC "
                                 "LIMIT ?", (doc_id, limit))
        return self.db.query("SELECT m.*, d.doc_code FROM metadata_changes m LEFT JOIN documents d "
                             "ON d.id = m.document_id ORDER BY m.changed_at DESC LIMIT ?", (limit,))

    def log_approval(self, version_id: str, doc_id: str, action: str, actor: str, reason: str = "") -> None:
        self.db.execute("INSERT INTO approvals (id, version_id, document_id, action, actor, at, reason) "
                        "VALUES (?, ?, ?, ?, ?, ?, ?)",
                        (new_id("apr-"), version_id, doc_id, action, actor, now_iso(), reason))

    def approvals(self, doc_id: str | None = None, limit: int = 500) -> list[dict[str, Any]]:
        if doc_id:
            return self.db.query("SELECT a.*, v.version_label FROM approvals a LEFT JOIN document_versions v "
                                 "ON v.id = a.version_id WHERE a.document_id = ? ORDER BY a.at DESC LIMIT ?",
                                 (doc_id, limit))
        return self.db.query("SELECT a.*, d.doc_code, v.version_label FROM approvals a "
                             "LEFT JOIN documents d ON d.id = a.document_id "
                             "LEFT JOIN document_versions v ON v.id = a.version_id ORDER BY a.at DESC LIMIT ?",
                             (limit,))
