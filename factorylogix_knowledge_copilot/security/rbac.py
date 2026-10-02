"""Control de acceso basado en roles (RBAC) y matriz de clasificación."""
from __future__ import annotations

from typing import Iterable

from core.errors import PermissionDenied
from models.domain import AuthenticatedUser, Role

# Permisos disponibles
P = {
    "chat.query": "Consultar conocimiento aprobado",
    "sources.view": "Ver fuentes y evidencias",
    "sources.download": "Descargar archivo original",
    "incident.create": "Crear incidentes/escalamientos",
    "incident.manage": "Gestionar todos los incidentes",
    "analytics.view": "Ver analítica general",
    "knowledge.upload": "Cargar documentos y nuevas versiones",
    "knowledge.edit": "Editar contenido y Q&A",
    "knowledge.approve": "Aprobar o rechazar contenido",
    "knowledge.publish": "Publicar, desactivar, rollback",
    "governance.manage": "Metadatos, vigencia, clasificación, retención",
    "governance.view": "Ver gobierno de datos y catálogo",
    "documents.delete": "Eliminación autorizada",
    "feedback.review": "Revisar feedback y correcciones",
    "eval.run": "Ejecutar evaluación RAG",
    "eval.view": "Ver resultados de evaluación",
    "users.manage": "Usuarios y roles",
    "settings.manage": "Configuración",
    "audit.view": "Ver auditoría",
    "health.view": "Ver salud del sistema",
    "export.data": "Exportar datos y reportes",
    "connectors.query": "Consultar FactoryLogix en vivo (solo lectura)",
    "debug.view": "Ver detalles técnicos de recuperación",
}

_BASE = {"chat.query", "sources.view"}
_ENGINEERING = _BASE | {"incident.create", "analytics.view", "sources.download", "debug.view", "eval.view",
                        "governance.view", "connectors.query"}

ROLE_PERMISSIONS: dict[str, frozenset[str]] = {
    Role.OPERATOR.value: frozenset(_BASE | {"incident.create"}),
    Role.SUPERVISOR.value: frozenset(_BASE | {"incident.create", "incident.manage", "analytics.view",
                                              "sources.download", "export.data", "connectors.query"}),
    Role.PRODUCT_ENGINEER.value: frozenset(_ENGINEERING),
    Role.QUALITY.value: frozenset(_ENGINEERING | {"export.data"}),
    Role.NPI.value: frozenset(_ENGINEERING),
    Role.MES_SUPPORT.value: frozenset(_ENGINEERING | {"incident.manage", "health.view", "export.data",
                                                      "feedback.review"}),
    Role.KNOWLEDGE_MANAGER.value: frozenset(_ENGINEERING | {"knowledge.upload", "knowledge.edit",
                                                            "knowledge.approve", "knowledge.publish",
                                                            "feedback.review", "eval.run", "export.data"}),
    Role.DATA_STEWARD.value: frozenset(_ENGINEERING | {"governance.manage", "knowledge.approve",
                                                       "knowledge.publish", "documents.delete", "export.data",
                                                       "eval.run"}),
    Role.ADMINISTRATOR.value: frozenset(_ENGINEERING | {"users.manage", "settings.manage", "health.view",
                                                        "audit.view", "export.data", "eval.run",
                                                        "knowledge.upload", "knowledge.approve",
                                                        "knowledge.publish", "governance.manage",
                                                        "documents.delete", "feedback.review",
                                                        "incident.manage", "knowledge.edit"}),
    Role.AUDITOR.value: frozenset({"chat.query", "sources.view", "sources.download", "audit.view",
                                   "governance.view", "analytics.view", "eval.view", "health.view",
                                   "export.data", "debug.view"}),
}

DEFAULT_CLEARANCE: dict[str, tuple[str, ...]] = {
    "Operator": ("Public", "Internal"),
    "Supervisor": ("Public", "Internal", "Confidential"),
    "Product Engineer": ("Public", "Internal", "Confidential"),
    "Quality": ("Public", "Internal", "Confidential"),
    "NPI": ("Public", "Internal", "Confidential"),
    "MES Support": ("Public", "Internal", "Confidential", "Restricted"),
    "Knowledge Manager": ("Public", "Internal", "Confidential"),
    "Data Steward": ("Public", "Internal", "Confidential", "Restricted"),
    "Administrator": ("Public", "Internal", "Confidential", "Restricted"),
    "Auditor": ("Public", "Internal", "Confidential", "Restricted"),
}

# Profundidad de respuesta por rol
DETAIL_LEVEL = {
    "Operator": "operator",
    "Supervisor": "supervisor",
    "Product Engineer": "engineering",
    "Quality": "engineering",
    "NPI": "engineering",
    "MES Support": "engineering",
    "Knowledge Manager": "engineering",
    "Data Steward": "engineering",
    "Administrator": "admin",
    "Auditor": "engineering",
}


class AccessPolicy:
    def __init__(self, access_matrix: dict[str, Iterable[str]] | None = None):
        matrix = {k: tuple(v) for k, v in (access_matrix or {}).items()}
        self.clearance = {role: matrix.get(role, DEFAULT_CLEARANCE[role]) for role in DEFAULT_CLEARANCE}

    def permissions_for(self, role: str) -> frozenset[str]:
        return ROLE_PERMISSIONS.get(role, frozenset())

    def clearance_for(self, role: str) -> tuple[str, ...]:
        return self.clearance.get(role, ("Public",))

    def can_see(self, role: str, classification: str) -> bool:
        return classification in self.clearance_for(role)


def require(user: AuthenticatedUser, permission: str) -> None:
    if "*" in user.permissions:
        return
    if permission not in user.permissions:
        raise PermissionDenied()


def require_classification(user: AuthenticatedUser, classification: str) -> None:
    if classification not in user.clearance:
        raise PermissionDenied("No tienes acceso a esta clasificación de información.")
