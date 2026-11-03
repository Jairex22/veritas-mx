"""Connection test, schema discovery, controlled probes and capability tests.

Probes are deliberately small: one entity set at a time, ``$top=1``, with a pause between calls,
and only on request of an administrator. Probe results keep property NAMES returned, never values.
"""
import time
import urllib.parse

from django.db import transaction
from django.utils import timezone

from . import catalog, metadata
from . import status as st
from .client import FlxError, auth_mode, base_url, cfg, detect_auth, get
from .models import FlxEntitySet, FlxRun, FlxSchema, FlxState
from .payload import property_names, rows_of

ACCEPT_JSON = {4: "application/json;odata.metadata=minimal, application/json;q=0.9", 2: "application/json;odata=verbose, application/json;q=0.9"}


def current_schema():
    return FlxSchema.objects.filter(is_current=True).first()


def major(schema=None):
    schema = schema or current_schema()
    return 4 if schema and str(schema.odata_version or schema.edmx_version).startswith("4") else 2


# ---------------------------------------------------------------- schema persistence
@transaction.atomic
def save_schema(parsed, xml_bytes, source, user=None):
    previous = current_schema()
    prev_sets = {e.name: e for e in previous.entity_sets.all()} if previous else {}
    FlxSchema.objects.filter(is_current=True).update(is_current=False)
    schema = FlxSchema.objects.create(source=source, base_url=base_url() if source == FlxSchema.Source.LIVE else "", odata_version=parsed["odata_version"],
                                      edmx_version=parsed["edmx_version"], sha256=parsed["sha256"], size=parsed["size"],
                                      entity_set_count=len(parsed["entity_sets"]), function_imports=parsed["function_imports"],
                                      xml=xml_bytes.decode("utf-8", "replace"), loaded_by=user if user and user.is_authenticated else None)
    objs = []
    for name, es in parsed["entity_sets"].items():
        o = FlxEntitySet(schema=schema, name=name, entity_type=es["entity_type"], category=catalog.category(name), keys=es["keys"],
                         properties=es["properties"], navigation=es["navigation"], declared_capabilities=es["declared_capabilities"])
        prev = prev_sets.get(name)
        # keep verified results only if the live structure did not change
        if prev and source == FlxSchema.Source.LIVE and prev.schema.source == FlxSchema.Source.LIVE and prev.properties == es["properties"]:
            for f in ("status", "http_status", "latency_ms", "checked_at", "detail", "returned_properties", "capabilities", "capabilities_checked_at"):
                setattr(o, f, getattr(prev, f))
        objs.append(o)
    FlxEntitySet.objects.bulk_create(objs)
    return schema


def load_schema_file(xml_bytes, user):
    parsed = metadata.parse(xml_bytes)
    schema = save_schema(parsed, xml_bytes, FlxSchema.Source.FILE, user)
    FlxRun.objects.create(kind="schema_file", user=user, finished=timezone.now(), outcome="ok",
                          summary={"entity_sets": schema.entity_set_count, "sha256": schema.sha256[:12]})
    return schema


# ---------------------------------------------------------------- connection + schema (staged)
def test_connection(user=None, via="web", fetch_schema=True):
    """Staged diagnosis: configuration → authentication offered → service document → $metadata.
    Returns (stages, schema_or_None). Never reports success without a valid response."""
    run = FlxRun.objects.create(kind="connection", user=user if user and user.is_authenticated else None, via=via)
    stages = []

    def add(name, state, detail, ms=None):
        stages.append({"stage": name, "state": state, "ok": state in st.STAGE_OK, "detail": detail, "ms": ms})

    schema = None
    try:
        url = base_url()
        add("Configuración", st.OK, f"Servicio configurado: {url} · autenticación configurada: {auth_mode()}")
    except FlxError as e:
        add("Configuración", e.state, str(e))
        return _finish(run, stages), None
    a = detect_auth()
    if a["anonymous_allowed"]:
        add("Métodos de autenticación", st.OK, "El servicio responde sin credenciales (acceso anónimo permitido por el servidor).", a.get("ms"))
    elif a.get("state") == st.AUTH_REQUIRED:
        add("Métodos de autenticación", st.OK, "El servidor exige autenticación; métodos ofrecidos: " + (", ".join(a["schemes"]) or "no declarados") + ".")
    else:
        add("Métodos de autenticación", a.get("state", st.UNREACHABLE), a.get("message", ""))
        return _finish(run, stages), None
    try:
        r = get("", accept="application/json", use_cache=False, force=True)
        names = _service_doc_names(r)
        FlxState.objects.update_or_create(pk=1, defaults={"service_doc_sets": names})
        add("Documento de servicio", st.CONNECTED, f"HTTP {r.status} · {len(names)} recursos listados. Un índice accesible NO prueba acceso a los datos.", r.ms)
    except FlxError as e:
        add("Documento de servicio", e.state, str(e))
        return _finish(run, stages), None
    if not fetch_schema:
        return _finish(run, stages), None
    try:
        r = get("$metadata", accept="application/xml", use_cache=False, force=True)
        parsed = metadata.parse(r.body)
        ver = (r.headers.get("odata-version") or r.headers.get("dataserviceversion") or "").split(";")[0]
        if ver:
            parsed["odata_version"] = ver
        schema = save_schema(parsed, r.body, FlxSchema.Source.LIVE, user)
        add("Lectura de $metadata", st.CONNECTED, f"OData {schema.odata_version or '?'} · {schema.entity_set_count} EntitySets · "
                                                 f"{len(schema.function_imports)} FunctionImports · {schema.size // 1024} KB", r.ms)
    except metadata.MetadataError as e:
        add("Lectura de $metadata", st.BAD_RESPONSE, str(e))
    except FlxError as e:
        add("Lectura de $metadata", e.state, str(e))
    return _finish(run, stages), schema


def _service_doc_names(r):
    try:
        d = r.json()
    except FlxError:
        return []
    if isinstance(d, dict) and isinstance(d.get("value"), list):
        return [x.get("name") or x.get("url") for x in d["value"] if isinstance(x, dict)]
    if isinstance(d, dict) and isinstance(d.get("d"), dict):
        return list(d["d"].get("EntitySets") or [])
    return []


def _finish(run, stages):
    run.finished = timezone.now()
    run.outcome = "ok" if stages and all(s["ok"] for s in stages) else (stages[-1]["state"] if stages else "error")
    run.summary = {"stages": stages}
    run.save()
    return stages


# ---------------------------------------------------------------- controlled probes
def probe_entity(es, mj=None):
    """GET <set>?$top=1. Updates the registry row. Returns the resulting state."""
    mj = mj or major(es.schema)
    t0 = time.monotonic()
    try:
        r = get(f"{urllib.parse.quote(es.name)}?{urllib.parse.urlencode({'$top': '1'}, safe='$')}", accept=ACCEPT_JSON[mj], use_cache=False)
        rows, _nxt, _cnt = rows_of(r.json())
        es.http_status, es.latency_ms = r.status, r.ms
        if not rows:
            es.status, es.detail, es.returned_properties = st.NO_DATA, st.EXPLAIN[st.NO_DATA], []
        else:
            names = property_names(rows[0])
            declared = set(es.properties) | set(es.navigation)
            unknown = sorted(set(names) - declared)
            missing_keys = [k for k in es.keys if k not in names]
            es.returned_properties = names
            if unknown or missing_keys:
                es.status = st.SCHEMA_MISMATCH
                es.detail = ("Propiedades no declaradas en $metadata: " + ", ".join(unknown[:15]) if unknown else "") + \
                            (" · Claves ausentes: " + ", ".join(missing_keys) if missing_keys else "")
            else:
                es.status, es.detail = st.CONNECTED, f"Consulta $top=1 válida ({len(names)} propiedades, coinciden con $metadata)."
        es.capabilities = {**(es.capabilities or {}), "$top": True}
    except FlxError as e:
        es.status, es.http_status = e.state, e.http_status
        es.latency_ms = int((time.monotonic() - t0) * 1000)
        es.detail = (str(e) + (f" · Servidor: {e.detail}" if e.detail else ""))[:500]
    es.checked_at = timezone.now()
    es.save()
    return es.status


def probe(names=None, user=None, via="web", delay_ms=None, progress=None, cancelled=None):
    schema = current_schema()
    if schema is None or schema.source != FlxSchema.Source.LIVE:
        raise FlxError(st.CONFIG_ERROR, "Primero lea el $metadata del servidor (un esquema cargado de archivo no permite sondear).")
    qs = schema.entity_sets.all()
    if names:
        qs = qs.filter(name__in=names)
    items = list(qs.order_by("name"))
    delay = (cfg()["PROBE_DELAY_MS"] if delay_ms is None else delay_ms) / 1000
    run = FlxRun.objects.create(kind="probe", user=user if user and user.is_authenticated else None, via=via, summary={"requested": len(items)})
    counts, stopped = {}, ""
    mj = major(schema)
    for i, es in enumerate(items):
        if cancelled and cancelled():
            stopped = "cancelado"
            break
        state = probe_entity(es, mj)
        counts[state] = counts.get(state, 0) + 1
        if progress:
            progress(int(100 * (i + 1) / max(len(items), 1)), f"{es.name}: {state}")
        if state in (st.AUTH_REQUIRED, st.CIRCUIT_OPEN, st.UNREACHABLE, st.CONFIG_ERROR):
            stopped = f"detenido por {state}: el resto queda sin probar"
            break
        if i + 1 < len(items) and delay:
            time.sleep(delay)
    run.finished, run.outcome = timezone.now(), "ok" if not stopped else "stopped"
    run.summary = {"requested": len(items), "counts": counts, "stopped": stopped}
    run.save()
    return run


# ---------------------------------------------------------------- capability tests (one entity, on request)
def test_capabilities(es, user=None, via="web"):
    """Verify which query options this entity set really accepts. Uses tiny queries ($top=1)."""
    if es.status not in st.OK_STATES:
        raise FlxError(st.CONFIG_ERROR, "Primero el sondeo debe confirmar que el conjunto es consultable.")
    mj = major(es.schema)
    acc = ACCEPT_JSON[mj]
    q = urllib.parse.quote(es.name)
    caps, notes = {"$top": True}, {}
    key = es.keys[0] if es.keys else (sorted(es.properties)[0] if es.properties else None)
    sample = None

    def ok(path):
        try:
            r = get(path, accept=acc, use_cache=False)
            rows, nxt, cnt = rows_of(r.json())
            return True, rows, cnt, r
        except FlxError as e:
            return False, e, None, None

    def enc(params):
        return urllib.parse.urlencode(params, safe="$,()'", quote_via=urllib.parse.quote)

    if key:
        good, rows, _c, _r = ok(f"{q}?{enc({'$top': '1', '$select': key})}")
        caps["$select"] = bool(good and rows is not None and (not rows or set(property_names(rows[0])) <= {key}))
        if good and rows:
            sample = rows[0].get(key)
        good, *_ = ok(f"{q}?{enc({'$top': '1', '$orderby': key})}")
        caps["$orderby"] = good
    good, *_ = ok(f"{q}?{enc({'$top': '1', '$skip': '1'})}")
    caps["$skip"] = good
    if mj == 4:
        good, rows, cnt, _r = ok(f"{q}?{enc({'$top': '1', '$count': 'true'})}")
    else:
        good, rows, cnt, _r = ok(f"{q}?{enc({'$top': '1', '$inlinecount': 'allpages'})}")
    caps["$count"] = bool(good and cnt is not None)
    if key and sample is not None and key in es.properties:
        from .query import literal

        try:
            lit = literal(sample, es.properties[key]["type"], mj)
            good, rows, *_ = ok(f"{q}?{enc({'$top': '1', '$filter': f'{key} eq {lit}'})}")
            caps["$filter"] = bool(good)
        except ValueError:
            notes["$filter"] = "Tipo de clave no soportado para la prueba."
    else:
        notes["$filter"] = "Sin valor de clave para probar."
    if es.navigation:
        nav = sorted(es.navigation)[0]
        good, *_ = ok(f"{q}?{enc({'$top': '1', '$expand': nav})}")
        caps["$expand"] = good
    else:
        notes["$expand"] = "La entidad no declara navegación."
    es.capabilities = {**caps, "_notes": notes}
    es.capabilities_checked_at = timezone.now()
    es.save(update_fields=["capabilities", "capabilities_checked_at"])
    FlxRun.objects.create(kind="capabilities", user=user if user and user.is_authenticated else None, via=via, finished=timezone.now(), outcome="ok",
                          summary={"entity": es.name, "capabilities": caps})
    return es.capabilities


# ---------------------------------------------------------------- report (structure only, no record values)
def report():
    s = FlxState.get()
    schema = current_schema()
    sets = list(schema.entity_sets.all()) if schema else []
    present = {e.name for e in sets}
    expected = [{"category": cat, "name": n, "in_metadata": n in present} for cat, names in catalog.EXPECTED.items() for n in names]
    return {
        "generated_at": timezone.now().isoformat(), "app": "GPV Operations Hub 2.0", "service": _safe_base(),
        "auth": {"configured": auth_mode(), "offered_by_server": s.auth_schemes_offered, "blocked_after_401": bool(s.auth_blocked_at)},
        "state": {"last_status": s.last_status, "last_success_at": s.last_success_at.isoformat() if s.last_success_at else None,
                  "last_latency_ms": s.last_latency_ms, "detail": s.last_detail},
        "schema": None if not schema else {"source": schema.source, "fetched_at": schema.fetched_at.isoformat(), "odata_version": schema.odata_version,
                                           "entity_sets": schema.entity_set_count, "sha256": schema.sha256, "size": schema.size,
                                           "function_imports": schema.function_imports},
        "entity_sets": [{"name": e.name, "category": e.category, "entity_type": e.entity_type, "keys": e.keys,
                         "properties": {k: v.get("type") for k, v in e.properties.items()}, "navigation": e.navigation,
                         "declared_capabilities": e.declared_capabilities, "status": e.status, "http_status": e.http_status,
                         "latency_ms": e.latency_ms, "checked_at": e.checked_at.isoformat() if e.checked_at else None,
                         "detail": e.detail, "returned_properties": e.returned_properties, "capabilities": e.capabilities} for e in sets],
        "expected_from_gpv_list": expected,
        "note": "Reporte de estructura y estado: no contiene valores de registros, credenciales ni encabezados de autorización.",
    }


def _safe_base():
    try:
        return base_url()
    except FlxError as e:
        return f"(configuración inválida: {e})"
