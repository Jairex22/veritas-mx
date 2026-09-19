from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Certification, Operator, Station
from ..security import CurrentUser, get_current_user

router = APIRouter(prefix="/api/training", tags=["Capacitación"])


@router.get("/matrix")
def training_matrix(db: Session = Depends(get_db), current_user: CurrentUser = Depends(get_current_user)):
    certifications = db.query(Certification).all()
    operators = {o.id: o for o in db.query(Operator).all()}
    stations = {s.id: s for s in db.query(Station).all()}

    items = []
    for c in certifications:
        op = operators.get(c.operator_id)
        st = stations.get(c.station_id)
        if not op or not st:
            continue
        items.append(
            {
                "operator_id": op.id,
                "employee_number": op.employee_number,
                "operator_name": op.full_name,
                "station": st.name,
                "level": c.level.value,
                "certified_at": c.certified_at.isoformat() if c.certified_at else None,
                "expires_at": c.expires_at.isoformat() if c.expires_at else None,
                "reinforcement_needed": c.reinforcement_needed,
                "recommended_course": c.recommended_course,
                "plan_status": c.plan_status,
            }
        )
    return {"items": items}
