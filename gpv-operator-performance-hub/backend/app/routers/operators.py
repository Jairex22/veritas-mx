from __future__ import annotations

from collections import Counter, defaultdict
from datetime import date, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..analytics import _date_range, _events_query, build_operator_score, events_to_samples, get_scoring_weights
from ..audit import log_action
from ..database import get_db
from ..models import (
    Certification,
    Operator,
    ProductionEvent,
    QualityEvent,
    Station,
    SupervisorNote,
    TrainingAction,
    WorkOrder,
)
from ..schemas import SupervisorNoteCreate, TrainingActionCreate
from ..scoring import compute_score
from ..security import CurrentUser, get_current_user, require_supervisor_or_above

router = APIRouter(prefix="/api/operators", tags=["Operadores"])


def _serialize_score(result):
    return {
        "score": result.score,
        "classification": result.classification,
        "data_confidence": result.data_confidence,
        "sample_size": result.sample_size,
        "distinct_days": result.distinct_days,
        "breakdown": [b.__dict__ for b in result.breakdown],
        "explanation": result.explanation,
        "disclaimer": result.disclaimer,
    }


@router.get("")
def list_operators(
    shift: str | None = None,
    area: str | None = None,
    search: str | None = None,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    q = db.query(Operator).filter(Operator.is_active.is_(True))
    if shift:
        q = q.filter(Operator.shift == shift)
    if area:
        q = q.filter(Operator.area == area)
    if search:
        like = f"%{search.lower()}%"
        from sqlalchemy import func

        q = q.filter(func.lower(Operator.full_name).like(like) | func.lower(Operator.employee_number).like(like))
    operators = q.order_by(Operator.full_name).all()

    cert_counts = defaultdict(int)
    for c in db.query(Certification).all():
        cert_counts[c.operator_id] += 1

    start_30, end_30 = _date_range(30)
    last_activity_map = {}
    for e in _events_query(db, start_30, end_30).all():
        current = last_activity_map.get(e.operator_id)
        if current is None or e.event_date > current:
            last_activity_map[e.operator_id] = e.event_date

    return {
        "items": [
            {
                "id": op.id,
                "employee_number": op.employee_number,
                "full_name": op.full_name,
                "shift": op.shift.value,
                "area": op.area,
                "hire_date": op.hire_date.isoformat(),
                "is_new_hire": op.is_new_hire,
                "authorized_station_count": cert_counts.get(op.id, 0),
                "last_activity": last_activity_map.get(op.id).isoformat() if op.id in last_activity_map else None,
            }
            for op in operators
        ]
    }


@router.get("/{operator_id}")
def operator_detail(operator_id: int, db: Session = Depends(get_db), current_user: CurrentUser = Depends(get_current_user)):
    op = db.get(Operator, operator_id)
    if not op:
        raise HTTPException(404, "No se encontró al operador solicitado.")

    weights = get_scoring_weights(db)
    stations = {s.id: s for s in db.query(Station).all()}

    trends = {}
    for label, days in (("d7", 7), ("d30", 30), ("d90", 90)):
        start_date, end_date = _date_range(days)
        result, _events = build_operator_score(db, operator_id, start_date, end_date, weights)
        trends[label] = _serialize_score(result)

    # Producción por día (90 días) para la gráfica.
    start_90, end_90 = _date_range(90)
    events_90 = _events_query(db, start_90, end_90, operator_id=operator_id).all()
    daily = defaultdict(lambda: {"processed": 0, "conforming": 0, "rejected": 0, "reworked": 0})
    for e in events_90:
        d = daily[e.event_date.isoformat()]
        d["processed"] += e.units_processed
        d["conforming"] += e.units_conforming
        d["rejected"] += e.units_rejected
        d["reworked"] += e.units_reworked
    daily_series = [
        {"date": d, **v, "fpy": round(100.0 * v["conforming"] / v["processed"], 1) if v["processed"] else None}
        for d, v in sorted(daily.items())
    ]

    # Historial por estación.
    station_agg = defaultdict(lambda: {"processed": 0, "conforming": 0, "cycle_times": []})
    for e in events_90:
        agg = station_agg[e.station_id]
        agg["processed"] += e.units_processed
        agg["conforming"] += e.units_conforming
        agg["cycle_times"].append(e.cycle_time_seconds)
    station_history = []
    for st_id, agg in station_agg.items():
        st = stations[st_id]
        avg_cycle = sum(agg["cycle_times"]) / len(agg["cycle_times"]) if agg["cycle_times"] else 0
        station_history.append(
            {
                "station": st.name,
                "units_processed": agg["processed"],
                "fpy": round(100.0 * agg["conforming"] / agg["processed"], 1) if agg["processed"] else None,
                "avg_cycle_time_seconds": round(avg_cycle, 1),
                "standard_cycle_seconds": st.standard_cycle_seconds,
                "compliance_pct": round(100.0 * st.standard_cycle_seconds / avg_cycle, 1) if avg_cycle else None,
            }
        )
    station_history.sort(key=lambda x: x["units_processed"], reverse=True)

    # Comparación contra el promedio del grupo equivalente (misma área, mismo turno).
    peers = db.query(Operator).filter(Operator.area == op.area, Operator.shift == op.shift, Operator.id != op.id).all()
    peer_scores = []
    for peer in peers:
        peer_result, _ = build_operator_score(db, peer.id, start_90, end_90, weights)
        if peer_result.score is not None:
            peer_scores.append(peer_result.score)
    group_average = round(sum(peer_scores) / len(peer_scores), 1) if peer_scores else None

    # Productos y work orders trabajados: combinaciones más frecuentes en el periodo.
    from ..models import Product

    product_counter = Counter((e.product_id, e.work_order_id) for e in events_90)

    products_map = {p.id: p for p in db.query(Product).all()}
    wo_map = {w.id: w for w in db.query(WorkOrder).all()}
    products_worked = [
        {
            "product": products_map[pid].name,
            "work_order": wo_map[wid].code if wid in wo_map else "—",
            "units": count,
        }
        for (pid, wid), count in product_counter.most_common(8)
    ]

    certifications = (
        db.query(Certification).filter(Certification.operator_id == operator_id).all()
    )
    certifications_out = [
        {
            "station": stations[c.station_id].name,
            "level": c.level.value,
            "certified_at": c.certified_at.isoformat() if c.certified_at else None,
            "expires_at": c.expires_at.isoformat() if c.expires_at else None,
            "reinforcement_needed": c.reinforcement_needed,
            "recommended_course": c.recommended_course,
            "plan_status": c.plan_status,
        }
        for c in certifications
    ]
    authorized_stations = [c["station"] for c in certifications_out]

    # Contexto del resultado: factores detectados automáticamente.
    context_factors = []
    if op.is_new_hire:
        context_factors.append("Operador nuevo: ingreso registrado hace menos de 30 días.")
    if trends["d30"]["sample_size"] < weights.min_units:
        context_factors.append("Baja cantidad de muestras en los últimos 30 días.")
    small_batch_ratio = 0
    rework_events = sum(1 for e in events_90 if e.is_rework_pass)
    if rework_events > 0:
        context_factors.append(f"Se registraron {rework_events} pases de retrabajo en el periodo de 90 días.")
    down_events = sum(1 for e in events_90 if e.station_was_down)
    if down_events > 0:
        context_factors.append(f"La estación reportó paros en {down_events} evento(s) durante su turno.")
    if not context_factors:
        context_factors.append("No se detectaron factores contextuales relevantes en el periodo analizado.")

    notes = (
        db.query(SupervisorNote)
        .filter(SupervisorNote.operator_id == operator_id)
        .order_by(SupervisorNote.created_at.desc())
        .all()
    )
    training_actions = (
        db.query(TrainingAction)
        .filter(TrainingAction.operator_id == operator_id)
        .order_by(TrainingAction.created_at.desc())
        .all()
    )

    recommendations = []
    for c in certifications_out:
        if c["reinforcement_needed"]:
            recommendations.append(f"Reforzamiento sugerido en {c['station']}: {c['recommended_course']}")
    if trends["d30"]["classification"] == "Requiere apoyo":
        recommendations.append(
            "Revisar contexto del turno antes de asignar una acción de capacitación; el resultado puede deberse al proceso."
        )
    if not recommendations:
        recommendations.append("Sin recomendaciones activas por el momento.")

    last_activity = max((e.event_date for e in events_90), default=None)

    return {
        "operator": {
            "id": op.id,
            "employee_number": op.employee_number,
            "full_name": op.full_name,
            "shift": op.shift.value,
            "area": op.area,
            "hire_date": op.hire_date.isoformat(),
            "is_new_hire": op.is_new_hire,
            "last_activity": last_activity.isoformat() if last_activity else None,
            "authorized_stations": authorized_stations,
        },
        "trends": trends,
        "daily_series": daily_series,
        "station_history": station_history,
        "group_comparison": {"operator_score_90d": trends["d90"]["score"], "group_average_90d": group_average},
        "products_worked": products_worked,
        "certifications": certifications_out,
        "context_factors": context_factors,
        "recommendations": recommendations,
        "supervisor_notes": [
            {"author": n.author, "note": n.note, "created_at": n.created_at.isoformat()} for n in notes
        ],
        "training_actions": [
            {
                "action_type": t.action_type,
                "description": t.description,
                "status": t.status,
                "created_at": t.created_at.isoformat(),
                "created_by": t.created_by,
            }
            for t in training_actions
        ],
    }


@router.post("/training-actions")
def create_training_action(
    payload: TrainingActionCreate,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(require_supervisor_or_above),
):
    op = db.get(Operator, payload.operator_id)
    if not op:
        raise HTTPException(404, "No se encontró al operador solicitado.")
    action = TrainingAction(
        operator_id=payload.operator_id,
        station_id=payload.station_id,
        created_at=date.today(),
        action_type=payload.action_type,
        description=payload.description,
        status="Propuesta",
        created_by=current_user.display_name or current_user.username,
    )
    db.add(action)
    db.commit()
    log_action(
        db, username=current_user.username, role=current_user.role, action="Acción de capacitación registrada",
        entity="Operator", entity_id=payload.operator_id, details=payload.description,
    )
    return {"status": "ok"}


@router.post("/supervisor-notes")
def create_supervisor_note(
    payload: SupervisorNoteCreate,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(require_supervisor_or_above),
):
    op = db.get(Operator, payload.operator_id)
    if not op:
        raise HTTPException(404, "No se encontró al operador solicitado.")
    note = SupervisorNote(
        operator_id=payload.operator_id,
        created_at=datetime.utcnow(),
        author=current_user.display_name or current_user.username,
        note=payload.note,
    )
    db.add(note)
    db.commit()
    log_action(
        db, username=current_user.username, role=current_user.role, action="Observación de supervisor registrada",
        entity="Operator", entity_id=payload.operator_id, details=payload.note,
    )
    return {"status": "ok"}
