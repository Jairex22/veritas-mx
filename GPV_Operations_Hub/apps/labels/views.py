import copy
import json
import re

from django import forms
from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.http import Http404, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.text import slugify
from django.views.decorators.http import require_POST

from apps.core.audit import audit
from apps.core.files import store_upload
from apps.core.jobs import UserFacingError
from apps.core.models import StoredFile
from apps.core.permissions import can_access_area, filter_by_area, has_cap, require_cap
from apps.core.utils import api, json_error, json_ok, read_json

from . import printing, services
from .models import LabelTemplate, LabelTemplateVersion, PrintJob, Printer, SerialCounter
from .render import SCHEMA, TemplateError, base_values, default_template, to_pdf, to_svg, to_zpl, validate_template


def _job_allowed(user, job):
    if job.user_id == user.pk:
        return True
    area_id = job.template_version.template.area_id
    return has_cap(user, "labels.reprint") and (area_id is None or can_access_area(user, area_id))


def _tpl(request, pk):
    t = get_object_or_404(LabelTemplate, pk=pk)
    if t.area_id and not can_access_area(request.user, t.area_id):
        raise Http404()
    return t


@require_cap("labels.print")
def template_list(request):
    items = filter_by_area(LabelTemplate.objects.select_related("published", "owner"), request.user) | LabelTemplate.objects.filter(area__isnull=True)
    return render(request, "labels/list.html", {"items": items.distinct(), "can_design": has_cap(request.user, "labels.design"),
                                                "jobs": [j for j in PrintJob.objects.select_related("template_version__template", "printer", "user")[:60]
                                                         if _job_allowed(request.user, j)][:20]})


@require_POST
@require_cap("labels.design")
def template_create(request):
    name = request.POST.get("name", "").strip() or "Etiqueta nueva"
    data = default_template(name, float(request.POST.get("w") or 100), float(request.POST.get("h") or 50), int(request.POST.get("dpi") or 203))
    if request.FILES.get("file"):
        try:
            sf = store_upload(request.FILES["file"], request.user, allowed={"json"})
            data = json.loads(sf.path.read_text(encoding="utf-8"))
            if "template" in data and isinstance(data["template"], dict):
                data = data["template"]
            validate_template(data)
            name = data.get("name") or name
        except (UserFacingError, TemplateError, ValueError) as exc:
            messages.error(request, f"No se pudo importar la plantilla: {exc}")
            return redirect("labels:list")
    code = slugify(name)[:50] or "etiqueta"
    base, n = code, 2
    while LabelTemplate.objects.filter(code=code).exists():
        code = f"{base}-{n}"
        n += 1
    prof = getattr(request.user, "profile", None)
    t = LabelTemplate.objects.create(name=name[:120], code=code, owner=request.user, draft=data, draft_updated_by=request.user,
                                     area=prof.areas.first() if prof else None)
    audit(request.user, "labels.template_created", t, f"Plantilla {t.name}")
    return redirect("labels:designer", pk=t.pk)


@require_POST
@require_cap("labels.design")
def template_duplicate(request, pk):
    src = _tpl(request, pk)
    code, n = f"{src.code}-copia", 2
    while LabelTemplate.objects.filter(code=code).exists():
        code = f"{src.code}-copia-{n}"
        n += 1
    d = copy.deepcopy(src.draft)
    d["name"] = f"{src.name} (copia)"
    t = LabelTemplate.objects.create(name=d["name"][:120], code=code, owner=request.user, draft=d, area=src.area, draft_updated_by=request.user)
    return redirect("labels:designer", pk=t.pk)


@require_cap("labels.print")
def template_export(request, pk):
    t = _tpl(request, pk)
    version = request.GET.get("v")
    data = t.draft if not version else get_object_or_404(LabelTemplateVersion, template=t, version=int(version)).definition
    resp = HttpResponse(json.dumps({"schema": SCHEMA, "exported": timezone.localtime().isoformat(), "template": data}, ensure_ascii=False, indent=2),
                        content_type="application/json; charset=utf-8")
    resp["Content-Disposition"] = f'attachment; filename="{t.code}{"_v" + version if version else "_borrador"}.gpvlabel.json"'
    return resp


@require_cap("labels.design")
def designer(request, pk):
    t = _tpl(request, pk)
    return render(request, "labels/designer.html", {
        "t": t, "boot": {"id": t.pk, "revision": t.draft_revision, "draft": t.draft, "can_publish": has_cap(request.user, "labels.publish"),
                         "counters": list(SerialCounter.objects.values_list("name", flat=True))},
        "versions": t.versions.select_related("published_by")[:20],
    })


@require_POST
@api
def api_save_draft(request, pk):
    if not has_cap(request.user, "labels.design"):
        return json_error("Permiso requerido: diseñar etiquetas.", status=403)
    t = _tpl(request, pk)
    body = read_json(request)
    try:
        data = validate_template(body.get("draft"))
    except TemplateError as exc:
        return json_error(str(exc))
    with transaction.atomic():
        locked = LabelTemplate.objects.select_for_update().get(pk=t.pk)
        if int(body.get("revision", 0)) != locked.draft_revision:
            return json_error(f"El borrador fue guardado por {locked.draft_updated_by.username if locked.draft_updated_by else 'otro usuario'} "
                              f"({timezone.localtime(locked.draft_updated):%H:%M:%S}). Recargue para no sobrescribir su trabajo.", status=409)
        locked.draft = data
        locked.name = (data.get("name") or locked.name)[:120]
        locked.draft_revision += 1
        locked.draft_updated = timezone.now()
        locked.draft_updated_by = request.user
        locked.save()
    return json_ok({"revision": locked.draft_revision})


@require_POST
@api
def api_preview(request, pk):
    _tpl(request, pk)
    body = read_json(request)
    try:
        tpl = validate_template(body.get("draft"))
        vals = base_values(body.get("record") or {}, body.get("prompts") or {}, serial=body.get("serial") or "GPV000001")
        svg, res = to_svg(tpl, vals, show_overflow=True)
    except TemplateError as exc:
        return json_error(str(exc))
    overflow = [g.get("id") for g in res["prims"] if g["overflow"]]
    return json_ok({"svg": svg, "warnings": res["warnings"], "overflow": overflow})


@require_POST
@require_cap("labels.publish")
def publish(request, pk):
    t = _tpl(request, pk)
    try:
        data = validate_template(t.draft)
    except TemplateError as exc:
        messages.error(request, str(exc))
        return redirect("labels:designer", pk=t.pk)
    with transaction.atomic():
        n = (t.versions.order_by("-version").values_list("version", flat=True).first() or 0) + 1
        v = LabelTemplateVersion.objects.create(template=t, version=n, definition=copy.deepcopy(data), published_by=request.user,
                                                notes=request.POST.get("notes", "")[:300])
        t.published = v
        t.save(update_fields=["published"])
    audit(request.user, "labels.published", t, f"Plantilla {t.name} v{n} publicada")
    messages.success(request, f"Versión {n} publicada. Las impresiones usan siempre una versión publicada.")
    return redirect("labels:designer", pk=t.pk)


@require_cap("labels.print")
def export_file(request, pk, fmt):
    """Exact-size SVG/PDF/ZPL of a published version (or draft for designers) with sample or given data."""
    t = _tpl(request, pk)
    if request.GET.get("v"):
        tpl = get_object_or_404(LabelTemplateVersion, template=t, version=int(request.GET["v"])).definition
    elif has_cap(request.user, "labels.design"):
        tpl = t.draft
    elif t.published:
        tpl = t.published.definition
    else:
        raise Http404("Sin versión publicada.")
    vals = base_values({k: v for k, v in request.GET.items() if k not in ("v",)}, {}, serial=request.GET.get("serial", "GPV000001"))
    try:
        if fmt == "svg":
            svg, _r = to_svg(tpl, vals)
            resp = HttpResponse(svg, content_type="image/svg+xml")
        elif fmt == "pdf":
            pdf, _w = to_pdf(tpl, [vals])
            resp = HttpResponse(pdf, content_type="application/pdf")
        elif fmt == "zpl":
            z, _w = to_zpl(tpl, [vals])
            resp = HttpResponse(z, content_type="text/plain")
        else:
            raise Http404()
    except TemplateError as exc:
        return HttpResponse(str(exc), status=400, content_type="text/plain; charset=utf-8")
    resp["Content-Disposition"] = f'{"inline" if request.GET.get("inline") else "attachment"}; filename="{t.code}.{fmt}"'
    if fmt == "svg":
        resp["Content-Security-Policy"] = "default-src 'none'; img-src data:; style-src 'unsafe-inline'"
    return resp


# ---------------------------------------------------------------- print wizard
def _records_from_source(request, source):
    """Returns (records list[dict], description, columns)."""
    from apps.production.models import Dataset, ProductionRecord
    from apps.production.fields import RECORD_COLUMNS
    from apps.production.importer import _display

    if source == "dataset":
        ds = get_object_or_404(Dataset, pk=request.POST.get("dataset") or request.GET.get("dataset"))
        qs = filter_by_area(ProductionRecord.objects.filter(dataset=ds, is_current=True), request.user).order_by("id")
        q = (request.POST.get("q") or request.GET.get("q") or "").strip()
        if q:
            from django.db.models import Q

            qs = qs.filter(Q(work_order__icontains=q) | Q(serial__icontains=q) | Q(part_number__icontains=q) | Q(line__icontains=q))
        rows = []
        for r in qs[:2000]:
            d = {f: _display(getattr(r, f)) for f in RECORD_COLUMNS}
            d.update(r.extra or {})
            d["area"] = r.area.code if r.area else ""
            d["_id"] = r.pk
            rows.append(d)
        cols = [c for c in ["work_order", "part_number", "serial", "lot", "qty_good", "date", "line", "customer", "station"] if any(x.get(c) for x in rows)]
        return rows, f"Dataset {ds.name}" + (f" (filtro «{q}»)" if q else ""), cols
    if source == "file":
        sf = get_object_or_404(StoredFile, pk=request.POST.get("file_id") or request.GET.get("file_id"), owner=request.user)
        from apps.documents.ops_tabular import read_csv_rows, sheet_rows, xlsx_info

        data = sf.path.read_bytes()
        if sf.ext == "xlsx":
            rows = sheet_rows(data, xlsx_info(data)["sheets"][0]["name"])
        else:
            rows, _e, _d = read_csv_rows(data)
        if not rows:
            raise UserFacingError("El archivo no tiene datos.")
        header = [h.strip() for h in rows[0]]
        recs = [dict(zip(header, r)) for r in rows[1:] if any(c.strip() for c in r)]
        return recs, f"Archivo {sf.original_name}", header
    return [{}], "Captura manual", []


def _select(records, mode, spec, ids):
    if mode == "all":
        return records
    if mode == "range":
        m = re.fullmatch(r"\s*(\d+)\s*-\s*(\d+)\s*", spec or "")
        if not m:
            raise UserFacingError("Rango inválido (ej. 1-20).")
        a, b = int(m.group(1)), int(m.group(2))
        if a < 1 or b < a or a > len(records):
            raise UserFacingError(f"Rango fuera de los registros (1 a {len(records)}).")
        return records[a - 1:b]
    if mode == "selection":
        chosen = [int(i) for i in ids]
        if not chosen:
            raise UserFacingError("Marque los registros a imprimir.")
        return [records[i] for i in chosen if 0 <= i < len(records)]
    if mode == "single":
        return records[:1]
    raise UserFacingError("Modo de selección inválido.")


@require_cap("labels.print")
def print_page(request, pk):
    t = _tpl(request, pk)
    if not t.published:
        messages.error(request, "La plantilla no tiene una versión publicada. Un responsable debe publicarla antes de imprimir.")
        return redirect("labels:list")
    from apps.production.models import Dataset

    source = request.GET.get("source", "manual")
    ctx = {"t": t, "version": t.published, "source": source, "datasets": Dataset.objects.all(),
           "printers": Printer.objects.filter(enabled=True, validated_at__isnull=False) | Printer.objects.filter(kind=Printer.Kind.BROWSER),
           "prompts": t.published.definition.get("prompts", []), "records": [], "columns": []}
    try:
        if source in ("dataset", "file") and (request.GET.get("dataset") or request.GET.get("file_id")):
            recs, desc, cols = _records_from_source(request, source)
            ctx.update({"records": list(enumerate(recs[:500])), "columns": cols or list(recs[0].keys())[:8] if recs else [], "desc": desc,
                        "total_records": len(recs)})
    except UserFacingError as exc:
        messages.error(request, str(exc))
    ctx["printers"] = ctx["printers"].distinct()
    return render(request, "labels/print.html", ctx)


@require_POST
@require_cap("labels.print")
def upload_data(request, pk):
    t = _tpl(request, pk)
    try:
        sf = store_upload(request.FILES["file"], request.user, allowed={"csv", "xlsx", "txt"})
    except (KeyError, UserFacingError) as exc:
        messages.error(request, str(exc) if isinstance(exc, UserFacingError) else "Seleccione un archivo CSV/XLSX.")
        return redirect("labels:print", pk=t.pk)
    return redirect(f"/etiquetas/{t.pk}/imprimir/?source=file&file_id={sf.pk}")


def _print_params(request, t):
    version = t.published
    if request.POST.get("version"):
        version = get_object_or_404(LabelTemplateVersion, template=t, version=int(request.POST["version"]))
    source = request.POST.get("source", "manual")
    recs, desc, _cols = _records_from_source(request, source)
    recs = _select(recs, request.POST.get("mode", "single" if source == "manual" else "selection"), request.POST.get("range"),
                   request.POST.getlist("rec"))
    prompts = {p["name"]: request.POST.get(f"prompt_{p['name']}", p.get("default", "")) for p in version.definition.get("prompts", [])}
    for p in version.definition.get("prompts", []):
        if p.get("required") and not prompts.get(p["name"]):
            raise UserFacingError(f"Capture el valor solicitado «{p.get('label') or p['name']}».")
    copies = int(request.POST.get("copies") or 1)
    printer = None
    if request.POST.get("printer"):
        printer = get_object_or_404(Printer, pk=request.POST["printer"])
    return version, recs, prompts, copies, printer, desc


@require_POST
@api
def api_print_preview(request, pk):
    t = _tpl(request, pk)
    version, recs, prompts, copies, printer, desc = _print_params(request, t)
    vals = base_values(recs[0], prompts, serial="(se asigna al imprimir)" if version.definition.get("serial_counter") else None)
    svg, res = to_svg(version.definition, vals, show_overflow=True)
    return json_ok({"svg": svg, "warnings": res["warnings"], "records": len(recs), "copies": copies, "total": len(recs) * copies,
                    "printer": printer.name if printer else "Navegador / PDF"})


@require_POST
@api
def api_print(request, pk):
    if not has_cap(request.user, "labels.print"):
        return json_error("Permiso requerido: imprimir etiquetas.", status=403)
    t = _tpl(request, pk)
    version, recs, prompts, copies, printer, desc = _print_params(request, t)
    expected = int(request.POST.get("confirm_total") or 0)
    if expected != len(recs) * copies:
        return json_error(f"La cantidad confirmada ({expected}) no coincide con la calculada ({len(recs) * copies}). Revise y confirme de nuevo.")
    job, created = services.create_and_print(request.user, version, recs, prompts, copies, printer, request.POST.get("idempotency_key"), source=desc)
    return json_ok(_job_payload(job, created))


def _job_payload(job, created=True):
    files = []
    if job.output_pdf:
        files.append({"name": job.output_pdf.original_name, "url": f"/archivos/{job.output_pdf.pk}/?inline=1", "type": "PDF tamaño exacto",
                      "size_h": f"{job.output_pdf.size // 1024 + 1} KB"})
    if job.output_zpl:
        files.append({"name": job.output_zpl.original_name, "url": f"/archivos/{job.output_zpl.pk}/", "type": "ZPL", "size_h": f"{job.output_zpl.size // 1024 + 1} KB"})
    return {"job": str(job.pk), "number": job.number, "status": job.get_status_display(), "created": created, "files": files,
            "url": f"/etiquetas/trabajos/{job.pk}/",
            "summary": (f"Trabajo #{job.number}: {job.total_labels} etiquetas · {job.get_status_display()}" +
                        ("" if created else " (solicitud repetida: no se generó un trabajo nuevo)")),
            "warnings": [w for w in job.evidence.splitlines() if w][:20]}


@require_cap("labels.print")
def job_detail(request, job_id):
    job = get_object_or_404(PrintJob.objects.select_related("template_version__template", "printer", "user", "reprint_of"), pk=job_id)
    if not _job_allowed(request.user, job):
        raise PermissionDenied("Solo el autor o un supervisor del área pueden ver este trabajo.")
    return render(request, "labels/job.html", {"job": job, "events": job.events.select_related("user"),
                                               "can_reprint": has_cap(request.user, "labels.reprint"),
                                               "printers": (Printer.objects.filter(enabled=True, validated_at__isnull=False) | Printer.objects.filter(kind=Printer.Kind.BROWSER)).distinct()})


@require_POST
@require_cap("labels.print")
def job_confirm(request, job_id):
    job = get_object_or_404(PrintJob, pk=job_id)
    if not _job_allowed(request.user, job):
        raise PermissionDenied()
    try:
        services.confirm(job, request.user, request.POST.get("result") == "ok", request.POST.get("note", ""))
        messages.success(request, "Estado actualizado.")
    except UserFacingError as exc:
        messages.error(request, str(exc))
    return redirect("labels:job", job_id=job.pk)


@require_POST
@api
def api_reprint(request, job_id):
    if not has_cap(request.user, "labels.reprint"):
        return json_error("La reimpresión requiere el permiso «Reimprimir etiquetas».", status=403)
    src = get_object_or_404(PrintJob, pk=job_id)
    if not _job_allowed(request.user, src):
        return json_error("El trabajo pertenece a un área sin permiso.", status=403)
    reason = request.POST.get("reason", "").strip()
    if len(reason) < 5:
        return json_error("Indique el motivo de la reimpresión (mínimo 5 caracteres).")
    records = []
    seen = set()
    for d in src.data:
        key = d.get("serial_gpv") or d.get("consecutivo")
        if d.get("copia") == "1" and key not in seen:
            seen.add(key)
            records.append({k: v for k, v in d.items() if k not in ("consecutivo", "copia", "serial_gpv")})
    printer = Printer.objects.filter(pk=request.POST.get("printer") or 0).first()
    job, created = services.create_and_print(request.user, src.template_version, records, {}, src.copies, printer,
                                             request.POST.get("idempotency_key"), source=f"Reimpresión de #{src.number}", reprint_of=src,
                                             reprint_reason=reason)
    return json_ok(_job_payload(job, created))


# ---------------------------------------------------------------- printers (admin)
class PrinterForm(forms.ModelForm):
    class Meta:
        model = Printer
        fields = ["name", "kind", "language", "host", "port", "queue_name", "dpi", "model_notes", "area", "darkness", "speed"]

    def clean(self):
        d = super().clean()
        if d.get("kind") == Printer.Kind.ZPL_TCP:
            if not d.get("host") or not d.get("port"):
                self.add_error("host", "Una impresora de red requiere host/IP y puerto registrados.")
            if d.get("language") != Printer.Language.ZPL:
                self.add_error("language", "La ruta ZPL por red solo envía ZPL; use una impresora que lo soporte.")
        if d.get("kind") in (Printer.Kind.WINDOWS_QUEUE, Printer.Kind.CUPS_QUEUE) and not d.get("queue_name"):
            self.add_error("queue_name", "Indique el nombre exacto de la cola en el servidor.")
        if d.get("kind") != Printer.Kind.BROWSER and not d.get("dpi"):
            self.add_error("dpi", "Registre la resolución real (ficha técnica o configuración de la impresora).")
        if d.get("kind") in (Printer.Kind.WINDOWS_QUEUE, Printer.Kind.CUPS_QUEUE) and d.get("language") == Printer.Language.PDF:
            self.add_error("language", "El envío RAW de PDF a una cola no está soportado; use ZPL compatible o la ruta navegador/PDF con el controlador del fabricante.")
        if d.get("darkness") is not None and not (0 <= d["darkness"] <= 30):
            self.add_error("darkness", "Oscuridad ZPL entre 0 y 30.")
        if d.get("speed") is not None and not (1 <= d["speed"] <= 14):
            self.add_error("speed", "Velocidad ZPL entre 1 y 14.")
        return d


@require_cap("admin.printers")
def printers(request, printer_id=None):
    obj = get_object_or_404(Printer, pk=printer_id) if printer_id else None
    form = PrinterForm(request.POST or None, instance=obj)
    if request.method == "POST" and form.is_valid():
        p = form.save(commit=False)
        changed = obj is None or any(form.initial.get(k) != form.cleaned_data.get(k) for k in ("kind", "host", "port", "queue_name", "dpi", "language"))
        if changed:
            p.enabled = False
            p.validated_at = None
        p.save()
        audit(request.user, "printer.saved", p, f"Impresora {p.name} ({p.get_kind_display()})" + (" — requiere nueva validación" if changed else ""))
        messages.success(request, "Impresora guardada." + (" Pruebe la conexión y habilítela." if changed and p.is_direct else ""))
        return redirect("labels:printers")
    return render(request, "labels/printers.html", {"form": form, "obj": obj, "items": Printer.objects.all(),
                                                    "counters": SerialCounter.objects.all()})


@require_POST
@require_cap("admin.printers")
def printer_test(request, printer_id):
    p = get_object_or_404(Printer, pk=printer_id)
    ok, detail = printing.test_connection(p)
    p.last_test = f"{timezone.localtime():%Y-%m-%d %H:%M} · {'OK' if ok else 'FALLÓ'} · {detail}"[:300]
    if ok:
        p.validated_at = timezone.now()
    p.save(update_fields=["last_test", "validated_at"])
    audit(request.user, "printer.tested", p, p.last_test)
    (messages.success if ok else messages.error)(request, p.last_test)
    return redirect("labels:printers")


@require_POST
@require_cap("admin.printers")
def printer_toggle(request, printer_id):
    p = get_object_or_404(Printer, pk=printer_id)
    if not p.enabled and p.is_direct and not p.validated_at:
        messages.error(request, "Primero pruebe la conexión con éxito.")
        return redirect("labels:printers")
    p.enabled = not p.enabled
    p.save(update_fields=["enabled"])
    audit(request.user, "printer.toggled", p, f"{p.name} {'habilitada' if p.enabled else 'deshabilitada'}")
    return redirect("labels:printers")


@require_POST
@require_cap("admin.printers")
def counter_save(request):
    name = slugify(request.POST.get("name", ""))
    if not name:
        messages.error(request, "Nombre de contador inválido.")
        return redirect("labels:printers")
    c, created = SerialCounter.objects.get_or_create(name=name, defaults={"prefix": request.POST.get("prefix", "")[:30],
                                                                         "pad": int(request.POST.get("pad") or 6),
                                                                         "next_value": int(request.POST.get("next_value") or 1)})
    if not created:
        messages.info(request, "El contador ya existe; su valor no se modifica desde aquí para evitar duplicados.")
    audit(request.user, "labels.counter", c, f"Contador {c.name}")
    return redirect("labels:printers")
