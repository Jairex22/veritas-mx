"""Asistente de mapeo OData: descubrimiento, muestreo, prueba y activación.

Todas las llamadas a FactoryLogix son GET de sólo lectura. El mapeo resultante
se guarda en config/<GPV_ODATA_MAPPING_FILE> firmado con el usuario que lo
verificó, y la fuente de datos se recarga sin reiniciar el servicio.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field

from ..connectors.factorylogix import load_json_config
from ..container import Container
from ..core.errors import Forbidden, NotAvailable
from ..core.security import SessionUser
from ..data.external import MAPPING_SCHEMA, clean_mapping, preview_mapping, validate_odata_mapping
from .deps import container, current_user

router = APIRouter(prefix="/api/connectors/odata", tags=["odata"])
IDENT = r"^[A-Za-z_][A-Za-z0-9_./]{0,127}$"


class SampleRequest(BaseModel):
    entity_set: str = Field(..., pattern=IDENT)
    top: int = Field(10, ge=1, le=50)
    select: list[str] = Field(default_factory=list, max_length=40)
    orderby: str | None = Field(None, pattern=r"^[A-Za-z_][A-Za-z0-9_./]{0,127}( (asc|desc))?$")


class MappingRequest(BaseModel):
    mapping: dict[str, Any]
    top: int = Field(50, ge=5, le=200)


class SaveRequest(BaseModel):
    mapping: dict[str, Any]
    activate: bool = False
    confirm_verified: bool = False


def _schema_public() -> dict:
    return {sec: {"label": v["label"], "required": v["required"],
                  "fields": [{"name": f, "label": lbl, "required": req} for f, (lbl, req) in v["fields"].items()],
                  "value_maps": v["value_maps"]} for sec, v in MAPPING_SCHEMA.items()}


@router.get("/metadata")
def metadata(refresh: bool = Query(False), user: SessionUser = Depends(current_user),
             c: Container = Depends(container)) -> dict:
    user.require("connectors.probe")
    meta = c.connectors.odata.metadata(refresh=refresh)
    c.audit.record(category="CONFIG", action="odata.metadata", outcome="OK", username=user.username,
                   role=user.role.value, details={"entity_sets": len(meta["entity_sets"]), "version": meta.get("version")})
    return {"base_url": c.settings.odata_base_url, **meta}


@router.post("/sample")
def sample(body: SampleRequest, user: SessionUser = Depends(current_user), c: Container = Depends(container)) -> dict:
    user.require("connectors.probe")
    rows = c.connectors.odata.sample(body.entity_set, body.top, body.select or None, body.orderby)
    columns: list[str] = []
    for r in rows:
        for k in r:
            if k not in columns and not str(k).startswith("@") and not str(k).startswith("__"):
                columns.append(str(k))
    c.audit.record(category="CONFIG", action="odata.sample", outcome="OK", username=user.username, role=user.role.value,
                   target=body.entity_set, details={"rows": len(rows), "top": body.top})
    return {"entity_set": body.entity_set, "rows": rows, "columns": columns, "count": len(rows),
            "note": "Muestra de sólo lectura obtenida con $top; no se modificó nada en FactoryLogix."}


@router.get("/mapping")
def get_mapping(user: SessionUser = Depends(current_user), c: Container = Depends(container)) -> dict:
    user.require("connectors.read")
    s = c.settings
    current = load_json_config(s.config_dir, s.odata_mapping_file)
    errors = validate_odata_mapping(current) if current is not None else ["No existe archivo de mapeo."]
    active = c.source.provenance()["kind"] == "ODATA"
    return {"path": str(s.config_dir / s.odata_mapping_file), "mapping": current, "errors": errors, "active": active,
            "mode": s.mode.value, "real_data_source": s.real_data_source, "schema": _schema_public(),
            "can_configure": user.role.value == "admin"}


@router.post("/mapping/test")
def test_mapping(body: MappingRequest, user: SessionUser = Depends(current_user),
                 c: Container = Depends(container)) -> dict:
    user.require("connectors.probe")
    mapping = clean_mapping(body.mapping)
    report = preview_mapping(c.connectors.odata, mapping, top=body.top)
    c.audit.record(category="CONFIG", action="odata.mapping.test", outcome="OK" if report["ok"] else "WARNINGS",
                   username=user.username, role=user.role.value,
                   details={"units_built": report["units_built"], "warnings": report["warnings"][:10]})
    return {"mapping": mapping, "report": report}


@router.post("/mapping/save")
def save_mapping(body: SaveRequest, user: SessionUser = Depends(current_user),
                 c: Container = Depends(container)) -> dict:
    user.require("connectors.configure")
    if not body.confirm_verified:
        raise Forbidden("Debe confirmar que el mapeo fue verificado contra la instalación de FactoryLogix.",
                        code="MAPPING_NOT_CONFIRMED")
    mapping = clean_mapping(body.mapping)
    mapping["verified"] = True
    mapping["verified_by"] = user.username
    mapping["verified_on"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    s = c.settings
    path = s.config_dir / s.odata_mapping_file
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(mapping, indent=2, ensure_ascii=False), encoding="utf-8")
    result: dict[str, Any] = {"saved": str(path), "mapping": mapping, "activated": False, "source": None}
    if body.activate:
        if s.is_demo:
            raise NotAvailable("La activación de OData requiere GPV_MODE=REAL. En DEMO sólo se guardó el archivo.",
                               code="ACTIVATION_REQUIRES_REAL")
        if s.real_data_source != "odata":
            s.real_data_source = "odata"
            result["note"] = ("Fuente cambiada a OData en memoria. Para que persista tras un reinicio, defina "
                              "GPV_REAL_DATA_SOURCE=odata en el .env del servidor.")
        src = c.reload_source()
        result["activated"] = src.provenance()["kind"] == "ODATA"
        result["source"] = src.provenance()
        if not result["activated"]:
            result["note"] = c.source_note or getattr(src, "reason", "")
    c.audit.record(category="CONFIG", action="odata.mapping.save", outcome="ACTIVATED" if result["activated"] else "SAVED",
                   username=user.username, role=user.role.value, target=str(path),
                   details={"events_entity_set": mapping["events"]["entity_set"], "activate": body.activate})
    return result
