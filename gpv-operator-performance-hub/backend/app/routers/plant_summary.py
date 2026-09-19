from __future__ import annotations

from collections import Counter
from datetime import date, datetime, timedelta

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from ..analytics import CLASSIFICATION_TONE, _date_range, _events_query, build_performance_rows, get_scoring_weights, station_summary
from ..database import get_db
from ..models import Operator, ProductionEvent, Station
from ..security import get_current_user, CurrentUser

router = APIRouter(prefix="/api/plant-summary", tags=["Resumen de planta"])


@router.get("")
def plant_summary(
    period_days: int = Query(7, ge=1, le=90),
    shift: str | None = None,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    start_date, end_date = _date_range(period_days)
    prev_start, prev_end = _date_range(period_days, end_date=start_date - timedelta(days=1))

    events = _events_query(db, start_date, end_date, shift=shift).all()
    prev_events = _events_query(db, prev_start, prev_end, shift=shift).all()

    total_processed = sum(e.units_processed for e in events)
    total_conforming = sum(e.units_conforming for e in events)
    total_rejected = sum(e.units_rejected for e in events)
    total_reworked = sum(e.units_reworked for e in events)

    fpy = round(100.0 * total_conforming / total_processed, 1) if total_processed else 0.0
    prev_processed = sum(e.units_processed for e in prev_events)
    prev_conforming = sum(e.units_conforming for e in prev_events)
    prev_fpy = round(100.0 * prev_conforming / prev_processed, 1) if prev_processed else None

    defect_rate = round(100.0 * total_rejected / total_processed, 1) if total_processed else 0.0
    rework_rate = round(100.0 * total_reworked / total_processed, 1) if total_processed else 0.0

    stations = {s.id: s for s in db.query(Station).all()}
    cycle_ratios = [
        (stations[e.station_id].standard_cycle_seconds / e.cycle_time_seconds) * 100
        for e in events
        if e.cycle_time_seconds > 0
    ]
    compliance = round(sum(cycle_ratios) / len(cycle_ratios), 1) if cycle_ratios else 0.0
    avg_cycle = round(sum(e.cycle_time_seconds for e in events) / len(events), 1) if events else 0.0

    active_operator_ids = {e.operator_id for e in events}
    total_operators = db.query(Operator).filter(Operator.is_active.is_(True)).count()

    rows = build_performance_rows(db, period_days=period_days, shift=shift)
    insufficient = [r for r in rows if r["classification"] == "Datos insuficientes"]
    with_data = [r for r in rows if r["units_processed"] > 0]
    coverage_pct = round(100.0 * len(with_data) / len(rows), 1) if rows else 0.0

    dist_counter = Counter(r["classification"] for r in rows)
    performance_distribution = [
        {"classification": label, "count": dist_counter.get(label, 0), "tone": CLASSIFICATION_TONE[label]}
        for label in ["Excelente", "Bueno", "En observación", "Requiere apoyo", "Datos insuficientes"]
    ]

    st_rows = station_summary(db, period_days=period_days)
    at_risk_stations = [s for s in st_rows if s["alerts"]]
    quality_by_station = [
        {"station": s["name"], "fpy": s["fpy"], "rework_rate": s["rework_rate"]} for s in st_rows if s["units_processed"]
    ]

    # Tendencia de producción por hora (últimas 24h con datos, aproximado por hora del timestamp).
    hourly = Counter()
    for e in events:
        hourly[e.event_timestamp.hour] += e.units_processed
    hourly_trend = [{"hour": f"{h:02d}:00", "units": hourly.get(h, 0)} for h in range(24)]

    # Comparación entre turnos.
    shift_totals: dict[str, dict] = {}
    for e in events:
        s = shift_totals.setdefault(e.shift.value, {"processed": 0, "conforming": 0})
        s["processed"] += e.units_processed
        s["conforming"] += e.units_conforming
    shift_comparison = [
        {
            "shift": shift_name,
            "units_processed": v["processed"],
            "fpy": round(100.0 * v["conforming"] / v["processed"], 1) if v["processed"] else 0.0,
        }
        for shift_name, v in shift_totals.items()
    ]

    # Anomalías recientes: eventos con defecto alto o paro de estación en los últimos días.
    anomalies = []
    for e in sorted(events, key=lambda x: x.event_timestamp, reverse=True):
        if e.station_was_down:
            anomalies.append(
                {
                    "type": "Estación detenida",
                    "detail": f"{stations[e.station_id].name} — {e.event_date.isoformat()}",
                    "severity": "warning",
                }
            )
        if e.units_processed and (e.units_rejected / e.units_processed) > 0.15:
            anomalies.append(
                {
                    "type": "Tasa de rechazo elevada",
                    "detail": f"{stations[e.station_id].name} — {e.event_date.isoformat()} ({e.units_rejected}/{e.units_processed} unidades)",
                    "severity": "bad",
                }
            )
        if len(anomalies) >= 8:
            break

    attention_today = []
    for s in at_risk_stations[:5]:
        attention_today.append(
            {"title": s["name"], "detail": ", ".join(s["alerts"]), "category": "Estación"}
        )
    for r in [row for row in rows if row["classification"] == "Requiere apoyo"][:5]:
        attention_today.append(
            {
                "title": r["full_name"],
                "detail": f"Puntaje {r['score']} en {r['main_station']}. Revisar contexto antes de asignar capacitación.",
                "category": "Operador",
            }
        )

    def trend_dir(cur, prev):
        if prev is None:
            return "neutral"
        if cur > prev + 0.5:
            return "up"
        if cur < prev - 0.5:
            return "down"
        return "neutral"

    fpy_context = (
        f"{fpy:.1f} %, {abs(round(fpy - prev_fpy, 1))} puntos "
        f"{'por encima' if prev_fpy is not None and fpy >= prev_fpy else 'por debajo'} del periodo anterior"
        if prev_fpy is not None
        else f"{fpy:.1f} %, sin periodo anterior comparable"
    )

    kpis = [
        {"label": "Operadores activos", "value": str(len(active_operator_ids)), "context": f"de {total_operators} registrados", "trend_direction": "neutral", "tone": "neutral"},
        {"label": "Unidades procesadas", "value": f"{total_processed:,}", "context": f"en los últimos {period_days} días", "trend_direction": "neutral", "tone": "neutral"},
        {"label": "First Pass Yield", "value": f"{fpy:.1f} %", "context": fpy_context, "trend_direction": trend_dir(fpy, prev_fpy), "tone": "good" if fpy >= 95 else ("warning" if fpy >= 88 else "bad")},
        {"label": "Tiempo de ciclo promedio", "value": f"{avg_cycle:.1f} s", "context": f"cumplimiento promedio {compliance:.1f}% contra estándar", "trend_direction": "neutral", "tone": "good" if compliance >= 95 else "warning"},
        {"label": "Tasa de retrabajo", "value": f"{rework_rate:.1f} %", "context": f"{total_reworked:,} unidades reprocesadas", "trend_direction": "neutral", "tone": "good" if rework_rate < 3 else "warning"},
        {"label": "Tasa de defectos", "value": f"{defect_rate:.1f} %", "context": f"{total_rejected:,} unidades rechazadas", "trend_direction": "neutral", "tone": "good" if defect_rate < 3 else "bad"},
        {"label": "Cumplimiento contra estándar", "value": f"{compliance:.1f} %", "context": "promedio ponderado de todas las estaciones activas", "trend_direction": "neutral", "tone": "good" if compliance >= 95 else "warning"},
        {"label": "Estaciones con riesgo", "value": str(len(at_risk_stations)), "context": "requieren revisión de proceso, no necesariamente del operador", "trend_direction": "neutral", "tone": "bad" if at_risk_stations else "good"},
        {"label": "Operadores con datos insuficientes", "value": str(len(insufficient)), "context": "aún no acumulan el mínimo de unidades para clasificar", "trend_direction": "neutral", "tone": "neutral"},
        {"label": "Cobertura de datos", "value": f"{coverage_pct:.1f} %", "context": "operadores con actividad registrada en el periodo", "trend_direction": "neutral", "tone": "good" if coverage_pct >= 80 else "warning"},
    ]

    return {
        "kpis": kpis,
        "hourly_trend": hourly_trend,
        "quality_by_station": quality_by_station,
        "performance_distribution": performance_distribution,
        "shift_comparison": shift_comparison,
        "recent_anomalies": anomalies,
        "attention_today": attention_today,
        "data_coverage_pct": coverage_pct,
        "last_sync": datetime.utcnow().isoformat(),
    }
