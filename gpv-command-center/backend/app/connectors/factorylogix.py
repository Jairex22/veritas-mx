"""Conectores hacia FactoryLogix y fuentes auxiliares.

IMPORTANTE: este módulo NO define endpoints, servicios ni métodos de escritura
de FactoryLogix. Sólo realiza comprobaciones de alcance (GET) sobre URLs que el
administrador configura, y lectura OData de entidades que el responsable del
sistema mapea explícitamente tras inspeccionar `$metadata`.
"""
from __future__ import annotations

import json
import socket
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

import httpx

from ..settings import Settings
from .base import ConnectorState, ConnectorStatus, HttpClientFactory, now_iso


def _odata_auth(settings: Settings) -> tuple[httpx.Auth | None, dict[str, str], str]:
    if settings.odata_auth == "bearer" and settings.odata_token:
        return None, {"Authorization": f"Bearer {settings.odata_token}"}, "token Bearer configurado (env GPV_ODATA_TOKEN)"
    if settings.odata_auth == "basic" and settings.odata_username:
        return (httpx.BasicAuth(settings.odata_username, settings.odata_password), {},
                f"usuario '{settings.odata_username}' (env GPV_ODATA_USERNAME / GPV_ODATA_PASSWORD)")
    return None, {}, "sin credenciales configuradas"


def parse_entity_sets(xml_text: str) -> list[str]:
    """Extrae nombres de EntitySet de un documento $metadata (EDMX)."""
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return []
    names = [el.attrib["Name"] for el in root.iter() if el.tag.endswith("EntitySet") and "Name" in el.attrib]
    return sorted(set(names))


class ODataConnector:
    id = "odata"
    name = "FactoryLogix OData"
    purpose = "Consultas de sólo lectura donde estén autorizadas."

    def __init__(self, settings: Settings, http: HttpClientFactory):
        self.settings = settings
        self.http = http
        self.last: ConnectorStatus | None = None

    @property
    def configured(self) -> bool:
        return bool(self.settings.odata_base_url)

    def client(self) -> httpx.Client:
        auth, headers, _ = _odata_auth(self.settings)
        headers = {"Accept": "application/json", **headers}
        return self.http.client(self.settings.odata_base_url.rstrip("/") + "/", auth=auth, headers=headers)

    def status(self) -> ConnectorStatus:
        if self.last:
            return self.last
        _, _, cred = _odata_auth(self.settings)
        if not self.configured:
            return ConnectorStatus(self.id, self.name, "ODATA", self.purpose, False, ConnectorState.NOT_CONFIGURED,
                                   "URL base no configurada (GPV_ODATA_BASE_URL).", credential=cred,
                                   capabilities={"read": False, "write": False},
                                   diagnosis=["Configure GPV_ODATA_BASE_URL en el servidor y ejecute la prueba de conexión."])
        return ConnectorStatus(self.id, self.name, "ODATA", self.purpose, True, ConnectorState.UNKNOWN,
                               "Configurado; conexión aún no comprobada.", base_url=self.settings.odata_base_url,
                               credential=cred, capabilities={"read": False, "write": False})

    def probe(self) -> ConnectorStatus:
        base = self.status()
        if not self.configured:
            return base
        with self.client() as c:
            r = self.http.probe(c, "$metadata", "OData $metadata")
        discovered: dict[str, Any] = {}
        if r.state == ConnectorState.OK and r.response is not None:
            sets = parse_entity_sets(r.response.text)
            discovered = {"entity_sets": sets, "entity_set_count": len(sets)}
            if not sets:
                r.diagnosis.append("La respuesta no contiene EntitySets reconocibles; verifique que la URL apunte a la raíz OData.")
        st = ConnectorStatus(self.id, self.name, "ODATA", self.purpose, True, r.state, r.message,
                             base_url=self.settings.odata_base_url, http_status=r.http_status, latency_ms=r.latency_ms,
                             checked_at=now_iso(), diagnosis=r.diagnosis, credential=base.credential,
                             capabilities={"read": r.state == ConnectorState.OK, "write": False}, discovered=discovered)
        self.last = st
        return st


class ReachabilityConnector:
    """Conector que sólo comprueba alcance de una URL base configurada.

    Se usa para xTend API y FactoryLogixAPI mientras no existan métodos
    oficiales verificados para esta instalación.
    """

    def __init__(self, cid: str, name: str, kind: str, purpose: str, base_url: str, env_var: str,
                 http: HttpClientFactory, pending_note: str):
        self.id, self.name, self.kind, self.purpose = cid, name, kind, purpose
        self.base_url, self.env_var, self.http, self.pending_note = base_url, env_var, http, pending_note
        self.last: ConnectorStatus | None = None

    def status(self) -> ConnectorStatus:
        if self.last:
            return self.last
        if not self.base_url:
            return ConnectorStatus(self.id, self.name, self.kind, self.purpose, False, ConnectorState.NOT_CONFIGURED,
                                   f"URL base no configurada ({self.env_var}).",
                                   capabilities={"read": False, "write": False}, diagnosis=[self.pending_note])
        return ConnectorStatus(self.id, self.name, self.kind, self.purpose, True, ConnectorState.UNKNOWN,
                               "Configurado; conexión aún no comprobada.", base_url=self.base_url,
                               capabilities={"read": False, "write": False}, diagnosis=[self.pending_note])

    def probe(self) -> ConnectorStatus:
        if not self.base_url:
            return self.status()
        with self.http.client(self.base_url.rstrip("/") + "/") as c:
            r = self.http.probe(c, "", f"{self.name} (URL base)")
        diag = list(r.diagnosis) + [self.pending_note]
        if r.state == ConnectorState.OK:
            diag.insert(0, "El servidor responde. Esto NO verifica métodos ni permisos de transacción.")
        st = ConnectorStatus(self.id, self.name, self.kind, self.purpose, True, r.state, r.message,
                             base_url=self.base_url, http_status=r.http_status, latency_ms=r.latency_ms,
                             checked_at=now_iso(), diagnosis=diag,
                             capabilities={"read": False, "write": False, "reachable": r.state == ConnectorState.OK})
        self.last = st
        return st


class AuxFilesConnector:
    id = "aux"
    name = "Fuentes auxiliares (CSV / XML / diagnóstico)"
    purpose = "Importación de sólo lectura de exportaciones y archivos de diagnóstico."
    ALLOWED = {".csv", ".xml", ".txt", ".log", ".json"}

    def __init__(self, settings: Settings):
        self.settings = settings
        self.last: ConnectorStatus | None = None

    @property
    def directory(self) -> Path | None:
        return Path(self.settings.aux_dir) if self.settings.aux_dir else None

    def status(self) -> ConnectorStatus:
        return self.last or self.probe()

    def probe(self) -> ConnectorStatus:
        d = self.directory
        if d is None:
            return ConnectorStatus(self.id, self.name, "FILES", self.purpose, False, ConnectorState.NOT_CONFIGURED,
                                   "Directorio no configurado (GPV_AUX_DIR).", capabilities={"read": False, "write": False})
        if not d.is_dir():
            st = ConnectorStatus(self.id, self.name, "FILES", self.purpose, True, ConnectorState.UNREACHABLE,
                                 f"El directorio '{d}' no existe o no es accesible.", base_url=str(d), checked_at=now_iso(),
                                 capabilities={"read": False, "write": False})
        else:
            files = sorted(p.name for p in d.iterdir() if p.is_file() and p.suffix.lower() in self.ALLOWED)
            has_events = (d / "events.csv").is_file()
            st = ConnectorStatus(self.id, self.name, "FILES", self.purpose, True, ConnectorState.OK,
                                 f"{len(files)} archivo(s) disponibles.", base_url=str(d), checked_at=now_iso(),
                                 capabilities={"read": True, "write": False, "trace_source": has_events},
                                 discovered={"files": files[:200]},
                                 diagnosis=[] if has_events else ["No se encontró events.csv: el directorio no puede usarse como fuente de trazabilidad."])
        self.last = st
        return st


class DemoConnector:
    id = "demo"
    name = "Generador DEMO"
    purpose = "Datos sintéticos para demostración y capacitación."

    def __init__(self, active: bool):
        self.active = active

    def status(self) -> ConnectorStatus:
        return ConnectorStatus(self.id, self.name, "DEMO", self.purpose, self.active,
                               ConnectorState.SIMULATED if self.active else ConnectorState.DISABLED,
                               "Activo: datos 100 % sintéticos." if self.active else "Deshabilitado en modo REAL.",
                               capabilities={"read": self.active, "write": False, "simulated_operations": self.active},
                               checked_at=now_iso())

    probe = status


def tcp_reachable(host: str, port: int, timeout: float = 3.0) -> tuple[bool, str]:
    """Comprueba si un puerto TCP acepta conexión (sin enviar datos)."""
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True, "Puerto accesible."
    except socket.timeout:
        return False, "Tiempo de espera agotado."
    except OSError as exc:
        return False, f"No accesible: {exc.strerror or exc}"


def load_json_config(config_dir: Path, name: str) -> dict | list | None:
    path = config_dir / name
    if not path.is_file():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


class ConnectorRegistry:
    def __init__(self, settings: Settings, http: HttpClientFactory):
        self.settings = settings
        self.http = http
        self.odata = ODataConnector(settings, http)
        self.xtend = ReachabilityConnector(
            "xtend", "FactoryLogix xTend API", "XTEND", "Transacciones oficiales permitidas (pendiente de verificación).",
            settings.xtend_base_url, "GPV_XTEND_BASE_URL", http,
            "Métodos xTend NO verificados: la documentación oficial (xtendapi.aiscorp.com) debe revisarse con "
            "licencia y credenciales de GPV antes de registrar cualquier transacción.")
        self.flx = ReachabilityConnector(
            "flx_api", "FactoryLogixAPI", "FLX_API", "Sólo endpoints documentados y verificados para esta instalación.",
            settings.flx_api_base_url, "GPV_FLX_API_BASE_URL", http,
            "No hay endpoints verificados registrados para esta instalación (config/flx_endpoints.json).")
        self.aux = AuxFilesConnector(settings)
        self.demo = DemoConnector(settings.is_demo)

    def all(self) -> list:
        return [self.demo, self.odata, self.xtend, self.flx, self.aux]

    def get(self, cid: str):
        for c in self.all():
            if c.id == cid:
                return c
        return None

    def statuses(self) -> list[dict]:
        return [c.status().to_dict() for c in self.all()]
