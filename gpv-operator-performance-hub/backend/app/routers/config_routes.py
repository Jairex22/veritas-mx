from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..audit import log_action
from ..config import get_settings
from ..database import get_db
from ..models import ScoringConfig
from ..schemas import ScoringConfigOut, ScoringConfigUpdate
from ..security import CurrentUser, get_current_user, require_admin_or_engineer

router = APIRouter(prefix="/api/config", tags=["Configuración"])
settings = get_settings()


@router.get("/scoring", response_model=ScoringConfigOut)
def get_scoring_config(db: Session = Depends(get_db), current_user: CurrentUser = Depends(get_current_user)):
    cfg = db.query(ScoringConfig).order_by(ScoringConfig.id.desc()).first()
    if not cfg:
        raise HTTPException(404, "No hay configuración de puntaje registrada.")
    return cfg


@router.put("/scoring", response_model=ScoringConfigOut)
def update_scoring_config(
    payload: ScoringConfigUpdate,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(require_admin_or_engineer),
):
    total_weight = (
        payload.weight_quality + payload.weight_cycle + payload.weight_productivity
        + payload.weight_consistency + payload.weight_rework
    )
    if total_weight <= 0:
        raise HTTPException(400, "La suma de los pesos debe ser mayor a cero.")

    cfg = db.query(ScoringConfig).order_by(ScoringConfig.id.desc()).first()
    if not cfg:
        cfg = ScoringConfig()
        db.add(cfg)

    cfg.weight_quality = payload.weight_quality
    cfg.weight_cycle = payload.weight_cycle
    cfg.weight_productivity = payload.weight_productivity
    cfg.weight_consistency = payload.weight_consistency
    cfg.weight_rework = payload.weight_rework
    cfg.min_units_for_classification = payload.min_units_for_classification
    cfg.updated_at = datetime.utcnow()
    cfg.updated_by = current_user.display_name or current_user.username
    db.commit()
    db.refresh(cfg)

    log_action(
        db, username=current_user.username, role=current_user.role, action="Actualización de pesos de puntaje",
        entity="ScoringConfig", details=str(payload.model_dump()),
    )
    return cfg


@router.get("/connection")
def connection_status(current_user: CurrentUser = Depends(get_current_user)):
    return {
        "factorylogix_enabled": settings.flx_enabled,
        "base_url_configured": bool(settings.flx_base_url),
        "using_simulated_data": settings.use_simulated_data or not settings.flx_enabled,
        "plant_name": settings.plant_name,
        "timezone": settings.timezone,
    }
