"""Controlled OData query engine.

Callers (views, reports, the assistant) never send raw OData. They build a ``QuerySpec`` which is
validated against the CURRENT live schema and the capabilities VERIFIED for that entity set:

* the entity set must exist in $metadata and have passed a probe (CONNECTED / NO DATA);
* $select / $filter / $orderby / $expand may only name declared properties / navigation;
* an option is used only if the capability test confirmed the server accepts it ($top is
  confirmed by the probe itself);
* filter operators come from a fixed list; values are converted to literals according to the
  declared Edm type and OData version (no free text is concatenated into the URL);
* $top is capped (GPV_FLX_MAX_TOP), pagination follows the server continuation links up to
  GPV_FLX_MAX_PAGES / GPV_FLX_MAX_ROWS and reports when results were truncated.
"""
import re
import urllib.parse
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone as dt_tz
from decimal import Decimal, InvalidOperation

from django.utils import timezone

from . import status as st
from .client import FlxError, cfg, get
from .payload import normalize_row, rows_of

OPS = {"eq": "igual a", "ne": "distinto de", "gt": "mayor que", "ge": "mayor o igual", "lt": "menor que", "le": "menor o igual",
       "startswith": "empieza con", "contains": "contiene"}
NUMERIC = {"Edm.Int16", "Edm.Int32", "Edm.Int64", "Edm.Byte", "Edm.SByte", "Edm.Decimal", "Edm.Double", "Edm.Single"}
IDENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,127}$")


class QueryError(ValueError):
    pass


@dataclass
class QuerySpec:
    entity: str
    select: list = field(default_factory=list)
    filters: list = field(default_factory=list)  # [(prop, op, value)]
    orderby: list = field(default_factory=list)  # [(prop, "asc"|"desc")]
    top: int = 50
    expand: list = field(default_factory=list)
    count: bool = False
    max_rows: int = None


def literal(value, edm_type, major):
    t = edm_type or "Edm.String"
    if value is None:
        return "null"
    if t in NUMERIC:
        try:
            d = Decimal(str(value).strip())
        except InvalidOperation:
            raise ValueError(f"«{value}» no es numérico ({t}).")
        if t in ("Edm.Int16", "Edm.Int32", "Edm.Int64", "Edm.Byte", "Edm.SByte") and d != d.to_integral_value():
            raise ValueError(f"«{value}» debe ser entero ({t}).")
        s = format(d, "f")
        if major < 4 and t == "Edm.Decimal":
            return s + "M"
        if major < 4 and t == "Edm.Int64":
            return s + "L"
        return s
    if t == "Edm.Boolean":
        v = str(value).strip().lower()
        if v not in ("true", "false"):
            raise ValueError("Use true o false.")
        return v
    if t in ("Edm.DateTime", "Edm.DateTimeOffset", "Edm.Date"):
        if isinstance(value, datetime):
            d = value
        else:
            try:
                d = datetime.fromisoformat(str(value).strip().replace("Z", "+00:00"))
            except ValueError:
                raise ValueError(f"«{value}» no es una fecha válida (AAAA-MM-DD o AAAA-MM-DDTHH:MM).")
        if d.tzinfo is None:
            d = timezone.make_aware(d)  # local America/Mexico_City
        if t == "Edm.Date":
            return d.date().isoformat()
        iso = d.astimezone(dt_tz.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        if major >= 4:
            return iso
        return f"datetime'{iso[:-1]}'" if t == "Edm.DateTime" else f"datetimeoffset'{iso}'"
    if t == "Edm.Guid":
        try:
            g = str(uuid.UUID(str(value).strip()))
        except ValueError:
            raise ValueError(f"«{value}» no es un GUID válido.")
        return g if major >= 4 else f"guid'{g}'"
    if t == "Edm.String":
        s = str(value)
        if len(s) > 200 or any(ord(c) < 32 for c in s):
            raise ValueError("Texto demasiado largo o con caracteres de control.")
        return "'" + s.replace("'", "''") + "'"
    raise ValueError(f"Tipo {t} no soportado en filtros.")


def _filter_expr(prop, op, value, edm_type, major):
    if op not in OPS:
        raise QueryError(f"Operador no permitido: {op}")
    if op in ("startswith", "contains"):
        if edm_type != "Edm.String":
            raise QueryError(f"«{OPS[op]}» solo aplica a texto ({prop} es {edm_type}).")
        lit = literal(value, edm_type, major)
        if op == "startswith":
            return f"startswith({prop},{lit})" + ("" if major >= 4 else " eq true")
        return f"contains({prop},{lit})" if major >= 4 else f"substringof({lit},{prop}) eq true"
    try:
        return f"{prop} {op} {literal(value, edm_type, major)}"
    except ValueError as e:
        raise QueryError(str(e))


def validate(spec, es):
    """Return the list of OData parameters for a valid spec (raises QueryError)."""
    from .discovery import major

    if not es.queryable:
        raise QueryError(f"«{es.name}» no está verificado como consultable ({es.status}). Un administrador debe sondearlo primero.")
    caps = es.capabilities or {}
    mj = major(es.schema)
    props = es.properties
    params = []
    top = int(spec.top or 0)
    if top < 1 or top > cfg()["MAX_TOP"]:
        raise QueryError(f"$top debe estar entre 1 y {cfg()['MAX_TOP']}.")
    params.append(("$top", str(top)))

    def need(opt):
        if caps.get(opt) is not True:
            raise QueryError(f"La opción {opt} no está verificada para «{es.name}». Ejecute «Probar capacidades» (administrador).")

    if spec.select:
        need("$select")
        bad = [p for p in spec.select if p not in props or not IDENT.match(p)]
        if bad:
            raise QueryError("Propiedades inexistentes en $metadata: " + ", ".join(bad))
        params.append(("$select", ",".join(dict.fromkeys(spec.select))))
    if spec.filters:
        need("$filter")
        if len(spec.filters) > 5:
            raise QueryError("Máximo 5 condiciones.")
        exprs = []
        for prop, op, value in spec.filters:
            if prop not in props:
                raise QueryError(f"Propiedad inexistente en $metadata: {prop}")
            exprs.append(_filter_expr(prop, op, value, props[prop].get("type"), mj))
        params.append(("$filter", " and ".join(exprs)))
    if spec.orderby:
        need("$orderby")
        parts = []
        for prop, d in spec.orderby[:3]:
            if prop not in props or d not in ("asc", "desc"):
                raise QueryError(f"Orden no válido: {prop} {d}")
            parts.append(f"{prop} {d}")
        params.append(("$orderby", ",".join(parts)))
    if spec.expand:
        need("$expand")
        bad = [n for n in spec.expand if n not in es.navigation]
        if bad:
            raise QueryError("Navegación inexistente en $metadata: " + ", ".join(bad))
        params.append(("$expand", ",".join(spec.expand)))
    if spec.count:
        need("$count")
        params.append(("$count", "true") if mj >= 4 else ("$inlinecount", "allpages"))
    return params


def build_path(spec, es):
    params = validate(spec, es)
    return urllib.parse.quote(es.name) + "?" + urllib.parse.urlencode(params, safe="$,()'", quote_via=urllib.parse.quote)


def run(spec, es, use_cache=True):
    """Execute with server-driven paging. Returns a dict with rows and provenance."""
    from .discovery import ACCEPT_JSON, major

    path = build_path(spec, es)
    max_rows = min(spec.max_rows or spec.top, cfg()["MAX_ROWS"])
    rows, pages, count, latency, url = [], 0, None, 0, path
    truncated = False
    while url:
        pages += 1
        r = get(url, accept=ACCEPT_JSON[major(es.schema)], use_cache=use_cache)
        latency += r.ms
        page, nxt, cnt = rows_of(r.json())
        count = cnt if cnt is not None else count
        rows.extend(normalize_row(x) for x in page)
        if len(rows) >= max_rows:
            truncated = len(rows) > max_rows or bool(nxt)
            rows = rows[:max_rows]
            break
        if nxt and pages >= cfg()["MAX_PAGES"]:
            truncated = True
            break
        url = nxt
    return {"rows": rows, "count": count, "pages": pages, "truncated": truncated, "latency_ms": latency,
            "source": {"entity_set": es.name, "service_path": path.split("?")[0], "options": [k for k, _ in validate(spec, es)],
                       "fetched_at": timezone.now().isoformat(), "schema_sha256": es.schema.sha256[:12], "origin": "FactoryLogix OData (lectura)"}}


def entity(name):
    from .discovery import current_schema

    schema = current_schema()
    if schema is None:
        raise FlxError(st.CONFIG_ERROR, "No hay un esquema de FactoryLogix cargado.")
    es = schema.entity_sets.filter(name=name).first()
    if es is None:
        raise QueryError(f"«{name}» no existe en el $metadata actual.")
    return es
