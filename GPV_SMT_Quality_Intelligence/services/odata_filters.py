"""Construcción segura de URLs OData.

- Solo entidades y campos de la lista blanca.
- Los literales se formatean según el tipo Edm real (metadata) y la versión OData.
- Las comillas se escapan duplicándolas y todos los valores se codifican en URL.
"""
from __future__ import annotations

import re
from datetime import datetime, timezone
from urllib.parse import quote

from models.entities import FILTERABLE_FIELDS, KNOWN_ENTITIES, PropertyInfo
from models.query import ALLOWED_OPERATORS, Filter, QuerySpec

GUID_RE = re.compile(r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$")
MAX_STRING_LITERAL = 200
MAX_IN_VALUES = 10
MAX_TOP = 1000


class FilterError(ValueError):
    pass


def escape_string_literal(value: str) -> str:
    if not isinstance(value, str):
        raise FilterError("Se esperaba texto")
    if len(value) > MAX_STRING_LITERAL:
        raise FilterError("Valor demasiado largo")
    if any(ord(c) < 32 or ord(c) == 127 for c in value):
        raise FilterError("El valor contiene caracteres de control")
    return "'" + value.replace("'", "''") + "'"


def _to_utc(value: datetime) -> datetime:
    if not isinstance(value, datetime):
        raise FilterError("Se esperaba fecha/hora")
    if value.tzinfo is None:
        raise FilterError("La fecha debe incluir zona horaria")
    return value.astimezone(timezone.utc)


def format_literal(value, edm_type: str, odata_version: str) -> str:
    v4 = odata_version == "4"
    if edm_type == "Edm.String":
        return escape_string_literal(str(value))
    if edm_type == "Edm.Guid":
        s = str(value)
        if not GUID_RE.match(s):
            raise FilterError("GUID inválido")
        return s if v4 else f"guid'{s}'"
    if edm_type == "Edm.DateTimeOffset":
        s = _to_utc(value).strftime("%Y-%m-%dT%H:%M:%SZ")
        return s if v4 else f"datetimeoffset'{s}'"
    if edm_type == "Edm.DateTime":
        s = _to_utc(value).strftime("%Y-%m-%dT%H:%M:%S")
        return f"datetime'{s}'" if not v4 else s
    if edm_type in ("Edm.Int32", "Edm.Int64", "Edm.Int16"):
        if isinstance(value, bool) or not isinstance(value, int):
            raise FilterError("Se esperaba número entero")
        return str(value)
    if edm_type == "Edm.Boolean":
        if not isinstance(value, bool):
            raise FilterError("Se esperaba booleano")
        return "true" if value else "false"
    raise FilterError(f"Tipo {edm_type} no soportado para filtros")


def build_filter(spec: QuerySpec, props: dict[str, PropertyInfo], odata_version: str) -> str:
    allowed = FILTERABLE_FIELDS.get(spec.entity, frozenset())
    clauses = []
    for f in spec.filters:
        if f.field not in allowed:
            raise FilterError(f"Campo no autorizado para filtrar: {f.field}")
        if f.field not in props:
            raise FilterError(f"El campo {f.field} no existe en $metadata de {spec.entity}")
        if f.op not in ALLOWED_OPERATORS:
            raise FilterError(f"Operador no autorizado: {f.op}")
        edm = props[f.field].edm_type
        if f.op == "in":
            values = list(f.value)
            if not values or len(values) > MAX_IN_VALUES:
                raise FilterError("Lista de valores vacía o demasiado grande")
            ors = " or ".join(f"{f.field} eq {format_literal(v, edm, odata_version)}" for v in values)
            clauses.append(f"({ors})")
        else:
            clauses.append(f"{f.field} {f.op} {format_literal(f.value, edm, odata_version)}")
    return " and ".join(clauses)


def build_query_url(base_url: str, spec: QuerySpec, props: dict[str, PropertyInfo] | None,
                    odata_version: str) -> str:
    if spec.entity not in KNOWN_ENTITIES:
        raise FilterError(f"Entidad no autorizada: {spec.entity}")
    props = props or KNOWN_ENTITIES[spec.entity]
    if not (1 <= spec.top <= MAX_TOP):
        raise FilterError("$top fuera de rango")
    params: list[tuple[str, str]] = []
    flt = build_filter(spec, props, odata_version)
    if flt:
        params.append(("$filter", flt))
    if spec.orderby:
        order = []
        for fld, direction in spec.orderby:
            if fld not in props or direction not in ("asc", "desc"):
                raise FilterError("Orden no autorizado")
            order.append(f"{fld} {direction}")
        params.append(("$orderby", ",".join(order)))
    if spec.select:
        sel = [s for s in spec.select if s in props]
        if sel:
            params.append(("$select", ",".join(sel)))
    params.append(("$top", str(spec.top)))
    query = "&".join(f"{k}={quote(v, safe='')}" for k, v in params)
    return base_url.rstrip("/") + "/" + quote(spec.entity, safe="") + "?" + query
