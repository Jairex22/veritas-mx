from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import AuditLog
from ..security import CurrentUser, require_admin_or_engineer

router = APIRouter(prefix="/api/audit", tags=["Auditoría"])


@router.get("")
def list_audit_log(
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=10, le=200),
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(require_admin_or_engineer),
):
    q = db.query(AuditLog).order_by(AuditLog.timestamp.desc())
    total = q.count()
    items = q.offset((page - 1) * page_size).limit(page_size).all()
    return {
        "items": [
            {
                "timestamp": a.timestamp.isoformat(),
                "username": a.username,
                "role": a.role,
                "action": a.action,
                "entity": a.entity,
                "entity_id": a.entity_id,
                "details": a.details,
                "ip_address": a.ip_address,
            }
            for a in items
        ],
        "total": total,
        "page": page,
        "page_size": page_size,
    }
