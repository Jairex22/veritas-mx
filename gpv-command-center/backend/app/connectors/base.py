"""Base de conectores: estado, diagnóstico y cliente HTTP seguro."""
from __future__ import annotations

import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any

import httpx


class ConnectorState(str, Enum):
    NOT_CONFIGURED = "NOT_CONFIGURED"
    SIMULATED = "SIMULATED"
    UNKNOWN = "UNKNOWN"          # configurado pero aún no comprobado
    OK = "OK"
    AUTH_DENIED = "AUTH_DENIED"  # HTTP 401
    FORBIDDEN = "FORBIDDEN"      # HTTP 403
    NOT_FOUND = "NOT_FOUND"      # HTTP 404
    SERVER_ERROR = "SERVER_ERROR"  # HTTP 5xx
    UNEXPECTED = "UNEXPECTED"
    UNREACHABLE = "UNREACHABLE"
    TIMEOUT = "TIMEOUT"
    TLS_ERROR = "TLS_ERROR"
    DISABLED = "DISABLED"


@dataclass
class ConnectorStatus:
    id: str
    name: str
    kind: str
    purpose: str
    configured: bool
    state: ConnectorState
    message: str
    base_url: str = ""
    http_status: int | None = None
    latency_ms: float | None = None
    checked_at: str | None = None
    diagnosis: list[str] = field(default_factory=list)
    capabilities: dict[str, Any] = field(default_factory=dict)
    discovered: dict[str, Any] = field(default_factory=dict)
    credential: str = "no aplica"

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["state"] = self.state.value
        return d


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass
class HttpProbeResult:
    state: ConnectorState
    http_status: int | None
    latency_ms: float | None
    message: str
    diagnosis: list[str]
    response: httpx.Response | None = None


def diagnose_http(resp: httpx.Response, what: str) -> tuple[ConnectorState, str, list[str]]:
    code = resp.status_code
    if 200 <= code < 300:
        return ConnectorState.OK, f"{what}: respuesta HTTP {code}.", []
    if code == 401:
        scheme = resp.headers.get("WWW-Authenticate", "")
        diag = [
            "El servidor rechazó la autenticación (HTTP 401). No se intentará evadirla.",
            "Verifique con el administrador de FactoryLogix que la cuenta de servicio exista y tenga permiso para esta interfaz.",
            "Confirme que las credenciales del servidor (variables de entorno) sean correctas y vigentes.",
        ]
        if scheme:
            schemes = ", ".join(s.strip().split(" ")[0] for s in scheme.split(","))
            diag.append(f"Esquemas de autenticación anunciados por el servidor: {schemes}.")
            if any(s in scheme for s in ("Negotiate", "NTLM")):
                diag.append("El servidor solicita autenticación integrada de Windows (Negotiate/NTLM), "
                            "no soportada en v1.0. Se requiere aprobación de TI para habilitarla.")
        return ConnectorState.AUTH_DENIED, f"{what}: acceso denegado (HTTP 401).", diag
    if code == 403:
        return ConnectorState.FORBIDDEN, f"{what}: prohibido (HTTP 403).", [
            "La cuenta se autenticó pero no tiene privilegios sobre este recurso.",
            "Solicite al administrador de FactoryLogix los permisos de lectura correspondientes.",
        ]
    if code == 404:
        return ConnectorState.NOT_FOUND, f"{what}: recurso no encontrado (HTTP 404).", [
            "Verifique la URL base configurada; la ruta puede diferir en esta instalación.",
        ]
    if code >= 500:
        return ConnectorState.SERVER_ERROR, f"{what}: error del servidor (HTTP {code}).", [
            "El servidor de FactoryLogix devolvió un error interno. Revise los logs del servidor con el administrador.",
            "Puede indicar que el servicio no está habilitado/licenciado o que falta configuración del lado servidor.",
            "No se reintentará automáticamente con parámetros alternativos.",
        ]
    return ConnectorState.UNEXPECTED, f"{what}: respuesta inesperada HTTP {code}.", []


class HttpClientFactory:
    """Crea clientes HTTP con timeouts y TLS verificados. Permite inyectar
    un `transport` en pruebas para no tocar la red."""

    def __init__(self, timeout: float, verify_tls: bool, ca_bundle: str = "",
                 transport: httpx.BaseTransport | None = None):
        self.timeout = timeout
        self.verify: bool | str = ca_bundle or verify_tls
        self.transport = transport

    def client(self, base_url: str, auth: httpx.Auth | None = None, headers: dict | None = None) -> httpx.Client:
        return httpx.Client(base_url=base_url, timeout=self.timeout, verify=self.verify, auth=auth,
                            headers=headers or {}, transport=self.transport, follow_redirects=False)

    def probe(self, client: httpx.Client, path: str, what: str) -> HttpProbeResult:
        start = time.perf_counter()
        try:
            resp = client.get(path)
        except httpx.TimeoutException:
            return HttpProbeResult(ConnectorState.TIMEOUT, None, None, f"{what}: tiempo de espera agotado.",
                                   ["El servidor no respondió dentro del límite configurado (GPV_HTTP_TIMEOUT).",
                                    "Verifique conectividad de red y reglas de firewall entre este servidor y FactoryLogix."])
        except httpx.ConnectError as exc:
            msg = str(exc)
            if "CERTIFICATE" in msg.upper() or "SSL" in msg.upper():
                return HttpProbeResult(ConnectorState.TLS_ERROR, None, None, f"{what}: error de certificado TLS.",
                                       ["El certificado del servidor no es de confianza para este equipo.",
                                        "Configure GPV_CA_BUNDLE con la CA corporativa. No desactive la verificación TLS."])
            return HttpProbeResult(ConnectorState.UNREACHABLE, None, None, f"{what}: no se pudo conectar.",
                                   ["Host inaccesible o puerto cerrado.", f"Detalle técnico: {msg[:200]}"])
        except httpx.HTTPError as exc:
            return HttpProbeResult(ConnectorState.UNEXPECTED, None, None, f"{what}: error HTTP ({type(exc).__name__}).",
                                   [str(exc)[:200]])
        latency = round((time.perf_counter() - start) * 1000, 1)
        state, message, diag = diagnose_http(resp, what)
        return HttpProbeResult(state, resp.status_code, latency, message, diag, resp)
