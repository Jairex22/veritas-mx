"""Explicit, low-volume compatibility probes for ProductivityOverTime.

Executed ONLY when an administrator presses "Probar compatibilidad" (or automatically in
DEMO mode against the simulator). Every probe uses ``$top=1``; the full sequence is at most
eight GET requests and can only run once per ``MIN_PROBE_INTERVAL_SECONDS``.

A probe result is one of:
* ``ok``          - the server answered 200 and the result is consistent with the option.
* ``failed``      - the server rejected the option or demonstrably ignored it.
* ``not_tested``  - prerequisites missing (no mapped field, no sample value) or sequence aborted.

Results are bound to the schema hash and the field mapping; any change invalidates them.
"""
from __future__ import annotations

import hashlib
import json
import time
from dataclasses import asdict, dataclass
from datetime import timedelta
from typing import Any, Callable

from metadata_inspector import EntitySchema
from odata_client import FilterClause, ODataClient, QuerySpec, Status
from security import ValidationError, odata_datetime_literal, odata_value_literal
from timeutil import PlantClock, iso_utc, parse_odata_datetime, utc_now

PROBE_LABELS_ES: dict[str, str] = {
    "top": "Límite de registros ($top)",
    "select": "Selección de campos ($select)",
    "orderby": "Orden descendente por fecha ($orderby desc)",
    "orderby_asc": "Orden ascendente por fecha ($orderby asc)",
    "filter_date": "Filtro por rango de fecha ($filter)",
    "filter_line": "Filtro por línea ($filter)",
    "filter_station": "Filtro por estación ($filter)",
    "filter_shift": "Filtro por turno ($filter)",
}
PROBE_ORDER = tuple(PROBE_LABELS_ES)
# Statuses that abort the remaining probes (server health/auth problems).
_ABORT = {Status.TIMEOUT, Status.CONNECTION_ERROR, Status.SERVER_ERROR, Status.UNAVAILABLE,
          Status.TOO_MANY_REQUESTS, Status.AUTH_REQUIRED, Status.FORBIDDEN, Status.CIRCUIT_OPEN,
          Status.BUSY, Status.SESSION_LIMIT, Status.GLOBAL_LIMIT, Status.AUTH_NOT_AVAILABLE,
          Status.RESPONSE_TOO_LARGE, Status.REDIRECT_BLOCKED, Status.NOT_FOUND}


@dataclass
class ProbeResult:
    name: str
    label: str
    status: str  # ok | failed | not_tested
    detail: str
    http_status: int | None = None
    query: str = ""
    tested_at: str = ""


def binding_hash(schema: EntitySchema, mapping: dict[str, str | None]) -> str:
    """Identifies the schema+mapping combination the probe results apply to."""
    payload = json.dumps({"schema": schema.schema_hash, "mapping": mapping}, sort_keys=True)
    return hashlib.sha256(payload.encode()).hexdigest()[:16]


def _result(name: str, status: str, detail: str, odata_result: Any = None) -> ProbeResult:
    return ProbeResult(
        name=name, label=PROBE_LABELS_ES[name], status=status, detail=detail,
        http_status=getattr(odata_result, "http_status", None),
        query=getattr(odata_result, "relative_url", ""),
        tested_at=iso_utc(utc_now()),
    )


def run_probes(client: ODataClient, schema: EntitySchema, mapping: dict[str, str | None],
               session_id: str, clock: PlantClock, delay_seconds: float = 1.0,
               sleep: Callable[[float], None] = time.sleep) -> dict[str, ProbeResult]:
    """Run the probe sequence. Never issues a request without ``$top=1``."""
    results: dict[str, ProbeResult] = {}
    aborted_reason = ""
    ts_field = mapping.get("timestamp")
    sample: dict[str, Any] = {}

    def run(name: str, spec: QuerySpec) -> Any:
        nonlocal aborted_reason
        if aborted_reason:
            results[name] = _result(name, "not_tested", f"Secuencia detenida: {aborted_reason}")
            return None
        if results:
            sleep(delay_seconds)
        res = client.query(spec, session_id, enforce_spacing=False)
        if res.status in _ABORT:
            aborted_reason = res.message
            results[name] = _result(name, "not_tested", f"Secuencia detenida: {res.message}", res)
            return None
        return res

    # 1. $top
    res = run("top", QuerySpec(top=1))
    if res is not None:
        if res.ok and len(res.records) <= 1 and not res.top_ignored:
            sample = res.records[0] if res.records else {}
            detail = "El servidor respetó $top=1." if res.records else "Respondió sin registros (0) con $top=1."
            results["top"] = _result("top", "ok", detail, res)
        elif res.ok:
            results["top"] = _result("top", "failed", "El servidor ignoró $top: devolvió más registros de los solicitados.", res)
        else:
            results["top"] = _result("top", "failed", res.message, res)
    if results.get("top") and results["top"].status != "ok":
        for name in PROBE_ORDER[1:]:
            results.setdefault(name, _result(name, "not_tested", "Requiere que $top funcione; no se probó para evitar descargas masivas."))
        return results

    # 2. $select
    select_fields = tuple(dict.fromkeys([*schema.keys, *[v for v in mapping.values() if v]]))
    if select_fields:
        res = run("select", QuerySpec(top=1, select=select_fields))
        if res is not None:
            if res.ok and all(set(r).issubset(set(select_fields)) for r in res.records):
                results["select"] = _result("select", "ok", "El servidor devolvió solo los campos solicitados.", res)
            elif res.ok:
                results["select"] = _result("select", "failed", "El servidor ignoró $select.", res)
            else:
                results["select"] = _result("select", "failed", res.message, res)
    else:
        results["select"] = _result("select", "not_tested", "No hay campos confirmados para seleccionar.")

    ts_prop = schema.get(ts_field)
    # 3. $orderby on timestamp
    if ts_prop:
        res = run("orderby", QuerySpec(top=1, orderby=(ts_prop.name, "desc")))
        if res is not None:
            results["orderby"] = _result("orderby", "ok" if res.ok else "failed",
                                         "El servidor aceptó el orden descendente por fecha." if res.ok else res.message, res)
        res = run("orderby_asc", QuerySpec(top=1, orderby=(ts_prop.name, "asc")))
        if res is not None:
            results["orderby_asc"] = _result("orderby_asc", "ok" if res.ok else "failed",
                                             "El servidor aceptó el orden ascendente por fecha." if res.ok else res.message, res)
    else:
        results["orderby"] = _result("orderby", "not_tested", "Campo de fecha no confirmado.")
        results["orderby_asc"] = _result("orderby_asc", "not_tested", "Campo de fecha no confirmado.")

    # 4. date range filter (last 24 h)
    if ts_prop:
        end = clock.now()
        start = end - timedelta(days=1)
        try:
            clauses = (
                FilterClause(ts_prop.name, "ge", odata_datetime_literal(start, ts_prop.edm_type, schema.odata_version)),
                FilterClause(ts_prop.name, "lt", odata_datetime_literal(end, ts_prop.edm_type, schema.odata_version)),
            )
        except ValidationError as exc:
            results["filter_date"] = _result("filter_date", "failed", str(exc))
        else:
            res = run("filter_date", QuerySpec(top=1, filters=clauses))
            if res is not None:
                if not res.ok:
                    results["filter_date"] = _result("filter_date", "failed", res.message, res)
                else:
                    inside = True
                    for record in res.records:
                        moment = parse_odata_datetime(record.get(ts_prop.name), clock)
                        if moment is not None and not (start - timedelta(minutes=1) <= moment < end + timedelta(minutes=1)):
                            inside = False
                    if inside:
                        detail = ("El servidor aceptó el filtro por fecha." if res.records else
                                  "El servidor aceptó el filtro por fecha (sin registros en las últimas 24 h).")
                        results["filter_date"] = _result("filter_date", "ok", detail, res)
                    else:
                        results["filter_date"] = _result("filter_date", "failed",
                                                         "El servidor devolvió registros fuera del rango: el filtro no se aplicó.", res)
    else:
        results["filter_date"] = _result("filter_date", "not_tested", "Campo de fecha no confirmado.")

    # 5-7. equality filters using a sample value from probe 1
    for role in ("line", "station", "shift"):
        name = f"filter_{role}"
        prop = schema.get(mapping.get(role))
        if prop is None:
            results[name] = _result(name, "not_tested", "Campo no disponible o no confirmado.")
            continue
        value = sample.get(prop.name)
        if value is None or isinstance(value, bool):
            results[name] = _result(name, "not_tested", "No se obtuvo un valor de muestra para probar este filtro.")
            continue
        try:
            literal = odata_value_literal(str(value), prop.edm_type)
        except ValidationError:
            results[name] = _result(name, "not_tested", "El valor de muestra contiene caracteres no permitidos.")
            continue
        res = run(name, QuerySpec(top=1, filters=(FilterClause(prop.name, "eq", literal),)))
        if res is None:
            continue
        if not res.ok:
            results[name] = _result(name, "failed", res.message, res)
        elif all(str(r.get(prop.name)) == str(value) for r in res.records if prop.name in r):
            results[name] = _result(name, "ok", f"El servidor aceptó el filtro (valor de prueba: {value}).", res)
        else:
            results[name] = _result(name, "failed", "El servidor devolvió registros que no coinciden: el filtro no se aplicó.", res)
    return results


def was_aborted(results: dict[str, ProbeResult]) -> bool:
    """True when the sequence stopped because the server/auth failed (results are not evidence)."""
    return any(r.detail.startswith("Secuencia detenida") for r in results.values())


def probes_to_json(results: dict[str, ProbeResult]) -> dict[str, dict[str, Any]]:
    return {k: asdict(v) for k, v in results.items()}
