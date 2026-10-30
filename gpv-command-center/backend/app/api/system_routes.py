"""Estado del sistema, conectores, auditoría y utilidades DEMO."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Path, Query

from ..connectors.base import ConnectorState
from ..container import Container
from ..core.errors import Forbidden, NotFound
from ..core.security import SessionUser
from ..data.demo import DemoDataSource
from ..settings import APP_VERSION
from .deps import container, current_user

router = APIRouter(prefix="/api", tags=["sistema"])


def environment_badges(c: Container) -> dict:
    s = c.settings
    prov = c.source.provenance()
    badges = []
    if s.is_demo:
        badges.append({"id": "DEMO", "label": "DEMO", "tone": "demo",
                       "description": "Datos sintéticos. Ninguna acción alcanza FactoryLogix."})
        connection = {"state": "SIMULADO", "label": "Simulado", "tone": "demo"}
    else:
        badges.append({"id": "REAL", "label": "REAL", "tone": "info",
                       "description": "Datos de fuentes reales configuradas; sin datos sintéticos."})
        conn_ok = False
        if prov["kind"] == "ODATA":
            conn_ok = c.connectors.odata.status().state == ConnectorState.OK
        elif prov["kind"] == "AUX_FILE":
            conn_ok = c.connectors.aux.status().state == ConnectorState.OK
        if conn_ok:
            badges.append({"id": "CONECTADO", "label": "CONECTADO", "tone": "ok",
                           "description": f"Fuente activa verificada: {prov['label']}."})
            connection = {"state": "CONECTADO", "label": "Conectado", "tone": "ok"}
        else:
            connection = {"state": "SIN_CONEXION_VERIFICADA", "label": "Sin conexión verificada", "tone": "error"}
    writes_real = bool(c.operations.real_executors) and s.allow_production_writes and not s.is_demo
    if writes_real:
        badges.append({"id": "PRODUCCION", "label": "PRODUCCIÓN", "tone": "danger",
                       "description": "Escrituras reales habilitadas en FactoryLogix."})
    elif not s.is_demo:
        badges.append({"id": "SOLO_LECTURA", "label": "SOLO LECTURA", "tone": "warn",
                       "description": "No hay transacciones oficiales verificadas; las escrituras están deshabilitadas."})
    return {"badges": badges, "connection": connection, "writes": "REAL" if writes_real else
            ("SIMULADAS" if s.is_demo else "DESHABILITADAS")}


@router.get("/system/status")
def system_status(c: Container = Depends(container)) -> dict:
    # Público (sin datos sensibles): necesario para la pantalla de login.
    env = environment_badges(c)
    return {"app": "GPV FactoryLogix Command Center", "version": APP_VERSION, "mode": c.settings.mode.value,
            "data_source": c.source.provenance(), "source_note": c.source_note or getattr(c.source, "reason", ""),
            **env}


@router.get("/connectors")
def connectors(user: SessionUser = Depends(current_user), c: Container = Depends(container)) -> dict:
    user.require("connectors.read")
    s = c.settings
    return {
        "connectors": c.connectors.statuses(),
        "active_source": c.source.provenance(),
        "source_note": c.source_note or getattr(c.source, "reason", ""),
        "configuration": {
            "mode": s.mode.value, "real_data_source": s.real_data_source,
            "odata_mapping_file": str(s.config_dir / s.odata_mapping_file),
            "http_timeout_seconds": s.http_timeout_seconds, "verify_tls": s.verify_tls, "ca_bundle": bool(s.ca_bundle),
            "allow_production_writes": s.allow_production_writes,
            "real_executors_registered": sorted(c.operations.real_executors),
            "managed_by": "Variables de entorno del servidor (.env). Las credenciales nunca se exponen al navegador.",
        },
    }


@router.post("/connectors/{cid}/probe")
def probe(cid: str = Path(..., pattern=r"^[a-z_]{2,20}$"), user: SessionUser = Depends(current_user),
          c: Container = Depends(container)) -> dict:
    user.require("connectors.probe")
    conn = c.connectors.get(cid)
    if conn is None:
        raise NotFound(f"Conector '{cid}' desconocido.")
    status = conn.probe().to_dict()
    c.audit.record(category="CONFIG", action="connector.probe", outcome=status["state"], username=user.username,
                   role=user.role.value, target=cid,
                   details={"http_status": status["http_status"], "message": status["message"]})
    return status


@router.get("/audit")
def audit(category: str | None = Query(None, pattern="^[A-Z]{3,12}$"), q: str | None = Query(None, max_length=64),
          limit: int = Query(200, ge=1, le=1000), user: SessionUser = Depends(current_user),
          c: Container = Depends(container)) -> dict:
    user.require("audit.read")
    return {"entries": c.audit.list(category=category, limit=limit, search=q), "integrity": c.audit.verify_chain()}


@router.get("/audit/access")
def access(limit: int = Query(200, ge=1, le=1000), user: SessionUser = Depends(current_user),
           c: Container = Depends(container)) -> dict:
    user.require("audit.read")
    return {"entries": c.audit.list_access(limit)}


@router.post("/demo/reset")
def demo_reset(user: SessionUser = Depends(current_user), c: Container = Depends(container)) -> dict:
    user.require("demo.reset")
    if not c.settings.is_demo or not isinstance(c.source, DemoDataSource):
        raise Forbidden("Sólo disponible en modo DEMO.")
    c.source.reset()
    c.audit.record(category="SYSTEM", action="demo.reset", outcome="SUCCESS", username=user.username, role=user.role.value)
    return {"ok": True}

