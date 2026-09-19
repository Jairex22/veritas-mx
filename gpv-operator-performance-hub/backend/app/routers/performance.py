from __future__ import annotations

import csv
import io

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from ..analytics import build_performance_rows
from ..database import get_db
from ..security import get_current_user, CurrentUser

router = APIRouter(prefix="/api/performance", tags=["Rendimiento"])

SORTABLE_FIELDS = {
    "full_name", "shift", "area", "fpy", "avg_cycle_time_seconds", "cycle_compliance_pct",
    "consistency_index", "score", "units_processed", "last_activity",
}


def _filtered_sorted(
    db: Session,
    period_days: int,
    shift: str | None,
    area: str | None,
    station_id: int | None,
    search: str | None,
    sort_by: str,
    sort_dir: str,
    classification: str | None,
):
    rows = build_performance_rows(db, period_days=period_days, shift=shift, area=area, station_id=station_id, search=search)
    if classification:
        rows = [r for r in rows if r["classification"] == classification]

    key = sort_by if sort_by in SORTABLE_FIELDS else "full_name"
    reverse = sort_dir == "desc"
    rows.sort(key=lambda r: (r[key] is None, r[key]), reverse=reverse)
    return rows


@router.get("")
def list_performance(
    period_days: int = Query(30, ge=1, le=90),
    shift: str | None = None,
    area: str | None = None,
    station_id: int | None = None,
    classification: str | None = None,
    search: str | None = None,
    sort_by: str = "full_name",
    sort_dir: str = "asc",
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=5, le=200),
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    rows = _filtered_sorted(db, period_days, shift, area, station_id, search, sort_by, sort_dir, classification)
    total = len(rows)
    start = (page - 1) * page_size
    page_rows = rows[start : start + page_size]
    return {"items": page_rows, "total": total, "page": page, "page_size": page_size}


@router.get("/export.csv")
def export_csv(
    period_days: int = Query(30, ge=1, le=90),
    shift: str | None = None,
    area: str | None = None,
    station_id: int | None = None,
    classification: str | None = None,
    search: str | None = None,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    rows = _filtered_sorted(db, period_days, shift, area, station_id, search, "full_name", "asc", classification)
    buffer = io.StringIO()
    fieldnames = [
        "employee_number", "full_name", "shift", "area", "line", "main_station", "product", "work_order",
        "units_processed", "units_conforming", "units_rejected", "units_reworked", "fpy",
        "avg_cycle_time_seconds", "cycle_compliance_pct", "consistency_index", "data_confidence",
        "score", "classification", "trend", "last_activity",
    ]
    writer = csv.DictWriter(buffer, fieldnames=fieldnames)
    writer.writeheader()
    for row in rows:
        writer.writerow({k: row.get(k) for k in fieldnames})
    buffer.seek(0)
    return StreamingResponse(
        iter([buffer.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=rendimiento_operadores.csv"},
    )
