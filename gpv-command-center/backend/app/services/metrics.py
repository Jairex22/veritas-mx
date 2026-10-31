"""Production Intelligence: KPIs con definición formal y fuente de datos.

Si la fuente no está disponible, la capa API devuelve el error; aquí nunca
se rellenan valores ausentes.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from statistics import median
from typing import Any

from ..data.models import Unit, WorkOrder

DEFINITIONS = {
    "units_processed": "Seriales distintos con al menos un evento PASS de COMPLETE/TEST/PACK dentro de la ventana.",
    "units_packed": "Seriales con evento PACK PASS dentro de la ventana.",
    "fpy": "First Pass Yield por estación con eventos TEST = unidades cuyo PRIMER resultado de prueba en la estación (dentro de la ventana) fue PASS ÷ unidades probadas por primera vez en la ventana.",
    "rty": "Rolled Throughput Yield = producto de FPY de las estaciones de prueba con datos.",
    "failure_rate": "Eventos TEST con resultado FAIL ÷ total de eventos TEST en la ventana.",
    "rework_rate": "Seriales con ≥1 reparación registrada en la ventana ÷ seriales con actividad de cierre (PASS) o reparación en la ventana.",
    "wip": "Seriales cuyo estado reportado es IN_PROCESS, IN_REPAIR o HOLD (instantáneo, sin ventana), agrupados por estación actual.",
    "station_time": "Mediana de minutos entre el evento START de una estación y su evento PASS/FAIL de cierre (COMPLETE/TEST/PACK), por estación.",
    "top_defects": "Conteo de defectos registrados por código dentro de la ventana.",
    "active_orders": "Órdenes de trabajo con estado ACTIVE en la fuente.",
    "trend": "Seriales con evento PACK PASS (unidades empacadas) por hora dentro de la ventana.",
}


def compute_metrics(units: list[Unit], work_orders: list[WorkOrder], window_hours: int,
                    provenance: dict[str, Any], now: datetime | None = None) -> dict[str, Any]:
    now = now or datetime.now(timezone.utc)
    since = now - timedelta(hours=window_hours)
    closing_ops = ("COMPLETE", "TEST", "PACK")

    processed, packed, reworked = set(), set(), set()
    test_events = fail_events = 0
    first_attempts: dict[str, dict[str, str]] = defaultdict(dict)  # station -> serial -> result
    station_durations: dict[str, list[float]] = defaultdict(list)
    defects = Counter()
    trend = Counter()

    for u in units:
        events = u.sorted_events
        open_start: dict[str, datetime] = {}
        for e in events:
            if e.operation == "START":
                open_start[e.station] = e.ts
            if e.ts < since:
                continue
            if e.operation in closing_ops and e.result == "PASS":
                processed.add(u.serial)
            if e.operation == "PACK" and e.result == "PASS":
                packed.add(u.serial)
                trend[e.ts.replace(minute=0, second=0, microsecond=0).isoformat()] += 1
            if e.operation == "TEST":
                test_events += 1
                fail_events += e.result == "FAIL"
                if u.serial not in first_attempts[e.station]:
                    first_attempts[e.station][u.serial] = e.result
            if e.operation in closing_ops and e.result in ("PASS", "FAIL") and e.station in open_start:
                station_durations[e.station].append((e.ts - open_start.pop(e.station)).total_seconds() / 60)
            if e.operation == "REPAIR":
                reworked.add(u.serial)
        for d in u.defects:
            if d.ts >= since:
                defects[(d.code, d.description)] += 1

    fpy = {}
    for st in sorted(first_attempts):
        attempts = first_attempts[st]
        if attempts:
            fpy[st] = {"tested": len(attempts), "first_pass": sum(1 for r in attempts.values() if r == "PASS"),
                       "value": round(sum(1 for r in attempts.values() if r == "PASS") / len(attempts), 4)}
    rty = None
    if fpy:
        rty = 1.0
        for v in fpy.values():
            rty *= v["value"]
        rty = round(rty, 4)

    wip_by_station = Counter(u.current_station or "-" for u in units if u.status in ("IN_PROCESS", "IN_REPAIR", "HOLD"))
    status_counts = Counter(u.status for u in units)

    hours = []
    cursor = since.replace(minute=0, second=0, microsecond=0)
    while cursor <= now:
        hours.append({"hour": cursor.isoformat(), "units": trend.get(cursor.isoformat(), 0)})
        cursor += timedelta(hours=1)

    def ratio(a: int, b: int) -> float | None:
        return round(a / b, 4) if b else None

    return {
        "window_hours": window_hours,
        "generated_at": now.isoformat(timespec="seconds"),
        "source": provenance,
        "definitions": DEFINITIONS,
        "kpis": {
            "units_processed": {"value": len(processed), "unit": "unidades"},
            "units_packed": {"value": len(packed), "unit": "unidades"},
            "rty": {"value": rty, "unit": "ratio"},
            "failure_rate": {"value": ratio(fail_events, test_events), "unit": "ratio",
                             "numerator": fail_events, "denominator": test_events},
            "rework_rate": {"value": ratio(len(reworked), len(processed | reworked)), "unit": "ratio",
                            "numerator": len(reworked), "denominator": len(processed | reworked)},
            "wip": {"value": sum(wip_by_station.values()), "unit": "unidades"},
            "active_orders": {"value": sum(1 for w in work_orders if w.status == "ACTIVE"), "unit": "órdenes"},
        },
        "fpy": fpy,
        "wip_by_station": dict(wip_by_station.most_common()),
        "status_counts": dict(status_counts),
        "station_time_min": {st: {"median": round(median(v), 1), "samples": len(v)}
                             for st, v in sorted(station_durations.items()) if v},
        "top_defects": [{"code": c, "description": d, "count": n} for (c, d), n in defects.most_common(8)],
        "trend": hours,
        "work_orders": [w.to_dict() for w in work_orders],
    }
