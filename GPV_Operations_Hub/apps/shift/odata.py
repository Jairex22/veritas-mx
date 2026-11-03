"""Read-only OData connector (FactoryLogix pilot).

* Only HTTP GET is ever issued (``ReadOnlyClient`` refuses anything else). Nothing is written
  back to FactoryLogix.
* Credentials come from environment variables on the server; they are never stored in the
  database, logged, returned to the browser or included in diagnostics.
* Entity sets, properties and keys are taken from the real ``$metadata``; nothing is assumed.
* Pages are followed through the provider continuation links (``@odata.nextLink`` /
  ``d.__next``). Progress (watermark) is saved only after a whole cycle succeeds.
"""
import base64
import json
import logging
import os
import socket
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone as dt_tz
from decimal import Decimal, InvalidOperation

from django.db import IntegrityError, transaction
from django.utils import timezone

from .models import EventRevision, ODataConnection, ProductionEvent as PE, Station, SyncGap, SyncRun

log = logging.getLogger("gpv.odata")
PORTAL_FIELDS = {
    "external_key": "Clave externa (si no se definen claves en la conexión)", "work_order": "Orden", "operation": "Operación",
    "station": "Estación (código)", "line": "Línea (código)", "part_number": "Parte", "serial": "Serial", "panel_id": "Panel",
    "lot_ref": "Lote/etiqueta", "side": "Lado Top/Bottom", "qty": "Cantidad", "unit": "Unidad", "result": "Resultado",
    "attempt": "Intento", "event_at": "Instante del evento", "modified_at": "Instante de modificación", "scope_key": "Alcance (snapshot)",
}


class ODataError(Exception):
    def __init__(self, kind, message, status=None):
        super().__init__(message)
        self.kind, self.status = kind, status


KIND_TEXT = {
    "config": "Configuración incompleta", "connectivity": "Sin conectividad con el servidor", "timeout": "Tiempo agotado",
    "auth": "Autenticación rechazada", "forbidden": "Sin permiso para este recurso", "not_found": "Recurso o entidad inexistente",
    "server": "Fallo del servidor OData", "format": "Respuesta con formato no reconocido", "empty": "Consulta válida sin resultados",
    "dependency": "Falta un paquete opcional en el servidor", "mapping": "Mapeo incompleto o inválido",
}


class ReadOnlyClient:
    def __init__(self, conn: ODataConnection):
        self.conn = conn

    def _headers(self):
        h = {"Accept": "application/json", "User-Agent": "GPV-Operations-Hub/1.1 (read-only)"}
        a = self.conn.auth_type
        if a == ODataConnection.Auth.BASIC:
            user, pwd = os.environ.get(self.conn.username_env or ""), os.environ.get(self.conn.secret_env or "")
            if not user or not pwd:
                raise ODataError("config", f"Defina las variables de entorno {self.conn.username_env} y {self.conn.secret_env} en el servidor.")
            h["Authorization"] = "Basic " + base64.b64encode(f"{user}:{pwd}".encode()).decode()
        elif a == ODataConnection.Auth.BEARER:
            tok = os.environ.get(self.conn.secret_env or "")
            if not tok:
                raise ODataError("config", f"Defina la variable de entorno {self.conn.secret_env} con el token en el servidor.")
            h["Authorization"] = "Bearer " + tok
        return h

    def get(self, url, accept=None, method="GET"):
        if method != "GET":  # hard guarantee: the connector never writes
            raise ODataError("config", "El conector es de solo lectura: solo se permiten consultas GET.")
        if not url.lower().startswith(("http://", "https://")):
            raise ODataError("config", "La URL del servicio debe comenzar con http:// o https://.")
        if self.conn.auth_type == ODataConnection.Auth.NEGOTIATE:
            return self._get_negotiate(url, accept)
        headers = self._headers()
        if accept:
            headers["Accept"] = accept
        req = urllib.request.Request(url, headers=headers, method="GET")
        t0 = time.monotonic()
        try:
            with urllib.request.urlopen(req, timeout=self.conn.timeout_seconds) as r:
                body = r.read()
                return r.status, dict(r.headers), body, int((time.monotonic() - t0) * 1000)
        except urllib.error.HTTPError as e:
            raise _http_error(e.code)
        except (socket.timeout, TimeoutError):
            raise ODataError("timeout", f"Sin respuesta en {self.conn.timeout_seconds} s.")
        except urllib.error.URLError as e:
            if isinstance(e.reason, (socket.timeout, TimeoutError)):
                raise ODataError("timeout", f"Sin respuesta en {self.conn.timeout_seconds} s.")
            raise ODataError("connectivity", f"No se pudo conectar ({e.reason.__class__.__name__}). ¿Está en la red de GPV?")
        except OSError as e:
            raise ODataError("connectivity", f"No se pudo conectar ({e.__class__.__name__}).")

    def _get_negotiate(self, url, accept):
        try:
            import requests  # noqa: F401
            from requests_negotiate_sspi import HttpNegotiateAuth  # Windows-only optional package
        except ImportError:
            raise ODataError("dependency", "La autenticación Windows integrada requiere instalar en el servidor Windows: "
                                           "requests y requests-negotiate-sspi (requirements-optional.txt). No se usan credenciales de Windows por omisión.")
        import requests

        t0 = time.monotonic()
        try:
            r = requests.get(url, auth=HttpNegotiateAuth(), timeout=self.conn.timeout_seconds,
                             headers={"Accept": accept or "application/json"})
        except requests.Timeout:
            raise ODataError("timeout", f"Sin respuesta en {self.conn.timeout_seconds} s.")
        except requests.RequestException as e:
            raise ODataError("connectivity", f"No se pudo conectar ({e.__class__.__name__}).")
        if r.status_code >= 400:
            raise _http_error(r.status_code)
        return r.status_code, dict(r.headers), r.content, int((time.monotonic() - t0) * 1000)


def _http_error(code):
    if code == 401:
        return ODataError("auth", "El servidor rechazó la autenticación (HTTP 401).", code)
    if code == 403:
        return ODataError("forbidden", "Autenticado, pero sin permiso de lectura para este recurso (HTTP 403).", code)
    if code == 404:
        return ODataError("not_found", "El recurso no existe en el servicio (HTTP 404).", code)
    if code >= 500:
        return ODataError("server", f"El servidor OData respondió con error {code}.", code)
    return ODataError("server", f"Respuesta HTTP {code} inesperada.", code)


def _base(conn):
    url = (conn.service_url or "").strip()
    if not url:
        raise ODataError("config", "Falta la URL del servicio OData (POR CONFIRMAR). Configúrela en Administración › Portal del turno.")
    return url.rstrip("/") + "/"


# ---------------------------------------------------------------- $metadata
def parse_metadata(xml_bytes):
    """Return {"version": str, "entity_sets": {name: {"type": str, "keys": [..], "properties": {name: edm_type}}}}."""
    try:
        root = ET.fromstring(xml_bytes)
    except ET.ParseError as e:
        raise ODataError("format", f"$metadata no es XML válido ({e}).")
    version = root.attrib.get("Version", "")
    types, sets = {}, {}
    for el in root.iter():
        tag = el.tag.split("}")[-1]
        if tag == "DataServices":
            version = el.attrib.get("{http://schemas.microsoft.com/ado/2007/08/dataservices/metadata}DataServiceVersion", version) or version
        if tag == "Schema":
            ns = el.attrib.get("Namespace", "")
            for et in el:
                if et.tag.split("}")[-1] != "EntityType":
                    continue
                props = {p.attrib["Name"]: p.attrib.get("Type", "") for p in et if p.tag.split("}")[-1] == "Property"}
                keys = [k.attrib["Name"] for key in et if key.tag.split("}")[-1] == "Key" for k in key]
                types[f"{ns}.{et.attrib['Name']}"] = {"keys": keys, "properties": props}
                if et.attrib.get("BaseType") and not keys:
                    types[f"{ns}.{et.attrib['Name']}"]["base"] = et.attrib["BaseType"]
    for el in root.iter():
        if el.tag.split("}")[-1] == "EntitySet":
            t = el.attrib.get("EntityType", "")
            info = types.get(t, {"keys": [], "properties": {}})
            base = info.get("base")
            if base and base in types:
                info = {"keys": types[base]["keys"], "properties": {**types[base]["properties"], **info["properties"]}}
            sets[el.attrib["Name"]] = {"type": t, "keys": info["keys"], "properties": info["properties"]}
    return {"version": version, "entity_sets": sets}


# ---------------------------------------------------------------- JSON pages
def parse_page(body):
    try:
        data = json.loads(body.decode("utf-8-sig"))
    except (ValueError, UnicodeDecodeError):
        raise ODataError("format", "La respuesta no es JSON. Verifique que el servicio admita $format=json o Accept: application/json.")
    if isinstance(data, dict) and "value" in data:  # OData v4
        return data["value"], data.get("@odata.nextLink") or data.get("odata.nextLink")
    if isinstance(data, dict) and "d" in data:  # OData v2/v3 verbose
        d = data["d"]
        if isinstance(d, dict) and "results" in d:
            return d["results"], d.get("__next")
        if isinstance(d, list):
            return d, None
    raise ODataError("format", "Estructura JSON no reconocida (se esperaba «value» o «d.results»).")


def _literal_datetime(dt, version):
    iso = dt.astimezone(dt_tz.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    if version and version.startswith(("1", "2", "3")):
        return f"datetime'{iso[:-1]}'"
    return iso


def build_query(conn, since=None):
    params = {"$top": str(conn.page_size)}
    if conn.select_fields and conn.mapping:
        fields = sorted({v for v in conn.mapping.values() if v} | set(conn.key_fields or []))
        params["$select"] = ",".join(fields)
    field = conn.watermark_field or conn.time_field
    if since is not None and field:
        params["$filter"] = f"{field} ge {_literal_datetime(since, conn.odata_version)}"
        params["$orderby"] = field
    return _base(conn) + urllib.parse.quote(conn.entity_set) + "?" + urllib.parse.urlencode(params, safe="$,'():")


# ---------------------------------------------------------------- diagnosis
SAMPLE_STAGE = "Acceso real al conjunto de entidades (consulta de muestra limitada)"


def diagnosis_ok(stages):
    """Valid only if every stage passed AND a real limited query of the entity set succeeded."""
    return bool(stages) and all(s["ok"] for s in stages) and any(s["stage"] == SAMPLE_STAGE for s in stages)


def diagnose(conn, sample=5):
    """Staged diagnosis. Each stage: {stage, ok, kind, detail}. Never includes secrets."""
    stages = []
    client = ReadOnlyClient(conn)

    def add(stage, ok, detail, kind=""):
        stages.append({"stage": stage, "ok": ok, "kind": kind, "kind_text": KIND_TEXT.get(kind, ""), "detail": detail})

    try:
        base = _base(conn)
    except ODataError as e:
        add("Configuración", False, str(e), e.kind)
        return stages, None
    try:
        status, headers, body, ms = client.get(base)
        add("Conectividad e índice del servicio", True, f"HTTP {status} en {ms} ms. Un índice accesible NO demuestra acceso a los datos.")
    except ODataError as e:
        add("Conectividad e índice del servicio", False, str(e), e.kind)
        return stages, None
    meta = None
    try:
        status, headers, body, ms = client.get(base + "$metadata", accept="application/xml")
        meta = parse_metadata(body)
        ver = headers.get("OData-Version") or headers.get("DataServiceVersion") or meta["version"]
        meta["version"] = (ver or "").split(";")[0]
        add("Autenticación y lectura de $metadata", True, f"Versión OData {meta['version'] or 'no declarada'}; {len(meta['entity_sets'])} conjuntos de entidades.")
    except ODataError as e:
        add("Autenticación y lectura de $metadata", False, str(e), e.kind)
        return stages, None
    if not conn.entity_set:
        add("Acceso al conjunto de entidades", False, "Seleccione el conjunto de entidades a leer (ver lista de $metadata).", "config")
        return stages, meta
    info = meta["entity_sets"].get(conn.entity_set)
    if info is None:
        add("Acceso al conjunto de entidades", False, f"«{conn.entity_set}» no existe en $metadata.", "not_found")
        return stages, meta
    missing = [p for p in list(conn.mapping.values()) + list(conn.key_fields or []) if p and p not in info["properties"]]
    if missing:
        add("Mapeo contra $metadata", False, f"Propiedades mapeadas que no existen: {', '.join(missing)}.", "mapping")
        return stages, meta
    add("Mapeo contra $metadata", True, f"Claves declaradas: {', '.join(info['keys']) or 'ninguna'}; mapeo verificado.")
    try:
        url = _base(conn) + urllib.parse.quote(conn.entity_set) + "?" + urllib.parse.urlencode({"$top": str(sample)})
        status, headers, body, ms = client.get(url)
        rows, _next = parse_page(body)
        if not rows:
            add(SAMPLE_STAGE, True, f"HTTP {status} en {ms} ms, sin registros (resultado vacío). El permiso de lectura es real.", "empty")
        else:
            add(SAMPLE_STAGE, True, f"HTTP {status} en {ms} ms; {len(rows)} registros leídos (máx. {sample}).")
        meta["sample"] = [{k: v for k, v in r.items() if not k.startswith("__")} for r in rows[:sample]]
    except ODataError as e:
        add(SAMPLE_STAGE, False, str(e), e.kind)
    return stages, meta


# ---------------------------------------------------------------- record mapping
def _dt(v):
    if v in (None, ""):
        return None
    if isinstance(v, str) and v.startswith("/Date("):  # OData v2 JSON date
        ms = int(v[6:].split(")")[0].split("+")[0].split("-")[0] or 0)
        return datetime.fromtimestamp(ms / 1000, tz=dt_tz.utc)
    try:
        d = datetime.fromisoformat(str(v).replace("Z", "+00:00"))
    except ValueError:
        return None
    if d.tzinfo is None:
        d = timezone.make_aware(d)  # naive source instants are interpreted in America/Mexico_City (documented)
    return d


def map_row(conn, row, stations):
    m = conn.mapping
    g = lambda f: row.get(m.get(f)) if m.get(f) else None  # noqa: E731
    if conn.key_fields:
        if any(row.get(k) in (None, "") for k in conn.key_fields):
            raise ValueError("registro sin clave estable")
        key = "|".join(str(row.get(k)) for k in conn.key_fields)
    else:
        key = str(g("external_key") or "")
        if not key:
            raise ValueError("registro sin clave estable")
    try:
        qty = Decimal(str(g("qty"))) if g("qty") not in (None, "") else (Decimal(1) if g("serial") else None)
    except InvalidOperation:
        raise ValueError("cantidad no numérica")
    if qty is None:
        raise ValueError("sin cantidad ni serial")
    event_at = _dt(g("event_at"))
    if event_at is None:
        raise ValueError("sin instante del evento")
    st_code = str(g("station") or "")
    op = str(g("operation") or "")
    station = stations.get(st_code.upper()) or stations.get(("op", op.upper()))
    line = station.line if station else conn.line
    result = str(g("result") or "").upper()
    result = {"OK": "PASS", "PASSED": "PASS", "P": "PASS", "NG": "FAIL", "FAILED": "FAIL", "F": "FAIL"}.get(result, result)
    attempt = g("attempt")
    try:
        attempt = int(attempt) if attempt not in (None, "") else None
    except (TypeError, ValueError):
        attempt = None
    return {
        "external_key": key[:300], "work_order": str(g("work_order") or "")[:60], "operation": op[:60], "station": station, "line": line,
        "part_number": str(g("part_number") or "")[:80], "serial": str(g("serial") or "")[:80], "panel_id": str(g("panel_id") or "")[:80],
        "lot_ref": str(g("lot_ref") or "")[:80], "side": str(g("side") or (station.side if station else ""))[:6].lower(),
        "qty": qty, "unit": str(g("unit") or (line.count_unit if line else "pz"))[:20].lower(), "result": result[:20], "attempt": attempt,
        "event_at": event_at, "source_modified_at": _dt(g("modified_at")), "scope_key": str(g("scope_key") or g("work_order") or "")[:300],
        "raw": {k: (v if isinstance(v, (str, int, float, bool)) or v is None else str(v)) for k, v in row.items() if not k.startswith("__")},
    }


COMPARE = ["work_order", "operation", "part_number", "serial", "panel_id", "lot_ref", "qty", "unit", "result", "attempt", "event_at", "scope_key"]


def store(conn, values, now):
    """Upsert by (connection, external_key). Returns 'created' | 'updated' | 'unchanged'."""
    cur = PE.objects.filter(connection=conn, external_key=values["external_key"], is_current=True).first()
    fields = {k: values[k] for k in COMPARE}
    if cur is None:
        try:
            with transaction.atomic():
                PE.objects.create(source=PE.Source.SYNTHETIC if conn.synthetic else PE.Source.ODATA, connection=conn, kind=conn.event_kind,
                                  external_key=values["external_key"],
                                  station=values["station"], line=values["line"], side=values["side"], received_at=now,
                                  source_modified_at=values["source_modified_at"], raw=values["raw"], **fields)
            return "created"
        except IntegrityError:  # concurrent/overlapping insert of the same key
            return "unchanged"
    changed = {k: v for k, v in fields.items() if getattr(cur, k) != v}
    if not changed:
        return "unchanged"
    before = {k: str(getattr(cur, k)) for k in changed}
    for k, v in changed.items():
        setattr(cur, k, v)
    cur.version += 1
    cur.received_at = now
    cur.source_modified_at = values["source_modified_at"]
    cur.raw = values["raw"]
    cur.save()
    EventRevision.objects.create(event=cur, action="source_correction", before=before, note="Corrección recibida de la fuente")
    return "updated"


# ---------------------------------------------------------------- sync cycle
def sync_once(conn, now=None, client=None):
    """One bounded synchronization cycle. Watermark advances only if the whole cycle succeeds."""
    now = now or timezone.now()
    client = client or ReadOnlyClient(conn)
    run = SyncRun.objects.create(connection=conn, watermark_before=conn.watermark)
    ODataConnection.objects.filter(pk=conn.pk).update(last_attempt_at=now)
    _record_gap(conn, now)
    if conn.watermark_field and conn.watermark:
        since = conn.watermark - timedelta(minutes=conn.overlap_minutes)
    elif conn.watermark_field:
        since = now - timedelta(hours=conn.window_hours)
    else:
        since = now - timedelta(hours=conn.window_hours) if conn.time_field else None
    run.window_from = since
    stations = {}
    for s in Station.objects.select_related("line").all():
        stations[s.code.upper()] = s
        if s.operation:
            stations.setdefault(("op", s.operation.upper()), s)
    max_mod, max_evt = conn.watermark, conn.last_data_at
    t0 = time.monotonic()
    try:
        url = build_query(conn, since)
        while url:
            if run.pages >= conn.max_pages:
                raise ODataError("server", f"Se alcanzó el límite de {conn.max_pages} páginas; aumente el límite o reduzca la ventana.")
            status, headers, body, ms = client.get(url)
            rows, nxt = parse_page(body)
            run.pages += 1
            with transaction.atomic():  # one commit per page (each row keeps its own savepoint)
                for row in rows:
                    run.read += 1
                    try:
                        values = map_row(conn, row, stations)
                    except ValueError as e:
                        run.rejected += 1
                        log.warning("odata row rejected: %s", e)
                        continue
                    res = store(conn, values, now)
                    setattr(run, res, getattr(run, res) + 1)
                    if values["source_modified_at"] and (max_mod is None or values["source_modified_at"] > max_mod):
                        max_mod = values["source_modified_at"]
                    if max_evt is None or values["event_at"] > max_evt:
                        max_evt = values["event_at"]
            if nxt and not nxt.lower().startswith("http"):
                nxt = urllib.parse.urljoin(_base(conn), nxt)
            url = nxt
    except ODataError as e:
        run.status, run.error_kind, run.error, run.finished = "failed", e.kind, str(e)[:500], timezone.now()
        run.query_ms = int((time.monotonic() - t0) * 1000)
        run.save()
        failures = conn.consecutive_failures + 1
        delay = min(conn.refresh_seconds * (2 ** min(failures, 5)), 3600)
        ODataConnection.objects.filter(pk=conn.pk).update(last_error=f"{KIND_TEXT.get(e.kind, e.kind)}: {e}"[:500],
                                                          consecutive_failures=failures, next_attempt_at=now + timedelta(seconds=delay))
        return run
    run.status, run.finished, run.query_ms = "ok", timezone.now(), int((time.monotonic() - t0) * 1000)
    run.watermark_after = max_mod if conn.watermark_field else None
    run.save()
    ODataConnection.objects.filter(pk=conn.pk).update(
        watermark=run.watermark_after or conn.watermark, last_success_at=now, last_data_at=max_evt, last_error="",
        consecutive_failures=0, next_attempt_at=now + timedelta(seconds=conn.refresh_seconds))
    from .counting import reconcile_pending

    reconcile_pending()
    return run


def _record_gap(conn, now):
    """Detect an interval without queries (e.g. computer off) and record if it is recoverable."""
    last = conn.last_attempt_at
    if not last or (now - last).total_seconds() <= max(3 * conn.refresh_seconds, 300):
        return
    if conn.watermark_field and conn.watermark:
        recoverable, note = True, "Se recupera con la consulta incremental por marca de modificación (ventana solapada)."
    elif conn.time_field and (now - last) <= timedelta(hours=conn.window_hours):
        recoverable, note = True, f"Dentro de la ventana de refresco de {conn.window_hours} h."
    elif conn.time_field:
        recoverable = False
        note = f"Laguna mayor a la ventana de {conn.window_hours} h sin marca de modificación: el periodo anterior a la ventana no se reconsulta automáticamente."
    else:
        recoverable, note = False, "La fuente no tiene campo de tiempo configurado; no se puede reconsultar un periodo."
    SyncGap.objects.create(connection=conn, gap_from=last, gap_to=now, recoverable=recoverable, note=note)


def due_connections(now=None):
    now = now or timezone.now()
    for c in ODataConnection.objects.filter(enabled=True, validated_at__isnull=False):
        if c.next_attempt_at is None or c.next_attempt_at <= now:
            yield c
