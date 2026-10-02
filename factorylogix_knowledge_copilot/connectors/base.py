"""Infraestructura de conectores de solo lectura: circuit breaker, caché TTL y errores tipados."""
from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from typing import Any

from core.errors import ConnectorError


class ConnectorDisabled(ConnectorError):
    user_message = "El conector de FactoryLogix está desactivado (feature flag)."


class ConnectorAuthError(ConnectorError):
    user_message = "FactoryLogix rechazó las credenciales (HTTP 401). Contacta a Soporte MES."


class ConnectorForbidden(ConnectorError):
    user_message = "La cuenta de servicio no tiene permiso para esta entidad (HTTP 403)."


class ConnectorNotFound(ConnectorError):
    user_message = "Entidad o registro no encontrado en FactoryLogix (HTTP 404)."


class ConnectorRateLimited(ConnectorError):
    user_message = "FactoryLogix limitó las solicitudes (HTTP 429). Intenta más tarde."


class ConnectorServerError(ConnectorError):
    user_message = "FactoryLogix devolvió un error interno (HTTP 5xx)."


class ConnectorTimeout(ConnectorError):
    user_message = "Tiempo de espera agotado al consultar FactoryLogix."


class ConnectorUnavailable(ConnectorError):
    user_message = "FactoryLogix no está disponible (circuit breaker abierto o sin conexión)."


class CircuitBreaker:
    def __init__(self, failure_threshold: int = 3, reset_seconds: float = 60.0, clock=time.monotonic):
        self.failure_threshold = failure_threshold
        self.reset_seconds = reset_seconds
        self.clock = clock
        self.failures = 0
        self.opened_at: float | None = None
        self._lock = threading.Lock()

    @property
    def state(self) -> str:
        with self._lock:
            if self.opened_at is None:
                return "closed"
            if self.clock() - self.opened_at >= self.reset_seconds:
                return "half-open"
            return "open"

    def allow(self) -> bool:
        return self.state != "open"

    def record_success(self) -> None:
        with self._lock:
            self.failures = 0
            self.opened_at = None

    def record_failure(self) -> None:
        with self._lock:
            self.failures += 1
            if self.failures >= self.failure_threshold:
                self.opened_at = self.clock()


class TTLCache:
    def __init__(self, ttl_seconds: float, max_items: int = 256, clock=time.monotonic):
        self.ttl = ttl_seconds
        self.max_items = max_items
        self.clock = clock
        self._data: dict[str, tuple[float, Any]] = {}
        self._lock = threading.Lock()

    def get(self, key: str) -> Any | None:
        with self._lock:
            item = self._data.get(key)
            if not item:
                return None
            if self.clock() - item[0] > self.ttl:
                self._data.pop(key, None)
                return None
            return item[1]

    def set(self, key: str, value: Any) -> None:
        with self._lock:
            if len(self._data) >= self.max_items:
                oldest = min(self._data, key=lambda k: self._data[k][0])
                self._data.pop(oldest, None)
            self._data[key] = (self.clock(), value)

    def clear(self) -> None:
        with self._lock:
            self._data.clear()


@dataclass
class LiveResult:
    """Resultado de una consulta en vivo. Siempre se etiqueta como 'Información consultada en FactoryLogix'."""

    entity: str
    rows: list[dict[str, Any]]
    from_cache: bool
    retrieved_at: str
    source_label: str = "FactoryLogix (consulta en vivo, solo lectura)"
    warnings: list[str] = field(default_factory=list)
