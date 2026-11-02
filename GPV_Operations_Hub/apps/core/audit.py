from .logging_utils import get_op_id
from .models import AuditLog


def audit(actor, action, obj=None, summary="", changes=None, area=None):
    """Record an important change. Never pass passwords or file contents here."""
    object_type = obj.__class__.__name__ if obj is not None else ""
    object_id = str(getattr(obj, "pk", "") or "") if obj is not None else ""
    if area is None and obj is not None:
        area = getattr(obj, "area", None)
        if area is not None and not hasattr(area, "pk"):
            area = None
    return AuditLog.objects.create(
        actor=actor if (actor is not None and actor.is_authenticated) else None,
        action=action,
        object_type=object_type,
        object_id=object_id,
        area=area,
        summary=summary[:300],
        changes=changes or {},
        op_id=get_op_id(),
    )
