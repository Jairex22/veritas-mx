from __future__ import annotations

from collections import Counter, defaultdict
from datetime import timedelta

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from ..analytics import _date_range, quality_pareto
from ..database import get_db
from ..models import ProductionEvent, QualityEvent, Station, Product
from ..security import CurrentUser, get_current_user

router = APIRouter(prefix="/api/quality", tags=["Calidad"])


@router.get("")
def quality_overview(
    period_days: int = Query(30, ge=1, le=90),
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    start_date, end_date = _date_range(period_days)
    stations = {s.id: s for s in db.query(Station).all()}
    products = {p.id: p for p in db.query(Product).all()}

    quality_events = (
        db.query(QualityEvent).filter(QualityEvent.event_date >= start_date, QualityEvent.event_date <= end_date).all()
    )
    production_events = (
        db.query(ProductionEvent)
        .filter(ProductionEvent.event_date >= start_date, ProductionEvent.event_date <= end_date)
        .all()
    )

    pareto = quality_pareto(db, period_days=period_days)

    defects_by_station = Counter()
    for qe in quality_events:
        defects_by_station[stations[qe.station_id].name] += qe.quantity
    defects_by_station_out = [{"station": k, "quantity": v} for k, v in defects_by_station.most_common()]

    defects_by_product = Counter()
    for qe in quality_events:
        defects_by_product[products[qe.product_id].name] += qe.quantity
    defects_by_product_out = [{"product": k, "quantity": v} for k, v in defects_by_product.most_common()]

    fpy_by_shift = defaultdict(lambda: {"processed": 0, "conforming": 0})
    for pe in production_events:
        agg = fpy_by_shift[pe.shift.value]
        agg["processed"] += pe.units_processed
        agg["conforming"] += pe.units_conforming
    fpy_by_shift_out = [
        {"shift": k, "fpy": round(100.0 * v["conforming"] / v["processed"], 1) if v["processed"] else 0.0}
        for k, v in fpy_by_shift.items()
    ]

    rework_by_cause = Counter()
    for qe in quality_events:
        rework_by_cause[qe.cause_category.value] += qe.quantity
    rework_by_cause_out = [{"cause": k, "quantity": v} for k, v in rework_by_cause.most_common()]

    weekly = defaultdict(lambda: {"processed": 0, "conforming": 0})
    for pe in production_events:
        week_start = pe.event_date - timedelta(days=pe.event_date.weekday())
        agg = weekly[week_start.isoformat()]
        agg["processed"] += pe.units_processed
        agg["conforming"] += pe.units_conforming
    weekly_trend = [
        {"week": k, "fpy": round(100.0 * v["conforming"] / v["processed"], 1) if v["processed"] else 0.0}
        for k, v in sorted(weekly.items())
    ]

    blocked_units = sum(qe.quantity for qe in quality_events if qe.is_blocked_unit)
    validation_failures = sum(qe.quantity for qe in quality_events if qe.is_validation_failure)

    # Matriz estación-producto (FPY).
    matrix_agg = defaultdict(lambda: {"processed": 0, "conforming": 0})
    for pe in production_events:
        matrix_agg[(pe.station_id, pe.product_id)]["processed"] += pe.units_processed
        matrix_agg[(pe.station_id, pe.product_id)]["conforming"] += pe.units_conforming
    station_product_matrix = [
        {
            "station": stations[st_id].name,
            "product": products[pr_id].name,
            "fpy": round(100.0 * v["conforming"] / v["processed"], 1) if v["processed"] else None,
            "units_processed": v["processed"],
        }
        for (st_id, pr_id), v in matrix_agg.items()
    ]

    return {
        "pareto": pareto,
        "defects_by_station": defects_by_station_out,
        "defects_by_product": defects_by_product_out,
        "fpy_by_shift": fpy_by_shift_out,
        "rework_by_cause": rework_by_cause_out,
        "weekly_trend": weekly_trend,
        "blocked_units": blocked_units,
        "validation_failures": validation_failures,
        "station_product_matrix": station_product_matrix,
        "note": "Los defectos se clasifican por causa (proceso, material, equipo, programa, diseño, método, "
        "posible error operativo o causa sin confirmar). No se atribuyen automáticamente al operador.",
    }
