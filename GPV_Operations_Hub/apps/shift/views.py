from decimal import Decimal, InvalidOperation

from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.db.models import Q
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_GET, require_POST

from apps.core.audit import audit
from apps.core.files import store_upload
from apps.core.jobs import UserFacingError
from apps.core.models import Role, Shift
from apps.core.permissions import allowed_area_ids, can_access_area, has_cap, require_cap
from apps.core.utils import api, json_error, json_ok, read_json

from . import calendar as cal
from . import odata, services
from .counting import candidates, review as recon_review, scope_counts
from .models import (ChecklistRun, ChecklistTemplate, ContextChange, Downtime, DowntimeReason, Handover, HelpRequest, HelpReason, InstructionRead,
                     Line, MaterialRequest, ODataConnection, OperationInstruction, ProductionEvent as PE, QualityObservation, ShiftPlan,
                     ShiftReport, Station, SyncGap, UserContext)


# ---------------------------------------------------------------- helpers
def _lines(user):
    ids = allowed_area_ids(user)
    qs = Line.objects.filter(active=True).select_related("area", "site")
    return qs if ids is None else qs.filter(area__in=ids)


def _line(user, pk):
    line = get_object_or_404(Line, pk=pk)
    if not can_access_area(user, line.area_id):
        raise PermissionDenied("La línea pertenece a un área sin permiso.")
    return line


def _ctx(user):
    c, _ = UserContext.objects.get_or_create(user=user)
    if c.station and not can_access_area(user, c.station.line.area_id):
        c.station = None
        c.save(update_fields=["station"])
    return c


def _now_shift():
    cur = cal.current()
    return cur if cur else (None, None, None, None)


def _profile_views(user):
    """Role-adapted sections (combined roles are honored: groups add sections)."""
    role = getattr(getattr(user, "profile", None), "role", Role.OPERATOR)
    groups = set(user.groups.values_list("name", flat=True))
    return {"supervisor": user.is_superuser or role in (Role.ADMIN, Role.SUPERVISOR), "engineer": role in (Role.ENGINEER, Role.ADMIN) or user.is_superuser,
            "quality": "Calidad" in groups or has_cap(user, "shift.quality"), "maintenance": "Mantenimiento" in groups,
            "materials": "Materiales" in groups, "tests": "Pruebas" in groups, "attend": has_cap(user, "shift.attend"), "groups": sorted(groups)}


def next_action(ctx, shift_info, summary, user_open_help):
    if ctx.station is None:
        return ("Escanea el QR de tu estación o elígela", "/turno/contexto/")
    if not ctx.work_order:
        return ("Escanea la orden que vas a trabajar", "/turno/escanear/")
    if user_open_help:
        return ("Revisa el estado de tu solicitud de ayuda", f"/turno/ayuda/{user_open_help[0].pk}/")
    if summary and summary["exceptions"]:
        return ("Revisa el problema pendiente del cierre", "/turno/cierre/")
    if shift_info[3] and (shift_info[3] - timezone.now()).total_seconds() < 30 * 60:
        return ("Confirma el cierre del turno", "/turno/cierre/")
    return ("Sigue con tu orden; si algo falla pulsa «Necesito ayuda»", "/turno/trabajo/")


# ---------------------------------------------------------------- Mi turno
@require_cap("shift.use")
def my_shift(request):
    ctx = _ctx(request.user)
    shift, date, start, end = _now_shift()
    line = ctx.station.line if ctx.station else None
    summary = services.shift_summary(line, shift, date) if (line and shift) else None
    order = None
    if summary and ctx.work_order:
        order = next((o for o in summary["orders"] if o["work_order"].upper() == ctx.work_order.upper()), None)
        if order is None and line:
            c = scope_counts(line, ctx.work_order, start, end, target_unit=line.count_unit)
            order = {"work_order": ctx.work_order, "target": None, "good": float(c["confirmed"]), "provisional": float(c["provisional"]),
                     "pending": None, "unit": line.count_unit, "compliance": {"status": "insufficient", "reason": "Sin meta asignada a este turno."}}
    my_help = list(HelpRequest.objects.filter(created_by=request.user, status__in=["reported", "received", "in_progress"])[:5])
    action = next_action(ctx, (shift, date, start, end), summary, my_help)
    from apps.comms.services import visible_announcements

    return render(request, "shift/my_shift.html", {
        "ctx": ctx, "shift": shift, "date": date, "start": start, "end": end, "line": line, "summary": summary, "order": order,
        "my_help": my_help, "action": action, "views": _profile_views(request.user),
        "announcements": visible_announcements(request.user).order_by("-priority_rank", "-created")[:3],
        "sources": services.source_status(), "attend_count": _inbox(request.user).count() if has_cap(request.user, "shift.attend") or request.user.groups.exists() else 0,
    })


@require_GET
@api
def state_api(request):
    if not has_cap(request.user, "shift.use"):
        return json_error("Sin permiso.", status=403)
    ctx = _ctx(request.user)
    shift, date, start, end = _now_shift()
    data = {"server_time": timezone.localtime().strftime("%H:%M:%S"), "sources": services.source_status()}
    if ctx.station and shift:
        s = services.shift_summary(ctx.station.line, shift, date)
        data["orders"] = s["orders"]
        data["compliance"] = s["compliance"]
    return json_ok(data)


# ---------------------------------------------------------------- context (station/order)
@require_cap("shift.use")
def context(request):
    ctx = _ctx(request.user)
    if request.method == "POST":
        reason = request.POST.get("reason", "").strip()
        station = Station.objects.filter(pk=request.POST.get("station") or 0).select_related("line").first()
        wo = request.POST.get("work_order", "").strip()[:60]
        if station and not can_access_area(request.user, station.line.area_id):
            raise PermissionDenied("Estación de un área sin permiso.")
        changes = []
        if station and station != ctx.station:
            changes.append(("station", str(ctx.station or ""), str(station)))
        if wo != ctx.work_order:
            changes.append(("work_order", ctx.work_order, wo))
        if ctx.work_order and wo != ctx.work_order and len(reason) < 3:
            messages.error(request, "Cambiar la orden activa requiere indicar el motivo.")
            return redirect("shift:context")
        for f, old, new in changes:
            ContextChange.objects.create(user=request.user, field=f, old=old, new=new, reason=reason, via=request.POST.get("via", "web"))
        if station:
            ctx.station = station
        ctx.work_order = wo
        ctx.confirmed_at = ctx.updated = timezone.now()
        ctx.save()
        messages.success(request, "Contexto confirmado.")
        return redirect("shift:home")
    lines = _lines(request.user)
    shift, date, start, end = _now_shift()
    plans = ShiftPlan.objects.filter(line=ctx.station.line, shift=shift, date=date) if (ctx.station and shift) else []
    return render(request, "shift/context.html", {"ctx": ctx, "stations": Station.objects.filter(line__in=lines, active=True).select_related("line"),
                                                   "plans": plans, "history": ContextChange.objects.filter(user=request.user).order_by("-ts")[:10]})


@require_cap("shift.use")
def station_qr(request, token):
    """QR identifies the station only; the person must be logged in and confirm."""
    station = get_object_or_404(Station.objects.select_related("line"), qr_token=token, active=True)
    if not can_access_area(request.user, station.line.area_id):
        raise PermissionDenied("Estación de un área sin permiso.")
    return render(request, "shift/station_confirm.html", {"station": station, "ctx": _ctx(request.user)})


# ---------------------------------------------------------------- work & scan
@require_cap("shift.use")
def work(request):
    ctx = _ctx(request.user)
    shift, date, start, end = _now_shift()
    line = ctx.station.line if ctx.station else None
    summary = services.shift_summary(line, shift, date) if (line and shift) else None
    events = PE.objects.filter(line=line, event_at__gte=start, event_at__lt=end).select_related("station")[:50] if (line and start) else []
    return render(request, "shift/work.html", {"ctx": ctx, "summary": summary, "events": events, "shift": shift, "date": date})


@require_cap("shift.use")
def scan(request):
    code = request.GET.get("code", "").strip()
    result = {}
    if code:
        st = Station.objects.filter(qr_token=code).first()
        if st:
            return redirect("shift:station_qr", token=code)
        lines = _lines(request.user)
        ev = PE.objects.filter(Q(serial__iexact=code) | Q(panel_id__iexact=code) | Q(lot_ref__iexact=code), line__in=lines).select_related(
            "station", "line").order_by("event_at")
        if ev.exists():
            result["serial"] = {"code": code, "events": ev}
        plan = ShiftPlan.objects.filter(work_order__iexact=code, line__in=lines).order_by("-date").first()
        from apps.production.models import WorkOrder

        wo = WorkOrder.objects.filter(number__iexact=code).first()
        if plan or (wo and can_access_area(request.user, wo.area_id)):
            result["order"] = {"code": code, "plan": plan, "wo": wo}
        if not result:
            result["none"] = True
        from apps.labels.models import PrintJob

        result["labels"] = [j for j in PrintJob.objects.filter(serials__icontains=code).order_by("-created")[:50] if code in (j.serials or [])][:10]
    return render(request, "shift/scan.html", {"code": code, "result": result, "ctx": _ctx(request.user)})


# ---------------------------------------------------------------- help requests
def _inbox(user):
    qs = HelpRequest.objects.filter(status__in=["reported", "received", "in_progress", "resolved"]).select_related("reason", "line", "station")
    if has_cap(user, "shift.attend"):
        ids = allowed_area_ids(user)
        return qs if ids is None else qs.filter(line__area__in=ids)
    return qs.filter(group__in=user.groups.all())


@require_cap("shift.use")
def help_home(request):
    ctx = _ctx(request.user)
    if request.method == "POST":
        return _help_create(request, ctx)
    reasons = HelpReason.objects.filter(active=True)
    similar = []
    if ctx.station and request.GET.get("motivo"):
        r = HelpReason.objects.filter(code=request.GET["motivo"]).first()
        if r:
            similar = services.similar_open(ctx.station.line, ctx.station, r)
    return render(request, "shift/help_new.html", {"ctx": ctx, "reasons": reasons, "similar": similar, "sel": request.GET.get("motivo", ""),
                                                    "mine": HelpRequest.objects.filter(created_by=request.user)[:10],
                                                    "inbox": _inbox(request.user)[:50]})


def _help_create(request, ctx):
    is_json = request.content_type.startswith("application/json")
    body = read_json(request) if is_json else request.POST
    if ctx.station is None:
        if is_json:
            return json_error("Primero confirme su estación (escanee su QR).")
        messages.error(request, "Primero confirme su estación (escanee su QR).")
        return redirect("shift:context")
    reason = HelpReason.objects.filter(code=body.get("reason"), active=True).first()
    if reason is None:
        if is_json:
            return json_error("Elija un motivo.")
        messages.error(request, "Elija un motivo.")
        return redirect("shift:help")
    relate = HelpRequest.objects.filter(pk=body.get("relate_to") or 0).first()
    photo = None
    if not is_json and request.FILES.get("photo"):
        try:
            photo = store_upload(request.FILES["photo"], request.user, allowed={"png", "jpg", "jpeg"}, area=ctx.station.line.area)
        except UserFacingError as exc:
            messages.error(request, str(exc))
            return redirect("shift:help")
    h, created = services.create_help(request.user, ctx.station.line, ctx.station, reason, ctx.work_order, body.get("comment", ""), photo, relate,
                                      body.get("client_uuid") or None)
    if is_json:
        return json_ok({"id": h.pk, "created": created, "url": f"/turno/ayuda/{h.pk}/"})
    messages.success(request, f"Solicitud #{h.pk} enviada a {h.group or 'responsables'}." + ("" if created else " (ya estaba registrada)"))
    return redirect("shift:help_detail", pk=h.pk)


@require_cap("shift.use")
def help_detail(request, pk):
    h = get_object_or_404(HelpRequest.objects.select_related("reason", "line", "station", "created_by", "assignee"), pk=pk)
    if not can_access_area(request.user, h.line.area_id):
        raise PermissionDenied()
    if request.method == "POST":
        try:
            if request.POST.get("action") == "kaizen":
                return _help_to_kaizen(request, h)
            services.advance_help(h, request.user, request.POST.get("to"), request.POST.get("note", ""))
            messages.success(request, f"Estado: {h.get_status_display()}")
        except UserFacingError as exc:
            messages.error(request, str(exc))
        return redirect("shift:help_detail", pk=h.pk)
    allowed = services.TRANSITIONS.get(h.status, [])
    return render(request, "shift/help_detail.html", {"h": h, "status_labels": dict(HelpRequest.Status.choices), "events": h.events.select_related("user"), "allowed": allowed,
                                                       "can_attend": services.can_attend(request.user, h),
                                                       "repeats": HelpRequest.objects.filter(line=h.line, reason=h.reason).exclude(pk=h.pk).count()})


def _help_to_kaizen(request, h):
    from apps.kaizen.models import Improvement, KaizenTransition

    if not has_cap(request.user, "kaizen.create"):
        raise PermissionDenied()
    repeats = HelpRequest.objects.filter(line=h.line, reason=h.reason)
    imp = Improvement.objects.create(
        title=f"Recurrencia: {h.reason.label} en {h.line.code}"[:200], area=h.line.area, proposer=request.user,
        problem=f"{repeats.count()} solicitudes de ayuda «{h.reason.label}» registradas en {h.line.code}. Causa: POR INVESTIGAR (no es un diagnóstico).",
        objective="Reducir la recurrencia (definir indicador, unidad y periodo).")
    KaizenTransition.objects.create(improvement=imp, from_status="", to_status="proposal", user=request.user, comment="Desde solicitudes de ayuda")
    repeats.filter(kaizen__isnull=True).update(kaizen=imp)
    messages.success(request, f"Propuesta Kaizen {imp.code} creada y vinculada a {repeats.count()} solicitudes.")
    return redirect("kaizen:detail", pk=imp.pk)


# ---------------------------------------------------------------- downtime
@require_cap("shift.use")
def downtime(request):
    ctx = _ctx(request.user)
    if request.method == "POST":
        a = request.POST.get("action")
        try:
            if a == "start":
                if ctx.station is None:
                    raise UserFacingError("Confirme su estación.")
                if Downtime.objects.filter(station=ctx.station, ended_at__isnull=True).exists():
                    raise UserFacingError("Ya hay un paro abierto en esta estación; ciérrelo o corríjalo.")
                Downtime.objects.create(line=ctx.station.line, station=ctx.station, work_order=ctx.work_order, started_at=timezone.now(),
                                        started_by=request.user, reason=DowntimeReason.objects.filter(pk=request.POST.get("reason") or 0).first(),
                                        comment=request.POST.get("comment", "")[:300])
                messages.success(request, "Paro iniciado. Registre el fin al reanudar.")
            elif a in ("end", "correct"):
                d = get_object_or_404(Downtime, pk=request.POST.get("id"))
                if not can_access_area(request.user, d.line.area_id):
                    raise PermissionDenied()
                reason = DowntimeReason.objects.filter(pk=request.POST.get("reason") or 0).first()
                if a == "end":
                    if d.ended_at:
                        raise UserFacingError("El paro ya estaba cerrado.")
                    d.ended_at, d.ended_by = timezone.now(), request.user
                    if reason:
                        d.reason = reason
                    if request.POST.get("comment"):
                        d.comment = request.POST["comment"][:300]
                    d.save()
                    messages.success(request, f"Paro cerrado ({d.minutes():.0f} min).")
                else:
                    why = request.POST.get("why", "").strip()
                    if len(why) < 5:
                        raise UserFacingError("La corrección requiere un motivo.")
                    before = {"started_at": d.started_at.isoformat(), "ended_at": d.ended_at.isoformat() if d.ended_at else None,
                              "reason": str(d.reason or "")}
                    from datetime import datetime

                    tz = timezone.get_current_timezone()
                    for f in ("started_at", "ended_at"):
                        v = request.POST.get(f)
                        if v:
                            setattr(d, f, timezone.make_aware(datetime.fromisoformat(v), tz))
                    if d.ended_at and d.ended_at < d.started_at:
                        raise UserFacingError("El fin es anterior al inicio.")
                    if reason:
                        d.reason = reason
                    d.corrected = True
                    d.history = d.history + [{"ts": timezone.now().isoformat(), "user": request.user.username, "why": why, "before": before}]
                    d.save()
                    audit(request.user, "shift.downtime_corrected", d, why)
                    messages.success(request, "Paro corregido con historial.")
        except UserFacingError as exc:
            messages.error(request, str(exc))
        return redirect("shift:downtime")
    lines = _lines(request.user)
    return render(request, "shift/downtime.html", {"ctx": ctx, "reasons": DowntimeReason.objects.filter(active=True),
                                                    "open": Downtime.objects.filter(line__in=lines, ended_at__isnull=True).select_related("station", "reason"),
                                                    "recent": Downtime.objects.filter(line__in=lines).select_related("station", "reason")[:20]})


# ---------------------------------------------------------------- materials
@require_cap("shift.use")
def materials(request):
    ctx = _ctx(request.user)
    lines = _lines(request.user)
    if request.method == "POST":
        try:
            if request.POST.get("action") == "create":
                if ctx.station is None:
                    raise UserFacingError("Confirme su estación.")
                try:
                    qty = Decimal(request.POST.get("qty") or "0")
                except InvalidOperation:
                    raise UserFacingError("Cantidad no válida.")
                if qty <= 0 or not request.POST.get("material", "").strip():
                    raise UserFacingError("Indique material y cantidad positiva.")
                from django.contrib.auth.models import Group

                m = MaterialRequest.objects.create(line=ctx.station.line, station=ctx.station, work_order=ctx.work_order,
                                                   material=request.POST["material"].strip()[:120], qty=qty, unit=request.POST.get("unit", "pz")[:20],
                                                   reason=request.POST.get("reason", "")[:200], created_by=request.user,
                                                   group=Group.objects.filter(name="Materiales").first())
                services.notify(services.group_members(m.group), f"Solicitud de material #{m.pk}: {m.material}", f"{m.qty} {m.unit} · {m.line.code}",
                                "/turno/materiales/")
                messages.success(request, f"Solicitud #{m.pk} registrada (no es un movimiento de inventario).")
            else:
                m = get_object_or_404(MaterialRequest, pk=request.POST.get("id"), line__in=lines)
                to = request.POST.get("to")
                allowed = {"requested": ["received", "cancelled"], "received": ["in_progress", "delivered"], "in_progress": ["delivered"]}
                in_group = m.group_id and request.user.groups.filter(pk=m.group_id).exists()
                if to == "cancelled" and request.user.pk != m.created_by_id and not has_cap(request.user, "shift.attend"):
                    raise UserFacingError("Solo quien solicitó o un responsable puede cancelar.")
                if to != "cancelled" and not (in_group or has_cap(request.user, "shift.attend")):
                    raise UserFacingError("Solo el equipo de materiales o un responsable puede atender la solicitud.")
                if to not in allowed.get(m.status, []):
                    raise UserFacingError("Cambio de estado no permitido.")
                m.history = m.history + [{"ts": timezone.now().isoformat(), "from": m.status, "to": to, "user": request.user.username}]
                m.status, m.handled_by, m.updated = to, request.user, timezone.now()
                m.note = request.POST.get("note", m.note)[:300]
                m.save()
                services.notify([m.created_by], f"Material #{m.pk}: {m.get_status_display()}", m.material, "/turno/materiales/")
                messages.success(request, f"Solicitud #{m.pk}: {m.get_status_display()}")
        except UserFacingError as exc:
            messages.error(request, str(exc))
        return redirect("shift:materials")
    return render(request, "shift/materials.html", {"ctx": ctx, "items": MaterialRequest.objects.filter(line__in=lines).select_related("line", "station")[:60],
                                                     "can_attend": has_cap(request.user, "shift.attend") or request.user.groups.filter(name="Materiales").exists()})


# ---------------------------------------------------------------- manual capture & reconciliation
@require_cap("shift.capture")
def capture(request):
    ctx = _ctx(request.user)
    if request.method == "POST":
        from datetime import datetime

        tz = timezone.get_current_timezone()
        try:
            if ctx.station is None:
                raise UserFacingError("Confirme su estación.")
            try:
                qty = Decimal(request.POST.get("qty") or "0")
                start = timezone.make_aware(datetime.fromisoformat(request.POST["start"]), tz)
                end = timezone.make_aware(datetime.fromisoformat(request.POST["end"]), tz)
            except (InvalidOperation, KeyError, ValueError):
                raise UserFacingError("Revise cantidad y periodo (inicio y fin).")
            e, created = services.capture_manual(request.user, ctx.station.line, ctx.station, request.POST.get("work_order") or ctx.work_order,
                                                 qty, request.POST.get("unit") or ctx.station.line.count_unit, start, end,
                                                 request.POST.get("reason", ""), request.POST.get("lot_ref", "").strip(), "",
                                                 request.POST.get("client_uuid") or None)
            messages.success(request, f"Captura guardada como «{e.get_recon_status_display()}». No se suma a las cantidades confirmadas hasta conciliarse.")
        except UserFacingError as exc:
            messages.error(request, str(exc))
        return redirect("shift:capture")
    lines = _lines(request.user)
    return render(request, "shift/capture.html", {"ctx": ctx, "now": timezone.localtime(), "mine": PE.objects.filter(source=PE.Source.MANUAL, user=request.user)[:20],
                                                   "pending": PE.objects.filter(source=PE.Source.MANUAL, line__in=lines,
                                                                                recon_status__in=[PE.Recon.PENDING, PE.Recon.REVIEW]).count()})


@require_cap("shift.reconcile")
def reconciliation(request):
    lines = _lines(request.user)
    if request.method == "POST":
        m = get_object_or_404(PE, pk=request.POST.get("id"), source=PE.Source.MANUAL, line__in=lines)
        match = PE.objects.filter(pk=request.POST.get("match") or 0).exclude(source=PE.Source.MANUAL).first()
        try:
            recon_review(m, request.user, request.POST.get("decision"), match, request.POST.get("note", ""))
            messages.success(request, f"Captura #{m.pk}: {m.get_recon_status_display()}")
        except UserFacingError as exc:
            messages.error(request, str(exc))
        return redirect("shift:reconciliation")
    items = []
    for m in PE.objects.filter(source=PE.Source.MANUAL, line__in=lines, recon_status__in=[PE.Recon.PENDING, PE.Recon.REVIEW]).select_related("line", "user"):
        items.append((m, candidates(m)))
    done = PE.objects.filter(source=PE.Source.MANUAL, line__in=lines).exclude(recon_status__in=[PE.Recon.PENDING, PE.Recon.REVIEW])[:30]
    return render(request, "shift/reconciliation.html", {"items": items, "done": done})


# ---------------------------------------------------------------- close-out & reports
@require_cap("shift.use")
def closeout(request):
    ctx = _ctx(request.user)
    lines = _lines(request.user)
    line = ctx.station.line if ctx.station else lines.first()
    if request.GET.get("line"):
        line = _line(request.user, request.GET["line"])
    report = None
    if request.GET.get("r"):
        report = get_object_or_404(ShiftReport.objects.select_related("line", "shift"), pk=request.GET["r"], line__in=lines)
    elif line:
        report = ShiftReport.objects.filter(line=line).select_related("shift").first()
    shift, date, start, end = _now_shift()
    live = services.shift_summary(line, shift, date) if (line and shift) else None
    if request.method == "POST":
        a = request.POST.get("action")
        try:
            if a == "generate":
                prev = cal.previous()
                if not prev:
                    raise UserFacingError("No hay un turno terminado configurado.")
                r = services.generate_report(line, prev[0], prev[1], by=request.user.username)
                messages.info(request, "Borrador generado." if r else "El borrador de ese turno ya existía (no se duplica).")
            elif a == "downtime_reason":
                d = get_object_or_404(Downtime, pk=request.POST.get("id"), line__in=lines)
                d.reason = get_object_or_404(DowntimeReason, pk=request.POST.get("reason"))
                d.save(update_fields=["reason"])
                messages.success(request, "Motivo de paro registrado.")
            elif a == "help_comment":
                h = get_object_or_404(HelpRequest, pk=request.POST.get("id"), line__in=lines)
                h.comment = request.POST.get("comment", "")[:2000]
                h.save(update_fields=["comment"])
                messages.success(request, "Comentario agregado.")
            elif a in ("refresh", "review", "close"):
                if report is None:
                    raise UserFacingError("No hay reporte.")
                if a == "refresh":
                    services.refresh_draft(report)
                elif not has_cap(request.user, "shift.close"):
                    raise PermissionDenied("Solo un responsable revisa y cierra reportes.")
                elif a == "review":
                    services.review(report, request.user)
                else:
                    services.close(report, request.user, request.POST.get("force_reason", ""))
                messages.success(request, f"{report}: {report.get_status_display()}")
        except UserFacingError as exc:
            messages.error(request, str(exc))
        return redirect(request.get_full_path())
    revisions = ShiftReport.objects.filter(line=report.line, shift=report.shift, date=report.date).order_by("revision") if report else []
    return render(request, "shift/closeout.html", {"ctx": ctx, "line": line, "lines": lines, "report": report, "live": live,
                                                    "reasons": DowntimeReason.objects.filter(active=True), "revisions": revisions,
                                                    "reports": ShiftReport.objects.filter(line__in=lines).select_related("line", "shift")[:20],
                                                    "can_close": has_cap(request.user, "shift.close")})


@require_cap("shift.use")
def report_export(request, pk, fmt):
    from django.http import HttpResponse

    from apps.reports.exporters import to_pdf, to_xlsx

    r = get_object_or_404(ShiftReport, pk=pk)
    if not can_access_area(request.user, r.line.area_id):
        raise PermissionDenied()
    snap = services.report_as_snapshot(r)
    if fmt == "pdf":
        resp = HttpResponse(to_pdf(snap), content_type="application/pdf")
        disp = "inline" if request.GET.get("inline") else "attachment"
    elif fmt == "xlsx":
        resp = HttpResponse(to_xlsx(snap), content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
        disp = "attachment"
    else:
        raise Http404()
    resp["Content-Disposition"] = f'{disp}; filename="reporte_turno_{r.line.code}_{r.date}_{r.shift.code}_r{r.revision}.{fmt}"'
    return resp


# ---------------------------------------------------------------- handover
@require_cap("shift.use")
def handover(request):
    lines = _lines(request.user)
    if request.method == "POST":
        h = get_object_or_404(Handover, pk=request.POST.get("id"), line__in=lines)
        try:
            if request.POST.get("action") == "observe":
                h.observations = (h.observations + "\n" if h.observations else "") + f"[{request.user.username}] {request.POST.get('text', '')[:1000]}"
                h.save(update_fields=["observations"])
            else:
                services.receive_handover(h, request.user)
                messages.success(request, "Relevo recibido. Las incidencias siguen abiertas con su responsable.")
        except UserFacingError as exc:
            messages.error(request, str(exc))
        return redirect("shift:handover")
    items = Handover.objects.filter(line__in=lines).select_related("line", "shift", "received_by")[:20]
    open_help = HelpRequest.objects.filter(line__in=lines, status__in=["reported", "received", "in_progress"]).select_related("reason", "assignee")
    return render(request, "shift/handover.html", {"items": items, "open_help": open_help})


# ---------------------------------------------------------------- instructions & checklists
@require_cap("shift.use")
def instructions(request):
    ctx = _ctx(request.user)
    op = ctx.station.operation if ctx.station else ""
    line = ctx.station.line if ctx.station else None
    part = ""
    if ctx.work_order and line:
        p = ShiftPlan.objects.filter(line=line, work_order__iexact=ctx.work_order).order_by("-date").first()
        part = p.part_number if p else ""
    qs = OperationInstruction.objects.filter(status="approved")
    if line:
        qs = qs.filter(Q(line=line) | Q(line__isnull=True)).filter(Q(operation="") | Q(operation__iexact=op)).filter(Q(part_number="") | Q(part_number__iexact=part))
    if request.GET.get("leer"):
        ins = get_object_or_404(OperationInstruction, pk=request.GET["leer"])
        InstructionRead.objects.create(instruction=ins, user=request.user)
    checks = ChecklistTemplate.objects.filter(active=True)
    if line:
        checks = checks.filter(Q(line=line) | Q(line__isnull=True)).filter(Q(operation="") | Q(operation__iexact=op))
    return render(request, "shift/instructions.html", {"ctx": ctx, "items": qs, "checks": checks, "part": part,
                                                        "obsolete": OperationInstruction.objects.filter(status="obsolete")[:10]})


@require_cap("shift.use")
def checklist(request, pk):
    ctx = _ctx(request.user)
    t = get_object_or_404(ChecklistTemplate, pk=pk, active=True)
    if request.method == "POST":
        results = []
        failed = []
        for i, item in enumerate(t.items):
            ok = request.POST.get(f"item{i}") == "ok"
            note = request.POST.get(f"note{i}", "")[:300]
            if item.get("evidence") and ok and not note:
                messages.error(request, f"El punto «{item['text']}» requiere evidencia/nota.")
                return redirect("shift:checklist", pk=t.pk)
            results.append({"ok": ok, "note": note})
            if not ok:
                failed.append((item, note))
        run = ChecklistRun.objects.create(template=t, template_version=t.version, station=ctx.station, work_order=ctx.work_order, user=request.user,
                                          results=results, needs_attention=bool(failed))
        if failed and ctx.station:
            from django.contrib.auth.models import Group

            for item, note in failed:
                reason, _ = HelpReason.objects.get_or_create(code="lista-arranque", defaults={"label": "Punto de lista no conforme"})
                g = Group.objects.filter(name=item.get("fail_group", "")).first()
                h, _c = services.create_help(request.user, ctx.station.line, ctx.station, reason, ctx.work_order,
                                             f"Lista «{t.name}»: {item['text']} — {note}")
                if g:
                    h.group = g
                    h.save(update_fields=["group"])
            messages.warning(request, f"{len(failed)} punto(s) no conforme(s): se generaron pendientes. La lista NO libera la estación.")
        else:
            messages.success(request, "Lista registrada. Registrar la lista no equivale a una liberación de proceso.")
        audit(request.user, "shift.checklist", run, f"{t.name} v{t.version}: {len(failed)} no conformes")
        return redirect("shift:instructions")
    return render(request, "shift/checklist.html", {"t": t, "ctx": ctx})


# ---------------------------------------------------------------- quality observation
@require_cap("shift.use")
def quality(request):
    ctx = _ctx(request.user)
    lines = _lines(request.user)
    if request.method == "POST":
        try:
            if request.POST.get("action") == "create":
                if ctx.station is None:
                    raise UserFacingError("Confirme su estación.")
                ev = None
                if request.FILES.get("evidence"):
                    ev = store_upload(request.FILES["evidence"], request.user, allowed={"png", "jpg", "jpeg", "pdf"}, area=ctx.station.line.area)
                q = QualityObservation.objects.create(line=ctx.station.line, station=ctx.station, work_order=request.POST.get("work_order") or ctx.work_order,
                                                      serial=request.POST.get("serial", "")[:80], category=request.POST.get("category", "")[:80] or "Sin categoría",
                                                      description=request.POST.get("description", "")[:2000], evidence=ev, created_by=request.user)
                messages.success(request, f"Observación #{q.pk} registrada (no es una disposición).")
            else:
                if not has_cap(request.user, "shift.quality"):
                    raise PermissionDenied("Solo un rol autorizado da disposición.")
                q = get_object_or_404(QualityObservation, pk=request.POST.get("id"), line__in=lines)
                to = request.POST.get("to")
                if to not in QualityObservation.Status.values:
                    raise UserFacingError("Disposición no válida.")
                q.status, q.disposition_by, q.disposition_at = to, request.user, timezone.now()
                q.disposition_note = request.POST.get("note", "")[:300]
                q.official_reference = request.POST.get("official_reference", "")[:120]
                q.save()
                audit(request.user, "shift.quality_disposition", q, f"#{q.pk} → {q.get_status_display()} ({q.official_reference})")
                messages.success(request, "Disposición registrada.")
        except UserFacingError as exc:
            messages.error(request, str(exc))
        return redirect("shift:quality")
    return render(request, "shift/quality.html", {"ctx": ctx, "items": QualityObservation.objects.filter(line__in=lines).select_related("line")[:50],
                                                   "can_dispose": has_cap(request.user, "shift.quality"), "statuses": QualityObservation.Status.choices})


# ---------------------------------------------------------------- supervisor board, plan, area screen
@require_cap("shift.attend")
def board(request):
    shift, date, start, end = _now_shift()
    rows = []
    for line in _lines(request.user):
        s = services.shift_summary(line, shift, date) if shift else None
        rows.append((line, s))
    return render(request, "shift/board.html", {"rows": rows, "shift": shift, "date": date, "sources": services.source_status(),
                                                 "inbox": _inbox(request.user)[:30],
                                                 "pending_recon": PE.objects.filter(source=PE.Source.MANUAL, line__in=_lines(request.user),
                                                                                    recon_status__in=[PE.Recon.PENDING, PE.Recon.REVIEW]).count(),
                                                 "reports": ShiftReport.objects.filter(line__in=_lines(request.user)).exclude(status="closed").select_related("line", "shift")[:20],
                                                 "gaps": SyncGap.objects.all()[:5]})


@require_cap("shift.plan")
def plan(request):
    lines = _lines(request.user)
    shift, date, start, end = _now_shift()
    if request.method == "POST":
        from datetime import date as ddate

        line = _line(request.user, request.POST.get("line"))
        sh = get_object_or_404(Shift, pk=request.POST.get("shift"))
        try:
            target = Decimal(request.POST.get("target") or "0")
            d = ddate.fromisoformat(request.POST.get("date"))
        except (InvalidOperation, ValueError):
            messages.error(request, "Revise meta y fecha.")
            return redirect("shift:plan")
        reason = request.POST.get("reason", "").strip()
        wo = request.POST.get("work_order", "").strip()[:60]
        if not wo or target <= 0:
            messages.error(request, "Indique orden y una meta positiva.")
            return redirect("shift:plan")
        existing = ShiftPlan.objects.filter(line=line, shift=sh, date=d, work_order=wo).first()
        if existing and len(reason) < 5:
            messages.error(request, "Cambiar una meta existente requiere motivo.")
            return redirect("shift:plan")
        p, created = ShiftPlan.objects.update_or_create(line=line, shift=sh, date=d, work_order=wo, defaults={
            "target": target, "unit": request.POST.get("unit") or line.count_unit, "part_number": request.POST.get("part_number", "")[:80],
            "set_by": request.user, "updated": timezone.now(), "reason": reason or "Alta"})
        audit(request.user, "shift.plan_saved", p, f"{line.code} {d} {sh.code} {wo}: meta {target} {p.unit}" + (f" · {reason}" if reason else ""),
              {"before": str(existing.target) if existing else None})
        messages.success(request, "Meta del turno guardada.")
        return redirect("shift:plan")
    return render(request, "shift/plan.html", {"lines": lines, "shifts": Shift.objects.filter(active=True), "today": timezone.localdate(),
                                                "current": (shift, date), "items": ShiftPlan.objects.filter(line__in=lines).select_related("line", "shift")[:60]})


@require_cap("shift.use")
def area_screen(request, code):
    line = get_object_or_404(Line, code=code)
    if not can_access_area(request.user, line.area_id):
        raise PermissionDenied()
    return render(request, "shift/area_screen.html", {"line": line})


@require_GET
@api
def area_api(request, code):
    line = get_object_or_404(Line, code=code)
    if not (has_cap(request.user, "shift.use") and can_access_area(request.user, line.area_id)):
        return json_error("Sin permiso.", status=403)
    shift, date, start, end = _now_shift()
    s = services.shift_summary(line, shift, date) if shift else None
    if s is None:
        return json_ok({"line": line.code, "shift": None})
    return json_ok({"line": line.code, "shift": s["shift"], "window": s["window"], "orders": [{k: o[k] for k in ("work_order", "target", "good", "pending", "unit", "provisional")}
                                                                                          for o in s["orders"]],
                    "compliance": s["compliance"], "downtime_minutes": s["downtime_minutes"], "open_help": len(s["help"]),
                    "sources": [{"name": x["name"], "health_label": x["health_label"], "last_success": x["last_success"]} for x in s["sources"]],
                    "synthetic": line.synthetic, "server_time": timezone.localtime().strftime("%H:%M:%S")})


# ---------------------------------------------------------------- sources (OData)
@require_cap("shift.use")
def sources(request):
    conns = ODataConnection.objects.all()
    return render(request, "shift/sources.html", {"conns": conns, "status": services.source_status(), "can_configure": has_cap(request.user, "shift.configure"),
                                                   "runs": odata.SyncRun.objects.select_related("connection")[:20], "gaps": SyncGap.objects.all()[:10],
                                                   "fields": odata.PORTAL_FIELDS})


@require_POST
@require_cap("shift.configure")
def source_action(request, pk):
    conn = get_object_or_404(ODataConnection, pk=pk)
    a = request.POST.get("action")
    if a == "diagnose":
        stages, meta = odata.diagnose(conn)
        ok = odata.diagnosis_ok(stages)
        if meta:
            conn.odata_version = meta.get("version", "")
            conn.metadata_summary = {"entity_sets": {k: {"keys": v["keys"], "properties": v["properties"]} for k, v in meta["entity_sets"].items()},
                                     "sample": meta.get("sample", [])[:5]}
        conn.validated_at = timezone.now() if ok else None
        if not ok:
            conn.enabled = False
        conn.save()
        request.session[f"diag_{conn.pk}"] = stages
        audit(request.user, "shift.odata_diagnose", conn, f"Diagnóstico {'correcto' if ok else 'con fallas'}")
        messages.info(request, "Diagnóstico ejecutado.")
    elif a == "save_mapping":
        try:
            conn.entity_set = request.POST.get("entity_set", "").strip()
            conn.key_fields = [k.strip() for k in request.POST.get("key_fields", "").split(",") if k.strip()]
            conn.mapping = {f: request.POST.get(f"map_{f}", "").strip() for f in odata.PORTAL_FIELDS if request.POST.get(f"map_{f}", "").strip()}
            conn.watermark_field = request.POST.get("watermark_field", "").strip()
            conn.time_field = request.POST.get("time_field", "").strip() or conn.mapping.get("event_at", "")
            conn.validated_at = None  # mapping changed: must be re-validated
            conn.save()
            messages.success(request, "Mapeo guardado. Ejecute el diagnóstico para validarlo.")
        except Exception:
            messages.error(request, "Mapeo no válido.")
    elif a == "sync":
        if not conn.validated_at:
            messages.error(request, "Primero ejecute un diagnóstico correcto.")
        else:
            run = odata.sync_once(conn)
            messages.info(request, f"Sincronización {run.status}: {run.read} leídos, {run.created} nuevos, {run.updated} corregidos, {run.rejected} rechazados."
                          + (f" Error: {run.error}" if run.error else ""))
    elif a == "toggle":
        if not conn.validated_at and not conn.enabled:
            messages.error(request, "La sincronización solo se activa tras un diagnóstico correcto.")
        else:
            conn.enabled = not conn.enabled
            conn.save(update_fields=["enabled"])
    return redirect(f"/turno/fuentes/{conn.pk}/")


@require_cap("shift.use")
def source_detail(request, pk):
    conn = get_object_or_404(ODataConnection, pk=pk)
    meta = conn.metadata_summary or {}
    return render(request, "shift/source_detail.html", {"conn": conn, "stages": request.session.get(f"diag_{conn.pk}", []), "meta": meta,
                                                         "sets": sorted((meta.get("entity_sets") or {}).keys()),
                                                         "props": sorted(((meta.get("entity_sets") or {}).get(conn.entity_set) or {}).get("properties", {}).items()),
                                                         "fields": odata.PORTAL_FIELDS, "can_configure": has_cap(request.user, "shift.configure"),
                                                         "runs": conn.runs.all()[:15], "health": ODataConnection.Health(conn.health()).label})


# ---------------------------------------------------------------- labels from context
@require_cap("labels.print")
def labels(request):
    from apps.labels.models import LabelTemplate

    ctx = _ctx(request.user)
    qs = LabelTemplate.objects.filter(published__isnull=False)
    if ctx.station and ctx.station.line.label_templates.exists():
        qs = ctx.station.line.label_templates.filter(published__isnull=False)
    ids = allowed_area_ids(request.user)
    if ids is not None and hasattr(LabelTemplate, "area"):
        qs = qs.filter(Q(area__isnull=True) | Q(area__in=ids))
    return render(request, "shift/labels.html", {"ctx": ctx, "templates": qs})
