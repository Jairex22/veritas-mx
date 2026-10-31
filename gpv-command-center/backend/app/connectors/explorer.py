"""Explorador OData de consulta directa (sólo lectura).

Permite conectarse a un servicio OData de FactoryLogix indicado por el usuario,
leer su $metadata real y buscar un valor (caja, serial, orden) en todas las
entidades, sin mapeo previo. Las credenciales que el usuario escribe se guardan
únicamente en memoria del servidor durante su sesión: nunca en disco, base de
datos ni logs. Todas las peticiones son GET.
"""
from __future__ import annotations

import re
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlsplit

import httpx

from ..core.errors import DataSourceUnavailable, ValidationFailed
from .base import ConnectorState, HttpClientFactory, diagnose_http, now_iso
from .factorylogix import parse_metadata

# Propiedades candidatas para búsqueda automática (por nombre, sin distinguir mayúsculas).
KEY_HINTS = re.compile(
    r"serial|^sn$|_sn$|unit|barcode|workorder|work_order|^wo|order|job|box|carton|container|pallet|pack|lot|batch|"
    r"panel|label|number|name|^id$|identifier|code|ref", re.I)
SERIAL_HINTS = re.compile(r"serial|^sn$|_sn$|unitid|unit_id|barcode", re.I)
MAX_QUERIES = 120
_IDENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_./]{0,127}$")


def normalize_base_url(raw: str) -> str:
    raw = (raw or "").strip()
    if not raw:
        raise ValidationFailed("Indique la URL del servicio OData (p. ej. http://10.62.54.10/odata).")
    if "://" not in raw:
        raw = "http://" + raw
    parts = urlsplit(raw)
    if parts.scheme not in ("http", "https") or not parts.netloc or parts.query or parts.fragment:
        raise ValidationFailed("URL inválida: use http(s)://host[:puerto]/ruta sin parámetros.")
    if not re.match(r"^[A-Za-z0-9.\-]+(:\d{1,5})?$", parts.netloc):
        raise ValidationFailed("Host inválido.")
    return raw.rstrip("/") + "/"


def odata_literal(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


@dataclass
class ExplorerSession:
    base_url: str
    auth_kind: str
    username: str
    password: str = field(repr=False, default="")
    connected_at: str = ""
    version: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    state: str = ConnectorState.UNKNOWN.value
    message: str = ""
    diagnosis: list[str] = field(default_factory=list)

    @property
    def is_v4(self) -> bool:
        return str(self.version or "4").startswith("4")

    def public(self) -> dict[str, Any]:
        return {"base_url": self.base_url, "auth": self.auth_kind, "username": self.username if self.auth_kind != "none" else "",
                "connected_at": self.connected_at, "version": self.version, "state": self.state, "message": self.message,
                "diagnosis": self.diagnosis, "entity_set_count": len(self.metadata.get("entity_sets", []))}


class ODataExplorer:
    def __init__(self, http: HttpClientFactory):
        self.http = http
        self._sessions: dict[str, ExplorerSession] = {}
        self._lock = threading.Lock()

    # ---------------- sesiones ----------------
    def get(self, owner: str) -> ExplorerSession | None:
        with self._lock:
            return self._sessions.get(owner)

    def disconnect(self, owner: str) -> None:
        with self._lock:
            self._sessions.pop(owner, None)

    def connect(self, owner: str, base_url: str, auth_kind: str = "none", username: str = "", password: str = "") -> ExplorerSession:
        base = normalize_base_url(base_url)
        auth_kind = auth_kind if auth_kind in ("none", "basic", "ntlm") else "none"
        if auth_kind != "none" and not username:
            raise ValidationFailed("Indique el usuario para la autenticación seleccionada.")
        sess = ExplorerSession(base_url=base, auth_kind=auth_kind, username=username, password=password)
        with self._client(sess) as c:
            r = self.http.probe(c, "$metadata", "OData $metadata")
        sess.state, sess.message, sess.diagnosis = r.state.value, r.message, list(r.diagnosis)
        sess.connected_at = now_iso()
        if r.state == ConnectorState.OK and r.response is not None:
            sess.metadata = parse_metadata(r.response.text)
            sess.version = sess.metadata.get("version")
            if not sess.metadata["entity_sets"]:
                sess.diagnosis.append("No se encontraron EntitySets: verifique que la URL apunte a la raíz del servicio OData "
                                      "(normalmente termina en /odata o /odata/).")
        with self._lock:
            self._sessions[owner] = sess
        return sess

    # ---------------- HTTP ----------------
    def _client(self, sess: ExplorerSession) -> httpx.Client:
        auth: httpx.Auth | None = None
        if sess.auth_kind == "basic":
            auth = httpx.BasicAuth(sess.username, sess.password)
        elif sess.auth_kind == "ntlm":
            try:
                from httpx_ntlm import HttpNtlmAuth
                auth = HttpNtlmAuth(sess.username, sess.password)
            except ImportError:
                raise DataSourceUnavailable("NTLM requiere el paquete opcional 'httpx-ntlm' en el servidor.", code="NTLM_UNAVAILABLE")
        return self.http.client(sess.base_url, auth=auth, headers={"Accept": "application/json"})

    def _rows(self, sess: ExplorerSession, entity_set: str, params: dict[str, str]) -> list[dict]:
        if not sess.is_v4:
            params = {**params, "$format": "json"}
        try:
            with self._client(sess) as c:
                resp = c.get(entity_set, params=params)
        except httpx.HTTPError as exc:
            raise DataSourceUnavailable(f"OData no accesible: {type(exc).__name__}.", code="ODATA_UNREACHABLE")
        if resp.status_code != 200:
            state, msg, diag = diagnose_http(resp, f"OData {entity_set}")
            raise DataSourceUnavailable(msg, code=f"ODATA_{state.value}", details={"http_status": resp.status_code, "diagnosis": diag,
                                                                               "body": resp.text[:300]})
        try:
            payload = resp.json()
        except ValueError:
            raise DataSourceUnavailable("La respuesta no es JSON.", code="ODATA_NOT_JSON")
        if isinstance(payload, dict):
            if "value" in payload:
                return list(payload["value"])
            d = payload.get("d")
            if isinstance(d, dict) and "results" in d:
                return list(d["results"])
            if isinstance(d, list):
                return d
        return list(payload) if isinstance(payload, list) else []

    # ---------------- consultas ----------------
    def rows(self, sess: ExplorerSession, entity_set: str, top: int = 50, filter_expr: str | None = None,
             orderby: str | None = None) -> list[dict]:
        if not _IDENT.match(entity_set):
            raise ValidationFailed("EntitySet inválido.")
        params = {"$top": str(max(1, min(top, 500)))}
        if filter_expr:
            params["$filter"] = filter_expr
        if orderby:
            params["$orderby"] = orderby
        return [self._flatten(r) for r in self._rows(sess, entity_set, params)]

    def _filter(self, sess: ExplorerSession, prop: str, value: str, match: str) -> str:
        lit = odata_literal(value)
        if match == "contains":
            return f"contains({prop},{lit})" if sess.is_v4 else f"substringof({lit},{prop})"
        return f"{prop} eq {lit}"

    def search(self, sess: ExplorerSession, value: str, *, entity_set: str | None = None, prop: str | None = None,
               match: str = "eq", top: int = 200) -> dict[str, Any]:
        value = value.strip()
        if not value or len(value) > 128:
            raise ValidationFailed("Indique un valor de 1 a 128 caracteres.")
        if not sess.metadata.get("entity_sets"):
            raise DataSourceUnavailable("Sin $metadata: conecte primero.", code="EXPLORER_NOT_CONNECTED")
        match = "contains" if match == "contains" else "eq"
        targets: list[tuple[str, str]] = []
        for es in sess.metadata["entity_sets"]:
            if entity_set and es["name"] != entity_set:
                continue
            for p in es["properties"]:
                if not str(p["type"]).endswith("String"):
                    continue
                if prop and p["name"] != prop:
                    continue
                if not prop and not entity_set and not KEY_HINTS.search(p["name"]):
                    continue
                targets.append((es["name"], p["name"]))
        if entity_set and prop and not targets:
            raise ValidationFailed("La propiedad indicada no existe o no es de texto.")
        truncated = len(targets) > MAX_QUERIES
        targets = targets[:MAX_QUERIES]
        hits, errors = [], []

        def run(t: tuple[str, str]):
            es, pr = t
            return es, pr, self.rows(sess, es, top=top, filter_expr=self._filter(sess, pr, value, match))

        with ThreadPoolExecutor(max_workers=6) as pool:
            futures = {pool.submit(run, t): t for t in targets}
            for fut in as_completed(futures):
                es, pr = futures[fut]
                try:
                    es, pr, rows = fut.result()
                except Exception as exc:  # una propiedad no filtrable no debe abortar la búsqueda
                    errors.append({"entity_set": es, "property": pr, "error": getattr(exc, "message", str(exc))[:160]})
                    continue
                if rows:
                    hits.append({"entity_set": es, "property": pr, "count": len(rows), "rows": rows,
                                 "columns": self._columns(rows)})
        hits.sort(key=lambda h: (-h["count"], h["entity_set"]))
        serials = self._collect_serials(hits, value)
        return {"value": value, "match": match, "queries": len(targets), "truncated": truncated, "hits": hits,
                "serials": serials, "errors": errors[:20], "error_count": len(errors),
                "source": {"kind": "ODATA_DIRECT", "label": f"Lectura directa OData {sess.base_url}", "synthetic": False}}

    @staticmethod
    def _flatten(row: dict) -> dict:
        out = {}
        for k, v in row.items():
            if str(k).startswith("@") or str(k).startswith("__"):
                continue
            if isinstance(v, dict):
                if "results" in v or "__deferred" in v:
                    continue
                out[k] = v.get("value", str(v)[:120])
            elif isinstance(v, list):
                out[k] = f"[{len(v)} elementos]"
            else:
                out[k] = v
        return out

    @staticmethod
    def _columns(rows: list[dict]) -> list[str]:
        cols: list[str] = []
        for r in rows:
            for k in r:
                if k not in cols:
                    cols.append(k)
        return cols

    @staticmethod
    def _collect_serials(hits: list[dict], value: str) -> list[dict]:
        found: dict[str, dict] = {}
        for h in hits:
            for col in h["columns"]:
                if not SERIAL_HINTS.search(col):
                    continue
                for r in h["rows"]:
                    v = r.get(col)
                    if v is None or v == "" or isinstance(v, (dict, list)):
                        continue
                    s = str(v)
                    if s.lower() == value.lower():
                        continue
                    found.setdefault(s, {"serial": s, "sources": set()})["sources"].add(f"{h['entity_set']}.{col}")
        return [{"serial": k, "sources": sorted(v["sources"])} for k, v in sorted(found.items())]
