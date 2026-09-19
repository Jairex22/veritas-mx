from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from ..analytics import build_performance_rows, station_summary
from ..database import get_db
from ..models import Certification, Operator
from ..security import CurrentUser, get_current_user
from datetime import date, timedelta

router = APIRouter(prefix="/api/alerts", tags=["Alertas"])


@router.get("")
def list_alerts(
    period_days: int = Query(30, ge=1, le=90),
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    alerts: list[dict] = []

    for st in station_summary(db, period_days=period_days):
        for alert_text in st["alerts"]:
            alerts.append(
                {
                    "category": "Estación",
                    "severity": "bad" if "FPY" in alert_text else "warning",
                    "title": st["name"],
                    "detail": alert_text,
                    "context": "Posible causa de proceso; revisar antes de asociarlo a un operador específico.",
                }
            )

    rows = build_performance_rows(db, period_days=period_days)
    for r in rows:
        if r["classification"] == "Requiere apoyo":
            alerts.append(
                {
                    "category": "Operador",
                    "severity": "bad",
                    "title": r["full_name"],
                    "detail": f"Puntaje {r['score']} en {r['main_station']} — confianza de datos: {r['data_confidence']}",
                    "context": "Revisa el contexto del turno antes de asignar una acción de capacitación.",
                }
            )
        elif r["classification"] == "Datos insuficientes" and r["units_processed"] > 0:
            alerts.append(
                {
                    "category": "Cobertura de datos",
                    "severity": "neutral",
                    "title": r["full_name"],
                    "detail": "Todavía no hay suficientes unidades para calcular una tendencia confiable.",
                    "context": "",
                }
            )

    soon = date.today() + timedelta(days=30)
    expiring = (
        db.query(Certification)
        .filter(Certification.expires_at.isnot(None), Certification.expires_at <= soon, Certification.expires_at >= date.today())
        .all()
    )
    operators = {o.id: o for o in db.query(Operator).all()}
    for c in expiring:
        op = operators.get(c.operator_id)
        if not op:
            continue
        alerts.append(
            {
                "category": "Certificación",
                "severity": "warning",
                "title": op.full_name,
                "detail": f"Certificación vence el {c.expires_at.isoformat()}.",
                "context": "Planear renovación antes del vencimiento.",
            }
        )

    order = {"bad": 0, "warning": 1, "neutral": 2}
    alerts.sort(key=lambda a: order.get(a["severity"], 3))
    return {"items": alerts, "total": len(alerts)}
