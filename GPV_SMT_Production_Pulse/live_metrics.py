"""Monitor metrics computed exclusively from locally stored records (no OData access).

Quantity semantics
------------------
FactoryLogix fields can hold either a quantity *per interval* (each record is the production of
its own period) or a *cumulative counter* (each record is the running total). Summing a
cumulative counter is wrong, and differencing interval amounts is wrong, so every computation
goes through ``increments()``:

* ``interval``   -> increment of a record = its quantity.
* ``cumulative`` -> increment = quantity - previous quantity of the same counter group
  (line/station), a negative difference is treated as a counter reset (increment = new value);
  the first reading of a group has no baseline and is reported as *unknown*, never guessed.
* ``undetermined`` -> no production figure is produced.

The semantics come from ``collector.quantity_semantics`` (``interval``/``cumulative``) or, with
``auto``, from ``detect_semantics()``. Auto-detection is a heuristic and is always labelled as
such so MES can confirm it.

Time references are kept apart: *production time* (timestamp field of each record) versus
*query time* (when the collector read it). FactoryLogix may register data with delay, so the
newest production timestamp is reported together with its age; nothing is called "real time".
"""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any, Iterable

from timeutil import PlantClock

SEMANTICS_LABELS_ES = {
    "interval": "Cantidad por intervalo (cada registro es la producción de su periodo)",
    "cumulative": "Contador acumulado (se calcula la diferencia entre lecturas)",
    "undetermined": "Indeterminada: no se calculan unidades hasta confirmarla",
}
DIMENSION_LABELS_ES = {"line": "Línea", "station": "Estación", "shift": "Turno", "project": "Proyecto",
                       "work_order": "WO", "product": "Producto"}
COUNTER_GROUP = ("line", "station")


def _ts(row: dict[str, Any]) -> datetime:
    return datetime.fromisoformat(row["production_ts"])


def _group_key(row: dict[str, Any], mapping: dict[str, str | None]) -> tuple[Any, ...]:
    return tuple(row.get(dim) if mapping.get(dim) else None for dim in COUNTER_GROUP)


def detect_semantics(rows: list[dict[str, Any]], mapping: dict[str, str | None],
                     min_points: int = 6) -> dict[str, Any]:
    """Heuristic: cumulative counters are (almost) monotonically increasing per group.

    Returns {"semantics", "reason", "groups_evaluated"}. Requires ``min_points`` numeric readings
    in at least one group; groups that disagree make the result undetermined.
    """
    groups: dict[tuple[Any, ...], list[tuple[datetime, float]]] = defaultdict(list)
    for row in rows:
        if row.get("quantity") is not None:
            groups[_group_key(row, mapping)].append((_ts(row), float(row["quantity"])))
    votes: list[str] = []
    for points in groups.values():
        if len(points) < min_points:
            continue
        points.sort()
        values = [v for _, v in points]
        diffs = [b - a for a, b in zip(values, values[1:])]
        if all(d == 0 for d in diffs):
            continue  # constant series carries no information
        non_decreasing = sum(1 for d in diffs if d >= 0) / len(diffs)
        increasing = sum(1 for d in diffs if d > 0) / len(diffs)
        # Interval amounts fluctuate up and down; a counter (almost) never goes down except on resets.
        if non_decreasing >= 0.9 and increasing >= 0.6 and values[-1] > values[0]:
            votes.append("cumulative")
        else:
            votes.append("interval")
    if not votes:
        return {"semantics": "undetermined", "groups_evaluated": 0,
                "reason": f"Datos insuficientes: se requieren al menos {min_points} lecturas con variación por línea/estación."}
    if all(v == votes[0] for v in votes):
        reason = ("Los valores crecen de forma sostenida entre registros consecutivos (patrón de contador)."
                  if votes[0] == "cumulative" else
                  "Los valores suben y bajan entre registros consecutivos (patrón de cantidades por intervalo).")
        return {"semantics": votes[0], "groups_evaluated": len(votes), "reason": reason}
    return {"semantics": "undetermined", "groups_evaluated": len(votes),
            "reason": "Las líneas/estaciones muestran patrones contradictorios; confirmar con MES."}


def resolve_semantics(configured: str, rows: list[dict[str, Any]], mapping: dict[str, str | None]) -> dict[str, Any]:
    if configured in ("interval", "cumulative"):
        return {"semantics": configured, "source": "config",
                "reason": "Definida en config.json (collector.quantity_semantics).", "groups_evaluated": None}
    detected = detect_semantics(rows, mapping)
    detected["source"] = "auto"
    return detected


def increments(rows: list[dict[str, Any]], semantics: str,
               mapping: dict[str, str | None]) -> list[tuple[dict[str, Any], float | None]]:
    """Production attributable to each record (see module docstring). Rows must be time-ordered."""
    if semantics == "interval":
        return [(r, float(r["quantity"]) if r.get("quantity") is not None else None) for r in rows]
    if semantics != "cumulative":
        return [(r, None) for r in rows]
    last: dict[tuple[Any, ...], float] = {}
    out: list[tuple[dict[str, Any], float | None]] = []
    for r in sorted(rows, key=lambda x: (x["production_ts"], x.get("record_key", ""))):
        q = r.get("quantity")
        key = _group_key(r, mapping)
        if q is None:
            out.append((r, None))
            continue
        q = float(q)
        prev = last.get(key)
        inc = None if prev is None else (q - prev if q >= prev else q)  # negative -> counter reset
        last[key] = q
        out.append((r, inc))
    return out


def units_between(incs: Iterable[tuple[dict[str, Any], float | None]], start: datetime, end: datetime) -> dict[str, Any]:
    total = 0.0
    unknown = 0
    count = 0
    for row, inc in incs:
        ts = _ts(row)
        if start <= ts < end:
            count += 1
            if inc is None:
                unknown += 1
            else:
                total += inc
    return {"value": total if count else None, "records": count, "unknown": unknown, "partial": unknown > 0}


def compute_monitor(rows: list[dict[str, Any]], *, mapping: dict[str, str | None], semantics_config: str,
                    clock: PlantClock, now: datetime, recent_minutes: int,
                    runs: list[dict[str, Any]], collector_state: dict[str, Any], unit_label: str = "") -> dict[str, Any]:
    """Build the dashboard payload. ``rows`` should cover [today 00:00 - 24 h, now] for baselines."""
    local_now = clock.to_local(now)
    day_start = clock.day_start(local_now.date())
    qty_field = mapping.get("quantity")
    unit = unit_label.strip() or (f"{qty_field}" if qty_field else "")
    sem = resolve_semantics(semantics_config, rows, mapping) if qty_field else {
        "semantics": "undetermined", "source": "none", "reason": "No hay campo de cantidad confirmado.", "groups_evaluated": None}
    semantics = sem["semantics"]
    sem["label"] = SEMANTICS_LABELS_ES[semantics]
    incs = increments(rows, semantics, mapping) if qty_field else [(r, None) for r in rows]
    today = units_between(incs, day_start, now + timedelta(minutes=1))
    today_rows = [(r, i) for r, i in incs if day_start <= _ts(r) <= now + timedelta(minutes=1)]

    # Per dimension aggregates (only for mapped dimensions)
    dimensions: dict[str, list[dict[str, Any]]] = {}
    for dim in ("line", "project", "work_order", "product", "station", "shift"):
        if not mapping.get(dim):
            continue
        agg: dict[str, dict[str, Any]] = {}
        for row, inc in today_rows:
            name = row.get(dim) or "(sin valor)"
            g = agg.setdefault(name, {"name": name, "units": 0.0, "records": 0, "unknown": 0, "last_ts": None})
            g["records"] += 1
            if inc is None:
                g["unknown"] += 1
            else:
                g["units"] += inc
            g["last_ts"] = max(g["last_ts"] or row["production_ts"], row["production_ts"])
        dimensions[dim] = sorted(agg.values(), key=lambda g: g["name"])

    # Recent activity per line (by production time)
    recent_start = now - timedelta(minutes=recent_minutes)
    line_status: list[dict[str, Any]] = []
    line_values = sorted({r.get("line") for r in rows if r.get("line")}) if mapping.get("line") else []
    for line in line_values:
        line_incs = [(r, i) for r, i in incs if r.get("line") == line]
        recent = units_between(line_incs, recent_start, now + timedelta(minutes=1))
        last_ts = max(r["production_ts"] for r, _ in line_incs)
        day = units_between(line_incs, day_start, now + timedelta(minutes=1))
        active = bool(recent["records"]) and (recent["value"] or 0) > 0
        line_status.append({"line": line, "units_today": day["value"], "partial": day["partial"],
                            "recent_units": recent["value"], "last_production_ts": last_ts,
                            "status": "active" if active else ("syncing" if collector_state.get("catching_up") else "no_recent_data")})

    recent_all = units_between(incs, recent_start, now + timedelta(minutes=1))
    has_recent = bool(recent_all["records"]) and (recent_all["value"] or 0) > 0 if qty_field else bool(recent_all["records"])

    # Data is complete only up to the sync cursor while catching up, otherwise up to the last query.
    catching_up = bool(collector_state.get("catching_up"))
    complete_until = now
    if catching_up and collector_state.get("cursor"):
        complete_until = datetime.fromisoformat(collector_state["cursor"])
    elif collector_state.get("last_success_at"):
        complete_until = min(now, datetime.fromisoformat(collector_state["last_success_at"]))

    # Hourly series today and trend (last complete hour vs previous)
    series = []
    hour = day_start
    while hour <= now:
        nxt = hour + timedelta(hours=1)
        u = units_between(incs, hour, nxt)
        series.append({"label": clock.to_local(hour).strftime("%H:00"), "start": hour.astimezone(timezone.utc).isoformat(),
                       "value": u["value"], "records": u["records"], "partial": u["partial"],
                       "in_progress": nxt > complete_until})
        hour = nxt
    complete = [s for s in series if not s["in_progress"] and s["value"] is not None]
    trend: dict[str, Any] = {"status": "unavailable", "note": "Se requieren dos horas completas con registros."}
    if len(complete) >= 2:
        last_h, prev_h = complete[-1], complete[-2]
        if prev_h["value"]:
            pct = round((last_h["value"] - prev_h["value"]) / prev_h["value"] * 100, 1)
            trend = {"status": "partial" if last_h["partial"] or prev_h["partial"] else "verified",
                     "percent": pct, "direction": "up" if pct > 0 else "down" if pct < 0 else "flat",
                     "last_hour": last_h["label"], "previous_hour": prev_h["label"],
                     "last_value": last_h["value"], "previous_value": prev_h["value"],
                     "note": f"Hora {last_h['label']} vs {prev_h['label']} (por hora de producción)."}

    # Increment between the two latest successful readings (by query time)
    increment: dict[str, Any] = {"status": "unavailable", "note": "Se requieren dos lecturas exitosas del mismo día."}
    ok_runs = [r for r in runs if r.get("metrics")]
    if len(ok_runs) >= 2:
        cur, prev = ok_runs[0], ok_runs[1]
        if (cur["metrics"].get("day") == prev["metrics"].get("day") and cur["metrics"].get("units_today") is not None
                and prev["metrics"].get("units_today") is not None
                and cur["metrics"].get("semantics") == prev["metrics"].get("semantics")):
            delta = cur["metrics"]["units_today"] - prev["metrics"]["units_today"]
            seconds = (datetime.fromisoformat(cur["started_at"]) - datetime.fromisoformat(prev["started_at"])).total_seconds()
            catching_up = bool(cur.get("truncated") or prev.get("truncated"))
            increment = {"status": "partial" if catching_up or cur["metrics"].get("partial") else "verified",
                         "value": delta, "seconds": round(seconds), "from": prev["started_at"], "to": cur["started_at"],
                         "note": ("Incluye registros recuperados del historial (sincronización en curso)."
                                  if catching_up else
                                  "Producción registrada en FactoryLogix entre las dos últimas lecturas.")}

    latest_ts = max((r["production_ts"] for r in rows), default=None)
    last_success = collector_state.get("last_success_at")
    lag_seconds = None
    if latest_ts and last_success:
        lag_seconds = max(0, round((datetime.fromisoformat(last_success) - datetime.fromisoformat(latest_ts)).total_seconds()))

    activity = "active" if has_recent else ("syncing" if catching_up else "no_recent_data")
    return {
        "now": now.isoformat(),
        "activity": activity,
        "catching_up": catching_up,
        "complete_until": complete_until.isoformat(),
        "day": local_now.date().isoformat(),
        "unit": unit,
        "quantity_field": qty_field,
        "semantics": sem,
        "units_today": {**today, "status": ("unavailable" if today["value"] is None or semantics == "undetermined"
                                            else "partial" if today["partial"] or collector_state.get("catching_up") else "verified")},
        "increment": increment,
        "trend": trend,
        "series": series,
        "latest_production_ts": latest_ts,
        "latest_production_age_seconds": (round((now - datetime.fromisoformat(latest_ts)).total_seconds()) if latest_ts else None),
        "source_lag_seconds": lag_seconds,
        "has_recent_activity": has_recent,
        "recent_minutes": recent_minutes,
        "lines": line_status,
        "dimensions": dimensions,
        "dimension_labels": DIMENSION_LABELS_ES,
    }


def run_snapshot(monitor: dict[str, Any]) -> dict[str, Any]:
    """Small summary stored with each successful collector run (enables between-readings deltas)."""
    return {"day": monitor["day"], "units_today": monitor["units_today"]["value"],
            "partial": monitor["units_today"]["partial"], "semantics": monitor["semantics"]["semantics"],
            "by_line": {l["line"]: l["units_today"] for l in monitor["lines"]},
            "latest_production_ts": monitor["latest_production_ts"]}
