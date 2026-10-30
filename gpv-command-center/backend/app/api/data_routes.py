"""Trazabilidad, diagnóstico de rework y Production Intelligence (lectura)."""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Query

from ..container import Container
from ..core.security import SessionUser
from ..data.source import SEARCH_FIELDS
from ..services.diagnostics import DiagnosticsEngine
from ..services.metrics import compute_metrics
from .deps import container, current_user

router = APIRouter(prefix="/api", tags=["datos"])
Q_PATTERN = r"^[A-Za-z0-9._\-/ ]{1,64}$"


@router.get("/search")
def search(q: str = Query(..., min_length=1, max_length=64, pattern=Q_PATTERN),
           field: str = Query("any", pattern="^(" + "|".join(SEARCH_FIELDS) + ")$"),
           limit: int = Query(50, ge=1, le=500),
           user: SessionUser = Depends(current_user), c: Container = Depends(container)) -> dict:
    user.require("trace.read")
    results = c.source.search(q, field, limit=limit)
    return {"source": c.source.provenance(), "query": q, "field": field, "count": len(results),
            "results": [u.summary() for u in results]}


@router.get("/units/{serial}")
def unit_detail(serial: str, user: SessionUser = Depends(current_user), c: Container = Depends(container)) -> dict:
    user.require("trace.read")
    u = c.source.get_unit(serial)
    panel = []
    if u.panel_id:
        panel = [p.summary() | {"panel_position": p.panel_position} for p in c.source.get_panel(u.panel_id)]
    findings = [f.to_dict() for f in c.diagnostics.analyze([u] + [c.source.get_unit(p["serial"]) for p in panel
                                                                  if p["serial"] != u.serial])
                if u.serial in f.serials]
    return {"source": c.source.provenance(), "unit": u.detail(), "panel": panel, "findings": findings}


@router.get("/panels/{panel_id}")
def panel(panel_id: str, user: SessionUser = Depends(current_user), c: Container = Depends(container)) -> dict:
    user.require("trace.read")
    units = c.source.get_panel(panel_id)
    return {"source": c.source.provenance(), "panel_id": panel_id,
            "units": [u.summary() | {"panel_position": u.panel_position} for u in units]}


@router.get("/work-orders")
def work_orders(user: SessionUser = Depends(current_user), c: Container = Depends(container)) -> dict:
    user.require("trace.read")
    return {"source": c.source.provenance(), "work_orders": [w.to_dict() for w in c.source.work_orders()]}


@router.get("/diagnostics")
def diagnostics(severity: str | None = Query(None, pattern="^(CRITICAL|HIGH|MEDIUM|LOW)$"),
                rule: str | None = Query(None, max_length=40),
                user: SessionUser = Depends(current_user), c: Container = Depends(container)) -> dict:
    user.require("diagnostics.read")
    findings = [f.to_dict() for f in c.diagnostics.analyze(c.source.list_units())]
    summary = {s: sum(1 for f in findings if f["severity"] == s) for s in ("CRITICAL", "HIGH", "MEDIUM", "LOW")}
    by_rule = {r: sum(1 for f in findings if f["rule_id"] == r) for r in DiagnosticsEngine.RULES}
    if severity:
        findings = [f for f in findings if f["severity"] == severity]
    if rule:
        findings = [f for f in findings if f["rule_id"] == rule]
    return {"source": c.source.provenance(), "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "rules": DiagnosticsEngine.RULES, "summary": summary, "by_rule": by_rule,
            "thresholds": {"stuck_repair_hours": DiagnosticsEngine.STUCK_REPAIR_HOURS,
                           "depanel_wait_hours": DiagnosticsEngine.DEPANEL_WAIT_HOURS,
                           "loop_min_cycles": DiagnosticsEngine.LOOP_MIN_CYCLES,
                           "repeat_min_visits": DiagnosticsEngine.REPEAT_MIN_VISITS},
            "findings": findings}


@router.get("/metrics")
def metrics(window_hours: int = Query(24, ge=1, le=720), user: SessionUser = Depends(current_user),
            c: Container = Depends(container)) -> dict:
    user.require("metrics.read")
    return compute_metrics(c.source.list_units(), c.source.work_orders(), window_hours, c.source.provenance())
