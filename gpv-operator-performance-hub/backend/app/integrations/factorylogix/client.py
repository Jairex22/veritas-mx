"""
Cliente OData genérico para FactoryLogix Operations/Analytics.

IMPORTANTE — no se inventan endpoints reales de FactoryLogix. Este cliente es
una capa de transporte configurable: apunta a la URL base y a los nombres de
entidad que el equipo de IT/MES autorice, mediante variables de entorno (ver
`.env.example` y `MANUAL_FACTORYLOGIX.md`). Nunca hardcodees aquí una URL o
credencial real.

Comportamiento:
- Autenticación Basic (usuario/contraseña leídos de variables de entorno).
- Timeout configurable.
- Reintentos limitados con backoff simple.
- Registro de errores (no credenciales) vía logging estándar.
- Si `FACTORYLOGIX_ENABLED=false` o la conexión falla tras los reintentos,
  el llamador debe usar el último conjunto de datos válido (modo offline) —
  ver `adapter.py`.
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass

import requests
from requests.auth import HTTPBasicAuth

from ...config import get_settings

logger = logging.getLogger("factorylogix.client")


class FactoryLogixConnectionError(Exception):
    """Se agotaron los reintentos o la configuración es inválida."""


@dataclass
class ODataQuery:
    entity: str
    filter_expr: str | None = None
    select: list[str] | None = None
    top: int | None = None
    orderby: str | None = None


class FactoryLogixClient:
    def __init__(self):
        self.settings = get_settings()

    @property
    def is_configured(self) -> bool:
        return bool(self.settings.flx_enabled and self.settings.flx_base_url and self.settings.flx_username)

    def fetch_entity(self, query: ODataQuery) -> list[dict]:
        """Devuelve una lista de registros crudos (dict) tal como los entrega OData
        en `value`. Lanza FactoryLogixConnectionError si no se pudo obtener la
        información tras los reintentos configurados."""
        if not self.is_configured:
            raise FactoryLogixConnectionError(
                "FactoryLogix no está configurado (FACTORYLOGIX_ENABLED, "
                "FACTORYLOGIX_BASE_URL o FACTORYLOGIX_USERNAME faltantes)."
            )

        url = f"{self.settings.flx_base_url.rstrip('/')}/{query.entity}"
        params: dict[str, str] = {}
        if query.filter_expr:
            params["$filter"] = query.filter_expr
        if query.select:
            params["$select"] = ",".join(query.select)
        if query.top:
            params["$top"] = str(query.top)
        if query.orderby:
            params["$orderby"] = query.orderby

        auth = HTTPBasicAuth(self.settings.flx_username, self.settings.flx_password)
        last_error: Exception | None = None

        for attempt in range(1, self.settings.flx_max_retries + 2):
            try:
                response = requests.get(
                    url, params=params, auth=auth, timeout=self.settings.flx_timeout_seconds,
                    headers={"Accept": "application/json"},
                )
                response.raise_for_status()
                payload = response.json()
                return payload.get("value", payload if isinstance(payload, list) else [])
            except requests.RequestException as exc:
                last_error = exc
                logger.warning(
                    "Intento %s/%s fallido al consultar FactoryLogix (%s): %s",
                    attempt, self.settings.flx_max_retries + 1, query.entity, exc,
                )
                if attempt <= self.settings.flx_max_retries:
                    time.sleep(min(2 ** attempt, 8))

        raise FactoryLogixConnectionError(
            f"No fue posible consultar FactoryLogix ({query.entity}) tras "
            f"{self.settings.flx_max_retries + 1} intento(s): {last_error}"
        )
