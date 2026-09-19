"""
Funciones de agregación compartidas por los routers. Toda la lógica de
"qué significa un buen resultado" vive en `scoring.py`; este módulo sólo arma
las consultas y arma las estructuras que consumen las pantallas.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from datetime import date, datetime, timedelta

from sqlalchemy import func
from sqlalchemy.orm import Session

from .models import (
    Operator,
    PerformanceSnapshot,
    Product,
    ProductionEvent,
    QualityEvent,
    ScoringConfig,
    Shift,
    Station,
    WorkOrder,
)
from .scoring import GroupSample, ScoringWeights, compute_score

CLASSIFICATION_TONE = {
    "Excelente": "good",
    "Bueno": "info",
    "En observación": "warning",
    "Requiere apoyo": "bad",
    "Datos insuficientes": "neutral",
}


def get_scoring_weights(db: Session) -> ScoringWeights:
    cfg = db.query(ScoringConfig).order_by(ScoringConfig.id.desc()).first()
    if not cfg:
        return ScoringWeights()
    return ScoringWeights(
        quality=cfg.weight_quality,
        cycle=cfg.weight_cycle,
        productivity=cfg.weight_productivity,
        consistency=cfg.weight_consistency,
        rework=cfg.weight_rework,
        min_units=cfg.min_units_for_classification,
    )


def _date_range(period_days: int, end_date: date | None = None) -> tuple[date, date]:
    end_date = end_date or date.today()
    start_date = end_date - timedelta(days=max(period_days - 1, 0))
    return start_date, end_date


def _events_query(
    db: Session,
    start_date: date,
    end_date: date,
    shift: str | None = None,
    operator_id: int | None = None,
    station_id: int | None = None,
):
    q = db.query(ProductionEvent).filter(
        ProductionEvent.event_date >= start_date, ProductionEvent.event_date <= end_date
    )
    if shift:
        q = q.filter(ProductionEvent.shift == shift)
    if operator_id:
        q = q.filter(ProductionEvent.operator_id == operator_id)
    if station_id:
        q = q.filter(ProductionEvent.station_id == station_id)
    return q


def events_to_samples(events: list[ProductionEvent], station_by_id: dict[int, Station]) -> list[GroupSample]:
    return [
        GroupSample(
            units_processed=e.units_processed,
            units_conforming=e.units_conforming,
            units_rejected=e.units_rejected,
            units_reworked=e.units_reworked,
            cycle_time_seconds=e.cycle_time_seconds,
            standard_cycle_seconds=station_by_id[e.station_id].standard_cycle_seconds,
            event_date=e.event_date.isoformat(),
        )
        for e in events
    ]


def _trend_label(current: float | None, previous: float | None, tolerance: float = 1.5) -> str:
    if current is None or previous is None:
        return "Sin datos previos"
    diff = current - previous
    if abs(diff) < tolerance:
        return "Estable"
    return "Mejorando" if diff > 0 else "En descenso"


def build_operator_score(
    db: Session,
    operator_id: int,
    start_date: date,
    end_date: date,
    weights: ScoringWeights,
    shift: str | None = None,
):
    stations = {s.id: s for s in db.query(Station).all()}
    events = _events_query(db, start_date, end_date, shift=shift, operator_id=operator_id).all()
    samples = events_to_samples(events, stations)
    return compute_score(samples, weights), events


def build_performance_rows(
    db: Session,
    period_days: int = 30,
    shift: str | None = None,
    area: str | None = None,
    station_id: int | None = None,
    search: str | None = None,
) -> list[dict]:
    weights = get_scoring_weights(db)
    start_date, end_date = _date_range(period_days)
    prev_start, prev_end = _date_range(period_days, end_date=start_date - timedelta(days=1))

    stations = {s.id: s for s in db.query(Station).all()}
    products = {p.id: p for p in db.query(Product).all()}
    work_orders = {w.id: w for w in db.query(WorkOrder).all()}

    operators_q = db.query(Operator).filter(Operator.is_active.is_(True))
    if area:
        operators_q = operators_q.filter(Operator.area == area)
    if search:
        like = f"%{search.lower()}%"
        operators_q = operators_q.filter(
            func.lower(Operator.full_name).like(like) | func.lower(Operator.employee_number).like(like)
        )
    operators = operators_q.all()

    rows: list[dict] = []
    for op in operators:
        events = _events_query(db, start_date, end_date, shift=shift, operator_id=op.id, station_id=station_id).all()
        if station_id and not events:
            continue

        samples = events_to_samples(events, stations)
        result = compute_score(samples, weights)

        total_processed = sum(e.units_processed for e in events)
        total_conforming = sum(e.units_conforming for e in events)
        total_rejected = sum(e.units_rejected for e in events)
        total_reworked = sum(e.units_reworked for e in events)
        fpy = round(100.0 * total_conforming / total_processed, 1) if total_processed else 0.0

        cycle_ratios = [
            (stations[e.station_id].standard_cycle_seconds / e.cycle_time_seconds) * 100
            for e in events
            if e.cycle_time_seconds > 0
        ]
        cycle_compliance = round(sum(cycle_ratios) / len(cycle_ratios), 1) if cycle_ratios else 0.0
        avg_cycle = round(sum(e.cycle_time_seconds for e in events) / len(events), 1) if events else 0.0

        consistency_item = next((b for b in result.breakdown if b.key == "consistency"), None)
        consistency_index = round(consistency_item.normalized_value, 1) if consistency_item else 0.0

        station_counter = Counter(e.station_id for e in events)
        main_station = stations[station_counter.most_common(1)[0][0]].name if station_counter else "Sin actividad"

        product_counter = Counter(e.product_id for e in events)
        product_name = products[product_counter.most_common(1)[0][0]].name if product_counter else "—"

        wo_counter = Counter(e.work_order_id for e in events)
        wo_code = work_orders[wo_counter.most_common(1)[0][0]].code if wo_counter else "—"

        last_activity = max((e.event_date for e in events), default=None)

        # Tendencia: puntaje del periodo actual vs. el periodo equivalente anterior.
        prev_events = _events_query(db, prev_start, prev_end, shift=shift, operator_id=op.id, station_id=station_id).all()
        prev_samples = events_to_samples(prev_events, stations)
        prev_result = compute_score(prev_samples, weights)
        trend = _trend_label(result.score, prev_result.score)

        if not events:
            trend = "Sin datos previos"

        rows.append(
            {
                "operator_id": op.id,
                "employee_number": op.employee_number,
                "full_name": op.full_name,
                "shift": op.shift.value,
                "area": op.area,
                "line": f"Línea {op.area}",
                "main_station": main_station,
                "product": product_name,
                "work_order": wo_code,
                "units_processed": total_processed,
                "units_conforming": total_conforming,
                "units_rejected": total_rejected,
                "units_reworked": total_reworked,
                "fpy": fpy,
                "avg_cycle_time_seconds": avg_cycle,
                "cycle_compliance_pct": cycle_compliance,
                "consistency_index": consistency_index,
                "data_confidence": result.data_confidence,
                "score": result.score,
                "classification": result.classification,
                "trend": trend,
                "last_activity": last_activity,
            }
        )
    return rows


def station_summary(db: Session, period_days: int = 30) -> list[dict]:
    weights = get_scoring_weights(db)
    start_date, end_date = _date_range(period_days)
    stations = db.query(Station).order_by(Station.sequence_order).all()

    result_rows = []
    for st in stations:
        events = _events_query(db, start_date, end_date, station_id=st.id).all()
        total_processed = sum(e.units_processed for e in events)
        total_conforming = sum(e.units_conforming for e in events)
        total_reworked = sum(e.units_reworked for e in events)
        fpy = round(100.0 * total_conforming / total_processed, 1) if total_processed else None
        rework_rate = round(100.0 * total_reworked / total_processed, 1) if total_processed else None
        avg_cycle = round(sum(e.cycle_time_seconds for e in events) / len(events), 1) if events else None
        active_operators = len({e.operator_id for e in events})
        alerts = []
        if fpy is not None and fpy < 90:
            alerts.append("FPY por debajo de meta")
        if avg_cycle is not None and avg_cycle > st.standard_cycle_seconds * 1.15:
            alerts.append("Tiempo real por encima del estándar")
        if total_processed == 0:
            alerts.append("Sin actividad reciente")

        prev_start, prev_end = _date_range(period_days, end_date=start_date - timedelta(days=1))
        prev_events = _events_query(db, prev_start, prev_end, station_id=st.id).all()
        prev_fpy = (
            round(100.0 * sum(e.units_conforming for e in prev_events) / sum(e.units_processed for e in prev_events), 1)
            if prev_events and sum(e.units_processed for e in prev_events)
            else None
        )
        trend = _trend_label(fpy, prev_fpy, tolerance=1.0)

        result_rows.append(
            {
                "id": st.id,
                "name": st.name,
                "code": st.code,
                "area": st.area,
                "status": "Sin actividad" if total_processed == 0 else ("Con alertas" if alerts else "Operando"),
                "active_operators": active_operators,
                "units_processed": total_processed,
                "standard_cycle_seconds": st.standard_cycle_seconds,
                "avg_cycle_time_seconds": avg_cycle,
                "fpy": fpy,
                "rework_rate": rework_rate,
                "queue_estimate": max(0, int((avg_cycle or st.standard_cycle_seconds) - st.standard_cycle_seconds)),
                "alerts": alerts,
                "trend": trend,
            }
        )
    return result_rows


def quality_pareto(db: Session, period_days: int = 30) -> list[dict]:
    start_date, end_date = _date_range(period_days)
    events = (
        db.query(QualityEvent)
        .filter(QualityEvent.event_date >= start_date, QualityEvent.event_date <= end_date)
        .all()
    )
    counter: dict[str, dict] = defaultdict(lambda: {"quantity": 0, "description": "", "cause": ""})
    for ev in events:
        entry = counter[ev.defect_code]
        entry["quantity"] += ev.quantity
        entry["description"] = ev.defect_description
        entry["cause"] = ev.cause_category.value
    items = [
        {"defect_code": code, "description": v["description"], "cause": v["cause"], "quantity": v["quantity"]}
        for code, v in counter.items()
    ]
    items.sort(key=lambda x: x["quantity"], reverse=True)
    total = sum(i["quantity"] for i in items) or 1
    cumulative = 0
    for item in items:
        cumulative += item["quantity"]
        item["cumulative_pct"] = round(100.0 * cumulative / total, 1)
    return items
