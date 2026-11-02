import copy
import json

from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.http import Http404, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from apps.core.audit import audit
from apps.core.files import store_generated, store_upload
from apps.core.jobs import UserFacingError
from apps.core.permissions import filter_by_area, has_cap, require_cap
from apps.core.utils import api, json_error, json_ok, read_json

from . import engine
from .formula import FUNCTION_NAMES
from .models import Workbook, WorkbookVersion


def _wb(request, pk, edit=False):
    wb = get_object_or_404(Workbook.objects.select_related("owner", "updated_by", "dataset"), pk=pk)
    if not wb.user_can_view(request.user):
        raise Http404()
    if edit and not wb.user_can_edit(request.user):
        raise PermissionDenied("No tiene permiso para editar esta hoja.")
    return wb


@require_cap("sheets.edit")
def sheet_list(request):
    from django.db.models import Q

    from apps.core.permissions import allowed_area_ids
    from apps.production.models import Dataset

    ids = allowed_area_ids(request.user)
    qs = Workbook.objects.select_related("owner", "updated_by")
    if not request.user.is_superuser:
        cond = Q(owner=request.user)
        cond |= Q(shared=True, area__isnull=False) & (Q() if ids is None else Q(area__in=ids))
        qs = qs.filter(cond)
    return render(request, "sheets/list.html", {"items": qs[:200], "datasets": Dataset.objects.all()})


@require_POST
@require_cap("sheets.edit")
def sheet_create(request):
    from apps.production.models import Dataset

    name = request.POST.get("name", "").strip() or "Libro nuevo"
    warnings = []
    source = None
    dataset = None
    try:
        if request.FILES.get("file"):
            source = store_upload(request.FILES["file"], request.user, allowed={"xlsx", "csv"})
            blob = source.path.read_bytes()
            data, warnings = engine.from_xlsx(blob) if source.ext == "xlsx" else engine.from_csv(blob)
            if name == "Libro nuevo":
                name = source.original_name.rsplit(".", 1)[0]
        elif request.POST.get("dataset"):
            dataset = get_object_or_404(Dataset, pk=request.POST["dataset"])
            data, n = engine.from_records(dataset)
            warnings = [f"Se cargaron {n} registros vigentes del dataset «{dataset.name}». Los cambios solo afectan producción si se publican y validan."]
            name = name if name != "Libro nuevo" else f"{dataset.name} (edición)"
        else:
            data = engine.new_workbook_data()
    except UserFacingError as exc:
        messages.error(request, str(exc))
        return redirect("sheets:list")
    area = getattr(getattr(request.user, "profile", None), "areas", None)
    wb = Workbook.objects.create(name=name[:150], owner=request.user, data=data, updated_by=request.user, source_file=source, dataset=dataset,
                                 import_warnings=warnings, area=area.first() if area is not None else None)
    WorkbookVersion.objects.create(workbook=wb, version=1, data=data, user=request.user, summary="Creación")
    audit(request.user, "sheet.created", wb, f"Hoja {wb.name}")
    return redirect("sheets:edit", pk=wb.pk)


@require_cap("sheets.edit")
def sheet_edit(request, pk):
    wb = _wb(request, pk)
    return render(request, "sheets/editor.html", {
        "wb": wb, "boot": {"id": wb.pk, "name": wb.name, "version": wb.version, "data": wb.data, "can_edit": wb.user_can_edit(request.user),
                           "is_owner": wb.owner_id == request.user.pk, "updated_by": wb.updated_by.username if wb.updated_by else "",
                           "updated": timezone.localtime(wb.updated).strftime("%d/%m/%Y %H:%M"), "warnings": wb.import_warnings,
                           "dataset": wb.dataset.name if wb.dataset else "", "can_publish": has_cap(request.user, "sheets.publish") and bool(wb.dataset_id)},
        "functions": sorted(FUNCTION_NAMES.keys()),
    })


@require_POST
@api
def api_recalc(request, pk):
    _wb(request, pk)
    body = read_json(request)
    return json_ok(engine.recalc(body.get("data")))


@require_POST
@api
def api_save(request, pk):
    body = read_json(request)
    with transaction.atomic():
        wb = Workbook.objects.select_for_update().get(pk=_wb(request, pk, edit=True).pk)
        base = int(body.get("base_version", 0))
        if base != wb.version:
            return json_error(
                f"Conflicto de edición: {wb.updated_by.username if wb.updated_by else 'otro usuario'} guardó la versión {wb.version} "
                f"el {timezone.localtime(wb.updated):%d/%m/%Y %H:%M:%S} mientras usted editaba la versión {base}. "
                "Su trabajo NO se sobrescribió: recargue para ver la versión actual o guarde su trabajo como copia.",
                status=409, conflict=True, server_version=wb.version)
        data = engine.validate_data(body.get("data"))
        if wb.owner_id != request.user.pk and not request.user.is_superuser:
            viol = engine.protected_violations(wb.data, data)
            if viol:
                return json_error(f"Se modificaron columnas protegidas ({', '.join(viol[:10])}). Solo el propietario puede editarlas.", status=403)
        changed = engine.count_changes(wb.data, data)
        wb.data = data
        wb.version += 1
        wb.updated = timezone.now()
        wb.updated_by = request.user
        if body.get("name"):
            wb.name = str(body["name"])[:150]
        wb.save()
        WorkbookVersion.objects.create(workbook=wb, version=wb.version, data=data, user=request.user,
                                       summary=str(body.get("summary", ""))[:300], changed_cells=changed)
        old = WorkbookVersion.objects.filter(workbook=wb).order_by("-version")[50:]
        WorkbookVersion.objects.filter(pk__in=[v.pk for v in old]).delete()
    audit(request.user, "sheet.saved", wb, f"Hoja {wb.name} v{wb.version} ({changed} celdas)")
    return json_ok({"version": wb.version, "changed": changed, "warnings": engine.check_validations(data),
                    "updated": timezone.localtime(wb.updated).strftime("%d/%m/%Y %H:%M")})


@require_POST
@api
def api_save_copy(request, pk):
    src = _wb(request, pk)
    if not has_cap(request.user, "sheets.edit"):
        raise PermissionDenied()
    body = read_json(request)
    data = engine.validate_data(body.get("data"))
    wb = Workbook.objects.create(name=f"{src.name} (copia de {request.user.username})"[:150], owner=request.user, data=data,
                                 updated_by=request.user, area=src.area)
    WorkbookVersion.objects.create(workbook=wb, version=1, data=data, user=request.user, summary=f"Copia de #{src.pk} por conflicto")
    return json_ok({"url": f"/hojas/{wb.pk}/"})


@require_POST
@api
def api_op(request, pk):
    _wb(request, pk, edit=True)
    body = read_json(request)
    data = engine.validate_data(copy.deepcopy(body.get("data")))
    op = body.get("op") or {}
    t = op.get("type")
    if t in ("insert_rows", "delete_rows", "insert_cols", "delete_cols"):
        axis = "row" if "rows" in t else "col"
        count = int(op.get("count", 1)) * (1 if t.startswith("insert") else -1)
        data = engine.structure(data, op["sheet"], axis, int(op["index"]), count)
    elif t == "duplicate_rows":
        data = engine.duplicate_rows(data, op["sheet"], int(op["index"]), int(op.get("count", 1)))
    elif t == "rename_sheet":
        data = engine.rename_sheet(data, op["sheet"], op["new"])
    elif t == "duplicate_sheet":
        data = engine.duplicate_sheet(data, op["sheet"])
    elif t == "delete_sheet_check":
        return json_ok({"broken": engine.delete_sheet_check(data, op["sheet"])})
    elif t == "paste":
        return json_ok({"items": engine.paste_formulas(op.get("items", []), int(op.get("drow", 0)), int(op.get("dcol", 0)))})
    elif t == "sort":
        data = engine.sort_rows(data, op["sheet"], int(op["col"]), bool(op.get("asc", True)), int(op.get("header", 1)))
    elif t == "pivot":
        table = engine.pivot(data, op["sheet"], op["rows"], op["value"], op.get("agg", "sum"), op.get("cols") or None, int(op.get("header", 1)))
        return json_ok({"table": table})
    else:
        return json_error("Operación no soportada.")
    return json_ok({"data": data})


@require_POST
@api
def api_export(request, pk):
    wb = _wb(request, pk)
    body = read_json(request)
    data = engine.validate_data(body.get("data") or wb.data)
    fmt = body.get("fmt", "xlsx")
    if fmt == "csv":
        blob = engine.to_csv(data, body.get("sheet") or data["sheets"][0]["name"], body.get("delimiter", ","))
        name = f"{wb.name}_{body.get('sheet', '')}.csv"
    else:
        blob = engine.to_xlsx(data)
        name = f"{wb.name}.xlsx"
    sf = store_generated(blob, name, request.user)
    return json_ok({"files": [{"name": sf.original_name, "url": f"/archivos/{sf.pk}/", "size_h": f"{sf.size // 1024 + 1} KB"}]})


@require_cap("sheets.edit")
def versions(request, pk):
    wb = _wb(request, pk)
    if request.GET.get("v"):
        v = get_object_or_404(WorkbookVersion, workbook=wb, version=int(request.GET["v"]))
        blob = engine.to_xlsx(v.data)
        resp = HttpResponse(blob, content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
        resp["Content-Disposition"] = f'attachment; filename="{wb.name}_v{v.version}.xlsx"'
        return resp
    return render(request, "sheets/versions.html", {"wb": wb, "versions": wb.versions.select_related("user")})


@require_POST
@require_cap("sheets.publish")
def publish(request, pk):
    """Send the current saved sheet to the import pipeline (validation + traceability)."""
    from apps.production.fields import auto_map
    from apps.production.importer import analyze
    from apps.production.models import ImportBatch

    wb = _wb(request, pk)
    if not wb.dataset_id:
        messages.error(request, "La hoja no está vinculada a un dataset.")
        return redirect("sheets:edit", pk=wb.pk)
    sheet = request.POST.get("sheet") or wb.data["sheets"][0]["name"]
    try:
        blob = engine.to_csv(wb.data, sheet)
        sf = store_generated(blob, f"publicacion_hoja_{wb.pk}_v{wb.version}.csv", request.user, source="import", area=wb.dataset.area)
        batch = ImportBatch.objects.create(dataset=wb.dataset, source_file=sf, file_sha256=sf.sha256, created_by=request.user, mode="upsert",
                                           options={"header_row": 1, "source_workbook": wb.pk, "source_version": wb.version, "delimiter": ","})
        batch.analysis = analyze(sf, delimiter=",")
        headers = batch.analysis["sheets"][0]["headers"]
        batch.mapping = {f: h for f, h in auto_map(headers).items()}
        for f in headers:
            if f in ("date", "work_order", "qty_good", "line", "shift", "station", "area", "serial", "qty_planned", "qty_reject", "qty_scrap"):
                batch.mapping[f] = f
        batch.save()
    except UserFacingError as exc:
        messages.error(request, str(exc))
        return redirect("sheets:edit", pk=wb.pk)
    audit(request.user, "sheet.publish_started", wb, f"Publicación de hoja {wb.name} v{wb.version} a {wb.dataset.name} (lote #{batch.pk})")
    messages.info(request, f"Se preparó el lote #{batch.pk} desde la hoja v{wb.version}. Revise el mapeo, valide e importe para publicar.")
    return redirect(f"/produccion/importar/{batch.pk}/?paso=2")


@require_POST
@require_cap("sheets.edit")
def share(request, pk):
    wb = _wb(request, pk)
    if wb.owner_id != request.user.pk and not request.user.is_superuser:
        raise PermissionDenied("Solo el propietario puede cambiar el uso compartido.")
    wb.shared = request.POST.get("shared") == "on"
    from apps.core.models import Area

    wb.area = Area.objects.filter(pk=request.POST.get("area") or 0).first() or wb.area
    wb.save(update_fields=["shared", "area"])
    messages.success(request, "Uso compartido actualizado.")
    return redirect("sheets:edit", pk=wb.pk)
