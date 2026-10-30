"""Fuentes de datos externas (sólo lectura): archivos auxiliares y OData mapeado.

Ninguna de estas fuentes genera datos: si la información no existe o la
conexión falla, se propaga un error explícito.
"""
from __future__ import annotations

import csv
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx

from ..connectors.base import diagnose_http
from ..connectors.factorylogix import ODataConnector
from ..core.errors import DataSourceUnavailable, NotFound
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
            events.append(Event(id=str(r.get("id") or f"{serial}-{i}"), serial=serial, ts=ts,
                                station=str(r.get("station") or "").upper(),
                                operation=str(r.get("operation") or "COMPLETE").upper(),
                                result=str(r.get("result") or "INFO").upper(), operator=str(r.get("operator") or ""),
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
        payload = resp.json()
        return payload.get("value", payload if isinstance(payload, list) else [])

    def _rows(self, section: str, filter_expr: str | None = None) -> list[dict]:
        spec = self.mapping.get(section)
        if not spec:
            return []
        fields: dict[str, str] = spec["fields"]
        params = {"$top": str(self.max_rows), "$select": ",".join(fields.values())}
        if filter_expr:
            params["$filter"] = filter_expr
        out = []
        for raw in self._get(spec["entity_set"], params):
            row = {ours: raw.get(theirs) for ours, theirs in fields.items()}
            for key, table in (spec.get("value_maps") or {}).items():
                if row.get(key) is not None:
                    row[key] = table.get(str(row[key]), row[key])
            out.append(row)
        return out

    def list_units(self) -> list[Unit]:
        with self._lock:
            if self._cache and time.time() - self._cache[0] < self.CACHE_SECONDS:
                return list(self._cache[1])
            units = build_units(self._rows("events"), self._rows("defects"), self._rows("units"))
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
