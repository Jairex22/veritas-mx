"""Feedback útil/no útil y bandeja de correcciones (nunca se aprende automáticamente)."""
from __future__ import annotations

from typing import Any

from core.errors import NotFound, PermissionDenied, ValidationError, WorkflowError
from core.utils import now_iso
from models.domain import AuthenticatedUser
from repositories.operations import FeedbackRepository, QueryLogRepository
from security.rbac import require
from security.sanitize import clean_user_text
from services.audit_helper import Auditor
from services.knowledge_service import KnowledgeService


class FeedbackService:
    def __init__(self, feedback: FeedbackRepository, queries: QueryLogRepository, knowledge: KnowledgeService,
                 audit: Auditor):
        self.feedback = feedback
        self.queries = queries
        self.knowledge = knowledge
        self.audit = audit

    def rate(self, user: AuthenticatedUser, query_id: str, helpful: bool, comment: str = "") -> str:
        require(user, "chat.query")
        query = self.queries.get(query_id) if query_id else None
        if query_id and (not query or query["user_id"] != user.id):
            raise NotFound("Consulta no encontrada.")
        return self.feedback.create(query_id=query_id, user_id=user.id, rating="up" if helpful else "down",
                                    comment=clean_user_text(comment, 1000), is_correction=0,
                                    question=query["question"] if query else "", status="closed")

    def report_incorrect(self, user: AuthenticatedUser, query_id: str, original_answer: str, comment: str,
                         proposed_answer: str = "", correlation_id: str = "") -> str:
        """La corrección entra a una bandeja de revisión; NO se usa hasta su aprobación humana."""
        require(user, "chat.query")
        query = self.queries.get(query_id) if query_id else None
        if query_id and (not query or query["user_id"] != user.id):
            raise NotFound("Consulta no encontrada.")
        comment = clean_user_text(comment, 2000)
        if len(comment) < 5:
            raise ValidationError("Describe qué es incorrecto.")
        fid = self.feedback.create(query_id=query_id, user_id=user.id, rating="down", comment=comment,
                                   is_correction=1, question=query["question"] if query else "",
                                   original_answer=clean_user_text(original_answer, 6000),
                                   proposed_answer=clean_user_text(proposed_answer, 4000), status="pending_review")
        self.audit(user, "feedback.report_incorrect", "feedback", fid, "success", correlation_id=correlation_id)
        return fid

    def queue(self, user: AuthenticatedUser, status: str = "pending_review") -> list[dict[str, Any]]:
        require(user, "feedback.review")
        return self.feedback.list(status=status, corrections_only=True)

    def all_feedback(self, user: AuthenticatedUser) -> list[dict[str, Any]]:
        require(user, "feedback.review")
        return self.feedback.list()

    def accept_correction(self, user: AuthenticatedUser, feedback_id: str, question: str, answer: str, module: str,
                          classification: str, note: str = "", correlation_id: str = "") -> str:
        """Convierte la corrección en una Q&A propuesta (requiere aprobación de otra persona)."""
        require(user, "feedback.review")
        item = self.feedback.get(feedback_id)
        if not item or item["status"] != "pending_review":
            raise WorkflowError("La corrección no está pendiente.")
        if item["user_id"] == user.id and "*" not in user.permissions:
            raise PermissionDenied("No puedes revisar tu propia corrección.")
        qa_id = self.knowledge.propose_qa(user, question, answer, module, classification, feedback_id, correlation_id)
        self.feedback.update(feedback_id, status="accepted_to_qa", reviewed_by=user.username, reviewed_at=now_iso(),
                             review_note=clean_user_text(note, 1000))
        self.audit(user, "feedback.accept", "feedback", feedback_id, "success", details=f"qa={qa_id}",
                   correlation_id=correlation_id)
        return qa_id

    def dismiss(self, user: AuthenticatedUser, feedback_id: str, note: str, correlation_id: str = "") -> None:
        require(user, "feedback.review")
        note = clean_user_text(note, 1000)
        if not note:
            raise ValidationError("Indica el motivo.")
        item = self.feedback.get(feedback_id)
        if not item or item["status"] != "pending_review":
            raise WorkflowError("La corrección no está pendiente.")
        self.feedback.update(feedback_id, status="dismissed", reviewed_by=user.username, reviewed_at=now_iso(),
                             review_note=note)
        self.audit(user, "feedback.dismiss", "feedback", feedback_id, "success", reason=note,
                   correlation_id=correlation_id)
