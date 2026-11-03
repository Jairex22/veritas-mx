"""Productivity analytics computed strictly from confirmed fields.

Rules:
* Only the mapped (confirmed) fields are used. Without a confirmed quantity field, no
  production metric is produced; without a line field, no per-line metric is produced.
* No OEE, efficiency, FPY, availability or units-per-hour is computed: the entity does not
  provide confirmed definitions for them.
* Buckets without records are "no data" (never zero).
* Results based on truncated responses (MAX_RECORDS reached / server has more pages) or with
  excluded records are labelled ``partial`` instead of ``verified``.
* Drop detection is a heuristic indicator, explicitly labelled as such.
"""
from __future__ import annotations

import math
import re
from dataclasses import dataclass
from datetime import datetime, timedelta
from statistics import median
from typing import Any

from timeutil import PlantClock, iso_utc, parse_odata_datetime

INTERVAL_LABELS_ES = {"hour": "hora", "shift": "turno", "day": "día"}
NO_DATA_MESSAGE = "No hay información verificable para este periodo."


@dataclass
class NormalizedRecord:
    timestamp: datetime
    quantity: float | None
    line: str | None
    station: str | None
    shift: str | None
    raw: dict[str, Any]


def parse_number(value: Any) -> float | None:
    """Parse OData numeric values (numbers or numeric strings such as Edm.Decimal)."""
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value) if math.isfinite(float(value)) else None
    if isinstance(value, str) and re.fullmatch(r"\s*-?\d+(\.\d+)?([eE][-+]?\d+)?\s*", value):
        number = float(value)
        return number if math.isfinite(number) else None
    return None


def _text(value: Any) -> str | None:
    if value is None or isinstance(value, bool):
        return None
    text = str(value).strip()
    return text or None


def normalize_records(raw_records: list[dict[str, Any]], mapping: dict[str, str | None], clock: PlantClock,
                      period_start: datetime | None = None,
                      period_end: datetime | None = None) -> tuple[list[NormalizedRecord], dict[str, int]]:
    """Convert raw OData records using the confirmed mapping.

    Returns (records, exclusions) where exclusions counts discarded records by reason.
    """
    exclusions = {"sin_fecha_valida": 0, "fuera_del_periodo": 0}
    out: list[NormalizedRecord] = []
    ts_field = mapping.get("timestamp")
    for raw in raw_records:
        moment = parse_odata_datetime(raw.get(ts_field), clock) if ts_field else None
        if moment is None:
            exclusions["sin_fecha_valida"] += 1
            continue
        if period_start and period_end and not (period_start <= moment < period_end):
            exclusions["fuera_del_periodo"] += 1
            continue
        out.append(NormalizedRecord(
            timestamp=clock.to_local(moment),
            quantity=parse_number(raw.get(mapping["quantity"])) if mapping.get("quantity") else None,
            line=_text(raw.get(mapping["line"])) if mapping.get("line") else None,
            station=_text(raw.get(mapping["station"])) if mapping.get("station") else None,
            shift=_text(raw.get(mapping["shift"])) if mapping.get("shift") else None,
            raw=raw,
        ))
    out.sort(key=lambda r: r.timestamp)
    return out, exclusions


def _bucket(record: NormalizedRecord, interval: str) -> tuple[str, datetime, datetime, str]:
    """Return (key, start, end, label) of the bucket containing ``record``."""
    ts = record.timestamp
    if interval == "day":
        start = ts.replace(hour=0, minute=0, second=0, microsecond=0)
        return start.date().isoformat(), start, start + timedelta(days=1), start.strftime("%d/%m/%Y")
    if interval == "shift" and record.shift:
        day = ts.date().isoformat()
        start = ts.replace(minute=0, second=0, microsecond=0)
        return f"{day}|{record.shift}", start, start, f"{ts.strftime('%d/%m')} {record.shift}"
    start = ts.replace(minute=0, second=0, microsecond=0)
    return start.isoformat(), start, start + timedelta(hours=1), start.strftime("%d/%m %H:00")


def _fmt(value: float | None) -> str:
    if value is None:
        return "—"
    if float(value).is_integer():
        return f"{int(value):,}".replace(",", " ")
    return f"{value:,.2f}".replace(",", " ")


def _group(records: list[NormalizedRecord], key: str) -> list[dict[str, Any]]:
    groups: dict[str, dict[str, Any]] = {}
    for r in records:
        name = getattr(r, key) or "(sin valor)"
        g = groups.setdefault(name, {"name": name, "value": 0.0, "records": 0, "with_quantity": 0})
        g["records"] += 1
        if r.quantity is not None:
            g["value"] += r.quantity
            g["with_quantity"] += 1
    return sorted(groups.values(), key=lambda g: g["name"])


def analyze(raw_records: list[dict[str, Any]], *, mapping: dict[str, str | None], clock: PlantClock,
            period_start: datetime, period_end: datetime, interval: str, truncated: bool,
            fetched_at: str, from_cache: bool, unit_label: str = "", drop_threshold_percent: float = 25.0,
            min_buckets_for_drop: int = 4, now: datetime | None = None) -> dict[str, Any]:
    """Compute verified metrics, series and limitations for a set of raw records."""
    now = now or clock.now()
    records, exclusions = normalize_records(raw_records, mapping, clock, period_start, period_end)
    qty_field = mapping.get("quantity")
    unit = unit_label.strip() or (f"suma de {qty_field}" if qty_field else "")
    if interval == "shift" and not mapping.get("shift"):
        interval = "hour"
    excluded = sum(exclusions.values())
    missing_qty = sum(1 for r in records if r.quantity is None) if qty_field else 0
    complete = not truncated and excluded == 0 and missing_qty == 0
    quality = "verified" if complete else "partial"

    limitations: list[str] = []
    if truncated:
        limitations.append("La respuesta alcanzó el límite de registros configurado o el servidor indicó más páginas; "
                           "los totales corresponden solo a los registros recibidos (resultado parcial).")
    if exclusions["sin_fecha_valida"]:
        limitations.append(f"{exclusions['sin_fecha_valida']} registro(s) sin fecha válida fueron excluidos.")
    if exclusions["fuera_del_periodo"]:
        limitations.append(f"{exclusions['fuera_del_periodo']} registro(s) fuera del periodo fueron excluidos.")
    if missing_qty:
        limitations.append(f"{missing_qty} registro(s) sin cantidad numérica no suman a la producción.")
    if not qty_field:
        limitations.append("No hay un campo de cantidad confirmado: no se calculan métricas de producción.")
    limitations.append("No se calculan OEE, eficiencia, FPY, disponibilidad ni unidades por hora: "
                       "ProductivityOverTime no provee definiciones confirmadas para esas métricas.")
    if from_cache:
        limitations.append("Información obtenida de la caché local; ver fecha de extracción.")

    buckets: dict[str, dict[str, Any]] = {}
    for r in records:
        key, start, end, label = _bucket(r, interval)
        b = buckets.setdefault(key, {"key": key, "label": label, "start": start, "end": end,
                                     "value": 0.0, "records": 0, "with_quantity": 0})
        b["records"] += 1
        b["end"] = max(b["end"], r.timestamp)
        if r.quantity is not None:
            b["value"] += r.quantity
            b["with_quantity"] += 1
    series = []
    for b in sorted(buckets.values(), key=lambda x: x["start"]):
        in_progress = b["end"] > now if interval != "shift" else False
        series.append({"key": b["key"], "label": b["label"], "start": iso_utc(b["start"]),
                       "value": b["value"] if b["with_quantity"] else None,
                       "records": b["records"], "in_progress": in_progress})

    total = sum(r.quantity for r in records if r.quantity is not None) if qty_field else None
    with_values = [s for s in series if s["value"] is not None]
    interval_es = INTERVAL_LABELS_ES[interval]
    cards: list[dict[str, Any]] = []

    if not records:
        cards.append({"id": "production", "title": "Producción registrada", "status": "unavailable",
                      "display": "—", "unit": "", "note": NO_DATA_MESSAGE})
    elif qty_field:
        cards.append({"id": "production", "title": "Producción registrada", "status": quality,
                      "value": total, "display": _fmt(total), "unit": unit,
                      "note": f"{len(records)} registro(s) en el periodo."})
        if with_values:
            avg = total / len(with_values) if total is not None else None
            cards.append({"id": "per_period", "title": "Productividad por periodo", "status": quality,
                          "value": round(avg, 2) if avg is not None else None, "display": _fmt(round(avg, 2) if avg is not None else None),
                          "unit": f"{unit} por {interval_es}",
                          "note": f"Promedio de {len(with_values)} {interval_es}(s) con registros."})
    else:
        cards.append({"id": "production", "title": "Producción registrada", "status": "unavailable",
                      "display": "—", "unit": "", "note": "Campo de cantidad no confirmado."})

    by_line = _group(records, "line") if mapping.get("line") else []
    by_station = _group(records, "station") if mapping.get("station") else []
    by_shift = _group(records, "shift") if mapping.get("shift") else []
    if mapping.get("line") and records:
        active = [g for g in by_line if g["name"] != "(sin valor)" and (g["value"] > 0 if qty_field else g["records"] > 0)]
        cards.append({"id": "lines", "title": "Líneas con actividad registrada", "status": quality,
                      "value": len(active), "display": str(len(active)), "unit": "líneas",
                      "note": ", ".join(g["name"] for g in active[:6]) or "Sin actividad registrada."})

    cards.append({"id": "updated", "title": "Última actualización confirmada",
                  "status": "verified" if fetched_at else "unavailable",
                  "value": fetched_at, "display": fetched_at, "unit": "",
                  "note": "Desde caché local" if from_cache else "Consulta directa al servidor OData"})

    drops: list[dict[str, Any]] = []
    complete_buckets = [s for s in with_values if not s["in_progress"]]
    if qty_field and len(complete_buckets) >= max(2, min_buckets_for_drop):
        reference = median(s["value"] for s in complete_buckets)
        if reference > 0:
            for s in complete_buckets:
                pct = (s["value"] - reference) / reference * 100
                if pct <= -abs(drop_threshold_percent):
                    drops.append({"label": s["label"], "value": s["value"], "reference": reference,
                                  "percent": round(pct, 1)})

    return {
        "interval": interval,
        "interval_label": interval_es,
        "quantity_field": qty_field,
        "unit": unit,
        "records_received": len(raw_records),
        "records_used": len(records),
        "exclusions": exclusions,
        "missing_quantity": missing_qty,
        "truncated": truncated,
        "complete": complete,
        "quality": quality if records else "unavailable",
        "total": total,
        "cards": cards,
        "series": series,
        "by_line": by_line,
        "by_station": by_station,
        "by_shift": by_shift,
        "drops": drops,
        "drop_rule": (f"Intervalo completo con producción al menos {abs(drop_threshold_percent):g}% inferior "
                      f"a la mediana de los intervalos del periodo (indicador heurístico, no confirmado)."),
        "limitations": limitations,
        "empty_message": NO_DATA_MESSAGE if not records else "",
    }


def trend(current: dict[str, Any], previous: dict[str, Any] | None, previous_fetched_at: str | None) -> dict[str, Any]:
    """Compare totals of the current period with the immediately previous period of equal length."""
    if current.get("total") is None:
        return {"status": "unavailable", "note": "No hay producción confirmada en el periodo actual."}
    if previous is None:
        return {"status": "unavailable", "note": "No hay datos guardados del periodo anterior."}
    if previous.get("total") is None or previous.get("records_used", 0) == 0:
        return {"status": "unavailable", "note": "El periodo anterior no tiene producción verificable."}
    prev_total = previous["total"]
    cur_total = current["total"]
    status = "verified" if current.get("complete") and previous.get("complete") else "partial"
    if prev_total == 0:
        return {"status": status, "previous_total": prev_total, "current_total": cur_total, "percent": None,
                "note": "El periodo anterior registró 0; no se calcula porcentaje.",
                "previous_fetched_at": previous_fetched_at}
    pct = (cur_total - prev_total) / prev_total * 100
    return {"status": status, "previous_total": prev_total, "current_total": cur_total, "percent": round(pct, 1),
            "direction": "up" if pct > 0 else ("down" if pct < 0 else "flat"),
            "note": "Comparación con el periodo anterior de igual duración (mismos filtros).",
            "previous_fetched_at": previous_fetched_at}


def compare_snapshots(a: dict[str, Any], b: dict[str, Any]) -> dict[str, Any]:
    """Compare two stored analyses (totals and per-line) for the trends page."""
    result: dict[str, Any] = {"a_total": a.get("total"), "b_total": b.get("total"),
                              "status": "verified" if a.get("complete") and b.get("complete") else "partial"}
    if a.get("total") is not None and b.get("total") not in (None, 0):
        result["percent_a_vs_b"] = round((a["total"] - b["total"]) / b["total"] * 100, 1)
    else:
        result["percent_a_vs_b"] = None
    lines = sorted({g["name"] for g in a.get("by_line", [])} | {g["name"] for g in b.get("by_line", [])})
    a_map = {g["name"]: g["value"] for g in a.get("by_line", [])}
    b_map = {g["name"]: g["value"] for g in b.get("by_line", [])}
    result["by_line"] = [{"name": n, "a": a_map.get(n), "b": b_map.get(n)} for n in lines]
    return result


def display_rows(raw_records: list[dict[str, Any]], mapping: dict[str, str | None], clock: PlantClock,
                 limit: int = 1000) -> list[dict[str, Any]]:
    """Rows for the results table using confirmed fields only (local time)."""
    records, _ = normalize_records(raw_records, mapping, clock)
    rows = []
    for r in records[-limit:][::-1]:
        rows.append({
            "timestamp": r.timestamp.strftime("%Y-%m-%d %H:%M"),
            "line": r.line, "station": r.station, "shift": r.shift, "quantity": r.quantity,
        })
    return rows
