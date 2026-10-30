"""Fuente de datos DEMO: información 100 % sintética y determinista.

Todos los identificadores llevan el prefijo DEMO para que nunca puedan
confundirse con datos reales de FactoryLogix. Las mutaciones (operaciones
simuladas) sólo afectan a esta estructura en memoria.
"""
from __future__ import annotations

import random
import threading
from datetime import datetime, timedelta, timezone
from typing import Any

from ..core.errors import Conflict, NotFound, ValidationFailed
from .models import Component, Defect, Event, Repair, Unit, WorkOrder
from .source import ProductionDataSource

ROUTE = ["SMT_TOP", "SMT_BOTTOM", "AOI", "ICT", "DEPANEL", "FCT", "FINAL_ASSY", "FINAL_TEST", "PACK"]
PANEL_STATIONS = ["SMT_TOP", "SMT_BOTTOM", "AOI", "ICT"]
AREA_BY_STATION = {
    "SMT_TOP": "SMT", "SMT_BOTTOM": "SMT", "AOI": "SMT", "ICT": "PRUEBAS", "DEPANEL": "SMT",
    "FCT": "PRUEBAS", "FINAL_ASSY": "ENSAMBLE", "FINAL_TEST": "PRUEBAS", "PACK": "EMPAQUE", "DEBUG": "REPARACION",
}
TEST_STATIONS = {"AOI", "ICT", "FCT", "FINAL_TEST"}
DEFECT_CATALOG = {
    "AOI": [("SOL-BRIDGE", "Puente de soldadura", "Corto visible entre pines"), ("MISSING", "Componente faltante", "Pad sin componente")],
    "ICT": [("ICT-OPEN", "Circuito abierto", "Medición fuera de rango"), ("ICT-SHORT", "Corto en red", "Resistencia < umbral")],
    "FCT": [("FCT-V12", "Riel 12V fuera de tolerancia", "Voltaje 11.2V"), ("FCT-COMM", "Falla de comunicación CAN", "Timeout de bus")],
    "FINAL_TEST": [("FT-LEAK", "Corriente de fuga", "Fuga > 2mA"), ("FT-FW", "Versión de firmware incorrecta", "FW 2.3 esperado 2.4")],
}
REPAIR_ACTIONS = ["Retrabajo de soldadura", "Reemplazo de componente", "Reflujo localizado", "Reprogramación de firmware"]
COMPONENTS = {
    "PCBA-CTRL-7700": [("U1", "MCU-STM32F4-DEMO", "Microcontrolador"), ("U12", "PMIC-TPS-DEMO", "Regulador"),
                       ("C45", "CAP-10UF-DEMO", "Capacitor 10uF"), ("J3", "CONN-CAN-DEMO", "Conector CAN")],
    "PCBA-PWR-3100": [("Q1", "MOSFET-60V-DEMO", "MOSFET"), ("T1", "XFMR-DEMO", "Transformador"),
                      ("U3", "CTRL-PWM-DEMO", "Controlador PWM"), ("F1", "FUSE-5A-DEMO", "Fusible")],
    "PCBA-SENS-1200": [("U2", "ADC-24B-DEMO", "ADC"), ("U5", "SENSOR-T-DEMO", "Sensor temperatura")],
}


class _Builder:
    def __init__(self, rng: random.Random):
        self.rng = rng
        self.ev = 0
        self.df = 0
        self.rp = 0

    def event(self, unit: Unit, ts: datetime, station: str, operation: str, result: str, details: str = "") -> Event:
        self.ev += 1
        e = Event(id=f"EV-DEMO-{self.ev:06d}", serial=unit.serial, ts=ts, station=station, operation=operation,
                  result=result, operator=f"OP-DEMO-{self.rng.randint(1, 8):02d}", line=unit.line,
                  area=AREA_BY_STATION.get(station, ""), work_order=unit.work_order, details=details)
        unit.events.append(e)
        return e

    def defect(self, unit: Unit, ts: datetime, station: str, idx: int | None = None, status: str = "OPEN") -> Defect:
        self.df += 1
        options = DEFECT_CATALOG.get(station, DEFECT_CATALOG["FCT"])
        code, desc, symptom = options[idx if idx is not None else self.rng.randrange(len(options))]
        d = Defect(id=f"DF-DEMO-{self.df:05d}", serial=unit.serial, ts=ts, station=station, code=code,
                   description=desc, symptom=symptom, ref_designator=self.rng.choice([c.ref_designator for c in unit.components] or ["-"]),
                   status=status)
        unit.defects.append(d)
        self.event(unit, ts, station, "DEFECT", "FAIL", f"{code}: {desc}")
        return d

    def repair(self, unit: Unit, ts: datetime, defect: Defect | None, action: str | None = None) -> Repair:
        self.rp += 1
        r = Repair(id=f"RP-DEMO-{self.rp:05d}", serial=unit.serial, ts=ts, defect_id=defect.id if defect else None,
                   station="DEBUG", action=action or self.rng.choice(REPAIR_ACTIONS), operator=f"TEC-DEMO-{self.rng.randint(1, 4):02d}")
        unit.repairs.append(r)
        if defect:
            defect.status = "REPAIRED"
            defect.repair_id = r.id
        self.event(unit, ts, "DEBUG", "REPAIR", "PASS", r.action)
        return r


def _components(rng: random.Random, assembly: str) -> list[Component]:
    return [Component(ref, pn, desc, lot=f"LOT-DEMO-{rng.randint(1000, 9999)}", reel_id=f"REEL-DEMO-{rng.randint(10000, 99999)}")
            for ref, pn, desc in COMPONENTS.get(assembly, [])]


def generate_demo_dataset(now: datetime | None = None, seed: int = 7700) -> tuple[list[Unit], list[WorkOrder], dict[str, dict]]:
    now = now or datetime.now(timezone.utc)
    rng = random.Random(seed)
    b = _Builder(rng)
    wos = [
        WorkOrder("WO-DEMO-24101", "PCBA-CTRL-7700", "C", 48, "SMT-L1", "ACTIVE", "B-DEMO-0912", now - timedelta(hours=30)),
        WorkOrder("WO-DEMO-24102", "PCBA-PWR-3100", "B", 40, "SMT-L2", "ACTIVE", "B-DEMO-0913", now - timedelta(hours=11)),
        WorkOrder("WO-DEMO-24103", "PCBA-SENS-1200", "A", 32, "SMT-L1", "ACTIVE", "B-DEMO-0915", now - timedelta(hours=4)),
        WorkOrder("WO-DEMO-24099", "PCBA-CTRL-7700", "B", 24, "SMT-L1", "CLOSED", "B-DEMO-0901", now - timedelta(hours=70)),
    ]
    units: list[Unit] = []

    def new_unit(serial: str, wo: WorkOrder, panel_id: str | None, pos: int | None) -> Unit:
        u = Unit(serial=serial, work_order=wo.number, assembly=wo.assembly, revision=wo.revision, batch=wo.batch,
                 line=wo.line, area="SMT", panel_id=panel_id, panel_position=pos, status="IN_PROCESS",
                 current_station=ROUTE[0], route=list(ROUTE))
        u.components = _components(rng, wo.assembly)
        units.append(u)
        return u

    # ---------------- Unidades normales (incluye retrabajos resueltos con evidencia) ----------------
    seq = 0
    for wo in wos:
        n_panels = {"WO-DEMO-24101": 8, "WO-DEMO-24102": 7, "WO-DEMO-24103": 6, "WO-DEMO-24099": 6}[wo.number]
        for p in range(n_panels):
            panel_id = f"PNL-DEMO-{wo.number[-5:]}-{p + 1:02d}"
            panel_units = []
            for pos in range(1, 5):
                seq += 1
                panel_units.append(new_unit(f"DEMO-GPV-{seq:06d}", wo, panel_id, pos))
            t = wo.started_at + timedelta(minutes=50 * p)
            for u in panel_units:
                _run_unit(b, rng, u, t, now, panel_units)

    # ---------------- Escenarios guionizados para el motor de diagnóstico ----------------
    wo1, wo2 = wos[0], wos[1]
    h = lambda hours: now - timedelta(hours=hours)  # noqa: E731

    def walk(u: Unit, stations: list[str], start: datetime, step_min: int = 20) -> datetime:
        t = start
        for st in stations:
            b.event(u, t, st, "START", "INFO")
            t += timedelta(minutes=step_min)
            b.event(u, t, st, "TEST" if st in TEST_STATIONS else "COMPLETE", "PASS")
            t += timedelta(minutes=5)
        return t

    # S1: bucle FCT <-> DEBUG (3 fallas consecutivas)
    u = new_unit("DEMO-GPV-L00001", wo1, None, None)
    t = walk(u, ROUTE[:5], h(26))
    for i in range(3):
        b.event(u, t, "FCT", "START", "INFO"); t += timedelta(minutes=15)
        b.event(u, t, "FCT", "TEST", "FAIL", "Riel 12V = 11.2V"); d = b.defect(u, t, "FCT", 0)
        t += timedelta(minutes=30); b.event(u, t, "DEBUG", "START", "INFO")
        if i < 2:
            t += timedelta(minutes=50); b.repair(u, t, d, ["Reflujo localizado U12", "Reemplazo de componente C45"][i])
            t += timedelta(minutes=20)
    u.status, u.current_station = "IN_REPAIR", "DEBUG"

    # S2: atrapado en reparación > 30 h sin acción registrada
    u = new_unit("DEMO-GPV-R00002", wo1, None, None)
    t = walk(u, ROUTE[:7], h(36))
    b.event(u, h(31), "FINAL_TEST", "START", "INFO")
    b.event(u, h(31) + timedelta(minutes=10), "FINAL_TEST", "TEST", "FAIL", "Fuga 3.1mA")
    b.defect(u, h(31) + timedelta(minutes=10), "FINAL_TEST", 0)
    b.event(u, h(30), "DEBUG", "START", "INFO")
    u.status, u.current_station = "IN_REPAIR", "DEBUG"

    # S3: defecto reparado y verificado, pero HOLD pendiente sin liberar
    u = new_unit("DEMO-GPV-H00003", wo2, None, None)
    t = walk(u, ROUTE[:5], h(18))
    b.event(u, t, "FCT", "START", "INFO"); t += timedelta(minutes=10)
    b.event(u, t, "FCT", "TEST", "FAIL"); d = b.defect(u, t, "FCT", 1)
    t += timedelta(minutes=20); b.event(u, t, "DEBUG", "START", "INFO")
    t += timedelta(minutes=40); b.repair(u, t, d, "Reemplazo de transceptor CAN")
    t += timedelta(minutes=20); b.event(u, t, "FCT", "START", "INFO"); t += timedelta(minutes=10)
    b.event(u, t, "FCT", "TEST", "PASS"); d.status = "VERIFIED"
    t += timedelta(minutes=5); b.event(u, t, "FCT", "HOLD", "HOLD", "Contención de calidad: lote de transceptor bajo revisión")
    u.status, u.current_station = "HOLD", "FINAL_ASSY"

    # S4: panel con unidades PASS y FAIL, bloqueado antes de DEPANEL
    for pos in range(1, 5):
        u = new_unit(f"DEMO-GPV-M0000{pos}", wo1, "PNL-DEMO-MIX-04", pos)
        t = walk(u, ROUTE[:3], h(12))
        b.event(u, t, "ICT", "START", "INFO"); t += timedelta(minutes=12)
        if pos == 3:
            b.event(u, t, "ICT", "TEST", "FAIL", "Red VCC_3V3 abierta"); b.defect(u, t, "ICT", 0)
            b.event(u, t + timedelta(minutes=30), "DEBUG", "START", "INFO")
            u.status, u.current_station = "IN_REPAIR", "DEBUG"
        else:
            b.event(u, t, "ICT", "TEST", "PASS")
            u.status, u.current_station = "IN_PROCESS", "DEPANEL"

    # S5: regresa repetidamente a FINAL_TEST
    u = new_unit("DEMO-GPV-A00005", wo2, None, None)
    t = walk(u, ROUTE[:7], h(16))
    for i in range(3):
        b.event(u, t, "FINAL_TEST", "START", "INFO"); t += timedelta(minutes=10)
        if i < 2:
            b.event(u, t, "FINAL_TEST", "TEST", "FAIL"); d = b.defect(u, t, "FINAL_TEST", 1)
            t += timedelta(minutes=15); b.event(u, t, "DEBUG", "START", "INFO")
            t += timedelta(minutes=25); b.repair(u, t, d, "Reprogramación de firmware")
            t += timedelta(minutes=10)
        else:
            b.event(u, t, "FINAL_TEST", "TEST", "PASS")
            for df in u.defects:
                df.status = "VERIFIED"
    u.status, u.current_station = "IN_PROCESS", "PACK"

    # S6: estado reportado PACKED pero la última prueba fue FAIL y no hay evento PACK
    u = new_unit("DEMO-GPV-I00006", wo1, None, None)
    t = walk(u, ROUTE[:7], h(22))
    b.event(u, t, "FINAL_TEST", "START", "INFO")
    b.event(u, t + timedelta(minutes=10), "FINAL_TEST", "TEST", "FAIL", "Corriente fuera de límite")
    u.status, u.current_station = "PACKED", None

    # S7: estación FCT omitida: reportado en FINAL_ASSY sin FCT PASS
    u = new_unit("DEMO-GPV-I00007", wo2, None, None)
    t = walk(u, ["SMT_TOP", "SMT_BOTTOM", "AOI", "ICT", "DEPANEL"], h(14))
    walk(u, ["FINAL_ASSY"], t + timedelta(minutes=30))
    u.status, u.current_station = "IN_PROCESS", "FINAL_TEST"
    u.reported_last_completed = "FCT"

    # S8: defecto declarado VERIFIED sin reparación ni re-prueba registradas
    u = new_unit("DEMO-GPV-V00008", wo1, None, None)
    t = walk(u, ROUTE[:5], h(10))
    b.event(u, t, "FCT", "START", "INFO")
    b.event(u, t + timedelta(minutes=10), "FCT", "TEST", "FAIL")
    d = b.defect(u, t + timedelta(minutes=10), "FCT", 0)
    d.status = "VERIFIED"
    u.status, u.current_station = "IN_PROCESS", "FINAL_ASSY"

    for u in units:
        if u.status in ("IN_PROCESS", "IN_REPAIR", "HOLD") and u.current_station:
            u.area = AREA_BY_STATION.get(u.current_station, u.area)
        elif u.status in ("PACKED", "COMPLETE"):
            u.area = "EMPAQUE"

    boxes = {}
    for wo in wos:
        if wo.status == "ACTIVE":
            for i in range(1, 3):
                box_id = f"BOX-DEMO-{wo.number[-5:]}-{i:02d}"
                boxes[box_id] = {"box_id": box_id, "work_order": wo.number, "assembly": wo.assembly,
                                 "revision": wo.revision, "capacity": 6, "serials": [], "status": "OPEN"}
    return units, wos, boxes


def _run_unit(b: _Builder, rng: random.Random, u: Unit, start: datetime, now: datetime, panel: list[Unit]) -> None:
    """Simula el avance de una unidad hasta `now` con fallas ocasionales reparadas."""
    t = start + timedelta(minutes=rng.randint(0, 3))
    for st in ROUTE:
        if t >= now:
            u.status, u.current_station = "IN_PROCESS", st
            return
        b.event(u, t, st, "START", "INFO")
        t += timedelta(minutes=rng.randint(8, 30))
        if t >= now:
            u.status, u.current_station = "IN_PROCESS", st
            return
        if st in TEST_STATIONS and rng.random() < 0.07:
            b.event(u, t, st, "TEST", "FAIL")
            d = b.defect(u, t, st)
            t += timedelta(minutes=rng.randint(10, 40))
            b.event(u, t, "DEBUG", "START", "INFO")
            t += timedelta(minutes=rng.randint(20, 90))
            if t >= now:
                u.status, u.current_station = "IN_REPAIR", "DEBUG"
                return
            b.repair(u, t, d)
            t += timedelta(minutes=rng.randint(5, 20))
            b.event(u, t, st, "START", "INFO")
            t += timedelta(minutes=rng.randint(8, 20))
            if t >= now:
                u.status, u.current_station = "IN_PROCESS", st
                return
            d.status = "VERIFIED"
        if st == "PACK":
            b.event(u, t, st, "PACK", "PASS", f"Caja BOX-DEMO-{u.work_order[-5:]}-H{rng.randint(1, 9)}")
        else:
            b.event(u, t, st, "TEST" if st in TEST_STATIONS else "COMPLETE", "PASS")
        t += timedelta(minutes=rng.randint(10, 55))
    u.status, u.current_station = "PACKED", None


class DemoDataSource(ProductionDataSource):
    kind = "DEMO"
    label = "Datos sintéticos DEMO"
    synthetic = True

    def __init__(self, now: datetime | None = None, seed: int = 7700):
        self._lock = threading.RLock()
        self._seed = seed
        self._fixed_now = now
        self.reset()

    def reset(self) -> None:
        with self._lock:
            self._units, self._wos, self._boxes = generate_demo_dataset(self._fixed_now, self._seed)
            self._index = {u.serial.lower(): u for u in self._units}
            self._mut = 0

    def list_units(self) -> list[Unit]:
        with self._lock:
            return list(self._units)

    def work_orders(self) -> list[WorkOrder]:
        return list(self._wos)

    def get_unit(self, serial: str) -> Unit:
        u = self._index.get(serial.lower())
        if not u:
            raise NotFound(f"Serial '{serial}' no encontrado en datos DEMO.")
        return u

    def find_box(self, box_id: str) -> dict[str, Any]:
        box = self._boxes.get(box_id.upper())
        if not box:
            raise NotFound(f"Caja '{box_id}' no encontrada en datos DEMO.")
        return dict(box, serials=list(box["serials"]))

    # ------------------------------------------------------------------
    # Mutaciones SIMULADAS. Sólo modifican memoria del proceso DEMO.
    # ------------------------------------------------------------------
    @property
    def lock(self) -> threading.RLock:
        return self._lock

    def _event(self, u: Unit, station: str, operation: str, result: str, operator: str, details: str = "") -> Event:
        self._mut += 1
        e = Event(id=f"EV-DEMO-SIM-{self._mut:05d}", serial=u.serial, ts=datetime.now(timezone.utc), station=station,
                  operation=operation, result=result, operator=operator, line=u.line,
                  area=AREA_BY_STATION.get(station, ""), work_order=u.work_order, details=details)
        u.events.append(e)
        return e

    def _next_station(self, u: Unit, station: str) -> str | None:
        if station in u.route:
            i = u.route.index(station)
            return u.route[i + 1] if i + 1 < len(u.route) else None
        return None

    def sim_register_event(self, u: Unit, station: str, note: str, operator: str) -> dict:
        e = self._event(u, station, "START", "INFO", operator, note)
        u.version += 1
        return {"event_id": e.id}

    def sim_record_test(self, u: Unit, station: str, result: str, operator: str, note: str = "") -> dict:
        e = self._event(u, station, "TEST", result, operator, note)
        if result == "PASS":
            for d in u.defects:
                if d.station == station and d.status == "REPAIRED":
                    d.status = "VERIFIED"
            u.current_station = self._next_station(u, station)
            u.status = "IN_PROCESS"
        else:
            u.current_station = station
        u.version += 1
        return {"event_id": e.id}

    def sim_record_defect(self, u: Unit, station: str, code: str, description: str, symptom: str, ref: str, operator: str) -> dict:
        self._mut += 1
        d = Defect(id=f"DF-DEMO-SIM-{self._mut:05d}", serial=u.serial, ts=datetime.now(timezone.utc), station=station,
                   code=code, description=description, symptom=symptom, ref_designator=ref, status="OPEN")
        u.defects.append(d)
        self._event(u, station, "DEFECT", "FAIL", operator, f"{code}: {description}")
        self._event(u, "DEBUG", "START", "INFO", operator, "Enviado a reparación")
        u.status, u.current_station = "IN_REPAIR", "DEBUG"
        u.version += 1
        return {"defect_id": d.id}

    def sim_record_repair(self, u: Unit, defect_id: str, action: str, operator: str) -> dict:
        d = next((x for x in u.defects if x.id == defect_id), None)
        if not d:
            raise NotFound(f"Defecto '{defect_id}' no pertenece al serial {u.serial}.")
        if d.status != "OPEN":
            raise Conflict(f"El defecto {defect_id} no está abierto (estado {d.status}).")
        self._mut += 1
        r = Repair(id=f"RP-DEMO-SIM-{self._mut:05d}", serial=u.serial, ts=datetime.now(timezone.utc),
                   defect_id=d.id, station="DEBUG", action=action, operator=operator)
        u.repairs.append(r)
        d.status, d.repair_id = "REPAIRED", r.id
        self._event(u, "DEBUG", "REPAIR", "PASS", operator, action)
        if not u.open_defects:
            # Debe regresar a la estación donde se detectó para re-prueba (no se declara resuelto sin evidencia).
            u.status, u.current_station = "IN_PROCESS", d.station
        u.version += 1
        return {"repair_id": r.id, "retest_station": d.station}

    def sim_place_hold(self, u: Unit, reason: str, operator: str) -> dict:
        e = self._event(u, u.current_station or "-", "HOLD", "HOLD", operator, reason)
        u.status = "HOLD"
        u.version += 1
        return {"event_id": e.id}

    def sim_release_hold(self, u: Unit, reason: str, operator: str) -> dict:
        e = self._event(u, u.current_station or "-", "RELEASE", "INFO", operator, reason)
        u.status = "IN_PROCESS"
        u.version += 1
        return {"event_id": e.id}

    def sim_complete_station(self, u: Unit, station: str, operator: str) -> dict:
        self._event(u, station, "START", "INFO", operator)
        e = self._event(u, station, "COMPLETE", "PASS", operator)
        u.current_station = self._next_station(u, station)
        u.version += 1
        return {"event_id": e.id, "next_station": u.current_station}

    def sim_pack_box(self, box_id: str, units: list[Unit], operator: str) -> dict:
        box = self._boxes.get(box_id.upper())
        if not box:
            raise NotFound(f"Caja '{box_id}' no encontrada.")
        if len(box["serials"]) + len(units) > box["capacity"]:
            raise ValidationFailed("La cantidad excede la capacidad de la caja.")
        for u in units:
            self._event(u, "PACK", "PACK", "PASS", operator, f"Caja {box_id}")
            u.status, u.current_station, u.area = "PACKED", None, "EMPAQUE"
            u.version += 1
            box["serials"].append(u.serial)
        if len(box["serials"]) == box["capacity"]:
            box["status"] = "FULL"
        return {"box_id": box_id, "packed": [u.serial for u in units], "box_count": len(box["serials"])}

    def serial_in_any_box(self, serial: str) -> str | None:
        for box in self._boxes.values():
            if serial in box["serials"]:
                return box["box_id"]
        return None
