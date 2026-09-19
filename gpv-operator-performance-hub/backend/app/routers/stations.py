from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from ..analytics import station_summary
from ..database import get_db
from ..security import CurrentUser, get_current_user

router = APIRouter(prefix="/api/stations", tags=["Estaciones"])


@router.get("")
def list_stations(
    period_days: int = Query(30, ge=1, le=90),
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    return {"items": station_summary(db, period_days=period_days)}
