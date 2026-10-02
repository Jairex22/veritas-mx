"""Conector OData de FactoryLogix Analytics: SOLO LECTURA, desactivado por defecto.

- Solo método GET; no existe ningún método para Proceed/Unproceed/Reroute/cierre de defectos.
- Entidades y campos en allowlist (config/odata_entities.yaml).
- Credenciales solo desde variables de entorno (FLKC_ODATA_TOKEN o FLKC_ODATA_USERNAME/PASSWORD).
- Timeout, reintentos limitados con backoff, circuit breaker, caché TTL y manejo separado de
  401/403/404/429/5xx/timeout.
"""
from __future__ import annotations

import ipaddress
import socket
import time
from typing import Any, Callable
from urllib.parse import urlparse

import requests

from connectors.base import (CircuitBreaker, ConnectorAuthError, ConnectorDisabled, ConnectorForbidden,
                             ConnectorNotFound, ConnectorRateLimited, ConnectorServerError, ConnectorTimeout,
                             ConnectorUnavailable, LiveResult, TTLCache)
from core.errors import ValidationError
from core.logging_setup import get_logger
from core.text import truncate
from core.utils import now_iso
from security.sanitize import validate_identifier

log = get_logger("odata")


class ODataConnector:
    def __init__(self, *, enabled: bool, base_url: str, entities: dict[str, dict[str, Any]],
                 allowed_hosts: list[str] | None = None, timeout: float = 10, max_retries: int = 2,
                 backoff: float = 1.0, failure_threshold: int = 3, reset_seconds: float = 60,
                 cache_ttl: float = 120, max_rows: int = 200, verify_tls: bool = True,
                 token: str | None = None, username: str | None = None, password: str | None = None,
                 session: requests.Session | None = None, sleep: Callable[[float], None] = time.sleep):
        self.enabled = enabled
        self.base_url = (base_url or "").rstrip("/")
        self.entities = entities
        self.allowed_hosts = [h.lower() for h in (allowed_hosts or [])]
        self.timeout = timeout
        self.max_retries = max(0, min(int(max_retries), 5))
        self.backoff = backoff
        self.max_rows = max_rows
        self.verify_tls = verify_tls
        self.breaker = CircuitBreaker(failure_threshold, reset_seconds)
        self.cache = TTLCache(cache_ttl)
        self.session = session or requests.Session()
        self.session.trust_env = False
        self.sleep = sleep
        self._auth_header: dict[str, str] = {}
        self._basic: tuple[str, str] | None = None
        if token:
            self._auth_header = {"Authorization": f"Bearer {token}"}
        elif username and password:
            self._basic = (username, password)

    # --- validaciones ---
    def _check_enabled(self) -> None:
        if not self.enabled:
            raise ConnectorDisabled()
        if not self.base_url:
            raise ConnectorDisabled("El conector OData no tiene URL configurada.")

    def _check_host(self) -> None:
        parsed = urlparse(self.base_url)
        host = (parsed.hostname or "").lower()
        if parsed.scheme not in {"http", "https"} or not host:
            raise ValidationError("URL OData inválida.")
        if self.allowed_hosts:
            if host not in self.allowed_hosts:
                raise ValidationError("Host OData fuera de la allowlist configurada.")
            return
        try:
            addr = ipaddress.ip_address(host)
        except ValueError:
            try:
                addr = ipaddress.ip_address(socket.gethostbyname(host))
            except (socket.gaierror, UnicodeError) as exc:
                raise ConnectorUnavailable("No se pudo resolver el host de FactoryLogix.") from exc
        if not (addr.is_private or addr.is_loopback):
            raise ValidationError("El host OData debe pertenecer a la red interna.")

    @staticmethod
    def _escape(value: str) -> str:
        return value.replace("'", "''")

    def build_params(self, entity: str, key_field: str, key_value: str, top: int) -> dict[str, str]:
        if entity not in self.entities:
            raise ValidationError("Entidad no permitida.")
        spec = self.entities[entity]
        if key_field not in spec.get("key_fields", []):
            raise ValidationError("Campo de búsqueda no permitido para esta entidad.")
        value = validate_identifier(key_value, key_field)
        if not value:
            raise ValidationError("Indica un valor de búsqueda.")
        params = {"$filter": f"{key_field} eq '{self._escape(value)}'",
                  "$top": str(max(1, min(int(top), self.max_rows)))}
        if spec.get("select"):
            params["$select"] = ",".join(spec["select"])
        return params

    # --- consulta ---
    def query(self, entity: str, key_field: str, key_value: str, top: int = 50) -> LiveResult:
        self._check_enabled()
        params = self.build_params(entity, key_field, key_value, top)
        self._check_host()
        cache_key = f"{entity}|{params['$filter']}|{params['$top']}"
        cached = self.cache.get(cache_key)
        if cached is not None:
            return LiveResult(entity=entity, rows=cached["rows"], from_cache=True, retrieved_at=cached["at"])
        if not self.breaker.allow():
            raise ConnectorUnavailable()

        url = f"{self.base_url}/{entity}"
        attempt = 0
        while True:
            attempt += 1
            try:
                resp = self.session.get(url, params=params, headers={"Accept": "application/json",
                                                                     **self._auth_header},
                                        auth=self._basic, timeout=self.timeout, verify=self.verify_tls)
            except requests.Timeout:
                error: Exception = ConnectorTimeout()
                retryable = True
            except requests.RequestException:
                error = ConnectorUnavailable("No hay conexión con FactoryLogix.")
                retryable = True
            else:
                status = resp.status_code
                if status == 200:
                    rows = self._sanitize_rows(entity, resp)
                    self.breaker.record_success()
                    at = now_iso()
                    self.cache.set(cache_key, {"rows": rows, "at": at})
                    return LiveResult(entity=entity, rows=rows, from_cache=False, retrieved_at=at)
                if status == 401:
                    raise ConnectorAuthError()
                if status == 403:
                    raise ConnectorForbidden()
                if status == 404:
                    raise ConnectorNotFound()
                if status == 429:
                    error, retryable = ConnectorRateLimited(), True
                elif status >= 500:
                    error, retryable = ConnectorServerError(), True
                else:
                    error, retryable = ConnectorServerError(f"Respuesta inesperada de FactoryLogix (HTTP {status})."), False
            self.breaker.record_failure()
            log.warning("odata error entity=%s attempt=%d type=%s", entity, attempt, type(error).__name__)
            if not retryable or attempt > self.max_retries or not self.breaker.allow():
                raise error
            self.sleep(self.backoff * (2 ** (attempt - 1)))

    def _sanitize_rows(self, entity: str, resp: requests.Response) -> list[dict[str, Any]]:
        try:
            payload = resp.json()
        except ValueError as exc:
            raise ConnectorServerError("Respuesta OData no es JSON válido.") from exc
        values = payload.get("value", []) if isinstance(payload, dict) else []
        allowed = set(self.entities[entity].get("select", [])) or None
        rows = []
        for item in values[: self.max_rows]:
            if not isinstance(item, dict):
                continue
            rows.append({str(k)[:60]: truncate(str(v), 200) for k, v in item.items()
                         if not str(k).startswith("@") and (allowed is None or k in allowed)})
        return rows

    def status(self) -> dict[str, Any]:
        return {"enabled": self.enabled, "configured": bool(self.base_url), "circuit": self.breaker.state,
                "auth": "token" if self._auth_header else "basic" if self._basic else "none",
                "entities": len(self.entities)}


class XTendConnector:
    """Integración futura con FactoryLogix xTend. Intencionalmente sin operaciones: cualquier integración
    requiere especificación, revisión de seguridad y aprobación de MES. Nunca se habilitarán escrituras."""

    def __init__(self, enabled: bool = False):
        self.enabled = enabled

    def status(self) -> dict[str, Any]:
        return {"enabled": False, "configured": False, "note": "Pendiente de especificación aprobada (solo lectura)."}

    def query(self, *_args: Any, **_kwargs: Any) -> LiveResult:
        raise ConnectorDisabled("La integración xTend no está habilitada en esta versión.")
