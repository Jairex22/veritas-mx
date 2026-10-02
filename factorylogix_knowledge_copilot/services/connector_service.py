"""Consultas en vivo a FactoryLogix (solo lectura) con permisos, auditoría y etiquetado de origen."""
from __future__ import annotations

from typing import Any

from connectors.base import LiveResult
from connectors.odata import ODataConnector, XTendConnector
from core.errors import CopilotError
from models.domain import AuthenticatedUser
from security.rbac import require
from services.audit_helper import Auditor


class ConnectorService:
    def __init__(self, odata: ODataConnector, xtend: XTendConnector, audit: Auditor):
        self.odata = odata
        self.xtend = xtend
        self.audit = audit

    @property
    def entities(self) -> dict[str, dict[str, Any]]:
        return self.odata.entities

    def status(self) -> dict[str, Any]:
        return {"odata": self.odata.status(), "xtend": self.xtend.status()}

    def query(self, user: AuthenticatedUser, entity: str, key_field: str, key_value: str,
              correlation_id: str = "") -> LiveResult:
        require(user, "connectors.query")
        try:
            result = self.odata.query(entity, key_field, key_value)
        except CopilotError as exc:
            self.audit(user, "connector.odata_query", "odata", entity, "failure",
                       reason=exc.user_message, correlation_id=correlation_id)
            raise
        self.audit(user, "connector.odata_query", "odata", entity, "success",
                   details=f"rows={len(result.rows)} cache={result.from_cache}", correlation_id=correlation_id)
        return result
