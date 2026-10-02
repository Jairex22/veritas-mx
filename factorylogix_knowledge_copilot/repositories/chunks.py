"""Repositorio de fragmentos (chunks), índice FTS5 y elegibilidad para recuperación."""
from __future__ import annotations

import re
from typing import Any, Iterable

import numpy as np

from core.utils import new_id, now_iso
from database.connection import Database
from models.domain import SearchFilters

_FILTER_COLUMNS = {"customer": "d.customer", "product": "d.product", "line": "d.line", "process": "d.process",
                   "station": "d.station", "module": "d.fl_module"}


class ChunkRepository:
    def __init__(self, db: Database):
        self.db = db

    def replace_for_version(self, version_id: str, document_id: str, title: str,
                            chunks: Iterable[dict[str, Any]], embeddings: np.ndarray | None,
                            model_name: str) -> int:
        chunk_list = list(chunks)
        ts = now_iso()
        with self.db.transaction() as conn:
            old_ids = [r[0] for r in conn.execute("SELECT id FROM chunks WHERE version_id = ?", (version_id,))]
            if old_ids and self.db.has_fts5:
                conn.executemany("DELETE FROM chunks_fts WHERE chunk_id = ?", [(i,) for i in old_ids])
            conn.execute("DELETE FROM chunks WHERE version_id = ?", (version_id,))
            for idx, chunk in enumerate(chunk_list):
                chunk_id = new_id("chk-")
                blob = embeddings[idx].astype(np.float32).tobytes() if embeddings is not None else None
                conn.execute(
                    "INSERT INTO chunks (id, version_id, document_id, chunk_index, section, page, text, char_count, "
                    "embedding, embedding_model, injection_flag, created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                    (chunk_id, version_id, document_id, idx, chunk.get("section", ""), chunk.get("page"),
                     chunk["text"], len(chunk["text"]), blob, model_name, int(chunk.get("injection_flag", 0)), ts))
                if self.db.has_fts5:
                    conn.execute("INSERT INTO chunks_fts (chunk_id, title, section, text) VALUES (?, ?, ?, ?)",
                                 (chunk_id, title, chunk.get("section", ""), chunk["text"]))
        return len(chunk_list)

    def delete_for_version(self, version_id: str) -> None:
        with self.db.transaction() as conn:
            ids = [r[0] for r in conn.execute("SELECT id FROM chunks WHERE version_id = ?", (version_id,))]
            if ids and self.db.has_fts5:
                conn.executemany("DELETE FROM chunks_fts WHERE chunk_id = ?", [(i,) for i in ids])
            conn.execute("DELETE FROM chunks WHERE version_id = ?", (version_id,))

    def for_version(self, version_id: str) -> list[dict[str, Any]]:
        return self.db.query("SELECT id, chunk_index, section, page, text, injection_flag FROM chunks "
                             "WHERE version_id = ? ORDER BY chunk_index", (version_id,))

    def get(self, chunk_id: str) -> dict[str, Any] | None:
        return self.db.query_one("SELECT * FROM chunks WHERE id = ?", (chunk_id,))

    def eligible(self, clearance: Iterable[str], filters: SearchFilters | None, today_iso: str,
                 include_version_ids: Iterable[str] = ()) -> list[dict[str, Any]]:
        """Chunks recuperables: documento activo, versión publicada y aprobada, vigente y con
        clasificación permitida para el rol. `include_version_ids` permite pruebas previas a publicar."""
        clearance = list(clearance)
        extra = list(include_version_ids)
        sql = (
            "SELECT c.id AS chunk_id, c.document_id, c.version_id, c.section, c.page, c.text, c.embedding, "
            "c.injection_flag, d.doc_code, d.title, d.source_type, d.classification, d.owner, d.is_demo, "
            "d.fl_module, d.customer, d.product, d.line, d.station, d.process, v.version_label, "
            "v.effective_date, v.review_date, v.expiration_date "
            "FROM chunks c JOIN document_versions v ON v.id = c.version_id "
            "JOIN documents d ON d.id = c.document_id "
            f"WHERE d.deleted_at IS NULL AND d.classification IN ({','.join('?' for _ in clearance) or 'NULL'}) "
        )
        params: list[Any] = [*clearance]
        published = ("(d.is_active = 1 AND v.id = d.published_version_id AND v.status = 'Approved' "
                     "AND (v.effective_date IS NULL OR v.effective_date = '' OR v.effective_date <= ?) "
                     "AND (v.expiration_date IS NULL OR v.expiration_date = '' OR v.expiration_date > ?))")
        params += [today_iso, today_iso]
        if extra:
            sql += f"AND ({published} OR v.id IN ({','.join('?' for _ in extra)})) "
            params += extra
        else:
            sql += f"AND {published} "
        if filters:
            for key, value in filters.active().items():
                column = _FILTER_COLUMNS.get(key)
                if column:
                    # Documentos genéricos (campo vacío) aplican a todos los filtros.
                    sql += f"AND ({column} = '' OR LOWER({column}) = LOWER(?)) "
                    params.append(value)
        return self.db.query(sql, params)

    def fts_search(self, terms: list[str], limit: int) -> list[tuple[str, float]]:
        """BM25 de FTS5. Los términos se citan para evitar inyección de sintaxis FTS."""
        if not self.db.has_fts5 or not terms:
            return []
        safe = []
        for term in terms:
            cleaned = re.sub(r"[^0-9a-zA-Z]", "", term)
            if len(cleaned) >= 2:
                safe.append(f'"{cleaned}"*' if len(cleaned) >= 4 else f'"{cleaned}"')
        if not safe:
            return []
        match = " OR ".join(dict.fromkeys(safe))
        rows = self.db.query("SELECT chunk_id, bm25(chunks_fts, 0.0, 2.0, 1.5, 1.0) AS score FROM chunks_fts "
                             "WHERE chunks_fts MATCH ? ORDER BY score LIMIT ?", (match, int(limit)))
        # bm25() devuelve valores negativos: más negativo = más relevante.
        return [(r["chunk_id"], -float(r["score"])) for r in rows]

    def counts(self) -> dict[str, int]:
        total = int(self.db.scalar("SELECT COUNT(*) FROM chunks", default=0))
        embedded = int(self.db.scalar("SELECT COUNT(*) FROM chunks WHERE embedding IS NOT NULL", default=0))
        fts = int(self.db.scalar("SELECT COUNT(*) FROM chunks_fts", default=0)) if self.db.has_fts5 else 0
        return {"chunks": total, "embedded": embedded, "fts_rows": fts}

    def versions_with_chunks(self) -> list[dict[str, Any]]:
        return self.db.query("SELECT v.id AS version_id, v.document_id, v.extracted_text, d.title, d.doc_code "
                             "FROM document_versions v JOIN documents d ON d.id = v.document_id "
                             "WHERE d.deleted_at IS NULL AND v.extracted_text <> ''")
