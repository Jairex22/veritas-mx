import io
import json

from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.http import Http404, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from apps.core.audit import audit
from apps.core.jobs import UserFacingError, enqueue
from apps.core.models import Area, Role, Shift
from apps.core.permissions import has_cap, require_cap
from apps.core.utils import api, json_error, json_ok, paginate, read_json
from apps.production.metrics import (AGGS, DIMENSIONS, MEASURES, Filters, kpi_summary, order_rows, pareto,
                                     records_queryset, series)
from apps.production.views import _filter_context

from .exporters import safe_cell_text, to_csv, to_xlsx
from .models import FORMATS, Dashboard, ReportKind, ReportRun, ReportSchedule
from .services import create_run, next_occurrence, retry_run, validate_plan_join, widget_data
from .snapshot import ORDER_COLUMNS, order_table_rows


def _ser_metric(m):
    return {k: v for k, v in m.items()}


@require_cap("dashboard.view")
def dashboard(request):
    f = Filters.from_dict(request.GET)
    ctx = _filter_context(request, f)
    ctx["persist_key"] = "dashboard"
    ctx["boards"] = [d for d in Dashboard.objects.all() if d.user_can_view(request.user)]
    return render(request, "reports/dashboard.html", ctx)


@api
def dashboard_data(request):
    if not has_cap(request.user, "dashboard.view"):
        return json_error("Permiso requerido: ver dashboards.", status=403)
    f = Filters.from_dict(request.GET)
    kpis = kpi_summary(request.user, f)
    rows, _ = order_rows(request.user, f)
    by_line = {}
    for r in rows:
        key = r["line"] or "(sin línea)"
        b = by_line.setdefault(key, {"key": key, "planned": 0.0, "good": 0.0, "pending": 0.0})
        b["planned"] += float(r["planned"] or 0)
        b["good"] += float(r["good"] or 0)
        b["pending"] += float(r["pending"] or 0)
    late = [{"number": r["number"], "line": r["line"], "pending": float(r["pending"] or 0),
             "due": timezone.localtime(r["due"]).strftime("%d/%m %H:%M") if r["due"] else "", "id": r["id"]}
            for r in rows if r["late"]][:20]
    from apps.kaizen.models import Improvement, Status

    from apps.core.permissions import filter_by_area

    kz = filter_by_area(Improvement.objects.all(), request.user)
    kaizen = [{"key": s.label, "value": kz.filter(status=s.value).count()} for s in Status]
    data = {
        "kpis": {k: (_ser_metric(v) if isinstance(v, dict) else v) for k, v in kpis.items() if k not in ("last_import", "last_plan_change")},
        "last_import": timezone.localtime(kpis["last_import"]).strftime("%d/%m/%Y %H:%M") if kpis["last_import"] else None,
        "by_line": sorted(by_line.values(), key=lambda x: x["key"]),
        "by_day": series(request.user, f, "date", "qty_good", "sum", limit=62),
        "by_shift": series(request.user, f, "shift", "qty_good", "sum"),
        "by_hour": series(request.user, f, "hour", "qty_good", "sum"),
        "pareto": pareto(request.user, f)[:15],
        "late": late, "kaizen": kaizen, "server_time": timezone.localtime().strftime("%H:%M:%S"),
    }
    return json_ok(data)


@require_cap("dashboard.view")
def export(request):
    """Export exactly the current selection (same filters, same metric layer)."""
    f = Filters.from_dict(request.GET)
    fmt = request.GET.get("fmt", "xlsx")
    table = request.GET.get("table", "orders")
    if table == "records":
        qs = records_queryset(request.user, f, kinds=None).select_related("dataset", "area").order_by("date", "id")
        if request.GET.get("dataset"):
            qs = qs.filter(dataset__code=request.GET["dataset"])
        if request.GET.get("cause"):
            qs = qs.filter(cause__iexact=request.GET["cause"])
        cols = ["date", "shift", "area", "line", "work_order", "part_number", "station", "serial", "result", "cause", "unit",
                "qty_good", "qty_reject", "qty_scrap", "qty_rework", "dataset", "batch"]
        labels = ["Fecha", "Turno", "Área", "Línea", "Orden", "Parte", "Estación", "Serial", "Resultado", "Causa", "Unidad",
                  "Buenas", "Rechazo", "Scrap", "Retrabajo", "Dataset", "Lote"]
        rows = []
        for r in qs.iterator(chunk_size=2000):
            rows.append([r.date.isoformat() if r.date else "", r.shift, r.area.code if r.area else "", r.line, r.work_order, r.part_number,
                         r.station, r.serial, r.result, r.cause, r.unit,
                         *[float(getattr(r, k)) if getattr(r, k) is not None else None for k in ("qty_good", "qty_reject", "qty_scrap", "qty_rework")],
                         r.dataset.code, r.batch_id or "captura"])
        snap_table = {"title": "Registros", "columns": [{"key": c, "label": l} for c, l in zip(cols, labels)], "rows": rows}
    else:
        rows_o, _ = order_rows(request.user, f)
        snap_table = {"title": "Órdenes", "columns": ORDER_COLUMNS, "rows": order_table_rows(rows_o)}
    kpis = kpi_summary(request.user, f)
    from .snapshot import _kpi, _plain

    snap = {"title": f"Exportación {snap_table['title']}", "period_text": f.describe(), "generated_at": timezone.localtime().strftime("%Y-%m-%d %H:%M:%S"),
            "timezone": "America/Mexico_City", "author": request.user.get_full_name() or request.user.username,
            "data_version": kpis["data_version"], "kpis": [_kpi("Cumplimiento agrupado", kpis["compliance"]), _plain("Pendiente", kpis["pending_total"]),
                                                          _plain("Órdenes atrasadas", kpis["late_count"])],
            "tables": [snap_table], "charts": [], "observations": [], "incidents": [], "warnings": kpis["warnings"], "notes": "",
            "last_import": ""}
    stamp = timezone.localtime().strftime("%Y%m%d_%H%M")
    audit(request.user, "export.selection", None, f"Exportación {table} {fmt}: {f.describe()}")
    if fmt == "csv":
        resp = HttpResponse(to_csv(snap), content_type="text/csv; charset=utf-8")
        resp["Content-Disposition"] = f'attachment; filename="{table}_{stamp}.csv"'
        return resp
    resp = HttpResponse(to_xlsx(snap), content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    resp["Content-Disposition"] = f'attachment; filename="{table}_{stamp}.xlsx"'
    return resp


# ---------------------------------------------------------------- reports
@require_cap("dashboard.view")
def reports(request):
    runs = [r for r in ReportRun.objects.select_related("author", "schedule")[:200] if r.user_can_view(request.user)]
    page = paginate(request, runs, 25)
    f = Filters.from_dict(request.GET)
    ctx = {"page": page, "kinds": ReportKind.choices, "formats": FORMATS, "schedules": ReportSchedule.objects.all()[:50],
           "can_generate": has_cap(request.user, "reports.generate"), "can_schedule": has_cap(request.user, "reports.schedule")}
    ctx.update(_filter_context(request, f))
    return render(request, "reports/reports.html", ctx)


@require_POST
@require_cap("reports.generate")
def report_generate(request):
    kind = request.POST.get("kind")
    if kind not in ReportKind.values:
        return json_error("Seleccione una plantilla de reporte.")
    formats = request.POST.getlist("formats") or ["pdf"]
    filters = {k: request.POST.get(k, "") for k in ("period", "date_from", "date_to", "customer", "area", "line", "shift",
                                                     "work_order", "part_number", "responsible", "unit", "late_only", "station")}
    filters = {k: v for k, v in filters.items() if v}
    run = create_run(kind, filters, request.user, formats, title=request.POST.get("title", "").strip(), notes=request.POST.get("notes", "").strip())
    job, _ = enqueue("reports.generate", {"run_id": run.pk}, request.user, idempotency_key=f"report-run-{run.pk}")
    audit(request.user, "report.requested", run, f"Reporte {run.get_kind_display()} {formats}")
    return json_ok(job_id=str(job.pk))


@require_cap("dashboard.view")
def report_detail(request, run_id):
    run = get_object_or_404(ReportRun.objects.select_related("author", "schedule"), pk=run_id)
    if not run.user_can_view(request.user):
        raise PermissionDenied("No tiene acceso a este reporte (áreas o destinatarios).")
    history = ReportRun.objects.filter(kind=run.kind, schedule=run.schedule).exclude(pk=run.pk)[:20] if run.schedule_id else []
    return render(request, "reports/report_detail.html", {"run": run, "outputs": run.outputs.select_related("file"), "history": history})


@require_POST
@require_cap("reports.generate")
def report_retry(request, run_id):
    run = get_object_or_404(ReportRun, pk=run_id)
    if not run.user_can_view(request.user):
        raise PermissionDenied()
    try:
        retry_run(run, request.user)
        messages.success(request, "Reintento enviado.")
    except UserFacingError as exc:
        messages.error(request, str(exc))
    return redirect("reports:report_detail", run_id=run.pk)


@require_cap("reports.schedule")
def schedule_edit(request, schedule_id=None):
    sch = get_object_or_404(ReportSchedule, pk=schedule_id) if schedule_id else None
    from django.contrib.auth import get_user_model

    users = get_user_model().objects.filter(is_active=True).order_by("username")
    if request.method == "POST":
        from datetime import time as dtime

        try:
            t = request.POST.get("time_of_day") or "06:30"
            hh, mm = [int(x) for x in t.split(":")[:2]]
            obj = sch or ReportSchedule(created_by=request.user)
            obj.name = request.POST.get("name", "").strip() or "Reporte programado"
            obj.kind = request.POST.get("kind")
            if obj.kind not in ReportKind.values:
                raise UserFacingError("Plantilla inválida.")
            obj.frequency = request.POST.get("frequency", "daily")
            obj.time_of_day = dtime(hh, mm)
            obj.weekday = int(request.POST["weekday"]) if request.POST.get("weekday") not in (None, "") else None
            obj.shift = Shift.objects.filter(pk=request.POST.get("shift") or 0).first()
            if obj.frequency == "shift" and not obj.shift:
                raise UserFacingError("Seleccione el turno para la frecuencia por turno.")
            obj.formats = [f for f in request.POST.getlist("formats") if f in dict(FORMATS)] or ["pdf"]
            obj.filters = {"period": request.POST.get("period", "today")}
            if request.POST.get("area"):
                obj.filters["area"] = request.POST["area"]
            if request.POST.get("line"):
                obj.filters["line"] = request.POST["line"]
            obj.active = request.POST.get("active") == "on"
            obj.save()
            obj.recipients.set(users.filter(pk__in=request.POST.getlist("recipients")))
            obj.next_run_at = next_occurrence(obj, timezone.now()) if obj.active else None
            obj.save(update_fields=["next_run_at"])
        except (UserFacingError, ValueError) as exc:
            messages.error(request, str(exc) or "Datos inválidos.")
            return redirect(request.path)
        audit(request.user, "report.schedule_saved", obj, f"Programación {obj.name}")
        messages.success(request, f"Programación guardada. Próxima generación: {timezone.localtime(obj.next_run_at):%Y-%m-%d %H:%M}" if obj.next_run_at else "Programación guardada (inactiva).")
        return redirect("reports:reports")
    return render(request, "reports/schedule_form.html", {"sch": sch, "kinds": ReportKind.choices, "formats": FORMATS, "users": users,
                                                          "shifts": Shift.objects.all(), "areas": Area.objects.all(),
                                                          "frequencies": ReportSchedule.Frequency.choices,
                                                          "weekdays": list(enumerate(["Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo"]))})


# ---------------------------------------------------------------- dashboard builder
@require_cap("dashboard.view")
def boards(request):
    items = [d for d in Dashboard.objects.select_related("owner") if d.user_can_view(request.user)]
    return render(request, "reports/boards.html", {"items": items, "can_build": has_cap(request.user, "dashboard.build")})


@require_cap("dashboard.view")
def board_view(request, board_id):
    board = get_object_or_404(Dashboard, pk=board_id)
    if not board.user_can_view(request.user):
        raise Http404()
    f = Filters.from_dict(request.GET)
    ctx = _filter_context(request, f)
    can_edit = has_cap(request.user, "dashboard.build") and (board.owner_id == request.user.pk or request.user.is_superuser)
    ctx.update({"board": board, "config_json": board.config, "can_edit": can_edit, "persist_key": f"board{board.pk}",
                "dims": DIMENSIONS, "measures": MEASURES, "aggs": AGGS, "roles": Role.choices, "all_areas": Area.objects.all()})
    return render(request, "reports/board.html", ctx)


@require_POST
@require_cap("dashboard.build")
def board_create(request):
    name = request.POST.get("name", "").strip() or "Nuevo dashboard"
    b = Dashboard.objects.create(name=name, owner=request.user, config={"widgets": [
        {"title": "Producción buena por día", "dimension": "date", "measure": "qty_good", "agg": "sum", "chart": "line", "limit": 60, "width": 2},
        {"title": "Buenas por línea", "dimension": "line", "measure": "qty_good", "agg": "sum", "chart": "bar", "limit": 30, "order": "value_desc", "width": 1},
    ]})
    audit(request.user, "dashboard.created", b, b.name)
    return redirect("reports:board", board_id=b.pk)


@require_POST
@require_cap("dashboard.build")
def board_duplicate(request, board_id):
    src = get_object_or_404(Dashboard, pk=board_id)
    if not src.user_can_view(request.user):
        raise Http404()
    b = Dashboard.objects.create(name=f"{src.name} (copia)", owner=request.user, config=json.loads(json.dumps(src.config)))
    audit(request.user, "dashboard.duplicated", b, f"Copia de {src.name}")
    return redirect("reports:board", board_id=b.pk)


@require_POST
@api
def board_save(request, board_id):
    board = get_object_or_404(Dashboard, pk=board_id)
    if not has_cap(request.user, "dashboard.build") or (board.owner_id != request.user.pk and not request.user.is_superuser):
        return json_error("Solo el propietario con permiso de construcción puede modificar este dashboard.", status=403)
    data = read_json(request)
    if int(data.get("version", 0)) != board.version:
        return json_error("El dashboard fue modificado en otra sesión. Recargue la página antes de guardar.", status=409)
    widgets = data.get("widgets", [])
    if not isinstance(widgets, list) or len(widgets) > 24:
        return json_error("Configuración no válida (máximo 24 widgets).")
    clean = []
    for w in widgets:
        if w.get("dimension") not in DIMENSIONS or w.get("measure") not in MEASURES or w.get("agg") not in AGGS:
            return json_error(f"Widget «{w.get('title', '')}»: dimensión, medida o agregación no permitida.")
        if w.get("calc"):
            from .services import safe_calc

            safe_calc(w["calc"], {m: 1 for m in MEASURES})
        clean.append({k: w.get(k) for k in ("title", "dimension", "measure", "agg", "chart", "limit", "order", "width", "calc", "join_plan",
                                            "join_key", "filters")})
    board.config = {"widgets": clean}
    board.name = (data.get("name") or board.name)[:120]
    board.shared_all = bool(data.get("shared_all"))
    board.shared_roles = [r for r in data.get("shared_roles", []) if r in Role.values]
    board.version += 1
    board.updated = timezone.now()
    board.save()
    board.shared_areas.set(Area.objects.filter(code__in=data.get("shared_areas", [])))
    audit(request.user, "dashboard.saved", board, f"{board.name} v{board.version}")
    return json_ok({"version": board.version})


@require_POST
@api
def widget_api(request):
    if not has_cap(request.user, "dashboard.view"):
        return json_error("Permiso requerido.", status=403)
    data = read_json(request)
    return json_ok(widget_data(request.user, data.get("widget", {}), data.get("filters", {})))


@api
def join_check(request):
    return json_ok(validate_plan_join(request.GET.get("key", "work_order")))
