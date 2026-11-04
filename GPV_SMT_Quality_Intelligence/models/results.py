"""Estados explícitos y resultado de una consulta OData.

Nunca se usa True/False para representar el resultado de una consulta:
la UI debe poder distinguir "sin registros" de "no se pudo consultar".
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class ODataStatus(str, Enum):
    OK = "OK"                          # Respuesta válida con registros
    EMPTY = "EMPTY"                    # Respuesta válida sin registros (NO equivale a PASS)
    AUTH_ERROR = "AUTH_ERROR"          # HTTP 401
    FORBIDDEN = "FORBIDDEN"            # HTTP 403
    NOT_FOUND = "NOT_FOUND"            # HTTP 404 (entidad/endpoint inexistente)
    BAD_REQUEST = "BAD_REQUEST"        # HTTP 400 (filtro no soportado por el servidor)
    RATE_LIMITED = "RATE_LIMITED"      # HTTP 429
    SERVER_ERROR = "SERVER_ERROR"      # HTTP 5xx
    HTTP_ERROR = "HTTP_ERROR"          # Otro código HTTP no esperado
    TIMEOUT = "TIMEOUT"
    CONNECTION_ERROR = "CONNECTION_ERROR"   # Red, DNS, conexión rechazada/interrumpida
    INVALID_RESPONSE = "INVALID_RESPONSE"   # JSON inválido o estructura inesperada
    BLOCKED_BY_POLICY = "BLOCKED_BY_POLICY" # Modo real no aprobado / Basic sobre HTTP
    NOT_CONFIGURED = "NOT_CONFIGURED"       # Faltan credenciales o URL
    VALIDATION_ERROR = "VALIDATION_ERROR"   # Entrada rechazada antes de consultar
    BUSY = "BUSY"                           # Límite de concurrencia alcanzado
    NOT_REQUESTED = "NOT_REQUESTED"         # La fuente no fue necesaria


SUCCESS_STATUSES = frozenset({ODataStatus.OK, ODataStatus.EMPTY})
RETRYABLE_HTTP = frozenset({429, 500, 502, 503, 504})

STATUS_LABELS_ES = {
    ODataStatus.OK: "Consulta correcta",
    ODataStatus.EMPTY: "Consulta correcta sin registros",
    ODataStatus.AUTH_ERROR: "Autenticación rechazada (HTTP 401)",
    ODataStatus.FORBIDDEN: "Acceso denegado (HTTP 403)",
    ODataStatus.NOT_FOUND: "Entidad o endpoint no encontrado (HTTP 404)",
    ODataStatus.BAD_REQUEST: "Consulta rechazada por el servidor (HTTP 400)",
    ODataStatus.RATE_LIMITED: "Servidor saturado (HTTP 429)",
    ODataStatus.SERVER_ERROR: "Error interno de FactoryLogix (HTTP 5xx)",
    ODataStatus.HTTP_ERROR: "Respuesta HTTP no esperada",
    ODataStatus.TIMEOUT: "Tiempo de espera agotado",
    ODataStatus.CONNECTION_ERROR: "Servidor inaccesible (red/DNS)",
    ODataStatus.INVALID_RESPONSE: "Respuesta OData inválida",
    ODataStatus.BLOCKED_BY_POLICY: "Bloqueado por política de seguridad",
    ODataStatus.NOT_CONFIGURED: "Conexión no configurada",
    ODataStatus.VALIDATION_ERROR: "Entrada no válida",
    ODataStatus.BUSY: "Otra consulta OData en curso",
    ODataStatus.NOT_REQUESTED: "No requerida",
}


@dataclass
class QueryResult:
    status: ODataStatus
    entity: str
    rows: list[dict[str, Any]] = field(default_factory=list)
    http_status: int | None = None
    elapsed_ms: float = 0.0
    timings: dict[str, float] = field(default_factory=dict)
    attempts: int = 0
    error: str | None = None
    query_description: str = ""
    data_source: str = "live"          # live | demo | cache
    truncated: bool = False
    stale: bool = False
    cached_at: str | None = None
    fetched_at: str | None = None

    @property
    def ok(self) -> bool:
        return self.status in SUCCESS_STATUSES

    def to_status_dict(self) -> dict[str, Any]:
        """Resumen sin filas, apto para la UI y el diagnóstico."""
        return {
            "entity": self.entity,
            "status": self.status.value,
            "label": STATUS_LABELS_ES.get(self.status, self.status.value),
            "ok": self.ok,
            "http_status": self.http_status,
            "elapsed_ms": round(self.elapsed_ms, 1),
            "timings": {k: round(v, 1) for k, v in self.timings.items()},
            "attempts": self.attempts,
            "error": self.error,
            "rows": len(self.rows),
            "query": self.query_description,
            "data_source": self.data_source,
            "truncated": self.truncated,
            "stale": self.stale,
            "cached_at": self.cached_at,
            "fetched_at": self.fetched_at,
        }
