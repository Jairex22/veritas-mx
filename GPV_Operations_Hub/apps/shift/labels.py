"""Label data taken from the operator's confirmed context (no retyping)."""
from django.utils import timezone

from . import calendar as cal
from .models import ShiftPlan, UserContext


def context_record(user):
    ctx = UserContext.objects.filter(user=user).select_related("station__line__area").first()
    if not ctx or not ctx.station:
        return {"work_order": "", "part_number": "", "line": "", "station": "", "operation": "", "area": "", "date": timezone.localdate().isoformat(),
                "shift": ""}
    line = ctx.station.line
    cur = cal.current()
    plan = None
    if ctx.work_order:
        plan = ShiftPlan.objects.filter(line=line, work_order__iexact=ctx.work_order).order_by("-date").first()
    return {"work_order": ctx.work_order, "part_number": plan.part_number if plan else "", "line": line.code, "station": ctx.station.code,
            "operation": ctx.station.operation, "area": line.area.code, "date": timezone.localdate().isoformat(), "shift": cur[0].code if cur else ""}
