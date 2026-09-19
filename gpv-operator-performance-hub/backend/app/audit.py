"""Registro de auditoría: toda acción sensible (login, cambios de configuración,
acciones de capacitación, notas de supervisor) queda registrada aquí."""
from __future__ import annotations

from datetime import datetime

from sqlalchemy.orm import Session

from .models import AuditLog


def log_action(
    db: Session,
    *,
    username: str,
    role: str,
    action: str,
    entity: str = "",
    entity_id: str = "",
    details: str = "",
    ip_address: str = "",
) -> None:
    entry = AuditLog(
        timestamp=datetime.utcnow(),
        username=username,
        role=role,
        action=action,
        entity=entity,
        entity_id=str(entity_id),
        details=details,
        ip_address=ip_address,
    )
    db.add(entry)
    db.commit()
