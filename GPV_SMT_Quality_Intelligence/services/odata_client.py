"""Cliente FactoryLogix OData independiente de la UI.

Características:
- Lista blanca de entidades/campos (services.odata_filters).
- Tipos y versión OData leídos de $metadata (con respaldo marcado como no verificado).
- Límite global de solicitudes simultáneas (semáforo, por defecto 1).
- Reintentos con backoff solo para HTTP 429/500/502/503/504; nunca para 401/403.
- Sin seguir redirecciones (evita reenviar credenciales a otro host).
- Sin proxy del sistema para la red interna.
- Validación estricta de la estructura JSON.
- Medición de tiempos: espera de cabeceras (red + servidor), descarga y parseo.
- Nunca registra cabeceras Authorization ni contraseñas.
"""
from __future__ import annotations

import base64
import json
import logging
import socket
import threading
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from typing import Callable
from urllib.parse import urlsplit

from backend.credentials import Credential, CredentialError, get_credential
from models.entities import KNOWN_ENTITIES
from models.query import QuerySpec
from models.results import RETRYABLE_HTTP, ODataStatus, QueryResult
from services.metadata import MetadataError, ODataMetadata, parse_metadata
from services.odata_filters import FilterError, build_query_url

log = logging.getLogger("gpv.odata")


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise urllib.error.HTTPError(req.full_url, code, "Redirección no permitida", headers, fp)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def parse_odata_payload(raw: bytes) -> tuple[list[dict], str | None]:
    """Valida la estructura OData y devuelve (filas, nextLink).

    Acepta {"value": [...]} (v4), {"d": {"results": [...]}} (v2/v3) y
    {"d": [...]} (v1). Cualquier otra estructura lanza ValueError.
    """
    try:
        payload = json.loads(raw.decode("utf-8-sig"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"JSON inválido: {exc.__class__.__name__}") from exc
    if not isinstance(payload, dict):
        raise ValueError("La raíz JSON no es un objeto")
    next_link = None
    if "value" in payload:
        rows = payload["value"]
        next_link = payload.get("@odata.nextLink") or payload.get("odata.nextLink")
    elif "d" in payload:
        d = payload["d"]
        if isinstance(d, list):
            rows = d
        elif isinstance(d, dict) and isinstance(d.get("results"), list):
            rows = d["results"]
            next_link = d.get("__next")
        else:
            raise ValueError("Estructura 'd' inesperada")
    elif "error" in payload or "odata.error" in payload:
        raise ValueError("El servidor devolvió un objeto de error OData")
    else:
        raise ValueError("No se encontró la colección 'value'")
    if not isinstance(rows, list):
        raise ValueError("'value' no es una lista")
    clean = []
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError("Un registro no es un objeto JSON")
        clean.append({k: v for k, v in row.items()
                      if not k.startswith("@odata") and not k.startswith("odata.") and k != "__metadata"})
    if next_link is not None and not isinstance(next_link, str):
        next_link = None
    return clean, next_link


class FactoryLogixODataClient:
    METADATA_RETRY_SECONDS = 300

    def __init__(self, config: dict, credential_provider: Callable[[dict], Credential | None] = get_credential,
                 on_result: Callable[[QueryResult], None] | None = None):
        self.config = config
        self.odata_cfg = config["odata"]
        self.base_url = self.odata_cfg["base_url"].rstrip("/") + "/"
        self._credential_provider = credential_provider
        self._on_result = on_result
        self._semaphore = threading.BoundedSemaphore(max(1, int(self.odata_cfg["max_concurrent_requests"])))
        self._metadata: ODataMetadata | None = None
        self._metadata_at = 0.0
        self._metadata_failed_at = 0.0
        self._metadata_lock = threading.Lock()
        self.last_metadata_status: dict | None = None
        proxy = urllib.request.ProxyHandler({})
        self._opener = urllib.request.build_opener(proxy, _NoRedirect())

    # ------------------------------------------------------------------ policy
    def policy_check(self, entity: str) -> QueryResult | None:
        sec = self.config["security"]
        if self.config.get("mode") != "live":
            return QueryResult(ODataStatus.BLOCKED_BY_POLICY, entity,
                               error="La aplicación está en modo demostración")
        if not sec.get("live_mode_approved"):
            return QueryResult(ODataStatus.BLOCKED_BY_POLICY, entity,
                               error="El modo de conexión real no está aprobado "
                                     "(security.live_mode_approved=false en config.json)")
        scheme = urlsplit(self.base_url).scheme
        if self.odata_cfg["auth_method"] == "basic" and scheme != "https" \
                and not sec.get("allow_basic_auth_over_http"):
            return QueryResult(ODataStatus.BLOCKED_BY_POLICY, entity,
                               error="Basic Auth sobre HTTP no está aprobado por TI. "
                                     "Se requiere HTTPS/proxy corporativo o aprobación explícita "
                                     "(security.allow_basic_auth_over_http).")
        return None

    def _auth_header(self, entity: str) -> tuple[str | None, QueryResult | None]:
        if self.odata_cfg["auth_method"] == "none":
            return None, None
        try:
            cred = self._credential_provider(self.odata_cfg)
        except CredentialError as exc:
            return None, QueryResult(ODataStatus.NOT_CONFIGURED, entity, error=str(exc))
        if cred is None:
            return None, QueryResult(ODataStatus.NOT_CONFIGURED, entity,
                                     error="No hay credenciales configuradas para FactoryLogix")
        token = base64.b64encode(f"{cred.username}:{cred.password}".encode("utf-8")).decode("ascii")
        return f"Basic {token}", None

    # ----------------------------------------------------------------- request
    def _same_origin(self, url: str) -> bool:
        a, b = urlsplit(url), urlsplit(self.base_url)
        return (a.scheme, a.hostname, a.port) == (b.scheme, b.hostname, b.port)

    def _request(self, url: str, entity: str, accept: str, description: str) -> tuple[QueryResult, bytes | None]:
        """Una solicitud HTTP con reintentos acotados. Devuelve (resultado, cuerpo)."""
        result = QueryResult(ODataStatus.CONNECTION_ERROR, entity, query_description=description,
                             data_source="live")
        auth, problem = self._auth_header(entity)
        if problem:
            problem.query_description = description
            return problem, None
        timeout = float(self.odata_cfg["timeout_seconds"])
        max_bytes = int(float(self.odata_cfg["max_response_mb"]) * 1024 * 1024)
        max_attempts = 1 + max(0, min(2, int(self.odata_cfg["max_retries"])))
        backoff = float(self.odata_cfg["backoff_seconds"])
        timings = {"wait_headers_ms": 0.0, "download_ms": 0.0, "backoff_ms": 0.0}
        started = time.perf_counter()
        body = None
        for attempt in range(1, max_attempts + 1):
            result.attempts = attempt
            req = urllib.request.Request(url, method="GET")
            req.add_header("Accept", accept)
            req.add_header("User-Agent", "GPV-SMT-Quality-Intelligence")
            if auth:
                req.add_header("Authorization", auth)
            t0 = time.perf_counter()
            retry_after = None
            try:
                with self._opener.open(req, timeout=timeout) as resp:
                    t1 = time.perf_counter()
                    timings["wait_headers_ms"] += (t1 - t0) * 1000
                    result.http_status = resp.status
                    data = resp.read(max_bytes + 1)
                    timings["download_ms"] += (time.perf_counter() - t1) * 1000
                if len(data) > max_bytes:
                    result.status = ODataStatus.INVALID_RESPONSE
                    result.error = "La respuesta excede el tamaño máximo permitido"
                else:
                    result.status, result.error, body = ODataStatus.OK, None, data
                break
            except urllib.error.HTTPError as exc:
                timings["wait_headers_ms"] += (time.perf_counter() - t0) * 1000
                code = exc.code
                result.http_status = code
                result.status, result.error = self._map_http(code, exc.reason)
                try:
                    exc.close()
                except Exception:  # noqa: BLE001 - cierre best-effort del socket
                    pass
                if code in RETRYABLE_HTTP and attempt < max_attempts:
                    retry_after = exc.headers.get("Retry-After") if exc.headers else None
                else:
                    break
            except (TimeoutError, socket.timeout):
                timings["wait_headers_ms"] += (time.perf_counter() - t0) * 1000
                result.status = ODataStatus.TIMEOUT
                result.error = f"Sin respuesta completa en {timeout:g} s"
                break   # no se reintenta un timeout: evita cargar más al servidor
            except urllib.error.URLError as exc:
                timings["wait_headers_ms"] += (time.perf_counter() - t0) * 1000
                reason = exc.reason
                if isinstance(reason, (TimeoutError, socket.timeout)):
                    result.status = ODataStatus.TIMEOUT
                    result.error = f"Tiempo de conexión agotado ({timeout:g} s)"
                elif isinstance(reason, socket.gaierror):
                    result.status = ODataStatus.CONNECTION_ERROR
                    result.error = "No se pudo resolver el nombre del servidor (DNS)"
                elif isinstance(reason, ConnectionRefusedError):
                    result.status = ODataStatus.CONNECTION_ERROR
                    result.error = "Conexión rechazada por el servidor"
                else:
                    result.status = ODataStatus.CONNECTION_ERROR
                    result.error = f"Servidor inaccesible: {reason.__class__.__name__}"
                break
            except (ConnectionError, OSError) as exc:
                timings["wait_headers_ms"] += (time.perf_counter() - t0) * 1000
                result.status = ODataStatus.CONNECTION_ERROR
                result.error = f"Conexión interrumpida: {exc.__class__.__name__}"
                break
            # backoff antes del siguiente intento
            wait = backoff * attempt
            if retry_after and retry_after.isdigit():
                wait = min(30.0, max(wait, float(retry_after)))
            log.warning("Reintento %s/%s para %s tras %s (espera %.1fs)", attempt + 1, max_attempts,
                        entity, result.status.value, wait)
            time.sleep(wait)
            timings["backoff_ms"] += wait * 1000
        result.elapsed_ms = (time.perf_counter() - started) * 1000
        result.timings = timings
        result.fetched_at = _now_iso()
        return result, body

    @staticmethod
    def _map_http(code: int, reason) -> tuple[ODataStatus, str]:
        if code == 401:
            return ODataStatus.AUTH_ERROR, "HTTP 401: credenciales rechazadas o ausentes"
        if code == 403:
            return ODataStatus.FORBIDDEN, "HTTP 403: el usuario no tiene permiso para esta entidad"
        if code == 404:
            return ODataStatus.NOT_FOUND, "HTTP 404: entidad o endpoint inexistente"
        if code == 400:
            return ODataStatus.BAD_REQUEST, "HTTP 400: el servidor rechazó la consulta"
        if code == 429:
            return ODataStatus.RATE_LIMITED, "HTTP 429: demasiadas solicitudes"
        if 500 <= code <= 599:
            return ODataStatus.SERVER_ERROR, f"HTTP {code}: error del servidor FactoryLogix"
        if 300 <= code <= 399:
            return ODataStatus.HTTP_ERROR, f"HTTP {code}: redirección no permitida"
        return ODataStatus.HTTP_ERROR, f"HTTP {code}: {reason}"

    def _emit(self, result: QueryResult) -> QueryResult:
        log.info("ODATA | %s | %s | HTTP=%s | %.0f ms | intentos=%s | filas=%s | %s | %s",
                 result.entity, result.status.value, result.http_status, result.elapsed_ms,
                 result.attempts, len(result.rows), result.query_description, result.error or "")
        if self._on_result:
            try:
                self._on_result(result)
            except Exception:  # noqa: BLE001 - la auditoría no debe romper la consulta
                log.exception("Error registrando auditoría de consulta")
        return result

    def _acquire(self, entity: str) -> QueryResult | None:
        wait = float(self.odata_cfg["timeout_seconds"]) * 2
        if not self._semaphore.acquire(timeout=wait):
            return QueryResult(ODataStatus.BUSY, entity,
                               error="Límite de solicitudes simultáneas alcanzado; intente de nuevo")
        return None

    # ---------------------------------------------------------------- metadata
    def fetch_metadata(self, force: bool = False) -> tuple[QueryResult, ODataMetadata | None]:
        blocked = self.policy_check("$metadata")
        if blocked:
            return self._emit(blocked), None
        busy = self._acquire("$metadata")
        if busy:
            return self._emit(busy), None
        try:
            result, body = self._request(self.base_url + "$metadata", "$metadata",
                                         "application/xml", "$metadata")
        finally:
            self._semaphore.release()
        meta = None
        if result.status == ODataStatus.OK and body is not None:
            try:
                meta = parse_metadata(body)
            except MetadataError as exc:
                result.status, result.error = ODataStatus.INVALID_RESPONSE, str(exc)
        with self._metadata_lock:
            if meta:
                self._metadata, self._metadata_at = meta, time.monotonic()
            else:
                self._metadata_failed_at = time.monotonic()
            self.last_metadata_status = result.to_status_dict()
        return self._emit(result), meta

    def metadata(self) -> ODataMetadata | None:
        ttl = float(self.odata_cfg["metadata_ttl_minutes"]) * 60
        with self._metadata_lock:
            fresh = self._metadata and time.monotonic() - self._metadata_at < ttl
            recently_failed = time.monotonic() - self._metadata_failed_at < self.METADATA_RETRY_SECONDS \
                and self._metadata_failed_at > 0
            if fresh or recently_failed:
                return self._metadata
        _, meta = self.fetch_metadata()
        return meta or self._metadata

    # ------------------------------------------------------------------- query
    def execute(self, spec: QuerySpec) -> QueryResult:
        description = spec.describe()
        blocked = self.policy_check(spec.entity)
        if blocked:
            blocked.query_description = description
            return self._emit(blocked)
        meta = self.metadata()
        props, version, verified = KNOWN_ENTITIES.get(spec.entity), "4", False
        if meta is not None:
            real = meta.properties_for(spec.entity)
            if real is None:
                return self._emit(QueryResult(ODataStatus.NOT_FOUND, spec.entity, query_description=description,
                                              error=f"La entidad {spec.entity} no existe en $metadata"))
            props, version, verified = real, meta.odata_version, True
        try:
            url = build_query_url(self.base_url, spec, props, version)
        except FilterError as exc:
            return self._emit(QueryResult(ODataStatus.VALIDATION_ERROR, spec.entity,
                                          query_description=description, error=str(exc)))
        if not verified:
            description += " | tipos no verificados ($metadata no disponible)"
        busy = self._acquire(spec.entity)
        if busy:
            busy.query_description = description
            return self._emit(busy)
        try:
            all_rows: list[dict] = []
            total = QueryResult(ODataStatus.OK, spec.entity, query_description=description, data_source="live")
            pages = 0
            next_url: str | None = url
            while next_url and pages < int(self.odata_cfg["max_pages"]):
                pages += 1
                res, body = self._request(next_url, spec.entity, "application/json", description)
                total.attempts += res.attempts
                total.elapsed_ms += res.elapsed_ms
                for k, v in res.timings.items():
                    total.timings[k] = total.timings.get(k, 0.0) + v
                total.http_status, total.fetched_at = res.http_status, res.fetched_at
                if res.status != ODataStatus.OK or body is None:
                    total.status, total.error = res.status, res.error
                    total.rows = []
                    return self._emit(total)
                t0 = time.perf_counter()
                try:
                    rows, next_link = parse_odata_payload(body)
                except ValueError as exc:
                    total.status, total.error, total.rows = ODataStatus.INVALID_RESPONSE, str(exc), []
                    return self._emit(total)
                total.timings["parse_ms"] = total.timings.get("parse_ms", 0.0) + (time.perf_counter() - t0) * 1000
                all_rows.extend(rows)
                if len(all_rows) >= spec.top:
                    all_rows = all_rows[:spec.top]
                    total.truncated = bool(next_link) or len(rows) >= spec.top
                    break
                if next_link and not self._same_origin(next_link):
                    total.error = "nextLink de otro origen ignorado"
                    total.truncated = True
                    break
                next_url = next_link
            else:
                if next_url:
                    total.truncated = True
            if len(all_rows) >= spec.top:
                total.truncated = True
            total.rows = all_rows
            total.status = ODataStatus.OK if all_rows else ODataStatus.EMPTY
            return self._emit(total)
        finally:
            self._semaphore.release()
