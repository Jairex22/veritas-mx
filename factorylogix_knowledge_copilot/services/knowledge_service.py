"""Knowledge Training Center: carga, versionado, aprobación, publicación, rollback y reindexación.

"Entrenar" mediante RAG = agregar y aprobar conocimiento recuperable. NO modifica pesos de modelos.
"""
from __future__ import annotations

import difflib
import json
import shutil
from datetime import timedelta
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np

from core.config import Settings
from core.errors import NotFound, PermissionDenied, ValidationError, WorkflowError
from core.logging_setup import get_logger
from core.text import normalize
from core.utils import now_iso, parse_date, today
from governance.lifecycle import check_transition
from governance.policies import missing_metadata
from ingestion.pipeline import IngestionPipeline, PreparedContent, display_text
from models.domain import AuthenticatedUser, Classification, DocStatus, SourceType
from rag.conflicts import detect_conflicts
from rag.embeddings import Embedder
from rag.retriever import HybridRetriever
from repositories.chunks import ChunkRepository
from repositories.documents import DocumentRepository
from repositories.operations import QARepository
from schemas.validation import DocumentMetadataInput
from security.injection import InjectionDetector
from security.rbac import require
from security.sanitize import clean_user_text, safe_filename, safe_join
from services.audit_helper import Auditor

log = get_logger("knowledge")

RAG_TRAINING_NOTICE_ES = (
    "“Entrenar” al asistente mediante RAG significa AGREGAR y APROBAR conocimiento recuperable "
    "(documentos, versiones y Q&A). No modifica automáticamente los pesos de ningún modelo y el bot no "
    "aprende de las conversaciones: toda corrección pasa por revisión y aprobación humana.")
RAG_TRAINING_NOTICE_EN = (
    "“Training” the assistant through RAG means ADDING and APPROVING retrievable knowledge (documents, versions "
    "and Q&A). It never modifies model weights automatically and the bot does not learn from conversations: "
    "every correction goes through human review and approval.")


@dataclass
class IngestReport:
    document_id: str
    version_id: str
    version_label: str
    chunk_count: int
    duplicates: list[dict[str, Any]] = field(default_factory=list)
    near_duplicates: list[dict[str, Any]] = field(default_factory=list)
    injection_matches: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    preview: str = ""


@dataclass
class CheckResult:
    name: str
    ok: bool
    critical: bool
    detail: str = ""


class KnowledgeService:
    def __init__(self, settings: Settings, docs: DocumentRepository, chunks: ChunkRepository, audit: Auditor,
                 embedder: Embedder, retriever: HybridRetriever, detector: InjectionDetector, qa: QARepository):
        self.settings = settings
        self.docs = docs
        self.chunks = chunks
        self.audit = audit
        self.embedder = embedder
        self.retriever = retriever
        self.detector = detector
        self.qa = qa
        self.pipeline = IngestionPipeline(settings)
        self.files_dir = settings.path("paths.files_dir")

    # ------------------------------------------------------------------ util
    def _version(self, version_id: str) -> dict[str, Any]:
        version = self.docs.get_version(version_id)
        if not version:
            raise NotFound("Versión no encontrada.")
        return version

    def _document(self, doc_id: str) -> dict[str, Any]:
        doc = self.docs.get(doc_id)
        if not doc or doc.get("deleted_at"):
            raise NotFound("Documento no encontrado.")
        return doc

    def retention_options(self) -> list[str]:
        return list((self.settings.get("governance.retention_policies") or {}).keys())

    def _near_duplicates(self, text: str, exclude_doc: str | None) -> list[dict[str, Any]]:
        threshold = float(self.settings.get("ingestion.near_duplicate_threshold", 0.95))
        candidates = [r for r in self.chunks.versions_with_chunks() if r["document_id"] != exclude_doc][:500]
        if not candidates:
            return []
        vectors = self.embedder.embed([display_text(text)[:6000]] + [display_text(r["extracted_text"])[:6000]
                                                                       for r in candidates])
        sims = vectors[1:] @ vectors[0]
        found = []
        for row, sim in zip(candidates, sims):
            if float(sim) >= threshold:
                found.append({"doc_code": row["doc_code"], "title": row["title"], "similarity": round(float(sim), 3)})
        return found

    def _index_version(self, version_id: str, doc_id: str, title: str, text: str) -> int:
        pieces = self.pipeline.chunk(text)
        records = []
        for piece in pieces:
            records.append({"text": piece.text, "section": piece.section, "page": piece.page,
                            "injection_flag": int(self.detector.scan(piece.text).flagged)})
        embeddings = self.embedder.embed([f"{title}\n{r['section']}\n{r['text']}" for r in records]) if records \
            else np.zeros((0, self.embedder.dim), dtype=np.float32)
        count = self.chunks.replace_for_version(version_id, doc_id, title, records, embeddings, self.embedder.name)
        self.retriever.invalidate()
        return count

    # ------------------------------------------------------------------ ingesta
    def ingest_file(self, user: AuthenticatedUser, file_name: str, data: bytes, meta: DocumentMetadataInput,
                    document_id: str | None = None, correlation_id: str = "", is_demo: bool = False) -> IngestReport:
        require(user, "knowledge.upload")
        meta.retention_options = self.retention_options()
        meta.validated()
        try:
            prepared = self.pipeline.prepare_file(file_name, data)
        except Exception as exc:
            self.audit(user, "document.upload", "document", meta.doc_code, "failure",
                       reason=getattr(exc, "user_message", type(exc).__name__), correlation_id=correlation_id)
            raise
        return self._create_version(user, meta, prepared, data, file_name, document_id, correlation_id, is_demo)

    def ingest_text(self, user: AuthenticatedUser, text: str, meta: DocumentMetadataInput,
                    document_id: str | None = None, correlation_id: str = "", is_demo: bool = False,
                    created_by: str | None = None) -> IngestReport:
        require(user, "knowledge.upload")
        return self._ingest_text(user, text, meta, document_id, correlation_id, is_demo, created_by)

    def _ingest_text(self, user: AuthenticatedUser, text: str, meta: DocumentMetadataInput,
                     document_id: str | None, correlation_id: str, is_demo: bool,
                     created_by: str | None) -> IngestReport:
        meta.retention_options = self.retention_options()
        meta.validated()
        prepared = self.pipeline.prepare_text(text)
        return self._create_version(user, meta, prepared, None, None, document_id, correlation_id, is_demo,
                                    created_by)

    def _create_version(self, user: AuthenticatedUser, meta: DocumentMetadataInput, prepared: PreparedContent,
                        data: bytes | None, file_name: str | None, document_id: str | None, correlation_id: str,
                        is_demo: bool, created_by: str | None = None) -> IngestReport:
        author = created_by or user.username
        duplicates = self.docs.find_by_content_hash(prepared.hash)
        near = self._near_duplicates(prepared.text, document_id)
        injection = self.detector.scan(display_text(prepared.text))

        if document_id is None:
            if self.docs.get_by_code(meta.doc_code):
                raise ValidationError("Ya existe un documento con ese código. Carga una nueva versión.")
            document_id = self.docs.create(meta.document_fields(), author, is_demo=is_demo)
        else:
            doc = self._document(document_id)
            self._apply_metadata(user, doc, meta.document_fields(), "nueva versión", governance_check=False)

        version_no = self.docs.next_version_no(document_id)
        stored_path = None
        if data is not None and file_name:
            target_dir = safe_join(self.files_dir, document_id)
            target_dir.mkdir(parents=True, exist_ok=True)
            target = safe_join(target_dir, f"v{version_no}_{safe_filename(file_name)}")
            target.write_bytes(data)
            stored_path = str(target.relative_to(self.files_dir.resolve()))

        version_id = self.docs.create_version(document_id, {
            "version_no": version_no, "version_label": f"{version_no}.0", "status": DocStatus.DRAFT.value,
            "content_hash": prepared.hash, "file_hash": None,
            "file_name": safe_filename(file_name) if file_name else None, "stored_path": stored_path,
            "file_kind": prepared.file.kind if prepared.file else "text",
            "size_bytes": len(data) if data is not None else len(prepared.text.encode("utf-8")),
            "page_count": prepared.page_count, "extracted_text": prepared.text,
            "injection_flags": json.dumps(injection.matches) if injection.flagged else "",
            "duplicate_of": duplicates[0]["doc_code"] if duplicates else None,
            "effective_date": meta.effective_date, "review_date": meta.review_date,
            "expiration_date": meta.expiration_date or None, "change_note": meta.change_note,
            "created_by": author,
        })
        count = self._index_version(version_id, document_id, meta.title, prepared.text)
        self.audit(user, "document.upload", "document_version", version_id, "success",
                   details=f"doc={meta.doc_code} v{version_no} chunks={count} injection={injection.flagged} "
                           f"duplicates={len(duplicates)}", correlation_id=correlation_id)
        log.info("ingest doc=%s version=%s chunks=%d", meta.doc_code, version_id, count)
        return IngestReport(document_id=document_id, version_id=version_id, version_label=f"{version_no}.0",
                            chunk_count=count, duplicates=duplicates, near_duplicates=near,
                            injection_matches=injection.matches, warnings=prepared.warnings,
                            preview=display_text(prepared.text)[:3000])

    # ------------------------------------------------------------------ metadatos
    def _apply_metadata(self, user: AuthenticatedUser, doc: dict[str, Any], changes: dict[str, Any], reason: str,
                        governance_check: bool = True) -> list[str]:
        sensitive = {"classification", "retention_policy", "owner", "approver"}
        changed = []
        for key, new in changes.items():
            if key == "doc_code":
                continue
            old = doc.get(key)
            if str(old or "") == str(new or ""):
                continue
            if governance_check and key in sensitive and not user.can("governance.manage"):
                raise PermissionDenied("Solo Data Steward/Administrador puede cambiar clasificación, retención o "
                                       "propietario.")
            changed.append(key)
            self.docs.log_metadata_change(doc["id"], key, old, new, user.username, reason)
        if changed:
            self.docs.update(doc["id"], **{k: changes[k] for k in changed})
            self.retriever.invalidate()
        return changed

    def update_metadata(self, user: AuthenticatedUser, doc_id: str, changes: dict[str, Any], reason: str,
                        correlation_id: str = "") -> list[str]:
        if not (user.can("governance.manage") or user.can("knowledge.edit")):
            raise PermissionDenied()
        reason = clean_user_text(reason, 500)
        if not reason:
            raise ValidationError("Indica el motivo del cambio.")
        doc = self._document(doc_id)
        if "classification" in changes and changes["classification"] not in Classification.values():
            raise ValidationError("Clasificación inválida.")
        if "source_type" in changes and changes["source_type"] not in SourceType.values():
            raise ValidationError("Tipo de fuente inválido.")
        if "retention_policy" in changes and changes["retention_policy"] not in self.retention_options():
            raise ValidationError("Política de retención inválida.")
        clean = {k: clean_user_text(str(v), 1000) for k, v in changes.items()}
        changed = self._apply_metadata(user, doc, clean, reason)
        self.audit(user, "document.metadata_change", "document", doc_id, "success", reason=reason,
                   details="fields=" + ",".join(changed), correlation_id=correlation_id)
        return changed

    def update_version_dates(self, user: AuthenticatedUser, version_id: str, effective: str, review: str,
                             expiration: str, reason: str, correlation_id: str = "") -> None:
        require(user, "governance.manage")
        version = self._version(version_id)
        eff, rev, exp = parse_date(effective), parse_date(review), parse_date(expiration)
        if eff is None or rev is None:
            raise ValidationError("Fechas efectiva y de revisión obligatorias.")
        if exp is not None and exp <= eff:
            raise ValidationError("La expiración debe ser posterior a la fecha efectiva.")
        reason = clean_user_text(reason, 500)
        if not reason:
            raise ValidationError("Indica el motivo del cambio.")
        for field_name, old, new in (("effective_date", version["effective_date"], eff.isoformat()),
                                     ("review_date", version["review_date"], rev.isoformat()),
                                     ("expiration_date", version["expiration_date"], exp.isoformat() if exp else None)):
            if (old or None) != new:
                self.docs.log_metadata_change(version["document_id"], f"v{version['version_label']}.{field_name}",
                                              old, new, user.username, reason)
        self.docs.update_version(version_id, effective_date=eff.isoformat(), review_date=rev.isoformat(),
                                 expiration_date=exp.isoformat() if exp else None)
        self.retriever.invalidate()
        self.audit(user, "document.validity_change", "document_version", version_id, "success", reason=reason,
                   correlation_id=correlation_id)

    # ------------------------------------------------------------------ flujo de aprobación
    def _transition(self, user: AuthenticatedUser, version: dict[str, Any], target: str, action: str,
                    reason: str, correlation_id: str, **fields: Any) -> None:
        check_transition(version["status"], target, ever_approved=bool(version["ever_approved"]))
        self.docs.update_version(version["id"], status=target, **fields)
        self.docs.log_approval(version["id"], version["document_id"], action, user.username, reason)
        self.audit(user, f"document.{action}", "document_version", version["id"], "success", reason=reason,
                   correlation_id=correlation_id)
        self.retriever.invalidate()

    def submit_for_review(self, user: AuthenticatedUser, version_id: str, correlation_id: str = "") -> None:
        require(user, "knowledge.upload")
        version = self._version(version_id)
        self._transition(user, version, DocStatus.UNDER_REVIEW.value, "submit", "", correlation_id,
                         submitted_by=user.username, submitted_at=now_iso())

    def approve(self, user: AuthenticatedUser, version_id: str, reason: str = "",
                acknowledge_injection: bool = False, correlation_id: str = "") -> None:
        require(user, "knowledge.approve")
        version = self._version(version_id)
        if self.settings.get("governance.require_four_eyes", True) and version["created_by"] == user.username:
            self.audit(user, "document.approve", "document_version", version_id, "denied",
                       reason="four-eyes: el autor no puede aprobar su propia versión", correlation_id=correlation_id)
            raise PermissionDenied("Segregación de funciones: quien cargó la versión no puede aprobarla.")
        if version["injection_flags"] and not acknowledge_injection:
            raise WorkflowError("La versión contiene posibles instrucciones maliciosas (prompt injection). "
                                "Revísalas y confirma explícitamente antes de aprobar.")
        extra: dict[str, Any] = {"decided_by": user.username, "decided_at": now_iso(),
                                 "decision_reason": clean_user_text(reason, 500), "ever_approved": 1}
        if version["injection_flags"]:
            extra["injection_ack_by"] = user.username
        self._transition(user, version, DocStatus.APPROVED.value, "approve", reason, correlation_id, **extra)

    def reject(self, user: AuthenticatedUser, version_id: str, reason: str, correlation_id: str = "") -> None:
        require(user, "knowledge.approve")
        reason = clean_user_text(reason, 500)
        if not reason:
            raise ValidationError("El rechazo requiere un motivo.")
        version = self._version(version_id)
        self._transition(user, version, DocStatus.REJECTED.value, "reject", reason, correlation_id,
                         decided_by=user.username, decided_at=now_iso(), decision_reason=reason)

    def return_to_draft(self, user: AuthenticatedUser, version_id: str, reason: str, correlation_id: str = "") -> None:
        require(user, "knowledge.approve")
        version = self._version(version_id)
        self._transition(user, version, DocStatus.DRAFT.value, "return_to_draft", reason, correlation_id)

    def archive_version(self, user: AuthenticatedUser, version_id: str, reason: str, correlation_id: str = "") -> None:
        require(user, "knowledge.publish")
        version = self._version(version_id)
        doc = self._document(version["document_id"])
        self._transition(user, version, DocStatus.ARCHIVED.value, "archive", reason, correlation_id,
                         archived_at=now_iso())
        if doc["published_version_id"] == version_id:
            self.docs.update(doc["id"], published_version_id=None)

    def prepublish_checks(self, version_id: str) -> list[CheckResult]:
        version = self._version(version_id)
        doc = self._document(version["document_id"])
        checks: list[CheckResult] = []
        text = display_text(version["extracted_text"])
        checks.append(CheckResult("Texto extraído suficiente", len(text.strip()) >= 50, True,
                                  f"{len(text)} caracteres"))
        missing = missing_metadata(doc)
        checks.append(CheckResult("Metadatos obligatorios completos", not missing, True,
                                  ", ".join(missing) if missing else "OK"))
        eff, rev, exp = (parse_date(version["effective_date"]), parse_date(version["review_date"]),
                         parse_date(version["expiration_date"]))
        expired = exp is not None and exp <= today()
        checks.append(CheckResult("No expirado", not expired, True, f"expira: {exp or '—'}"))
        checks.append(CheckResult("Fecha de revisión vigente", rev is not None and rev >= today(), False,
                                  f"revisión: {rev or '—'}"))
        checks.append(CheckResult("Fecha efectiva definida", eff is not None, True, f"efectiva: {eff or '—'}"))
        injection_ok = not version["injection_flags"] or bool(version["injection_ack_by"])
        checks.append(CheckResult("Prompt injection revisado", injection_ok, True,
                                  version["injection_flags"] or "sin hallazgos"))
        chunks = self.chunks.for_version(version_id)
        checks.append(CheckResult("Fragmentos indexados", bool(chunks), True, f"{len(chunks)} fragmentos"))
        dup = [d for d in self.docs.find_by_content_hash(version["content_hash"]) if d["id"] != version_id
               and d["status"] == DocStatus.APPROVED.value]
        checks.append(CheckResult("Sin duplicado exacto aprobado", not dup, False,
                                  ", ".join(d["doc_code"] for d in dup) or "OK"))
        # Prueba de recuperación: cada tema (sección) debe recuperar esta versión entre los 3 primeros.
        sections = list(dict.fromkeys(c["section"].split(" > ")[-1] for c in chunks if c["section"]))[:5]
        questions = sections or [doc["title"]]
        found = 0
        conflicts = []
        for question in questions:
            result = self.retriever.retrieve(question, Classification.values(), None, [version_id], top_k=3)
            if any(h.version_id == version_id for h in result.hits):
                found += 1
            conflicts += [c for c in detect_conflicts(result.hits, float(self.settings.get("rag.min_relevance", 0.4)))
                          if doc["doc_code"] in (c.doc_a + c.doc_b)]
        checks.append(CheckResult("Recuperable por sus temas (prueba RAG)", found == len(questions), False,
                                  f"{found}/{len(questions)} temas recuperan esta versión"))
        checks.append(CheckResult("Sin contradicciones con fuentes aprobadas", not conflicts, False,
                                  "; ".join(f"{c.doc_a} vs {c.doc_b}" for c in conflicts[:3]) or "OK"))
        return checks

    def publish(self, user: AuthenticatedUser, version_id: str, reason: str = "", correlation_id: str = "",
                skip_checks: bool = False) -> list[CheckResult]:
        require(user, "knowledge.publish")
        version = self._version(version_id)
        if version["status"] != DocStatus.APPROVED.value:
            raise WorkflowError("Solo se publican versiones aprobadas.")
        checks = [] if skip_checks else self.prepublish_checks(version_id)
        failed = [c for c in checks if c.critical and not c.ok]
        if failed:
            self.audit(user, "document.publish", "document_version", version_id, "blocked",
                       reason="; ".join(c.name for c in failed), correlation_id=correlation_id)
            raise WorkflowError("Publicación bloqueada por pruebas críticas: " + "; ".join(c.name for c in failed))
        doc = self._document(version["document_id"])
        previous = doc.get("published_version_id")
        if previous and previous != version_id:
            prev = self._version(previous)
            if prev["status"] == DocStatus.APPROVED.value:
                self.docs.update_version(previous, status=DocStatus.ARCHIVED.value, archived_at=now_iso())
                self.docs.log_approval(previous, doc["id"], "superseded", user.username, f"reemplazada por {version_id}")
        self.docs.update_version(version_id, published_at=now_iso())
        self.docs.update(doc["id"], published_version_id=version_id, is_active=1)
        self.docs.log_approval(version_id, doc["id"], "publish", user.username, reason)
        self.audit(user, "document.publish", "document_version", version_id, "success", reason=reason,
                   details=f"doc={doc['doc_code']} previous={previous or '-'}", correlation_id=correlation_id)
        self.retriever.invalidate()
        return checks

    def rollback(self, user: AuthenticatedUser, document_id: str, target_version_id: str, reason: str,
                 correlation_id: str = "") -> None:
        require(user, "knowledge.publish")
        reason = clean_user_text(reason, 500)
        if not reason:
            raise ValidationError("El rollback requiere un motivo.")
        doc = self._document(document_id)
        target = self._version(target_version_id)
        if target["document_id"] != document_id:
            raise ValidationError("La versión no pertenece al documento.")
        exp = parse_date(target["expiration_date"])
        if exp is not None and exp <= today():
            raise WorkflowError("No se puede restaurar una versión expirada.")
        check_transition(target["status"], DocStatus.APPROVED.value, ever_approved=bool(target["ever_approved"]))
        current = doc.get("published_version_id")
        if current and current != target_version_id:
            cur = self._version(current)
            if cur["status"] == DocStatus.APPROVED.value:
                self.docs.update_version(current, status=DocStatus.ARCHIVED.value, archived_at=now_iso())
                self.docs.log_approval(current, document_id, "rolled_back_from", user.username, reason)
        self.docs.update_version(target_version_id, status=DocStatus.APPROVED.value, published_at=now_iso(),
                                 archived_at=None)
        self.docs.update(document_id, published_version_id=target_version_id, is_active=1)
        self.docs.log_approval(target_version_id, document_id, "rollback", user.username, reason)
        self.audit(user, "document.rollback", "document", document_id, "success", reason=reason,
                   details=f"from={current or '-'} to={target_version_id}", correlation_id=correlation_id)
        self.retriever.invalidate()

    def set_active(self, user: AuthenticatedUser, document_id: str, active: bool, reason: str,
                   correlation_id: str = "") -> None:
        require(user, "knowledge.publish")
        reason = clean_user_text(reason, 500)
        if not reason:
            raise ValidationError("Indica el motivo.")
        doc = self._document(document_id)
        self.docs.update(document_id, is_active=int(active))
        self.docs.log_metadata_change(document_id, "is_active", doc["is_active"], int(active), user.username, reason)
        self.audit(user, "document.activate" if active else "document.deactivate", "document", document_id,
                   "success", reason=reason, correlation_id=correlation_id)
        self.retriever.invalidate()

    def delete_document(self, user: AuthenticatedUser, document_id: str, reason: str,
                        correlation_id: str = "") -> None:
        """Eliminación autorizada: borra archivos, texto y fragmentos; conserva lápida en catálogo y auditoría."""
        require(user, "documents.delete")
        reason = clean_user_text(reason, 500)
        if not reason:
            raise ValidationError("La eliminación requiere un motivo.")
        doc = self._document(document_id)
        if doc["is_active"] and doc["published_version_id"]:
            raise WorkflowError("Desactiva el documento antes de eliminarlo.")
        for version in self.docs.list_versions(document_id):
            self.chunks.delete_for_version(version["id"])
            self.docs.update_version(version["id"], extracted_text="", stored_path=None,
                                     status=DocStatus.ARCHIVED.value if version["status"] not in
                                     (DocStatus.ARCHIVED.value,) else version["status"],
                                     archived_at=version["archived_at"] or now_iso())
        folder = self.files_dir / document_id
        if folder.is_dir():
            shutil.rmtree(safe_join(self.files_dir, document_id), ignore_errors=True)
        self.docs.update(document_id, deleted_at=now_iso(), deleted_reason=reason, is_active=0,
                         published_version_id=None)
        self.audit(user, "document.delete", "document", document_id, "success", reason=reason,
                   details=f"doc={doc['doc_code']}", correlation_id=correlation_id)
        self.retriever.invalidate()

    # ------------------------------------------------------------------ mantenimiento
    def run_lifecycle(self, user: AuthenticatedUser, correlation_id: str = "") -> dict[str, int]:
        """Marca como Expired las versiones aprobadas cuya fecha de expiración ya pasó."""
        expired = 0
        for v in self.docs.all_versions():
            exp = parse_date(v["expiration_date"])
            if v["status"] == DocStatus.APPROVED.value and exp is not None and exp <= today() and not v["deleted_at"]:
                self.docs.update_version(v["id"], status=DocStatus.EXPIRED.value)
                self.docs.log_approval(v["id"], v["document_id"], "expire", user.username, f"expiró el {exp}")
                self.audit(user, "document.expire", "document_version", v["id"], "success",
                           reason=f"expiration {exp}", correlation_id=correlation_id)
                expired += 1
        if expired:
            self.retriever.invalidate()
        return {"expired": expired}

    def reindex_all(self, user: AuthenticatedUser, correlation_id: str = "") -> dict[str, int]:
        require(user, "knowledge.publish")
        versions = self.chunks.versions_with_chunks()
        total = 0
        for v in versions:
            total += self._index_version(v["version_id"], v["document_id"], v["title"], v["extracted_text"])
        self.audit(user, "index.reindex", "index", "all", "success",
                   details=f"versions={len(versions)} chunks={total} model={self.embedder.name}",
                   correlation_id=correlation_id)
        return {"versions": len(versions), "chunks": total}

    # ------------------------------------------------------------------ consultas
    def catalog(self, user: AuthenticatedUser, include_deleted: bool = False) -> list[dict[str, Any]]:
        rows = self.docs.catalog(include_deleted)
        if "*" in user.permissions:
            return rows
        return [r for r in rows if r["classification"] in user.clearance]

    def versions(self, user: AuthenticatedUser, document_id: str) -> list[dict[str, Any]]:
        doc = self._document(document_id)
        if doc["classification"] not in user.clearance:
            raise PermissionDenied("No tienes acceso a esta clasificación de información.")
        return self.docs.list_versions(document_id)

    def version_text(self, user: AuthenticatedUser, version_id: str) -> str:
        version = self._version(version_id)
        doc = self._document(version["document_id"])
        if doc["classification"] not in user.clearance:
            raise PermissionDenied("No tienes acceso a esta clasificación de información.")
        return display_text(version["extracted_text"])

    def diff_versions(self, user: AuthenticatedUser, old_version_id: str, new_version_id: str) -> str:
        old = self.version_text(user, old_version_id).splitlines()
        new = self.version_text(user, new_version_id).splitlines()
        old_v, new_v = self._version(old_version_id), self._version(new_version_id)
        diff = difflib.unified_diff(old, new, fromfile=f"v{old_v['version_label']}",
                                    tofile=f"v{new_v['version_label']}", lineterm="")
        return "\n".join(diff) or "Sin diferencias de texto."

    def original_file(self, user: AuthenticatedUser, version_id: str, correlation_id: str = "") -> tuple[str, bytes]:
        require(user, "sources.download")
        version = self._version(version_id)
        doc = self._document(version["document_id"])
        if doc["classification"] not in user.clearance:
            raise PermissionDenied("No tienes acceso a esta clasificación de información.")
        if not version["stored_path"]:
            raise NotFound("Esta versión no tiene archivo original (contenido de texto).")
        path: Path = safe_join(self.files_dir, version["stored_path"])
        if not path.is_file():
            raise NotFound("Archivo original no disponible.")
        self.audit(user, "document.download", "document_version", version_id, "success",
                   details=f"classification={doc['classification']}", correlation_id=correlation_id)
        return version["file_name"] or path.name, path.read_bytes()

    # ------------------------------------------------------------------ Q&A aprobadas
    def propose_qa(self, user: AuthenticatedUser, question: str, answer: str, module: str, classification: str,
                   source_feedback_id: str | None = None, correlation_id: str = "") -> str:
        if not (user.can("knowledge.edit") or user.can("feedback.review")):
            raise PermissionDenied()
        question = clean_user_text(question, 500)
        answer = clean_user_text(answer, 4000)
        if len(question) < 8 or len(answer) < 15:
            raise ValidationError("Pregunta y respuesta deben ser descriptivas.")
        if classification not in Classification.values():
            raise ValidationError("Clasificación inválida.")
        if self.detector.scan(question + "\n" + answer).flagged:
            raise ValidationError("La Q&A contiene patrones de instrucciones maliciosas.")
        qid = self.qa.create(question=question, answer=answer, fl_module=module, classification=classification,
                             language="en" if normalize(question).startswith(("how", "what", "why", "where")) else "es",
                             status=DocStatus.UNDER_REVIEW.value, created_by=user.username,
                             source_feedback_id=source_feedback_id)
        self.audit(user, "qa.propose", "qa_pair", qid, "success", correlation_id=correlation_id)
        return qid

    def approve_qa(self, user: AuthenticatedUser, qa_id: str, reason: str = "", correlation_id: str = "") -> str:
        require(user, "knowledge.approve")
        item = self.qa.get(qa_id)
        if not item or item["status"] != DocStatus.UNDER_REVIEW.value:
            raise WorkflowError("La Q&A no está en revisión.")
        if self.settings.get("governance.require_four_eyes", True) and item["created_by"] == user.username:
            raise PermissionDenied("Segregación de funciones: quien propuso la Q&A no puede aprobarla.")
        today_iso = today().isoformat()
        review = (today() + timedelta(days=365)).isoformat()
        meta = DocumentMetadataInput(
            doc_code=f"QA-{qa_id[3:15].upper()}", title=f"Q&A aprobada: {item['question'][:150]}",
            description="Pregunta y respuesta aprobadas por revisión humana.", source_type=SourceType.APPROVED_QA.value,
            owner=user.username, approver=user.username, area="Knowledge Management",
            fl_module=item["fl_module"] or "General", classification=item["classification"],
            retention_policy=self.settings.get("governance.default_retention_policy", "standard-3y"),
            tags="qa,aprobada", language=item["language"], effective_date=today_iso, review_date=review)
        text = f"# Q&A aprobada\n\n## {item['question']}\n\n### Respuesta breve\n{item['answer']}\n"
        # La aprobación de la Q&A (permiso knowledge.approve) autoriza su conversión en fuente versionada.
        report = self._ingest_text(user, text, meta, None, correlation_id, False, item["created_by"])
        self._transition(user, self._version(report.version_id), DocStatus.UNDER_REVIEW.value, "submit",
                         "Q&A aprobada", correlation_id, submitted_by=item["created_by"], submitted_at=now_iso())
        self.approve(user, report.version_id, reason or "Q&A aprobada", correlation_id=correlation_id)
        self.publish(user, report.version_id, "Q&A aprobada", correlation_id, skip_checks=True)
        self.qa.update(qa_id, status=DocStatus.APPROVED.value, decided_by=user.username, decided_at=now_iso(),
                       decision_reason=reason, document_id=report.document_id)
        self.audit(user, "qa.approve", "qa_pair", qa_id, "success", reason=reason, correlation_id=correlation_id)
        return report.document_id

    def reject_qa(self, user: AuthenticatedUser, qa_id: str, reason: str, correlation_id: str = "") -> None:
        require(user, "knowledge.approve")
        reason = clean_user_text(reason, 500)
        if not reason:
            raise ValidationError("El rechazo requiere un motivo.")
        item = self.qa.get(qa_id)
        if not item or item["status"] != DocStatus.UNDER_REVIEW.value:
            raise WorkflowError("La Q&A no está en revisión.")
        self.qa.update(qa_id, status=DocStatus.REJECTED.value, decided_by=user.username, decided_at=now_iso(),
                       decision_reason=reason)
        self.audit(user, "qa.reject", "qa_pair", qa_id, "success", reason=reason, correlation_id=correlation_id)

    def export_approved_jsonl(self, user: AuthenticatedUser, correlation_id: str = "") -> str:
        """Exporta Q&A/correcciones APROBADAS en JSONL para un posible fine-tuning futuro (no se ejecuta)."""
        require(user, "export.data")
        lines = []
        for item in self.qa.list(DocStatus.APPROVED.value):
            if item["classification"] not in user.clearance:
                continue
            lines.append(json.dumps({
                "messages": [{"role": "user", "content": item["question"]},
                             {"role": "assistant", "content": item["answer"]}],
                "metadata": {"qa_id": item["id"], "module": item["fl_module"], "classification": item["classification"],
                             "approved_by": item["decided_by"], "approved_at": item["decided_at"],
                             "source_feedback_id": item["source_feedback_id"]}}, ensure_ascii=False))
        self.audit(user, "export.qa_jsonl", "qa_pair", "approved", "success", details=f"rows={len(lines)}",
                   correlation_id=correlation_id)
        return "\n".join(lines) + ("\n" if lines else "")
