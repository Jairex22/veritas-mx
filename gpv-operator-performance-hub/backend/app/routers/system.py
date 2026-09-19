"""
Estado de conexión con FactoryLogix y botón "Actualizar datos" de la barra
superior. En este demo, actualizar datos intenta una sincronización real si
`FACTORYLOGIX_ENABLED=true`; si falla o está desactivado, se informa
claramente que se están usando los últimos datos simulados/válidos
disponibles (modo offline), nunca se falla en silencio.
"""
from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..audit import log_action
from ..config import get_settings
from ..database import get_db
from ..integrations.factorylogix.client import FactoryLogixClient, FactoryLogixConnectionError, ODataQuery
from ..security import CurrentUser, get_current_user

router = APIRouter(prefix="/api/system", tags=["Sistema"])
settings = get_settings()

_sync_state = {
    "last_sync": datetime.utcnow().isoformat(),
    "status": "simulado",
    "message": "Usando datos simulados de demostración.",
}


@router.get("/status")
def system_status(current_user: CurrentUser = Depends(get_current_user)):
    return {
        "plant_name": settings.plant_name,
        "environment": settings.environment,
        "factorylogix_enabled": settings.flx_enabled,
        **_sync_state,
    }


@router.post("/sync")
def trigger_sync(db: Session = Depends(get_db), current_user: CurrentUser = Depends(get_current_user)):
    if not settings.flx_enabled:
        _sync_state.update(
            {
                "last_sync": datetime.utcnow().isoformat(),
                "status": "simulado",
                "message": "FactoryLogix no está habilitado. Se muestran los datos simulados de demostración.",
            }
        )
        return _sync_state

    client = FactoryLogixClient()
    try:
        client.fetch_entity(ODataQuery(entity=settings.flx_entity_production_activity, top=1))
        _sync_state.update(
            {
                "last_sync": datetime.utcnow().isoformat(),
                "status": "conectado",
                "message": "Sincronización con FactoryLogix completada.",
            }
        )
    except FactoryLogixConnectionError as exc:
        _sync_state.update(
            {
                "last_sync": _sync_state["last_sync"],
                "status": "offline",
                "message": "No fue posible consultar FactoryLogix. Se muestran los últimos datos disponibles.",
            }
        )
        log_action(
            db, username=current_user.username, role=current_user.role, action="Fallo de sincronización FactoryLogix",
            details=str(exc),
        )

    return _sync_state
