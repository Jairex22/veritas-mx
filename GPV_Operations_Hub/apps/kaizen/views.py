import io
from decimal import Decimal, InvalidOperation

from django import forms
from django.contrib import messages
from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from apps.core.audit import audit
from apps.core.files import store_upload
from apps.core.jobs import UserFacingError
from apps.core.models import Area
from apps.core.notify import notify
from apps.core.permissions import allowed_area_ids, can_access_area, filter_by_area, has_cap, require_cap

from .models import TRANSITIONS, Improvement, KaizenAction, KaizenMeasure, KaizenSaving, KaizenTransition, Status


class ImprovementForm(forms.ModelForm):
    class Meta:
        model = Improvement
        fields = ["title", "problem", "current_state", "objective", "area", "responsible", "priority", "start_date", "target_date", "indicator"]
        widgets = {"start_date": forms.DateInput(attrs={"type": "date"}), "target_date": forms.DateInput(attrs={"type": "date"}),
                   "problem": forms.Textarea(attrs={"rows": 3}), "current_state": forms.Textarea(attrs={"rows": 3}),
                   "objective": forms.Textarea(attrs={"rows": 3})}

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        ids = allowed_area_ids(user)
        self.fields["area"].queryset = Area.objects.filter(active=True) if ids is None else Area.objects.filter(id__in=ids)
        self.fields["responsible"].queryset = get_user_model().objects.filter(is_active=True).order_by("username")


def _get(request, pk):
    imp = get_object_or_404(Improvement.objects.select_related("area", "responsible", "proposer"), pk=pk)
    if not can_access_area(request.user, imp.area_id):
        raise PermissionDenied("La mejora pertenece a un área sin permiso.")
    return imp


def _can_edit(user, imp):
    return has_cap(user, "kaizen.evaluate") or user.pk in (imp.proposer_id, imp.responsible_id)


@require_cap("kaizen.create")
def board(request):
    qs = filter_by_area(Improvement.objects.select_related("area", "responsible"), request.user)
    q = request.GET.get("q", "").strip()
    if q:
        qs = qs.filter(title__icontains=q)
    if request.GET.get("area"):
        qs = qs.filter(area__code=request.GET["area"])
    cols = [(s, [i for i in qs if i.status == s.value]) for s in Status]
    return render(request, "kaizen/board.html", {"cols": cols, "q": q, "areas": Area.objects.all()})


@require_cap("kaizen.create")
def create(request):
    form = ImprovementForm(request.POST or None, user=request.user)
    if request.method == "POST" and form.is_valid():
        imp = form.save(commit=False)
        if not can_access_area(request.user, imp.area_id):
            raise PermissionDenied()
        imp.proposer = request.user
        imp.save()
        KaizenTransition.objects.create(improvement=imp, from_status="", to_status=Status.PROPOSAL, user=request.user, comment="Registro")
        audit(request.user, "kaizen.created", imp, f"{imp.code} {imp.title}")
        from apps.core.notify import users_for_scope

        notify([u for u in users_for_scope(area_ids=[imp.area_id], roles=["supervisor"])], f"Nueva propuesta Kaizen {imp.code}", imp.title,
               f"/kaizen/{imp.pk}/")
        messages.success(request, f"Mejora {imp.code} registrada.")
        return redirect("kaizen:detail", pk=imp.pk)
    return render(request, "kaizen/form.html", {"form": form})


@require_cap("kaizen.create")
def detail(request, pk):
    imp = _get(request, pk)
    from apps.comms.services import thread_context

    allowed = []
    for to, (cap, needs_comment) in TRANSITIONS.get(imp.status, {}).items():
        ok = (has_cap(request.user, cap) if cap != "owner" else (_can_edit(request.user, imp)))
        if ok:
            allowed.append((to, Status(to).label, needs_comment))
    from apps.production.models import WorkOrder

    return render(request, "kaizen/detail.html", {
        "imp": imp, "allowed": allowed, "can_edit": _can_edit(request.user, imp), "can_evaluate": has_cap(request.user, "kaizen.evaluate"),
        "users": get_user_model().objects.filter(is_active=True).order_by("username"),
        "orders": filter_by_area(WorkOrder.objects.all(), request.user)[:300],
        "whys": (imp.whys + [""] * 5)[:5], **thread_context(request, imp),
    })


@require_POST
@require_cap("kaizen.create")
def update(request, pk):
    imp = _get(request, pk)
    if not _can_edit(request.user, imp):
        raise PermissionDenied("Solo el proponente, el responsable o un evaluador pueden editar.")
    section = request.POST.get("section")
    if int(request.POST.get("version", 0)) != imp.version:
        messages.error(request, "La mejora fue modificada por otra persona. Revise los cambios y vuelva a intentarlo.")
        return redirect("kaizen:detail", pk=imp.pk)
    try:
        with transaction.atomic():
            if section == "analysis":
                imp.whys = [request.POST.get(f"why{i}", "").strip()[:500] for i in range(5)]
                imp.root_cause = request.POST.get("root_cause", "")
                imp.pdca = {k: request.POST.get(f"pdca_{k}", "") for k in ("plan", "do", "check", "act")}
                imp.results = request.POST.get("results", "")
            elif section == "action":
                desc = request.POST.get("description", "").strip()
                if not desc:
                    raise UserFacingError("Describa la acción.")
                KaizenAction.objects.create(improvement=imp, description=desc[:300], owner_id=request.POST.get("owner") or None,
                                            due=request.POST.get("due") or None)
            elif section == "action_done":
                KaizenAction.objects.filter(improvement=imp, pk=request.POST.get("action_id")).update(done_at=timezone.now())
            elif section == "measure":
                try:
                    KaizenMeasure.objects.create(
                        improvement=imp, name=request.POST["name"], unit=request.POST["unit"], source=request.POST["source"],
                        before_from=request.POST["before_from"], before_to=request.POST["before_to"], before_value=Decimal(request.POST["before_value"]),
                        after_from=request.POST["after_from"], after_to=request.POST["after_to"], after_value=Decimal(request.POST["after_value"]),
                        higher_is_better=request.POST.get("higher_is_better") == "on", notes=request.POST.get("notes", "")[:300])
                except (KeyError, InvalidOperation, ValueError):
                    raise UserFacingError("Complete indicador, unidad, fuente, periodos (antes/después) y valores numéricos.")
            elif section == "saving":
                try:
                    KaizenSaving.objects.create(improvement=imp, kind=request.POST["kind"], amount=Decimal(request.POST["amount"]),
                                                unit=request.POST["unit"], formula=request.POST["formula"], calculation=request.POST["calculation"],
                                                period=request.POST["period"], created_by=request.user)
                except (KeyError, InvalidOperation):
                    raise UserFacingError("Indique tipo, monto, unidad, fórmula, cálculo y periodo del ahorro.")
            elif section == "saving_approve":
                if not has_cap(request.user, "kaizen.evaluate"):
                    raise PermissionDenied("Solo un supervisor puede aprobar ahorros.")
                KaizenSaving.objects.filter(improvement=imp, pk=request.POST.get("saving_id")).update(approved_by=request.user, approved_at=timezone.now())
            elif section == "links":
                from apps.production.models import WorkOrder

                imp.linked_orders.set(filter_by_area(WorkOrder.objects.filter(pk__in=request.POST.getlist("orders")), request.user))
                for up in request.FILES.getlist("evidence"):
                    imp.evidence.add(store_upload(up, request.user, area=imp.area))
            else:
                raise UserFacingError("Sección desconocida.")
            imp.version += 1
            imp.save()
    except UserFacingError as exc:
        messages.error(request, str(exc))
        return redirect("kaizen:detail", pk=imp.pk)
    audit(request.user, f"kaizen.{section}", imp, f"{imp.code}: actualización {section}")
    messages.success(request, "Guardado.")
    return redirect("kaizen:detail", pk=imp.pk)


@require_POST
@require_cap("kaizen.create")
def transition(request, pk):
    imp = _get(request, pk)
    to = request.POST.get("to")
    rule = TRANSITIONS.get(imp.status, {}).get(to)
    if rule is None:
        messages.error(request, "Transición no permitida desde el estado actual.")
        return redirect("kaizen:detail", pk=imp.pk)
    cap, needs_comment = rule
    if (cap == "owner" and not _can_edit(request.user, imp)) or (cap != "owner" and not has_cap(request.user, cap)):
        raise PermissionDenied("No tiene permiso para esta transición.")
    comment = request.POST.get("comment", "").strip()
    if needs_comment and len(comment) < 5:
        messages.error(request, "Esta transición requiere un comentario (motivo).")
        return redirect("kaizen:detail", pk=imp.pk)
    if to == Status.CLOSED and not (imp.measures.exists() or imp.results.strip()):
        messages.error(request, "Para cerrar registre resultados o una comparación antes/después.")
        return redirect("kaizen:detail", pk=imp.pk)
    with transaction.atomic():
        KaizenTransition.objects.create(improvement=imp, from_status=imp.status, to_status=to, user=request.user, comment=comment)
        imp.status = to
        if to == Status.APPROVED:
            imp.approved_by, imp.approved_at = request.user, timezone.now()
        if to == Status.CLOSED:
            imp.closed_date = timezone.localdate()
        imp.version += 1
        imp.save()
    audit(request.user, "kaizen.transition", imp, f"{imp.code} → {Status(to).label}. {comment}")
    notify([u for u in (imp.proposer, imp.responsible) if u and u != request.user], f"Kaizen {imp.code}: {Status(to).label}", comment or imp.title,
           f"/kaizen/{imp.pk}/")
    messages.success(request, f"Estado cambiado a {Status(to).label}.")
    return redirect("kaizen:detail", pk=imp.pk)


@require_cap("kaizen.create")
def a3_pdf(request, pk):
    imp = _get(request, pk)
    data = render_a3(imp)
    resp = HttpResponse(data, content_type="application/pdf")
    resp["Content-Disposition"] = f'{"inline" if request.GET.get("inline") else "attachment"}; filename="A3_{imp.code}.pdf"'
    return resp


def render_a3(imp):
    """A3 landscape report: problem/analysis on the left, actions/results on the right."""
    from xml.sax.saxutils import escape

    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A3, landscape
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import mm
    from reportlab.platypus import Frame, KeepInFrame, Paragraph, Spacer, Table, TableStyle
    from reportlab.pdfgen import canvas as pdfcanvas

    buf = io.BytesIO()
    size = landscape(A3)
    c = pdfcanvas.Canvas(buf, pagesize=size)
    c.setTitle(f"A3 {imp.code}")
    st = getSampleStyleSheet()
    h = ParagraphStyle("h", parent=st["Heading3"], textColor=colors.HexColor("#14324a"), spaceBefore=4, spaceAfter=2)
    p = ParagraphStyle("p", parent=st["Normal"], fontSize=9, leading=11.5)
    E = lambda s: escape(s or "—").replace("\n", "<br/>")  # noqa: E731
    W, H = size
    c.setFillColor(colors.HexColor("#14324a"))
    c.rect(0, H - 22 * mm, W, 22 * mm, fill=1, stroke=0)
    c.setFillColor(colors.white)
    c.setFont("Helvetica-Bold", 16)
    c.drawString(12 * mm, H - 14 * mm, f"A3 Kaizen {imp.code} · {imp.title[:90]}")
    c.setFont("Helvetica", 9)
    c.drawRightString(W - 12 * mm, H - 14 * mm, f"Área {imp.area.code} · Estado {imp.get_status_display()} · Generado {timezone.localtime():%Y-%m-%d %H:%M}")
    left = [Paragraph("1. Problema", h), Paragraph(E(imp.problem), p), Paragraph("2. Estado actual", h), Paragraph(E(imp.current_state), p),
            Paragraph("3. Objetivo", h), Paragraph(E(imp.objective), p), Paragraph("4. Análisis — 5 porqués", h)]
    for i, w in enumerate(imp.whys or [], start=1):
        if w:
            left.append(Paragraph(f"¿Por qué {i}? {E(w)}", p))
    left += [Paragraph("Causa raíz", h), Paragraph(E(imp.root_cause), p), Paragraph("PDCA", h)]
    for k, label in (("plan", "Planear"), ("do", "Hacer"), ("check", "Verificar"), ("act", "Actuar")):
        left.append(Paragraph(f"<b>{label}:</b> {E((imp.pdca or {}).get(k, ''))}", p))
    right = [Paragraph("5. Plan de acciones", h)]
    rows = [["Acción", "Responsable", "Fecha", "Estado"]] + [[Paragraph(E(a.description), p), a.owner.username if a.owner else "", str(a.due or ""),
                                                               "Hecha" if a.done_at else "Pendiente"] for a in imp.actions.all()]
    t = Table(rows, colWidths=[95 * mm, 35 * mm, 25 * mm, 22 * mm], repeatRows=1)
    t.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), .3, colors.grey), ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#DCE6F0")), ("FONTSIZE", (0, 0), (-1, -1), 8),
                           ("VALIGN", (0, 0), (-1, -1), "TOP")]))
    right += [t, Paragraph("6. Resultados — antes / después (periodos, unidades y fuente explícitos)", h)]
    mrows = [["Indicador", "Antes (periodo)", "Después (periodo)", "Cambio", "Fuente"]]
    for m in imp.measures.all():
        dp = m.delta_pct
        mrows.append([f"{m.name} ({m.unit})", f"{m.before_value:g} ({m.before_from} a {m.before_to})", f"{m.after_value:g} ({m.after_from} a {m.after_to})",
                      f"{m.delta:+g}" + (f" ({dp:+.1f} %)" if dp is not None else "") + (" ✓" if m.improved else ""), Paragraph(E(m.source), p)])
    t2 = Table(mrows, colWidths=[38 * mm, 40 * mm, 40 * mm, 27 * mm, 32 * mm], repeatRows=1)
    t2.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), .3, colors.grey), ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#DCE6F0")), ("FONTSIZE", (0, 0), (-1, -1), 7.5)]))
    right += [t2, Paragraph(E(imp.results), p), Paragraph("7. Ahorros (solo con fórmula y aprobación)", h)]
    for s in imp.savings.all():
        right.append(Paragraph(f"{s.get_kind_display()}: <b>{s.amount:g} {E(s.unit)}</b> · {E(s.period)} · fórmula: {E(s.formula)} · "
                               f"{'aprobado por ' + s.approved_by.username + ' ' + timezone.localtime(s.approved_at).strftime('%Y-%m-%d') if s.approved_by else 'PENDIENTE DE APROBACIÓN'}", p))
    if not imp.savings.exists():
        right.append(Paragraph("Sin ahorros declarados.", p))
    right += [Spacer(1, 4), Paragraph("8. Aprobaciones y trazabilidad", h)]
    if imp.approved_by:
        right.append(Paragraph(f"Aprobada por {E(imp.approved_by.get_full_name() or imp.approved_by.username)} el {timezone.localtime(imp.approved_at):%Y-%m-%d %H:%M}", p))
    for tr in imp.transitions.select_related("user"):
        right.append(Paragraph(f"{timezone.localtime(tr.ts):%Y-%m-%d %H:%M} · {E(tr.user.username)} · {tr.from_status or '—'} → {tr.to_status} {E(tr.comment)}", p))
    for flow, x in ((left, 10 * mm), (right, W / 2 + 4 * mm)):
        fr = Frame(x, 12 * mm, W / 2 - 16 * mm, H - 38 * mm, showBoundary=0)
        fr.addFromList([KeepInFrame(W / 2 - 16 * mm, H - 38 * mm, flow, mode="shrink")], c)
    c.setFont("Helvetica", 7)
    c.setFillColor(colors.HexColor("#5b6b7b"))
    c.drawString(10 * mm, 6 * mm, f"Proponente {imp.proposer.username} · Responsable {imp.responsible.username if imp.responsible else '—'} · GPV Operations Hub")
    c.showPage()
    c.save()
    return buf.getvalue()
