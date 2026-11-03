"""Shift report, close-out, handover, help-request routing and reminders."""
import logging
from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.core.audit import audit
from apps.core.jobs import UserFacingError
from apps.core.notify import notify
from apps.production.metrics import pct

from . import calendar as cal
from .counting import scope_counts
from .models import (Downtime, Handover, HelpEvent, HelpRequest, Line, MaterialRequest, ODataConnection, ProductionEvent as PE,
                     QualityObservation, ShiftPlan, ShiftReport)

log = logging.getLogger("gpv.shift")
ZERO = Decimal("0")


def fmt(dt):
    return timezone.localtime(dt).strftime("%Y-%m-%d %H:%M") if dt else "—"


def source_status(now=None):
    now = now or timezone.now()
    out = []
    for c in ODataConnection.objects.all():
        h = c.health(now)
        age = int((now - c.last_success_at).total_seconds() // 60) if c.last_success_at else None
        out.append({"name": c.name, "health": h, "health_label": ODataConnection.Health(h).label, "last_success": fmt(c.last_success_at),
                    "last_data": fmt(c.last_data_at), "age_min": age, "error": c.last_error, "synthetic": c.synthetic})
    return out


# ---------------------------------------------------------------- shift summary (shared by Mi turno, report and handover)
def shift_summary(line, shift, date, now=None):
    now = now or timezone.now()
    start, end = cal.window(shift, date)
    plans = list(ShiftPlan.objects.filter(line=line, shift=shift, date=date))
    orders = []
    for p in plans:
        c = scope_counts(line, p.work_order, start, end, target_unit=p.unit)
        comparable = not c["issues"]
        orders.append({
            "work_order": p.work_order, "part_number": p.part_number, "target": float(p.target), "unit": p.unit,
            "good": float(c["confirmed"]) if comparable else None, "provisional": float(c["provisional"]),
            "pending": float(max(p.target - c["confirmed"], ZERO)) if comparable else None,
            "compliance": pct(c["confirmed"], p.target, "buenas confirmadas / meta del turno × 100") if comparable else
            {"value": None, "status": "not_calculable", "reason": "; ".join(c["issues"])},
            "issues": c["issues"], "pending_manual": c["pending_manual"], "fpy": c["fpy"], "retests": c["retests"],
        })
    comparable = [o for o in orders if o["good"] is not None]
    units = {o["unit"] for o in comparable}
    if not orders:
        group = {"value": None, "status": "insufficient", "reason": "No hay meta asignada al turno (plan del turno vacío)."}
    elif len(units) > 1:
        group = {"value": None, "status": "not_calculable", "reason": "Unidades distintas entre órdenes."}
    elif len(comparable) < len(orders):
        group = {"value": None, "status": "not_calculable", "reason": "Alguna orden no tiene cantidades comparables."}
    else:
        group = pct(Decimal(str(sum(o["good"] for o in comparable))), Decimal(str(sum(o["target"] for o in comparable))),
                    "Σ buenas confirmadas / Σ metas del turno × 100")
    from django.db.models import Q

    downs = list(Downtime.objects.filter(line=line, started_at__lt=end).filter(Q(ended_at__isnull=True) | Q(ended_at__gt=start))
                 .select_related("reason").distinct())
    help_qs = HelpRequest.objects.filter(line=line, created__lt=end).select_related("reason")
    open_help = [h for h in help_qs if h.is_open or (h.resolved_at and h.resolved_at > start)]
    materials = MaterialRequest.objects.filter(line=line, created__lt=end).exclude(status__in=["delivered", "cancelled"])
    quality = QualityObservation.objects.filter(line=line, created__gte=start, created__lt=end)
    pending_manual = PE.objects.filter(line=line, source=PE.Source.MANUAL, event_at__gte=start, event_at__lt=end,
                                       recon_status__in=[PE.Recon.PENDING, PE.Recon.REVIEW]).count()
    exceptions = []
    for d in downs:
        if d.reason_id is None:
            exceptions.append({"type": "downtime_reason", "id": d.pk, "text": f"Paro desde {fmt(d.started_at)} sin motivo"})
        if d.ended_at is None and end <= now:
            exceptions.append({"type": "downtime_open", "id": d.pk, "text": f"Paro iniciado {fmt(d.started_at)} sigue abierto"})
    for h in open_help:
        if h.is_open and not h.comment:
            exceptions.append({"type": "help_comment", "id": h.pk, "text": f"Solicitud de ayuda #{h.pk} ({h.reason}) sin comentario"})
    blocking = []
    if pending_manual:
        blocking.append(f"{pending_manual} captura(s) manual(es) pendiente(s) de conciliación")
    sources = source_status(now)
    for s in sources:
        if s["health"] in ("disconnected", "delayed", "unverified"):
            blocking.append(f"Fuente «{s['name']}»: {s['health_label']} (último éxito {s['last_success']})")
    return {
        "line": line.code, "line_synthetic": line.synthetic, "shift": shift.code, "date": date.isoformat(),
        "window": [fmt(start), fmt(end)], "planned_minutes": cal.planned_minutes(shift, date), "orders": orders, "compliance": group,
        "downtimes": [{"id": d.pk, "from": fmt(d.started_at), "to": fmt(d.ended_at), "minutes": round(d.minutes(min(now, end)), 1),
                       "reason": str(d.reason) if d.reason else "PENDIENTE", "comment": d.comment} for d in downs],
        "downtime_minutes": round(sum(d.minutes(min(now, end)) for d in downs), 1),
        "help": [{"id": h.pk, "reason": str(h.reason), "status": h.get_status_display(), "created": fmt(h.created), "comment": h.comment[:200]}
                 for h in open_help],
        "materials": [{"id": m.pk, "material": m.material, "qty": float(m.qty), "unit": m.unit, "status": m.get_status_display()} for m in materials],
        "quality": [{"id": q.pk, "category": q.category, "status": q.get_status_display(), "serial": q.serial} for q in quality],
        "pending_manual": pending_manual, "exceptions": exceptions, "blocking": blocking, "sources": sources,
        "generated_at": fmt(now),
    }


# ---------------------------------------------------------------- shift report lifecycle
def _status_for(summary):
    return ShiftReport.Status.PENDING_DATA if (summary["exceptions"] or summary["blocking"]) else ShiftReport.Status.DRAFT


def generate_report(line, shift, date, now=None, by="planificador"):
    """Create the first draft once (unique constraint protects retries and restarts)."""
    now = now or timezone.now()
    if ShiftReport.objects.filter(line=line, shift=shift, date=date).exists():
        return None
    s = shift_summary(line, shift, date, now)
    try:
        with transaction.atomic():
            r = ShiftReport.objects.create(line=line, shift=shift, date=date, revision=1, snapshot=s, status=_status_for(s), generated_by=by)
    except IntegrityError:
        return None
    _handover(line, shift, date, s)
    return r


def refresh_draft(report, user=None):
    if report.status == ShiftReport.Status.CLOSED:
        raise UserFacingError("El reporte está cerrado: los cambios crean una nueva revisión.")
    s = shift_summary(report.line, report.shift, report.date)
    report.snapshot, report.status = s, _status_for(s) if report.status != ShiftReport.Status.REVIEWED else report.status
    report.generated_at = timezone.now()
    report.save()
    return report


def review(report, user):
    if report.status == ShiftReport.Status.CLOSED:
        raise UserFacingError("El reporte ya está cerrado.")
    refresh_draft(report)
    if report.snapshot["exceptions"]:
        raise UserFacingError("Complete las excepciones pendientes antes de marcar como revisado.")
    report.status, report.reviewed_by, report.reviewed_at = ShiftReport.Status.REVIEWED, user, timezone.now()
    report.save()
    audit(user, "shift.report_reviewed", report, str(report))
    return report


def close(report, user, force_reason=""):
    if report.status == ShiftReport.Status.CLOSED:
        raise UserFacingError("El reporte ya está cerrado.")
    if report.status != ShiftReport.Status.REVIEWED:
        raise UserFacingError("Primero marque el reporte como revisado.")
    s = shift_summary(report.line, report.shift, report.date)
    if s["blocking"] and len(force_reason.strip()) < 10:
        raise UserFacingError("Hay datos provisionales o fuentes sin actualizar: " + "; ".join(s["blocking"]) +
                              ". Para cerrar así, indique un motivo (mín. 10 caracteres); quedarán visibles en el reporte.")
    s["closed_with_pending"] = s["blocking"] if s["blocking"] else []
    s["close_reason"] = force_reason
    report.snapshot = s
    report.status, report.closed_by, report.closed_at = ShiftReport.Status.CLOSED, user, timezone.now()
    report.save()
    report.pdf = _pdf(report, user)
    report.save(update_fields=["pdf"])
    audit(user, "shift.report_closed", report, f"{report} cerrado" + (f" con pendientes: {force_reason}" if s["blocking"] else ""))
    return report


def late_data_revisions(now=None):
    """If data arrives after a report was closed, open a new identified revision (the closed one is kept)."""
    created = []
    for r in ShiftReport.objects.filter(status=ShiftReport.Status.CLOSED).select_related("line", "shift"):
        if ShiftReport.objects.filter(line=r.line, shift=r.shift, date=r.date, revision__gt=r.revision).exists():
            continue
        start, end = cal.window(r.shift, r.date)
        late = PE.objects.filter(line=r.line, event_at__gte=start, event_at__lt=end, received_at__gt=r.closed_at).count()
        if not late:
            continue
        s = shift_summary(r.line, r.shift, r.date, now)
        try:
            with transaction.atomic():
                nr = ShiftReport.objects.create(line=r.line, shift=r.shift, date=r.date, revision=r.revision + 1, previous=r, snapshot=s,
                                                status=_status_for(s), revision_reason=f"{late} dato(s) recibido(s) después del cierre")
            created.append(nr)
        except IntegrityError:
            continue
    return created


def generate_due(now=None, lookback_days=7):
    """Called by the scheduler: draft reports for every shift that ended and has none (catch-up after downtime, once)."""
    now = now or timezone.now()
    out = []
    lines = list(Line.objects.filter(active=True, pilot=True))
    for shift, date, s, e in cal.ended_between(now - timedelta(days=lookback_days), now):
        for line in lines:
            if e <= line.created:  # never back-fill shifts that ended before the line was configured
                continue
            r = generate_report(line, shift, date, now)
            if r:
                out.append(r)
    out += late_data_revisions(now)
    return out


def _pdf(report, user):
    from apps.core.files import store_generated
    from apps.reports.exporters import to_pdf

    return store_generated(to_pdf(report_as_snapshot(report)), f"reporte_turno_{report.line.code}_{report.date}_{report.shift.code}_r{report.revision}.pdf",
                           user)


def report_as_snapshot(report):
    """Convert a shift report into the common exporter format (same figures in screen, PDF and XLSX)."""
    s = report.snapshot
    comp = s["compliance"]
    kpis = [{"label": "Cumplimiento del turno", "value": comp.get("value"), "status": comp.get("status"), "reason": comp.get("reason", ""),
             "unit": "%", "definition": comp.get("definition", "Σ buenas confirmadas / Σ metas del turno × 100"),
             "numerator": comp.get("numerator"), "denominator": comp.get("denominator")},
            {"label": "Minutos de paro registrados", "value": s["downtime_minutes"], "status": "ok", "reason": "", "unit": "min", "definition": "",
             "numerator": None, "denominator": None},
            {"label": "Capturas manuales pendientes", "value": s["pending_manual"], "status": "ok", "reason": "", "unit": "", "definition": "",
             "numerator": None, "denominator": None}]
    orders = [[o["work_order"], o["part_number"], o["unit"], o["target"], o["good"] if o["good"] is not None else "No calculable",
               o["provisional"], o["pending"] if o["pending"] is not None else "—",
               o["compliance"]["value"] if o["compliance"].get("status") == "ok" else "No calculable"] for o in s["orders"]]
    warnings = list(s.get("blocking", []))
    if s.get("line_synthetic"):
        warnings.insert(0, "LÍNEA DE EJEMPLO (datos sintéticos): no representa producción real.")
    return {
        "title": f"Reporte SMT del turno · {s['line']} · {s['date']} · {s['shift']} · revisión {report.revision}",
        "period_text": f"Turno {s['shift']} del {s['date']} ({s['window'][0]} a {s['window'][1]}); estado {report.get_status_display()}",
        "generated_at": s["generated_at"], "timezone": "America/Mexico_City", "author": report.generated_by,
        "data_version": f"rev{report.revision}-{report.generated_at:%Y%m%d%H%M%S}", "kpis": kpis,
        "tables": [{"title": "Órdenes del turno (operación de conteo)", "columns": [
            {"key": "wo", "label": "Orden"}, {"key": "pn", "label": "Parte"}, {"key": "u", "label": "Unidad"}, {"key": "t", "label": "Meta del turno", "num": True},
            {"key": "g", "label": "Buenas confirmadas", "num": True}, {"key": "p", "label": "Manual pendiente", "num": True},
            {"key": "pend", "label": "Pendiente", "num": True}, {"key": "c", "label": "Cumplimiento %", "num": True}], "rows": orders},
                   {"title": "Paros", "columns": [{"key": "a", "label": "Desde"}, {"key": "b", "label": "Hasta"}, {"key": "m", "label": "Minutos", "num": True},
                                                  {"key": "r", "label": "Motivo"}, {"key": "c", "label": "Comentario"}],
                    "rows": [[d["from"], d["to"], d["minutes"], d["reason"], d["comment"]] for d in s["downtimes"]]},
                   {"title": "Incidencias y solicitudes", "columns": [{"key": "i", "label": "#"}, {"key": "r", "label": "Motivo"},
                                                                     {"key": "s", "label": "Estado"}, {"key": "c", "label": "Comentario"}],
                    "rows": [[h["id"], h["reason"], h["status"], h["comment"]] for h in s["help"]]},
                   {"title": "Faltantes / solicitudes de material", "columns": [{"key": "m", "label": "Material"}, {"key": "q", "label": "Cantidad", "num": True},
                                                                               {"key": "u", "label": "Unidad"}, {"key": "s", "label": "Estado"}],
                    "rows": [[m["material"], m["qty"], m["unit"], m["status"]] for m in s["materials"]]}],
        "charts": [], "observations": [f"Fuente {x['name']}: {x['health_label']}, último éxito {x['last_success']}, último dato {x['last_data']}"
                                       for x in s["sources"]] + [f"Excepción: {e['text']}" for e in s["exceptions"]],
        "incidents": [], "warnings": warnings, "notes": s.get("close_reason", ""), "last_import": "",
    }


# ---------------------------------------------------------------- handover
def _handover(line, shift, date, summary):
    pending_orders = [o for o in summary["orders"] if o["pending"] not in (None, 0)]
    data = {"pending_orders": pending_orders, "open_help": [h for h in summary["help"] if h["status"] in ("Reportado", "Recibido", "En atención")],
            "open_downtimes": [d for d in summary["downtimes"] if d["to"] == "—"], "materials": summary["materials"],
            "quality": summary["quality"], "sources": summary["sources"]}
    try:
        with transaction.atomic():
            return Handover.objects.create(line=line, shift=shift, date=date, summary=data)
    except IntegrityError:
        return None


def receive_handover(h, user):
    """Receipt does NOT close incidents nor approve quality dispositions."""
    if h.received_at:
        raise UserFacingError("El relevo ya fue recibido.")
    h.received_by, h.received_at = user, timezone.now()
    h.save(update_fields=["received_by", "received_at"])
    audit(user, "shift.handover_received", h, f"Relevo {h.line.code} {h.date} {h.shift.code} recibido")
    return h


# ---------------------------------------------------------------- help requests
def group_members(group):
    if group is None:
        return []
    return list(get_user_model().objects.filter(groups=group, is_active=True))


def similar_open(line, station, reason):
    return HelpRequest.objects.filter(line=line, station=station, reason=reason, status__in=["reported", "received", "in_progress"])


def create_help(user, line, station, reason, work_order="", comment="", photo=None, relate_to=None, client_uuid=None):
    if client_uuid:
        existing = HelpRequest.objects.filter(client_uuid=client_uuid).first()
        if existing:
            return existing, False
    try:
        with transaction.atomic():
            h = HelpRequest.objects.create(reason=reason, line=line, station=station, work_order=work_order, comment=comment[:2000],
                                           photo=photo, group=reason.group, created_by=user, related_to=relate_to, client_uuid=client_uuid)
            HelpEvent.objects.create(request=h, status="reported", user=user, note=comment[:200])
    except IntegrityError:
        return HelpRequest.objects.get(client_uuid=client_uuid), False
    targets = group_members(reason.group)
    notify(targets, f"Ayuda: {reason.label} · {line.code}{' · ' + station.code if station else ''}", comment[:180], f"/turno/ayuda/{h.pk}/",
           level="high")
    audit(user, "shift.help_created", h, str(h))
    return h, True


TRANSITIONS = {"reported": ["received", "cancelled"], "received": ["in_progress", "cancelled"], "in_progress": ["resolved"],
               "resolved": ["verified", "in_progress"]}


def can_attend(user, h):
    from apps.core.permissions import has_cap

    return has_cap(user, "shift.attend") or (h.group_id and user.groups.filter(pk=h.group_id).exists())


def advance_help(h, user, to, note=""):
    from apps.core.permissions import has_cap

    if to not in TRANSITIONS.get(h.status, []):
        raise UserFacingError("Cambio de estado no permitido desde el estado actual.")
    if to == "cancelled" and user.pk != h.created_by_id and not has_cap(user, "shift.attend"):
        raise UserFacingError("Solo quien la reportó o un responsable puede cancelarla.")
    if to in ("received", "in_progress", "resolved") and not can_attend(user, h):
        raise UserFacingError("Solo el grupo asignado o un responsable pueden atender esta solicitud.")
    if to == "verified":
        if not has_cap(user, "shift.attend") and user.pk != h.created_by_id:
            raise UserFacingError("La verificación la hace quien reportó o un responsable.")
        if h.assignee_id == user.pk and h.reason.requires_verification:
            raise UserFacingError("Quien resolvió no puede verificar su propia solución.")
    if to == "resolved" and len(note.strip()) < 3:
        raise UserFacingError("Describa la solución.")
    now = timezone.now()
    h.status = to
    if to == "received":
        h.received_at, h.assignee = now, user
    elif to == "in_progress":
        h.started_at = h.started_at or now
        h.assignee = h.assignee or user
    elif to == "resolved":
        h.resolved_at, h.resolution = now, note
    elif to == "verified":
        h.verified_at = now
    h.save()
    HelpEvent.objects.create(request=h, status=to, user=user, note=note[:500])
    notify([h.created_by] if h.created_by_id != user.pk else [], f"Su solicitud de ayuda #{h.pk}: {h.get_status_display()}", note[:180],
           f"/turno/ayuda/{h.pk}/")
    return h


def remind_and_escalate(now=None):
    """Internal reminders/escalation by configured rules (no external messages)."""
    now = now or timezone.now()
    n = 0
    for h in HelpRequest.objects.filter(status__in=["reported", "received"]).select_related("reason"):
        age = (now - h.created).total_seconds() / 60
        if h.status == "reported" and age >= h.reason.remind_minutes and (h.last_reminder_at is None or
                                                                           (now - h.last_reminder_at).total_seconds() / 60 >= h.reason.remind_minutes):
            notify(group_members(h.group), f"Recordatorio: ayuda #{h.pk} sin recibir ({int(age)} min)", h.comment[:150], f"/turno/ayuda/{h.pk}/", level="high")
            h.last_reminder_at = now
            h.save(update_fields=["last_reminder_at"])
            n += 1
        if age >= h.reason.escalate_minutes and h.escalation_level == 0 and h.reason.escalate_group_id:
            notify(group_members(h.reason.escalate_group), f"Escalamiento: ayuda #{h.pk} sin atención ({int(age)} min)", h.comment[:150],
                   f"/turno/ayuda/{h.pk}/", level="critical")
            h.escalation_level = 1
            h.save(update_fields=["escalation_level"])
            HelpEvent.objects.create(request=h, status=h.status, note=f"Escalado por regla ({h.reason.escalate_minutes} min)")
            n += 1
    return n


# ---------------------------------------------------------------- manual production capture
def capture_manual(user, line, station, work_order, qty, unit, start, end, reason, lot_ref="", serial="", client_uuid=None):
    from .counting import reconcile

    if client_uuid:
        ex = PE.objects.filter(client_uuid=client_uuid).first()
        if ex:
            return ex, False
    if qty <= 0:
        raise UserFacingError("La cantidad debe ser positiva.")
    if len(reason.strip()) < 5:
        raise UserFacingError("Indique el motivo de la captura manual (contingencia).")
    if end < start:
        raise UserFacingError("El fin del periodo es anterior al inicio.")
    # production is captured at the line's count-point operation (same place FactoryLogix counts)
    cp = line.stations.filter(is_count_point=True, active=True).first()
    if cp is not None:
        station = cp
    try:
        with transaction.atomic():
            e = PE.objects.create(source=PE.Source.MANUAL, kind=PE.Kind.INCREMENTAL, line=line, station=station, operation=station.operation if station else "",
                                  work_order=work_order, qty=qty, unit=unit, event_at=start, period_end=end, reason=reason, user=user,
                                  lot_ref=lot_ref, serial=serial, recon_status=PE.Recon.PENDING, client_uuid=client_uuid)
    except IntegrityError:
        return PE.objects.get(client_uuid=client_uuid), False
    reconcile(e, user)
    audit(user, "shift.manual_capture", e, f"Captura manual {qty} {unit} orden {work_order}: {reason}")
    return e, True
