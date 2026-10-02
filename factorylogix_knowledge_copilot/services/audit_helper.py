"""Atajo para registrar auditoría desde los servicios."""
from __future__ import annotations

from models.domain import AuthenticatedUser
from repositories.audit import AuditRepository


class Auditor:
    def __init__(self, repo: AuditRepository):
        self.repo = repo

    def __call__(self, user: AuthenticatedUser | None, action: str, object_type: str, object_id: str,
                 result: str = "success", reason: str = "", details: str = "", correlation_id: str = "") -> str:
        return self.repo.append(username=user.username if user else "anonymous", role=user.role if user else "-",
                                action=action, object_type=object_type, object_id=object_id, result=result,
                                reason=reason, details=details, correlation_id=correlation_id)
