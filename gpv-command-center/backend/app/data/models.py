"""Modelo de dominio de trazabilidad, independiente de la fuente de datos."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any

RESULTS = ("PASS", "FAIL", "HOLD", "INFO")
OPERATIONS = ("START", "COMPLETE", "TEST", "DEFECT", "REPAIR", "HOLD", "RELEASE", "PACK", "SCRAP")
UNIT_STATUSES = ("IN_PROCESS", "HOLD", "IN_REPAIR", "COMPLETE", "PACKED", "SCRAPPED")
REPAIR_STATIONS = {"DEBUG", "REPAIR"}
TEST_STATIONS = {"AOI", "ICT", "FCT", "FINAL_TEST"}


@dataclass
class Event:
    id: str
    serial: str
    ts: datetime
    station: str
    operation: str
    result: str
    operator: str = ""
    line: str = ""
    area: str = ""
    work_order: str = ""
    details: str = ""

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["ts"] = self.ts.isoformat()
        return d


@dataclass
class Defect:
    id: str
    serial: str
    ts: datetime
    station: str
    code: str
    description: str
    symptom: str = ""
    ref_designator: str = ""
    status: str = "OPEN"  # OPEN | REPAIRED | VERIFIED
    repair_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["ts"] = self.ts.isoformat()
        return d


@dataclass
class Repair:
    id: str
    serial: str
    ts: datetime
    defect_id: str | None
    station: str
    action: str
    operator: str = ""

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["ts"] = self.ts.isoformat()
        return d


@dataclass
class Component:
    ref_designator: str
    part_number: str
    description: str = ""
    lot: str = ""
    reel_id: str = ""


@dataclass
class Unit:
    serial: str
    work_order: str
    assembly: str
    revision: str
    batch: str
    line: str
    area: str
    panel_id: str | None
    panel_position: int | None
    # Estado REPORTADO por la fuente (lo que dice el MES).
    status: str
    current_station: str | None
    route: list[str]
    route_inferred: bool = False
    events: list[Event] = field(default_factory=list)
    defects: list[Defect] = field(default_factory=list)
    repairs: list[Repair] = field(default_factory=list)
    components: list[Component] = field(default_factory=list)
    version: int = 1
    # Indica si el último completado reportado difiere del derivado (para diagnóstico).
    reported_last_completed: str | None = None

    # ---- derivados a partir del historial (hechos verificables) ----
    @property
    def sorted_events(self) -> list[Event]:
        return sorted(self.events, key=lambda e: (e.ts, e.id))

    @property
    def last_completed_station(self) -> str | None:
        for e in reversed(self.sorted_events):
            if e.operation in ("COMPLETE", "TEST", "PACK") and e.result == "PASS" and e.station not in REPAIR_STATIONS:
                return e.station
        return None

    @property
    def last_result(self) -> str | None:
        for e in reversed(self.sorted_events):
            if e.result in ("PASS", "FAIL", "HOLD"):
                return e.result
        return None

    @property
    def open_defects(self) -> list[Defect]:
        return [d for d in self.defects if d.status == "OPEN"]

    def summary(self) -> dict[str, Any]:
        last = self.sorted_events[-1] if self.events else None
        return {
            "serial": self.serial,
            "work_order": self.work_order,
            "assembly": self.assembly,
            "revision": self.revision,
            "batch": self.batch,
            "line": self.line,
            "area": self.area,
            "panel_id": self.panel_id,
            "status": self.status,
            "current_station": self.current_station,
            "last_completed_station": self.last_completed_station,
            "last_result": self.last_result,
            "open_defects": len(self.open_defects),
            "last_activity": last.ts.isoformat() if last else None,
        }

    def detail(self) -> dict[str, Any]:
        events = self.sorted_events
        return {
            **self.summary(),
            "panel_position": self.panel_position,
            "route": self.route,
            "route_inferred": self.route_inferred,
            "version": self.version,
            "events": [e.to_dict() for e in events],
            "scan_history": [e.to_dict() for e in events if e.operation in ("START", "COMPLETE", "PACK")],
            "defects": [d.to_dict() for d in sorted(self.defects, key=lambda d: d.ts)],
            "repairs": [r.to_dict() for r in sorted(self.repairs, key=lambda r: r.ts)],
            "symptoms": sorted({d.symptom for d in self.defects if d.symptom}),
            "components": [asdict(c) for c in self.components],
            "station_flow": station_flow(self),
        }


@dataclass
class WorkOrder:
    number: str
    assembly: str
    revision: str
    quantity: int
    line: str
    status: str  # ACTIVE | RELEASED | CLOSED
    batch: str
    started_at: datetime | None = None

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["started_at"] = self.started_at.isoformat() if self.started_at else None
        return d


def station_flow(unit: Unit) -> list[dict[str, Any]]:
    """Estado por estación de la ruta para el diagrama de flujo.

    Cada nodo reporta visitas, resultado más reciente y si es la estación actual.
    Incluye estaciones fuera de ruta (p.ej. DEBUG) como nodos laterales.
    """
    events = unit.sorted_events
    stations = list(unit.route)
    for e in events:
        if e.station not in stations:
            stations.append(e.station)
    flow = []
    for st in stations:
        st_events = [e for e in events if e.station == st]
        visits = sum(1 for e in st_events if e.operation == "START") or (1 if st_events else 0)
        last = st_events[-1] if st_events else None
        if unit.current_station == st and unit.status not in ("COMPLETE", "PACKED"):
            state = "CURRENT" if unit.status not in ("HOLD",) else "HOLD"
        elif last is None:
            state = "PENDING"
        elif last.result == "FAIL":
            state = "FAIL"
        elif last.result == "HOLD":
            state = "HOLD"
        else:
            state = "DONE"
        flow.append({
            "station": st,
            "in_route": st in unit.route,
            "state": state,
            "visits": visits,
            "fails": sum(1 for e in st_events if e.result == "FAIL" and e.operation == "TEST"),
            "last_ts": last.ts.isoformat() if last else None,
            "last_result": last.result if last else None,
        })
    return flow
