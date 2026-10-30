"""Operaciones controladas, packing y etiquetas."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Path
from pydantic import BaseModel, Field

from ..container import Container
from ..core.security import SessionUser
from ..services.operations import validate_packing
from .deps import container, current_user

router = APIRouter(prefix="/api", tags=["operaciones"])
ACTION_ID = Path(..., pattern=r"^[a-z_]{3,40}$")


class PrepareRequest(BaseModel):
    params: dict[str, Any] = Field(default_factory=dict)


class ExecuteRequest(BaseModel):
    params: dict[str, Any] = Field(default_factory=dict)
    confirmation_token: str = Field(..., min_length=10, max_length=4000)
    idempotency_key: str = Field(..., min_length=16, max_length=64)
    confirm: bool = False


class PackingValidateRequest(BaseModel):
    box_id: str = Field(..., pattern=r"^[A-Za-z0-9\-]{3,40}$")
    serials: list[str] = Field(default_factory=list, max_length=60)


class LabelPreviewRequest(BaseModel):
    template_id: str = Field(..., pattern=r"^[A-Za-z0-9_\-]{2,60}$")
    data: dict[str, str] = Field(default_factory=dict)


class LabelPrintRequest(LabelPreviewRequest):
    printer_id: str = Field(..., pattern=r"^[A-Za-z0-9_\-]{2,60}$")
    reason: str = Field("", max_length=240)


@router.get("/operations/catalog")
def catalog(user: SessionUser = Depends(current_user), c: Container = Depends(container)) -> dict:
    user.require("operations.read")
    return {"mode": c.settings.mode.value, "role": user.role.value, "actions": c.operations.catalog()}


@router.post("/operations/{action_id}/prepare")
def prepare(body: PrepareRequest, action_id: str = ACTION_ID, user: SessionUser = Depends(current_user),
            c: Container = Depends(container)) -> dict:
    return c.operations.prepare(action_id, body.params, user)


@router.post("/operations/{action_id}/execute")
def execute(body: ExecuteRequest, action_id: str = ACTION_ID, user: SessionUser = Depends(current_user),
            c: Container = Depends(container)) -> dict:
    return c.operations.execute(action_id, body.params, body.confirmation_token, body.idempotency_key, body.confirm, user)


@router.get("/packing/box/{box_id}")
def box(box_id: str = Path(..., pattern=r"^[A-Za-z0-9\-]{3,40}$"), user: SessionUser = Depends(current_user),
        c: Container = Depends(container)) -> dict:
    user.require("packing.use")
    return {"source": c.source.provenance(), "box": c.source.find_box(box_id)}


@router.post("/packing/validate")
def packing_validate(body: PackingValidateRequest, user: SessionUser = Depends(current_user),
                     c: Container = Depends(container)) -> dict:
    user.require("packing.use")
    return {"source": c.source.provenance(), **validate_packing(c.source, body.box_id, body.serials)}


@router.get("/labels/printers")
def printers(user: SessionUser = Depends(current_user), c: Container = Depends(container)) -> dict:
    user.require("labels.print")
    return {"printers": c.labels.printers(), "templates": c.labels.templates()}


@router.post("/labels/printers/{printer_id}/check")
def printer_check(printer_id: str = Path(..., pattern=r"^[A-Za-z0-9_\-]{2,60}$"),
                  user: SessionUser = Depends(current_user), c: Container = Depends(container)) -> dict:
    user.require("labels.print")
    return c.labels.check_printer(printer_id)


@router.post("/labels/preview")
def label_preview(body: LabelPreviewRequest, user: SessionUser = Depends(current_user),
                  c: Container = Depends(container)) -> dict:
    user.require("labels.print")
    prev = c.labels.preview(body.template_id, body.data)
    key = prev["data"].get("serial") or prev["data"].get("box_id") or ""
    return {**prev, "would_be_reprint": c.labels.is_reprint(body.template_id, key)}


@router.post("/labels/print")
def label_print(body: LabelPrintRequest, user: SessionUser = Depends(current_user),
                c: Container = Depends(container)) -> dict:
    return c.labels.print(body.printer_id, body.template_id, body.data, body.reason, user)


@router.get("/labels/jobs")
def label_jobs(user: SessionUser = Depends(current_user), c: Container = Depends(container)) -> dict:
    user.require("labels.print")
    return {"jobs": c.labels.jobs()}
