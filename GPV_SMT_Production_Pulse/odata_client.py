"""Protective OData client for FactoryLogix.

Design rules enforced here (not merely documented):

* Only HTTP GET, only to ``$metadata`` and ``ProductivityOverTime`` (see ``security.ensure_allowed_resource``).
* Every entity request carries ``$top`` <= ``MAX_RECORDS``; requests without ``$top`` are refused.
* One active OData request per process (non-blocking lock: a second request is rejected, not queued).
* Minimum spacing between requests, hourly budgets per session and global.
* Circuit breaker after consecutive server/network failures, honoring ``Retry-After``.
* No automatic retries, no redirects, no pagination following (``nextLink`` is only reported).
* Response body capped at ``MAX_RESPONSE_BYTES``; total request deadline enforced.
* Authorization headers are never logged.
"""
from __future__ import annotations

import json
import logging
import socket
import threading
import time
import urllib.error
import urllib.request
from collections import deque
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Protocol
from urllib.parse import quote

from security import ALLOWED_FILTER_OPERATORS, ensure_allowed_resource, validate_property_name
from settings import Config, Limits
from timeutil import iso_utc, utc_now

logger = logging.getLogger("pulse.odata")


class Status(str, Enum):
    """Outcome of an OData interaction (HTTP results plus local protection states)."""

    OK = "ok"
    BAD_REQUEST = "bad_request"              # HTTP 400
    AUTH_REQUIRED = "auth_required"          # HTTP 401
    FORBIDDEN = "forbidden"                  # HTTP 403
    NOT_FOUND = "not_found"                  # HTTP 404
    TOO_MANY_REQUESTS = "too_many_requests"  # HTTP 429
    SERVER_ERROR = "server_error"            # HTTP 500
    UNAVAILABLE = "unavailable"              # HTTP 502/503/504
    HTTP_ERROR = "http_error"                # other HTTP status
    TIMEOUT = "timeout"
    CONNECTION_ERROR = "connection_error"
    METADATA_INCOMPATIBLE = "metadata_incompatible"
    INVALID_JSON = "invalid_json"
    INCOMPLETE_DATA = "incomplete_data"
    RESPONSE_TOO_LARGE = "response_too_large"
    REDIRECT_BLOCKED = "redirect_blocked"
    UNSUPPORTED_FORMAT = "unsupported_format"
    BUSY = "busy"
    RATE_LIMITED = "rate_limited"
    SESSION_LIMIT = "session_limit"
    GLOBAL_LIMIT = "global_limit"
    CIRCUIT_OPEN = "circuit_open"
    BLOCKED_UNVERIFIED = "blocked_unverified"
    AUTH_NOT_AVAILABLE = "auth_not_available"


MESSAGES_ES: dict[Status, str] = {
    Status.OK: "Respuesta recibida de FactoryLogix.",
    Status.BAD_REQUEST: "FactoryLogix rechazó la consulta (consulta incompatible). No se reintentó sin filtros.",
    Status.AUTH_REQUIRED: "FactoryLogix requiere autenticación. Verifica la configuración aprobada por TI.",
    Status.FORBIDDEN: "Acceso denegado por FactoryLogix para esta cuenta.",
    Status.NOT_FOUND: "El recurso solicitado no existe en el servidor OData.",
    Status.TOO_MANY_REQUESTS: "FactoryLogix indicó demasiadas solicitudes. Se pausarán las consultas temporalmente.",
    Status.SERVER_ERROR: "FactoryLogix tuvo un error interno. Puedes visualizar la última información guardada.",
    Status.UNAVAILABLE: "El servicio FactoryLogix no está disponible. Puedes visualizar la última información guardada.",
    Status.HTTP_ERROR: "FactoryLogix respondió con un estado inesperado.",
    Status.TIMEOUT: "FactoryLogix no respondió a tiempo. Puedes visualizar la última información guardada.",
    Status.CONNECTION_ERROR: "No se pudo consultar FactoryLogix. Puedes visualizar la última información guardada.",
    Status.METADATA_INCOMPATIBLE: "La metadata de FactoryLogix no es compatible con lo esperado.",
    Status.INVALID_JSON: "FactoryLogix respondió con datos que no se pudieron interpretar (JSON inválido).",
    Status.INCOMPLETE_DATA: "La respuesta de FactoryLogix está incompleta.",
    Status.RESPONSE_TOO_LARGE: "La respuesta superó el tamaño máximo permitido y fue descartada.",
    Status.REDIRECT_BLOCKED: "El servidor intentó redirigir la solicitud; se bloqueó por seguridad.",
    Status.UNSUPPORTED_FORMAT: "FactoryLogix respondió en un formato no compatible (se esperaba JSON).",
    Status.BUSY: "Ya hay una consulta en curso. Espera a que termine.",
    Status.RATE_LIMITED: "Espera unos segundos antes de realizar otra consulta.",
    Status.SESSION_LIMIT: "Alcanzaste el límite de consultas por hora de esta sesión.",
    Status.GLOBAL_LIMIT: "Se alcanzó el límite de consultas por hora de la aplicación.",
    Status.CIRCUIT_OPEN: "Las consultas están pausadas temporalmente por errores repetidos del servidor.",
    Status.BLOCKED_UNVERIFIED: "Consulta bloqueada: los filtros necesarios no están comprobados.",
    Status.AUTH_NOT_AVAILABLE: "La autenticación Windows está configurada, pero falta la biblioteca opcional requerida.",
}

# Statuses that count as server/network health failures for the circuit breaker.
BREAKER_FAILURES = frozenset({
    Status.TOO_MANY_REQUESTS, Status.SERVER_ERROR, Status.UNAVAILABLE,
    Status.TIMEOUT, Status.CONNECTION_ERROR,
})
# Local states: no request reached the server.
LOCAL_REJECTIONS = frozenset({
    Status.BUSY, Status.RATE_LIMITED, Status.SESSION_LIMIT, Status.GLOBAL_LIMIT,
    Status.CIRCUIT_OPEN, Status.BLOCKED_UNVERIFIED, Status.AUTH_NOT_AVAILABLE,
})


# --------------------------------------------------------------------------- transport


class TransportTimeout(Exception):
    pass


class TransportConnectionError(Exception):
    pass


class ResponseTooLargeError(Exception):
    pass


class RedirectBlockedError(Exception):
    pass


class AuthNotAvailableError(Exception):
    pass


@dataclass
class TransportResponse:
    status: int
    headers: dict[str, str]
    body: bytes


class Transport(Protocol):
    """Minimal GET-only transport interface (real HTTP, Windows auth, or demo simulator)."""

    def get(self, url: str, headers: dict[str, str], timeout: float, max_bytes: int) -> TransportResponse:
        ...


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):  # type: ignore[override]
        raise RedirectBlockedError(f"redirect {code} blocked")


def _read_bounded(read: Callable[[int], bytes], max_bytes: int, deadline: float) -> bytes:
    chunks: list[bytes] = []
    total = 0
    while True:
        if time.monotonic() > deadline:
            raise TransportTimeout("total deadline exceeded while reading")
        chunk = read(65_536)
        if not chunk:
            break
        total += len(chunk)
        if total > max_bytes:
            raise ResponseTooLargeError(f"response exceeded {max_bytes} bytes")
        chunks.append(chunk)
    return b"".join(chunks)


class UrllibTransport:
    """Standard-library HTTP transport (anonymous or network-level authentication)."""

    def __init__(self, use_system_proxy: bool = False) -> None:
        handlers: list[Any] = [_NoRedirect()]
        if not use_system_proxy:
            handlers.append(urllib.request.ProxyHandler({}))
        self._opener = urllib.request.build_opener(*handlers)

    def get(self, url: str, headers: dict[str, str], timeout: float, max_bytes: int) -> TransportResponse:
        request = urllib.request.Request(url, headers=headers, method="GET")
        deadline = time.monotonic() + timeout
        try:
            with self._opener.open(request, timeout=timeout) as response:
                length = response.headers.get("Content-Length")
                if length and length.isdigit() and int(length) > max_bytes:
                    raise ResponseTooLargeError("declared Content-Length too large")
                body = _read_bounded(response.read, max_bytes, deadline)
                return TransportResponse(response.status, dict(response.headers.items()), body)
        except urllib.error.HTTPError as exc:
            try:
                body = _read_bounded(exc.read, min(max_bytes, 65_536), deadline)
            except Exception:  # noqa: BLE001 - error body is optional
                body = b""
            return TransportResponse(exc.code, dict(exc.headers.items()) if exc.headers else {}, body)
        except RedirectBlockedError:
            raise
        except urllib.error.URLError as exc:
            if isinstance(exc.reason, (socket.timeout, TimeoutError)):
                raise TransportTimeout(str(exc.reason)) from exc
            if isinstance(exc.reason, RedirectBlockedError):
                raise exc.reason from exc
            raise TransportConnectionError(str(exc.reason)) from exc
        except (socket.timeout, TimeoutError) as exc:
            raise TransportTimeout(str(exc)) from exc
        except (ConnectionError, OSError) as exc:
            raise TransportConnectionError(str(exc)) from exc


class NegotiateTransport:
    """Windows integrated authentication (Negotiate/NTLM via SSPI) using the logged-on user.

    Requires the optional packages ``requests`` and ``requests-negotiate-sspi`` installed
    per user (``py -m pip install --user ...``). No password is stored or requested.
    """

    def __init__(self, use_system_proxy: bool = False) -> None:
        try:
            import requests  # type: ignore[import-not-found]
            from requests_negotiate_sspi import HttpNegotiateAuth  # type: ignore[import-not-found]
        except ImportError as exc:
            raise AuthNotAvailableError(str(exc)) from exc
        self._requests = requests
        self._session = requests.Session()
        self._session.trust_env = use_system_proxy
        self._session.auth = HttpNegotiateAuth()
        self._session.max_redirects = 0

    def get(self, url: str, headers: dict[str, str], timeout: float, max_bytes: int) -> TransportResponse:
        deadline = time.monotonic() + timeout
        try:
            response = self._session.get(url, headers=headers, timeout=(timeout, timeout),
                                         stream=True, allow_redirects=False)
        except self._requests.exceptions.Timeout as exc:
            raise TransportTimeout(str(exc)) from exc
        except self._requests.exceptions.RequestException as exc:
            raise TransportConnectionError(str(exc)) from exc
        try:
            if 300 <= response.status_code < 400:
                raise RedirectBlockedError(f"redirect {response.status_code} blocked")
            raw = response.raw
            body = _read_bounded(lambda n: raw.read(n), max_bytes, deadline)
            return TransportResponse(response.status_code, dict(response.headers.items()), body)
        finally:
            response.close()


# --------------------------------------------------------------------------- protection


class CircuitBreaker:
    """Opens after N consecutive failures; half-open allows a single trial after cooldown."""

    def __init__(self, threshold: int, cooldown_seconds: float, clock: Callable[[], float] = time.monotonic) -> None:
        self.threshold = threshold
        self.cooldown = cooldown_seconds
        self.clock = clock
        self.failures = 0
        self.opened_at: float | None = None
        self.open_for = cooldown_seconds
        self.trial_in_progress = False
        self._lock = threading.Lock()

    @property
    def state(self) -> str:
        if self.opened_at is None:
            return "closed"
        if self.clock() - self.opened_at >= self.open_for:
            return "half_open"
        return "open"

    def allow(self) -> tuple[bool, float]:
        with self._lock:
            state = self.state
            if state == "closed":
                return True, 0.0
            if state == "half_open" and not self.trial_in_progress:
                self.trial_in_progress = True
                return True, 0.0
            remaining = 0.0 if self.opened_at is None else max(0.0, self.open_for - (self.clock() - self.opened_at))
            return False, remaining

    def record_success(self) -> None:
        with self._lock:
            self.failures = 0
            self.opened_at = None
            self.trial_in_progress = False

    def record_failure(self, retry_after: float | None = None) -> None:
        with self._lock:
            self.failures += 1
            self.trial_in_progress = False
            if self.failures >= self.threshold or retry_after is not None or self.opened_at is not None:
                self.opened_at = self.clock()
                self.open_for = max(self.cooldown, retry_after or 0.0)

    def cancel_trial(self) -> None:
        with self._lock:
            self.trial_in_progress = False

    def record_neutral(self) -> None:
        """A response that is not a health failure (e.g. HTTP 400) ends a half-open trial."""
        with self._lock:
            if self.trial_in_progress:
                self.trial_in_progress = False
                self.opened_at = None
                self.failures = 0

    def snapshot(self) -> dict[str, Any]:
        allowed_remaining = 0.0
        if self.opened_at is not None:
            allowed_remaining = max(0.0, self.open_for - (self.clock() - self.opened_at))
        return {"state": self.state, "consecutive_failures": self.failures,
                "seconds_remaining": round(allowed_remaining), "threshold": self.threshold}


class RequestGate:
    """Single-flight lock plus spacing and hourly budgets."""

    def __init__(self, limits: Limits, clock: Callable[[], float] = time.monotonic) -> None:
        self.limits = limits
        self.clock = clock
        self._active = threading.BoundedSemaphore(limits.MAX_CONCURRENT_REQUESTS)
        self._lock = threading.Lock()
        self._last_request: float | None = None
        self._global: deque[float] = deque()
        self._sessions: dict[str, deque[float]] = {}

    @staticmethod
    def _prune(times: deque[float], now: float) -> None:
        while times and now - times[0] >= 3600:
            times.popleft()

    def try_acquire(self, session_id: str, enforce_spacing: bool = True) -> tuple[Status, float]:
        """Return (Status.OK, 0) and hold the slot, or a rejection status with wait seconds."""
        if not self._active.acquire(blocking=False):
            return Status.BUSY, 0.0
        with self._lock:
            now = self.clock()
            spacing = self.limits.MIN_SECONDS_BETWEEN_ODATA_REQUESTS
            if enforce_spacing and self._last_request is not None and now - self._last_request < spacing:
                self._active.release()
                return Status.RATE_LIMITED, spacing - (now - self._last_request)
            self._prune(self._global, now)
            if len(self._global) >= self.limits.MAX_ODATA_REQUESTS_PER_HOUR_GLOBAL:
                self._active.release()
                return Status.GLOBAL_LIMIT, 3600 - (now - self._global[0])
            session_times = self._sessions.setdefault(session_id, deque())
            self._prune(session_times, now)
            if len(session_times) >= self.limits.MAX_ODATA_REQUESTS_PER_SESSION_PER_HOUR:
                self._active.release()
                return Status.SESSION_LIMIT, 3600 - (now - session_times[0])
            if enforce_spacing:
                # Admin sequences (metadata/probes) have their own spacing and rate limit.
                self._last_request = now
            self._global.append(now)
            session_times.append(now)
            if len(self._sessions) > 1000:  # bound memory
                for key in [k for k, v in self._sessions.items() if not v][:500]:
                    self._sessions.pop(key, None)
            return Status.OK, 0.0

    def release(self) -> None:
        self._active.release()

    def is_busy(self) -> bool:
        if self._active.acquire(blocking=False):
            self._active.release()
            return False
        return True

    def usage(self, session_id: str | None = None) -> dict[str, int]:
        with self._lock:
            now = self.clock()
            self._prune(self._global, now)
            data = {"global_last_hour": len(self._global)}
            if session_id and session_id in self._sessions:
                self._prune(self._sessions[session_id], now)
                data["session_last_hour"] = len(self._sessions[session_id])
            else:
                data["session_last_hour"] = 0
            return data


# --------------------------------------------------------------------------- queries


@dataclass(frozen=True)
class FilterClause:
    """``field op literal``. The literal must already be produced by ``security`` helpers."""

    field: str
    op: str
    literal: str


@dataclass(frozen=True)
class QuerySpec:
    """A bounded, validated query against ProductivityOverTime."""

    top: int
    select: tuple[str, ...] = ()
    filters: tuple[FilterClause, ...] = ()
    orderby: tuple[str, str] | None = None  # (field, "asc"|"desc")


@dataclass
class ODataResult:
    """Normalized result of one OData interaction."""

    status: Status
    message: str
    http_status: int | None = None
    records: list[dict[str, Any]] = field(default_factory=list)
    body: bytes | None = None
    elapsed_ms: float = 0.0
    relative_url: str = ""
    more_available: bool = False
    top_ignored: bool = False
    retry_after: float | None = None
    wait_seconds: float = 0.0
    technical_detail: str = ""
    requested_at: str = ""

    @property
    def ok(self) -> bool:
        return self.status == Status.OK

    @property
    def reached_server(self) -> bool:
        return self.status not in LOCAL_REJECTIONS


def _parse_retry_after(value: str | None) -> float | None:
    if value and value.strip().isdigit():
        return min(float(value.strip()), 3600.0)
    return None


def _status_from_http(code: int) -> Status:
    if 200 <= code < 300:
        return Status.OK
    return {400: Status.BAD_REQUEST, 401: Status.AUTH_REQUIRED, 403: Status.FORBIDDEN,
            404: Status.NOT_FOUND, 429: Status.TOO_MANY_REQUESTS, 500: Status.SERVER_ERROR,
            502: Status.UNAVAILABLE, 503: Status.UNAVAILABLE, 504: Status.UNAVAILABLE}.get(code, Status.HTTP_ERROR)


class PayloadError(Exception):
    def __init__(self, status: Status, detail: str) -> None:
        super().__init__(detail)
        self.status = status


def parse_entity_payload(body: bytes) -> tuple[list[dict[str, Any]], bool]:
    """Parse V4 (``value``), V3 light (``value``) or V2 verbose (``d.results``) JSON.

    Returns (records, more_available). ``more_available`` is True when the server sent a
    next-page link; the link is never followed.
    """
    stripped = body.lstrip()
    if stripped[:1] == b"<":
        raise PayloadError(Status.UNSUPPORTED_FORMAT, "XML/Atom payload received")
    try:
        data = json.loads(body.decode("utf-8-sig"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise PayloadError(Status.INVALID_JSON, str(exc)[:200]) from exc
    if not isinstance(data, dict):
        raise PayloadError(Status.INCOMPLETE_DATA, "top-level JSON is not an object")
    more = False
    if "value" in data:
        records = data["value"]
        more = bool(data.get("@odata.nextLink") or data.get("odata.nextLink"))
    elif isinstance(data.get("d"), dict) and "results" in data["d"]:
        records = data["d"]["results"]
        more = bool(data["d"].get("__next"))
    elif isinstance(data.get("d"), list):
        records = data["d"]
    else:
        raise PayloadError(Status.INCOMPLETE_DATA, "no 'value' or 'd.results' collection in payload")
    if not isinstance(records, list) or not all(isinstance(r, dict) for r in records):
        raise PayloadError(Status.INCOMPLETE_DATA, "collection is not a list of objects")
    cleaned = [{k: v for k, v in r.items() if not k.startswith(("@odata", "odata.", "__"))} for r in records]
    return cleaned, more


class ODataClient:
    """GET-only client restricted to $metadata and ProductivityOverTime."""

    def __init__(self, config: Config, transport: Transport | None,
                 clock: Callable[[], float] = time.monotonic,
                 transport_error: str = "") -> None:
        self.config = config
        self.limits = config.limits
        self.transport = transport
        self.transport_error = transport_error
        self.base_url = config.odata.base_url
        self.gate = RequestGate(config.limits, clock)
        self.breaker = CircuitBreaker(config.limits.CIRCUIT_BREAKER_FAILURE_THRESHOLD,
                                      config.limits.CIRCUIT_BREAKER_COOLDOWN_SECONDS, clock)
        self.last: dict[str, Any] = {}
        self.auth_description = "Simulador" if transport is not None and type(transport).__name__ == "DemoTransport" else "—"
        self.request_log: list[str] = []  # relative URLs actually sent (bounded), for audits/tests

    # ----------------------------------------------------------------- URL building
    def build_relative_url(self, resource: str, spec: QuerySpec | None = None) -> str:
        """Build ``resource?query`` from validated parts only. Raises on anything unsafe."""
        ensure_allowed_resource(resource)
        if resource == "$metadata":
            if spec is not None:
                raise ValueError("$metadata does not accept query options")
            return "$metadata"
        if spec is None:
            raise ValueError("entity queries require a QuerySpec with $top")
        if not 1 <= spec.top <= self.limits.MAX_RECORDS:
            raise ValueError(f"$top must be between 1 and MAX_RECORDS={self.limits.MAX_RECORDS}")
        params: list[str] = []
        if spec.select:
            params.append("$select=" + ",".join(validate_property_name(f) for f in spec.select))
        if spec.filters:
            parts = []
            for clause in spec.filters:
                validate_property_name(clause.field)
                if clause.op not in ALLOWED_FILTER_OPERATORS:
                    raise ValueError("operator not allowed")
                if any(ch in clause.literal for ch in ("&", "#", "?", "\n", "\r")):
                    raise ValueError("literal contains forbidden characters")
                parts.append(f"{clause.field} {clause.op} {clause.literal}")
            params.append("$filter=" + quote(" and ".join(parts), safe="',():"))
        if spec.orderby:
            name, direction = spec.orderby
            if direction not in ("asc", "desc"):
                raise ValueError("invalid order direction")
            params.append("$orderby=" + quote(f"{validate_property_name(name)} {direction}", safe=""))
        params.append(f"$top={spec.top}")
        if self.config.odata.append_format_json:
            params.append("$format=json")
        return f"{resource}?" + "&".join(params)

    # ----------------------------------------------------------------- public API
    def fetch_metadata(self, session_id: str) -> ODataResult:
        """Single GET to $metadata (bounded by MAX_METADATA_BYTES)."""
        return self._execute("$metadata", session_id, self.limits.MAX_METADATA_BYTES,
                             accept="application/xml", parse_entities=False, enforce_spacing=False)

    def query(self, spec: QuerySpec, session_id: str, enforce_spacing: bool = True) -> ODataResult:
        """Single bounded GET to ProductivityOverTime."""
        relative = self.build_relative_url("ProductivityOverTime", spec)
        result = self._execute(relative, session_id, self.limits.MAX_RESPONSE_BYTES,
                               accept=self.config.odata.accept_header, parse_entities=True,
                               enforce_spacing=enforce_spacing)
        if result.ok and len(result.records) > spec.top:
            # Server ignored $top: keep only the allowed amount and flag it.
            result.records = result.records[: spec.top]
            result.top_ignored = True
            result.more_available = True
        return result

    def snapshot(self) -> dict[str, Any]:
        return {"last": dict(self.last), "breaker": self.breaker.snapshot(), "busy": self.gate.is_busy()}

    # ----------------------------------------------------------------- internals
    def _execute(self, relative: str, session_id: str, max_bytes: int, accept: str,
                 parse_entities: bool, enforce_spacing: bool) -> ODataResult:
        requested_at = iso_utc(utc_now())
        if self.transport is None:
            return ODataResult(Status.AUTH_NOT_AVAILABLE, MESSAGES_ES[Status.AUTH_NOT_AVAILABLE],
                               technical_detail=self.transport_error, requested_at=requested_at)
        allowed, remaining = self.breaker.allow()
        if not allowed:
            return ODataResult(Status.CIRCUIT_OPEN,
                               f"{MESSAGES_ES[Status.CIRCUIT_OPEN]} Intenta de nuevo en {int(remaining) + 1} s.",
                               wait_seconds=remaining, requested_at=requested_at)
        gate_status, wait = self.gate.try_acquire(session_id, enforce_spacing=enforce_spacing)
        if gate_status != Status.OK:
            self.breaker.cancel_trial()  # no request was sent; a granted half-open trial is not consumed
            message = MESSAGES_ES[gate_status]
            if wait > 0:
                message += f" (espera {int(wait) + 1} s)"
            return ODataResult(gate_status, message, wait_seconds=wait, requested_at=requested_at)
        start = time.monotonic()
        result: ODataResult
        try:
            url = self.base_url + relative
            self.request_log.append(relative)
            del self.request_log[:-200]
            response = self.transport.get(url, {"Accept": accept, "User-Agent": "GPV-SMT-Production-Pulse/1.0"},
                                          float(self.limits.REQUEST_TIMEOUT_SECONDS), max_bytes)
            status = _status_from_http(response.status)
            elapsed = (time.monotonic() - start) * 1000
            if status != Status.OK:
                retry_after = _parse_retry_after(response.headers.get("Retry-After") or response.headers.get("retry-after"))
                detail = response.body[:500].decode("utf-8", "replace")
                result = ODataResult(status, MESSAGES_ES[status], response.status, elapsed_ms=elapsed,
                                     retry_after=retry_after, technical_detail=detail)
            elif parse_entities:
                try:
                    records, more = parse_entity_payload(response.body)
                    result = ODataResult(Status.OK, MESSAGES_ES[Status.OK], response.status, records=records,
                                         elapsed_ms=elapsed, more_available=more)
                except PayloadError as exc:
                    result = ODataResult(exc.status, MESSAGES_ES[exc.status], response.status,
                                         elapsed_ms=elapsed, technical_detail=str(exc))
            else:
                result = ODataResult(Status.OK, MESSAGES_ES[Status.OK], response.status,
                                     body=response.body, elapsed_ms=elapsed)
        except TransportTimeout as exc:
            result = ODataResult(Status.TIMEOUT, MESSAGES_ES[Status.TIMEOUT], technical_detail=str(exc))
        except ResponseTooLargeError as exc:
            result = ODataResult(Status.RESPONSE_TOO_LARGE, MESSAGES_ES[Status.RESPONSE_TOO_LARGE], technical_detail=str(exc))
        except RedirectBlockedError as exc:
            result = ODataResult(Status.REDIRECT_BLOCKED, MESSAGES_ES[Status.REDIRECT_BLOCKED], technical_detail=str(exc))
        except TransportConnectionError as exc:
            result = ODataResult(Status.CONNECTION_ERROR, MESSAGES_ES[Status.CONNECTION_ERROR], technical_detail=str(exc)[:300])
        except Exception as exc:  # noqa: BLE001 - never crash the UI thread
            logger.exception("unexpected transport error")
            result = ODataResult(Status.CONNECTION_ERROR, MESSAGES_ES[Status.CONNECTION_ERROR],
                                 technical_detail=type(exc).__name__)
        finally:
            self.gate.release()
        if not result.elapsed_ms:
            result.elapsed_ms = (time.monotonic() - start) * 1000
        result.relative_url = relative
        result.requested_at = requested_at

        if result.status in BREAKER_FAILURES:
            self.breaker.record_failure(result.retry_after if result.status == Status.TOO_MANY_REQUESTS else None)
        elif result.ok:
            self.breaker.record_success()
        else:
            self.breaker.record_neutral()

        self.last = {
            "at": requested_at, "resource": relative.split("?", 1)[0], "status": result.status.value,
            "http_status": result.http_status, "elapsed_ms": round(result.elapsed_ms, 1),
            "records": len(result.records), "message": result.message,
        }
        log = logger.info if result.ok else logger.warning
        log("odata GET %s -> %s http=%s %.0fms records=%d %s", relative, result.status.value,
            result.http_status, result.elapsed_ms, len(result.records), result.technical_detail[:200])
        return result


def build_client(config: Config, transport: Transport | None = None) -> ODataClient:
    """Create the client with the transport selected by configuration.

    ``auth_mode``:
    * ``windows_negotiate``: Windows integrated auth is mandatory; if the optional libraries are
      missing, no request is sent and the UI explains what to install.
    * ``auto``: use Windows integrated auth when the optional libraries are installed (credentials
      are only presented if the server asks for them with a 401 Negotiate/NTLM challenge);
      otherwise anonymous HTTP.
    * ``none``: anonymous HTTP only.
    """
    if transport is not None:
        return ODataClient(config, transport)
    mode = config.odata.auth_mode
    if mode in ("windows_negotiate", "auto"):
        try:
            client = ODataClient(config, NegotiateTransport(config.odata.use_system_proxy))
            client.auth_description = "Windows integrada (SSPI)"
            logger.info("auth: Windows integrated (Negotiate/NTLM via SSPI)")
            return client
        except AuthNotAvailableError as exc:
            if mode == "windows_negotiate":
                logger.error("windows_negotiate configured but optional libraries missing: %s", exc)
                return ODataClient(config, None, transport_error=str(exc))
            logger.info("auth auto: optional Windows auth libraries not installed; using anonymous HTTP")
    client = ODataClient(config, UrllibTransport(config.odata.use_system_proxy))
    client.auth_description = "Anónima / red" if mode == "none" else "Anónima (bibliotecas de autenticación Windows no instaladas)"
    return client
