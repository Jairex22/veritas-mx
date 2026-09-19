"""
Comparaciones entre operadores "equivalentes": misma estación, mismo producto y
mismo turno. Nunca se comparan operadores de contextos distintos sin normalizar.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from ..analytics import _date_range, _events_query, events_to_samples, get_scoring_weights
from ..database import get_db
from ..models import Operator, Product, Station
from ..scoring import compute_score
from ..security import CurrentUser, get_current_user

router = APIRouter(prefix="/api/comparisons", tags=["Comparaciones"])


@router.get("")
def compare_equivalent_operators(
    station_id: int,
    product_id: int | None = None,
    shift: str | None = None,
    period_days: int = Query(30, ge=1, le=90),
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    weights = get_scoring_weights(db)
    start_date, end_date = _date_range(period_days)

    events = _events_query(db, start_date, end_date, shift=shift, station_id=station_id).all()
    if product_id:
        events = [e for e in events if e.product_id == product_id]

    stations = {s.id: s for s in db.query(Station).all()}
    operators = {o.id: o for o in db.query(Operator).all()}

    by_operator: dict[int, list] = {}
    for e in events:
        by_operator.setdefault(e.operator_id, []).append(e)

    results = []
    for op_id, op_events in by_operator.items():
        samples = events_to_samples(op_events, stations)
        result = compute_score(samples, weights)
        op = operators[op_id]
        results.append(
            {
                "operator_id": op.id,
                "employee_number": op.employee_number,
                "full_name": op.full_name,
                "shift": op.shift.value,
                "score": result.score,
                "classification": result.classification,
                "data_confidence": result.data_confidence,
                "sample_size": result.sample_size,
                "units_processed": sum(e.units_processed for e in op_events),
            }
        )
    results.sort(key=lambda r: (r["score"] is None, -(r["score"] or 0)))

    station = stations.get(station_id)
    product = db.get(Product, product_id) if product_id else None

    return {
        "context": {
            "station": station.name if station else None,
            "product": product.name if product else "Todos los productos de la estación",
            "shift": shift or "Todos los turnos",
            "period_days": period_days,
        },
        "items": results,
        "note": "Sólo se comparan operadores que trabajaron en la misma estación (y producto, si se filtró) "
        "durante el mismo periodo. Verifica el turno y el nivel de confianza antes de sacar conclusiones.",
    }
