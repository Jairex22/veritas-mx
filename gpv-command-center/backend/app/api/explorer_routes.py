"""Consulta directa OData: conexión por sesión, búsqueda por valor y exploración de entidades."""
from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from ..container import Container
from ..core.errors import DataSourceUnavailable
from ..core.security import SessionUser
from .deps import container, current_user

router = APIRouter(prefix="/api/explorer", tags=["consulta directa"])
IDENT = r"^[A-Za-z_][A-Za-z0-9_./]{0,127}$"


class ConnectRequest(BaseModel):
    base_url: str = Field("", max_length=300)
    auth: str = Field("none", pattern=r"^(none|basic|ntlm)$")
    username: str = Field("", max_length=120)
    password: str = Field("", max_length=200)
    use_server_config: bool = False


class SearchRequest(BaseModel):
    value: str = Field(..., min_length=1, max_length=128)
    entity_set: str | None = Field(None, pattern=IDENT)
    property: str | None = Field(None, pattern=IDENT)
    match: str = Field("eq", pattern=r"^(eq|contains)$")
    top: int = Field(200, ge=1, le=500)


class RowsRequest(BaseModel):
    entity_set: str = Field(..., pattern=IDENT)
    top: int = Field(50, ge=1, le=500)
    orderby: str | None = Field(None, pattern=r"^[A-Za-z_][A-Za-z0-9_./]{0,127}( (asc|desc))?$")


def _session(c: Container, user: SessionUser):
    sess = c.explorer.get(user.username)
    if sess is None:
        raise DataSourceUnavailable("No hay conexión OData activa en su sesión. Conecte primero.", code="EXPLORER_NOT_CONNECTED")
    return sess


@router.get("/status")
def status(user: SessionUser = Depends(current_user), c: Container = Depends(container)) -> dict:
    user.require("odata.explore")
    sess = c.explorer.get(user.username)
    return {"connected": sess is not None and sess.state == "OK", "session": sess.public() if sess else None,
            "server_default_url": c.settings.odata_base_url, "server_auth": c.settings.odata_auth if c.settings.odata_base_url else None}


@router.post("/connect")
def connect(body: ConnectRequest, user: SessionUser = Depends(current_user), c: Container = Depends(container)) -> dict:
    user.require("odata.explore")
    s = c.settings
    if body.use_server_config and s.odata_base_url:
        sess = c.explorer.connect(user.username, s.odata_base_url, s.odata_auth if s.odata_auth in ("basic", "ntlm") else "none",
                                  s.odata_username, s.odata_password)
    else:
        sess = c.explorer.connect(user.username, body.base_url, body.auth, body.username, body.password)
    c.audit.record(category="CONFIG", action="explorer.connect", outcome=sess.state, username=user.username,
                   role=user.role.value, target=sess.base_url,
                   details={"auth": sess.auth_kind, "entity_sets": len(sess.metadata.get("entity_sets", []))})
    return {"session": sess.public(), "entity_sets": sess.metadata.get("entity_sets", [])}


@router.post("/disconnect")
def disconnect(user: SessionUser = Depends(current_user), c: Container = Depends(container)) -> dict:
    user.require("odata.explore")
    c.explorer.disconnect(user.username)
    return {"ok": True}


@router.post("/search")
def search(body: SearchRequest, user: SessionUser = Depends(current_user), c: Container = Depends(container)) -> dict:
    user.require("odata.explore")
    sess = _session(c, user)
    result = c.explorer.search(sess, body.value, entity_set=body.entity_set, prop=body.property, match=body.match, top=body.top)
    c.audit.record(category="CONFIG", action="explorer.search", outcome="OK", username=user.username, role=user.role.value,
                   target=body.value, details={"queries": result["queries"], "hits": len(result["hits"]),
                                               "serials": len(result["serials"]), "errors": result["error_count"]})
    return result


@router.post("/rows")
def rows(body: RowsRequest, user: SessionUser = Depends(current_user), c: Container = Depends(container)) -> dict:
    user.require("odata.explore")
    sess = _session(c, user)
    data = c.explorer.rows(sess, body.entity_set, body.top, orderby=body.orderby)
    return {"entity_set": body.entity_set, "rows": data, "columns": c.explorer._columns(data), "count": len(data)}
