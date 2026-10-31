"""Fuentes de datos externas (sólo lectura): archivos auxiliares y OData mapeado.

Ninguna de estas fuentes genera datos: si la información no existe o la
conexión falla, se propaga un error explícito.
"""
from __future__ import annotations

import csv
import json
import re
import threading
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import httpx

from ..connectors.base import diagnose_http
from ..connectors.factorylogix import ODataConnector
from ..core.errors import DataSourceUnavailable, NotFound, ValidationFailed
from .models import REPAIR_STATIONS, Defect, Event, Unit, WorkOrder
from .source import ProductionDataSource


def _parse_ts(value: str) -> datetime:
    value = (value or "").strip()
    if not value:
        raise ValueError("timestamp vacío")
    if value.endswith("Z"):
        value = value[:-1] + "+00:00"
    ts = datetime.fromisoformat(value)
    return ts if ts.tzinfo else ts.replace(tzinfo=timezone.utc)


def build_units(event_rows: list[dict[str, Any]], defect_rows: list[dict[str, Any]] | None = None,
                unit_rows: list[dict[str, Any]] | None = None) -> list[Unit]:
    """Construye unidades a partir de filas normalizadas.

    Si `unit_rows` aporta estado/estación reportados, se conservan como
    REPORTADOS; si no, se derivan del historial y la ruta queda marcada como
    inferida (orden de primera aparición de estaciones).
    """
    by_serial: dict[str, list[dict]] = {}
    for r in event_rows:
        s = str(r.get("serial") or "").strip()
        if s:
            by_serial.setdefault(s, []).append(r)
    reported = {str(r.get("serial")).strip(): r for r in (unit_rows or []) if r.get("serial")}
    units: list[Unit] = []
    for serial in sorted(set(by_serial) | set(reported)):
        rows = by_serial.get(serial, [])
        events = []
        for i, r in enumerate(rows):
            try:
                ts = _parse_ts(str(r.get("ts") or r.get("timestamp") or ""))
            except ValueError:
                continue
            result = str(r.get("result") or "INFO").upper()
            # Sin tipo de operación en la fuente: un PASS/FAIL es una prueba; INFO es un paso completado.
            operation = str(r.get("operation") or ("TEST" if result in ("PASS", "FAIL") else "HOLD" if result == "HOLD" else "COMPLETE")).upper()
            events.append(Event(id=str(r.get("id") or f"{serial}-{i}"), serial=serial, ts=ts,
                                station=str(r.get("station") or "").upper(),
                                operation=operation, result=result, operator=str(r.get("operator") or ""),
                                line=str(r.get("line") or ""), area=str(r.get("area") or ""),
                                work_order=str(r.get("work_order") or ""), details=str(r.get("details") or "")))
        events.sort(key=lambda e: e.ts)
        meta = {**(rows[0] if rows else {}), **reported.get(serial, {})}
        route: list[str] = []
        for e in events:
            if e.station and e.station not in route and e.station not in REPAIR_STATIONS:
                route.append(e.station)
        status = str(meta.get("status") or "").upper() or None
        current = meta.get("current_station")
        if not status:
            last = events[-1] if events else None
            if last is None:
                status = "IN_PROCESS"
            elif last.operation == "HOLD":
                status, current = "HOLD", last.station
            elif last.operation == "PACK":
                status, current = "PACKED", None
            elif last.station in REPAIR_STATIONS:
                status, current = "IN_REPAIR", last.station
            else:
                status, current = "IN_PROCESS", last.station
        u = Unit(serial=serial, work_order=str(meta.get("work_order") or ""), assembly=str(meta.get("assembly") or ""),
                 revision=str(meta.get("revision") or ""), batch=str(meta.get("batch") or ""),
                 line=str(meta.get("line") or ""), area=str(meta.get("area") or ""),
                 panel_id=(str(meta["panel_id"]) if meta.get("panel_id") else None), panel_position=None,
                 status=status, current_station=(str(current).upper() if current else None), route=route,
                 route_inferred=True, events=events)
        units.append(u)
    index = {u.serial: u for u in units}
    for i, r in enumerate(defect_rows or []):
        u = index.get(str(r.get("serial") or "").strip())
        if not u:
            continue
        try:
            ts = _parse_ts(str(r.get("ts") or r.get("timestamp") or ""))
        except ValueError:
            continue
        u.defects.append(Defect(id=str(r.get("id") or f"DF-{u.serial}-{i}"), serial=u.serial, ts=ts,
                                station=str(r.get("station") or "").upper(), code=str(r.get("code") or ""),
                                description=str(r.get("description") or ""), symptom=str(r.get("symptom") or ""),
                                ref_designator=str(r.get("ref_designator") or ""),
                                status=str(r.get("status") or "OPEN").upper()))
    return units


def _work_orders_from_units(units: list[Unit]) -> list[WorkOrder]:
    wos: dict[str, WorkOrder] = {}
    for u in units:
        if not u.work_order:
            continue
        wo = wos.get(u.work_order)
        first = u.sorted_events[0].ts if u.events else None
        if not wo:
            wos[u.work_order] = WorkOrder(u.work_order, u.assembly, u.revision, 0, u.line, "UNKNOWN", u.batch, first)
            wo = wos[u.work_order]
        wo.quantity += 1  # unidades observadas, no la cantidad planificada
        if first and (wo.started_at is None or first < wo.started_at):
            wo.started_at = first
    return list(wos.values())


class AuxCsvDataSource(ProductionDataSource):
    """Lee `events.csv` (y opcionalmente `defects.csv`) de GPV_AUX_DIR."""

    kind = "AUX_FILE"
    synthetic = False

    def __init__(self, directory: Path):
        self.directory = directory
        self.label = f"Archivos auxiliares ({directory})"
        self._cache: tuple[float, list[Unit]] | None = None
        self._lock = threading.Lock()

    def _read(self, name: str) -> list[dict]:
        path = self.directory / name
        if not path.is_file():
            return []
        with path.open(newline="", encoding="utf-8-sig") as fh:
            return [{(k or "").strip().lower(): (v or "").strip() for k, v in row.items()} for row in csv.DictReader(fh)]

    def list_units(self) -> list[Unit]:
        events = self.directory / "events.csv"
        if not events.is_file():
            raise DataSourceUnavailable(f"No existe {events}. La fuente auxiliar requiere events.csv.",
                                        code="AUX_EVENTS_MISSING")
        mtime = events.stat().st_mtime
        with self._lock:
            if not self._cache or self._cache[0] != mtime:
                self._cache = (mtime, build_units(self._read("events.csv"), self._read("defects.csv")))
            return list(self._cache[1])

    def work_orders(self) -> list[WorkOrder]:
        return _work_orders_from_units(self.list_units())


# ----------------------------------------------------------------------------
# Esquema del mapeo OData (lo que el asistente ofrece y lo que valida el servidor)
# ----------------------------------------------------------------------------
MAPPING_SCHEMA: dict[str, dict[str, Any]] = {
    "events": {
        "label": "Historial de operaciones (obligatorio)",
        "required": True,
        "fields": {
            "serial": ("Serial Number", True), "ts": ("Fecha/hora del evento", True), "station": ("Estación", True),
            "result": ("Resultado (PASS/FAIL/HOLD)", True), "operation": ("Tipo de operación", False),
            "work_order": ("Work Order", False), "assembly": ("Assembly Name", False), "revision": ("Product Revision", False),
            "batch": ("Batch", False), "line": ("Line", False), "area": ("Area", False), "operator": ("Operador", False),
            "panel_id": ("Panel", False), "details": ("Detalle / comentario", False), "id": ("Identificador del evento", False),
        },
        "value_maps": {"result": ["PASS", "FAIL", "HOLD", "INFO"],
                       "operation": ["START", "COMPLETE", "TEST", "DEFECT", "REPAIR", "HOLD", "RELEASE", "PACK", "SCRAP"]},
    },
    "defects": {
        "label": "Defectos (opcional)",
        "required": False,
        "fields": {
            "serial": ("Serial Number", True), "ts": ("Fecha/hora", True), "station": ("Estación", True),
            "code": ("Código de defecto", True), "description": ("Descripción", False), "symptom": ("Síntoma", False),
            "ref_designator": ("Ref. designador", False), "status": ("Estado (OPEN/REPAIRED/VERIFIED)", False),
            "id": ("Identificador del defecto", False),
        },
        "value_maps": {"status": ["OPEN", "REPAIRED", "VERIFIED"]},
    },
    "units": {
        "label": "Estado actual de unidades (opcional)",
        "required": False,
        "fields": {
            "serial": ("Serial Number", True), "status": ("Estado reportado", False), "current_station": ("Estación actual", False),
            "work_order": ("Work Order", False), "assembly": ("Assembly Name", False), "revision": ("Product Revision", False),
            "batch": ("Batch", False), "line": ("Line", False), "area": ("Area", False), "panel_id": ("Panel", False),
        },
        "value_maps": {"status": ["IN_PROCESS", "HOLD", "IN_REPAIR", "COMPLETE", "PACKED", "SCRAPPED"]},
    },
}
_IDENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_./]{0,127}$")


def clean_mapping(raw: Any) -> dict:
    """Normaliza un mapeo enviado por el asistente: elimina campos vacíos,
    valida identificadores y conserva sólo las claves conocidas."""
    if not isinstance(raw, dict):
        raise ValidationFailed("El mapeo debe ser un objeto JSON.")
    out: dict[str, Any] = {
        "verified": bool(raw.get("verified")), "verified_by": str(raw.get("verified_by") or "")[:120],
        "verified_on": str(raw.get("verified_on") or "")[:40], "notes": str(raw.get("notes") or "")[:500],
        "odata_version": "2" if str(raw.get("odata_version") or "4").startswith("2") else "4",
        "max_rows": max(50, min(int(raw.get("max_rows") or 2000), 50000)),
        "window_hours": max(0, min(int(raw.get("window_hours") or 0), 24 * 366)),
    }
    for section, schema in MAPPING_SCHEMA.items():
        sec = raw.get(section)
        if not isinstance(sec, dict) or not sec.get("entity_set"):
            out[section] = None
            continue
        es = str(sec["entity_set"]).strip()
        if not _IDENT.match(es):
            raise ValidationFailed(f"EntitySet inválido en '{section}': {es!r}.")
        fields = {}
        for ours, (label, required) in schema["fields"].items():
            theirs = str((sec.get("fields") or {}).get(ours) or "").strip()
            if theirs:
                if not _IDENT.match(theirs):
                    raise ValidationFailed(f"Propiedad inválida en '{section}.{ours}': {theirs!r}.")
                fields[ours] = theirs
            elif required:
                raise ValidationFailed(f"Falta el campo obligatorio '{label}' en '{schema['label']}'.",
                                       details={"fields": {f"{section}.{ours}": "Requerido."}})
        vmaps = {}
        for key, allowed in schema["value_maps"].items():
            table = (sec.get("value_maps") or {}).get(key)
            if isinstance(table, dict):
                clean = {str(k)[:80]: str(v).upper() for k, v in table.items() if str(v).upper() in allowed}
                if clean:
                    vmaps[key] = clean
        out[section] = {"entity_set": es, "fields": fields, "value_maps": vmaps}
    return out


class ODataDataSource(ProductionDataSource):
    """Lectura OData basada en un mapeo explícito de entidades y campos.

    El mapeo (config/odata_mapping.json) debe elaborarlo el responsable del
    sistema tras inspeccionar `$metadata`; aquí no se presupone ningún nombre
    de entidad de FactoryLogix.
    """

    kind = "ODATA"
    synthetic = False
    CACHE_SECONDS = 60

    def __init__(self, connector: ODataConnector, mapping: dict):
        self.connector = connector
        self.mapping = mapping
        self.label = "FactoryLogix OData (sólo lectura)"
        self.max_rows = int(mapping.get("max_rows", 2000))
        self.window_hours = int(mapping.get("window_hours", 0) or 0)
        self.v2 = str(mapping.get("odata_version", "4")).startswith("2")
        self._cache: tuple[float, list[Unit]] | None = None
        self._lock = threading.Lock()

    def _get(self, entity_set: str, params: dict[str, str]) -> list[dict]:
        try:
            with self.connector.client() as c:
                resp = c.get(entity_set, params=params)
        except httpx.HTTPError as exc:
            raise DataSourceUnavailable(f"OData no accesible: {type(exc).__name__}.", code="ODATA_UNREACHABLE")
        if resp.status_code != 200:
            state, msg, diag = diagnose_http(resp, f"OData {entity_set}")
            raise DataSourceUnavailable(msg, code=f"ODATA_{state.value}",
                                        details={"http_status": resp.status_code, "diagnosis": diag})
        try:
            payload = resp.json()
        except ValueError:
            raise DataSourceUnavailable("La respuesta OData no es JSON.", code="ODATA_NOT_JSON")
        if isinstance(payload, dict):
            if "value" in payload:
                return list(payload["value"])
            d = payload.get("d")
            if isinstance(d, dict) and "results" in d:
                return list(d["results"])
            if isinstance(d, list):
                return d
        return list(payload) if isinstance(payload, list) else []

    def _literal_datetime(self, dt: datetime) -> str:
        iso = dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
        return f"datetime'{iso}'" if self.v2 else iso + "Z"

    def _window_filter(self, section: str) -> str | None:
        spec = self.mapping.get(section)
        if not spec or not self.window_hours or "ts" not in spec["fields"]:
            return None
        since = datetime.now(timezone.utc) - timedelta(hours=self.window_hours)
        return f"{spec['fields']['ts']} ge {self._literal_datetime(since)}"

    def _rows(self, section: str, filter_expr: str | None = None, top: int | None = None) -> list[dict]:
        spec = self.mapping.get(section)
        if not spec:
            return []
        fields: dict[str, str] = spec["fields"]
        params = {"$top": str(top or self.max_rows), "$select": ",".join(fields.values())}
        if self.v2:
            params["$format"] = "json"
        if filter_expr:
            params["$filter"] = filter_expr
        out = []
        for raw in self._get(spec["entity_set"], params):
            row = {ours: _odata_value(raw.get(theirs)) for ours, theirs in fields.items()}
            for key, table in (spec.get("value_maps") or {}).items():
                if row.get(key) is not None:
                    row[key] = table.get(value_key(row[key]), row[key])
            out.append(row)
        return out

    def list_units(self) -> list[Unit]:
        with self._lock:
            if self._cache and time.time() - self._cache[0] < self.CACHE_SECONDS:
                return list(self._cache[1])
            units = build_units(self._rows("events", self._window_filter("events")),
                                self._rows("defects", self._window_filter("defects")), self._rows("units"))
            self._cache = (time.time(), units)
            return list(units)

    def get_unit(self, serial: str) -> Unit:
        spec = self.mapping.get("events")
        if not spec:
            raise DataSourceUnavailable("Mapeo OData incompleto: falta la sección 'events'.", code="ODATA_MAPPING")
        safe = serial.replace("'", "''")
        field = spec["fields"]["serial"]
        units = build_units(self._rows("events", f"{field} eq '{safe}'"),
                            self._rows("defects", f"{self.mapping['defects']['fields']['serial']} eq '{safe}'")
                            if self.mapping.get("defects") else [],
                            self._rows("units", f"{self.mapping['units']['fields']['serial']} eq '{safe}'")
                            if self.mapping.get("units") else [])
        if not units:
            raise NotFound(f"Serial '{serial}' no encontrado vía OData.")
        return units[0]

    def work_orders(self) -> list[WorkOrder]:
        return _work_orders_from_units(self.list_units())


_V2_DATE = re.compile(r"^/Date\((-?\d+)([+-]\d{4})?\)/$")


def value_key(v: Any) -> str:
    """Clave textual estable para mapas de valores (booleanos en minúsculas, como JSON)."""
    if isinstance(v, bool):
        return "true" if v else "false"
    return str(v)


def _odata_value(v: Any) -> Any:
    """Normaliza valores OData v2 (/Date(ms)/) y objetos anidados a texto."""
    if isinstance(v, str):
        m = _V2_DATE.match(v)
        if m:
            return datetime.fromtimestamp(int(m.group(1)) / 1000, tz=timezone.utc).isoformat()
        return v
    if isinstance(v, dict):
        return v.get("value") if "value" in v else json.dumps(v, default=str)[:200]
    return v


def preview_mapping(connector: ODataConnector, mapping: dict, top: int = 50) -> dict:
    """Prueba un mapeo contra OData con pocas filas y devuelve un diagnóstico
    de calidad: filas leídas, fechas no interpretables, valores de resultado /
    operación no reconocidos (candidatos a value_maps) y unidades construidas."""
    src = ODataDataSource(connector, mapping)
    report: dict[str, Any] = {"sections": {}, "warnings": [], "units_preview": []}
    rows_by_section: dict[str, list[dict]] = {}
    for section in ("events", "defects", "units"):
        if not mapping.get(section):
            continue
        rows = src._rows(section, top=max(5, min(top, 200)))
        rows_by_section[section] = rows
        info: dict[str, Any] = {"rows": len(rows), "unmapped_values": {}}
        if not rows:
            report["warnings"].append(f"'{section}': el EntitySet no devolvió filas (vacío, filtrado o $select rechazado).")
        if "ts" in mapping[section]["fields"] and rows:
            bad = 0
            for r in rows:
                try:
                    _parse_ts(str(r.get("ts") or ""))
                except ValueError:
                    bad += 1
            info["unparsable_timestamps"] = bad
            if bad:
                report["warnings"].append(f"'{section}': {bad} de {len(rows)} fechas no se pudieron interpretar "
                                          f"(se esperan ISO-8601 o /Date(ms)/ de OData v2).")
        for key, allowed in MAPPING_SCHEMA[section]["value_maps"].items():
            if key in mapping[section]["fields"] and rows:
                seen = sorted({value_key(r.get(key)) for r in rows if r.get(key) is not None})
                unknown = [v for v in seen if v.upper() not in allowed]
                info["unmapped_values"][key] = {"seen": seen[:40], "unknown": unknown[:40], "allowed": allowed}
                if unknown:
                    report["warnings"].append(f"'{section}.{key}': valores no reconocidos {unknown[:8]}; "
                                              f"asígnelos en el mapa de valores ({', '.join(allowed)}).")
        report["sections"][section] = info
    units = build_units(rows_by_section.get("events", []), rows_by_section.get("defects"), rows_by_section.get("units"))
    report["units_built"] = len(units)
    report["units_preview"] = [u.summary() for u in units[:10]]
    if mapping.get("events") and rows_by_section.get("events") and not units:
        report["warnings"].append("No se pudo construir ninguna unidad: revise que 'serial' y 'ts' apunten a propiedades con datos.")
    report["ok"] = bool(units) and not report["warnings"]
    return report


def validate_odata_mapping(mapping: Any) -> list[str]:
    errors = []
    if not isinstance(mapping, dict):
        return ["El mapeo debe ser un objeto JSON."]
    if not mapping.get("verified"):
        errors.append("El mapeo no está marcado como verificado ('verified': true) por el responsable del sistema.")
    ev = mapping.get("events")
    if not isinstance(ev, dict) or not ev.get("entity_set"):
        errors.append("Falta 'events.entity_set'.")
    else:
        for f in ("serial", "ts", "station", "result"):
            if f not in (ev.get("fields") or {}):
                errors.append(f"Falta el campo obligatorio events.fields.{f}.")
    return errors


def odata_mapping_path(config_dir: Path, name: str) -> Path:
    return config_dir / name
