import uuid
from decimal import Decimal, InvalidOperation

from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from apps.core.audit import audit
from apps.core.files import store_upload
from apps.core.jobs import UserFacingError, enqueue
from apps.core.models import Area, Shift
from apps.core.permissions import allowed_area_ids, can_access_area, filter_by_area, has_cap, require_cap
from apps.core.utils import json_error, json_ok, paginate

from .fields import DEFAULT_KEYS, FIELDS, REQUIRED, auto_map
from .forms import DatasetForm, PlanEditForm
from .importer import analyze, revert
from .metrics import Filters, kpi_summary, order_rows, projection, records_queryset
from .models import Dataset, DatasetKind, ImportBatch, MappingProfile, PlanChange, ProductionRecord, WorkOrder

PERIODS = [("today", "Hoy"), ("week", "Semana"), ("month", "Mes"), ("range", "Rango personalizado"), ("all", "Todo")]


def _filter_context(request, f):
    ids = allowed_area_ids(request.user)
    areas = Area.objects.filter(active=True) if ids is None else Area.objects.filter(id__in=ids)
    wo = filter_by_area(WorkOrder.objects.all(), request.user)
    return {
        "filters": f, "period_choices": PERIODS, "areas": areas, "shifts": Shift.objects.filter(active=True),
        "customers": sorted({c for c in wo.values_list("customer", flat=True) if c})[:200],
        "lines": sorted({c for c in wo.values_list("line", flat=True) if c})[:200],
    }


@require_cap("production.view")
def plan(request):
    f = Filters.from_dict(request.GET)
    rows, warnings = order_rows(request.user, f)
    kpis = kpi_summary(request.user, f)
    page = paginate(request, rows, 50)
    ctx = {"page": page, "kpis": kpis, "warnings": warnings, "query": request.GET.urlencode(), "persist_key": "plan"}
    ctx.update(_filter_context(request, f))
    return render(request, "production/plan.html", ctx)


@require_cap("production.view")
def order_detail(request, order_id):
    wo = get_object_or_404(WorkOrder.objects.select_related("area"), pk=order_id)
    if not can_access_area(request.user, wo.area_id):
        raise PermissionDenied("La orden pertenece a un área sin permiso.")
    f = Filters(period="all", work_order=wo.number)
    rows, warnings = order_rows(request.user, f)
    row = next((r for r in rows if r["id"] == wo.pk), None)
    proj = projection(request.user, f, row) if row else None
    # only records of areas the user may see (an order number can also appear in another area's datasets)
    records = filter_by_area(ProductionRecord.objects.filter(is_current=True, work_order__iexact=wo.number), request.user).select_related(
        "dataset").order_by("-date", "-id")[:200]
    can_edit = has_cap(request.user, "production.edit_plan")
    can_capture = has_cap(request.user, "production.capture") and (
        can_edit or wo.assigned_users.filter(pk=request.user.pk).exists())
    form = PlanEditForm(instance=wo) if can_edit else None
    from apps.comms.services import thread_context

    return render(request, "production/order_detail.html", {
        "wo": wo, "row": row, "projection": proj, "warnings": warnings, "records": records,
        "changes": wo.changes.select_related("user", "batch")[:100], "form": form, "can_capture": can_capture,
        "shifts": Shift.objects.filter(active=True), "today": timezone.localdate(), **thread_context(request, wo),
    })


@require_POST
@require_cap("production.edit_plan")
def order_edit(request, order_id):
    wo = get_object_or_404(WorkOrder, pk=order_id)
    if not can_access_area(request.user, wo.area_id):
        raise PermissionDenied("La orden pertenece a un área sin permiso.")
    form = PlanEditForm(request.POST, instance=WorkOrder.objects.get(pk=wo.pk))
    if not form.is_valid():
        messages.error(request, "Revise los datos: " + "; ".join(f"{k}: {', '.join(v)}" for k, v in form.errors.items()))
        return redirect("production:order", order_id=wo.pk)
    if int(request.POST.get("version", 0)) != wo.version:
        messages.error(request, "La orden fue modificada por otra persona mientras editaba. Revise los valores actuales y repita el cambio.")
        return redirect("production:order", order_id=wo.pk)
    reason = form.cleaned_data["reason"].strip()
    with transaction.atomic():
        locked = WorkOrder.objects.select_for_update().get(pk=wo.pk)
        changed = []
        for field in ("qty_planned", "priority", "due", "status", "responsible"):
            new = form.cleaned_data.get(field)
            old = getattr(locked, field)
            if str(old if old is not None else "") != str(new if new is not None else ""):
                PlanChange.objects.create(work_order=locked, field=field, old_value=None if old is None else str(old),
                                          new_value=None if new is None else str(new), reason=reason, user=request.user)
                setattr(locked, field, new)
                changed.append(field)
        new_users = set(form.cleaned_data["assigned_users"].values_list("pk", flat=True))
        old_users = set(locked.assigned_users.values_list("pk", flat=True))
        if new_users != old_users:
            PlanChange.objects.create(work_order=locked, field="assigned_users", old_value=",".join(map(str, sorted(old_users))),
                                      new_value=",".join(map(str, sorted(new_users))), reason=reason, user=request.user)
            locked.assigned_users.set(new_users)
            changed.append("assigned_users")
        if changed:
            locked.version += 1
            locked.updated = timezone.now()
            locked.save()
    if changed:
        audit(request.user, "plan.updated", locked, f"Orden {locked.number}: {', '.join(changed)} · {reason}")
        messages.success(request, f"Cambios guardados con motivo: {reason}")
    else:
        messages.info(request, "No hubo cambios.")
    return redirect("production:order", order_id=wo.pk)


def _manual_dataset(area):
    ds, _ = Dataset.objects.get_or_create(
        code="capturas-manuales",
        defaults={"name": "Capturas manuales", "kind": DatasetKind.INCREMENTAL, "area": area,
                  "key_fields": [], "description": "Avance capturado en el portal por usuarios autorizados."},
    )
    return ds


@require_POST
@require_cap("production.capture")
def order_capture(request, order_id):
    wo = get_object_or_404(WorkOrder, pk=order_id)
    if not can_access_area(request.user, wo.area_id):
        raise PermissionDenied("La orden pertenece a un área sin permiso.")
    if not has_cap(request.user, "production.edit_plan") and not wo.assigned_users.filter(pk=request.user.pk).exists():
        raise PermissionDenied("Solo puede capturar avance en órdenes que tiene asignadas.")
    try:
        qty = {k: Decimal(request.POST.get(k) or "0") for k in ("qty_good", "qty_reject", "qty_scrap")}
    except InvalidOperation:
        messages.error(request, "Las cantidades deben ser números (use punto decimal).")
        return redirect("production:order", order_id=wo.pk)
    if any(v < 0 for v in qty.values()) or not any(qty.values()):
        messages.error(request, "Capture al menos una cantidad positiva; no se permiten negativos.")
        return redirect("production:order", order_id=wo.pk)
    try:
        day = timezone.datetime.fromisoformat(request.POST.get("date")).date()
    except (TypeError, ValueError):
        day = timezone.localdate()
    ds = _manual_dataset(wo.area)
    rec = ProductionRecord.objects.create(
        dataset=ds, record_key=f"manual:{uuid.uuid4().hex}", area=wo.area, date=day, timestamp=timezone.now(),
        shift=request.POST.get("shift", "")[:20], line=wo.line, work_order=wo.number, part_number=wo.part_number, unit=wo.unit,
        station=request.POST.get("station", "")[:60] or ds.finished_station, notes=request.POST.get("notes", "")[:500],
        entered_by=request.user, **qty,
    )
    Dataset.objects.filter(pk=ds.pk).update(last_import_at=timezone.now())
    audit(request.user, "production.capture", rec, f"Captura manual orden {wo.number}: buenas {qty['qty_good']}, rechazo {qty['qty_reject']}, scrap {qty['qty_scrap']}", area=wo.area)
    messages.success(request, "Avance registrado.")
    return redirect("production:order", order_id=wo.pk)


# ---------------------------------------------------------------- import wizard
@require_cap("production.import")
def import_start(request):
    datasets = Dataset.objects.all()
    if request.method == "POST":
        ds = get_object_or_404(Dataset, pk=request.POST.get("dataset"))
        upload = request.FILES.get("file")
        if not upload:
            messages.error(request, "Seleccione o arrastre un archivo XLSX o CSV.")
            return redirect("production:import_start")
        try:
            sf = store_upload(upload, request.user, allowed={"xlsx", "csv", "txt", "tsv"}, source="import", area=ds.area)
            batch = ImportBatch.objects.create(dataset=ds, source_file=sf, file_sha256=sf.sha256, created_by=request.user,
                                               options={"header_row": 1})
            batch.analysis = analyze(sf)
            sheet0 = batch.analysis["sheets"][0] if batch.analysis["sheets"] else None
            batch.sheet = sheet0["name"] if sheet0 and sf.ext == "xlsx" else ""
            batch.mapping = auto_map(sheet0["headers"]) if sheet0 else {}
            prof = ds.profiles.first()
            if prof and sheet0 and all(h in sheet0["headers"] for h in prof.mapping.values() if h):
                batch.mapping = dict(prof.mapping)
                batch.options.update(prof.options)
                messages.info(request, f"Se aplicó el perfil de mapeo «{prof.name}».")
            batch.save()
        except UserFacingError as exc:
            messages.error(request, str(exc))
            return redirect("production:import_start")
        audit(request.user, "import.uploaded", batch, f"Archivo {sf.original_name} cargado para {ds.name}")
        return redirect(f"/produccion/importar/{batch.pk}/?paso=2")
    recent = ImportBatch.objects.select_related("dataset", "source_file", "created_by")[:15]
    return render(request, "production/import_start.html", {"datasets": datasets, "recent": recent})


def _get_batch(request, batch_id):
    batch = get_object_or_404(ImportBatch.objects.select_related("dataset", "source_file"), pk=batch_id)
    if batch.created_by_id != request.user.id:
        if not has_cap(request.user, "production.revert"):
            raise PermissionDenied("Este lote pertenece a otro usuario.")
        if batch.dataset.area_id is not None and not can_access_area(request.user, batch.dataset.area_id):
            raise PermissionDenied("Este lote pertenece a un área sin permiso.")
    return batch


@require_cap("production.import")
def import_wizard(request, batch_id):
    batch = _get_batch(request, batch_id)
    step = request.GET.get("paso", "2")
    analysis = batch.analysis or {}
    sheets = analysis.get("sheets", [])
    cur_sheet = next((s for s in sheets if s["name"] == batch.sheet), sheets[0] if sheets else None)
    if request.method == "POST" and batch.status in (ImportBatch.Status.DRAFT, ImportBatch.Status.VALIDATED):
        opts = dict(batch.options or {})
        new_header = int(request.POST.get("header_row") or 1)
        new_enc = request.POST.get("encoding", "")
        new_delim = request.POST.get("delimiter", "")
        new_delim = "\t" if new_delim == "tab" else new_delim
        reanalyze = (new_header != int(opts.get("header_row", 1)) or new_enc != opts.get("encoding", "") or new_delim != opts.get("delimiter", ""))
        opts.update({
            "header_row": new_header, "encoding": new_enc, "delimiter": new_delim,
            "date_order": request.POST.get("date_order", "auto"), "decimal_sep": request.POST.get("decimal_sep", "auto"),
            "allow_partial": request.POST.get("allow_partial") == "on",
        })
        batch.options = opts
        if request.POST.get("sheet") and request.POST.get("sheet") != batch.sheet:
            batch.sheet = request.POST["sheet"]
            reanalyze = True
        batch.mode = request.POST.get("mode", ImportBatch.Mode.APPEND)
        batch.scope = {k: request.POST.get(f"scope_{k}", "") for k in ("date_from", "date_to", "line") if request.POST.get(f"scope_{k}")}
        try:
            if reanalyze:
                batch.analysis = analyze(batch.source_file, header_row=new_header, encoding=new_enc or None, delimiter=new_delim or None)
                sheets = batch.analysis["sheets"]
                cur = next((s for s in sheets if s["name"] == batch.sheet), sheets[0] if sheets else None)
                batch.mapping = auto_map(cur["headers"]) if cur else {}
                batch.status = ImportBatch.Status.DRAFT
                batch.save()
                messages.info(request, "Se volvió a leer el archivo con las nuevas opciones; revise el mapeo.")
                return redirect(f"/produccion/importar/{batch.pk}/?paso=2")
            batch.mapping = {f: request.POST.get(f"map_{f}", "") for f in FIELDS if request.POST.get(f"map_{f}")}
            keys = request.POST.getlist("key_fields")
            if keys and has_cap(request.user, "production.configure"):
                batch.dataset.key_fields = keys
                batch.dataset.save(update_fields=["key_fields"])
            batch.status = ImportBatch.Status.DRAFT
            batch.save()
            if request.POST.get("profile_name"):
                MappingProfile.objects.update_or_create(
                    dataset=batch.dataset, name=request.POST["profile_name"][:120],
                    defaults={"mapping": batch.mapping, "created_by": request.user,
                              "options": {k: opts[k] for k in ("date_order", "decimal_sep", "header_row", "encoding", "delimiter")}},
                )
                messages.success(request, "Perfil de mapeo guardado.")
            job, _ = enqueue("production.import_validate", {"batch_id": batch.pk}, request.user)
            if job.status == job.Status.FAILED:
                messages.error(request, job.error)
                return redirect(f"/produccion/importar/{batch.pk}/?paso=2")
        except UserFacingError as exc:
            messages.error(request, str(exc))
            return redirect(f"/produccion/importar/{batch.pk}/?paso=2")
        return redirect(f"/produccion/importar/{batch.pk}/?paso=3&job={job.pk}")
    ds = batch.dataset
    required = set(REQUIRED.get(ds.kind, []))
    field_rows = [{"name": f, "label": l, "type": t, "required": f in required, "mapped": batch.mapping.get(f, "")}
                  for f, (l, t, _a) in FIELDS.items()]
    validation = analysis.get("validation")
    return render(request, "production/import_wizard.html", {
        "batch": batch, "step": step, "analysis": analysis, "sheet": cur_sheet, "fields": field_rows,
        "modes": ImportBatch.Mode.choices, "validation": validation, "key_fields": ds.key_fields or DEFAULT_KEYS.get(ds.kind, []),
        "job_id": request.GET.get("job", ""), "can_configure": has_cap(request.user, "production.configure"),
        "is_snapshot": ds.kind == DatasetKind.SNAPSHOT,
    })


@require_POST
@require_cap("production.import")
def import_commit(request, batch_id):
    batch = _get_batch(request, batch_id)
    if batch.status != ImportBatch.Status.VALIDATED:
        return json_error("Valide el archivo antes de importar (o el lote ya fue importado).")
    job, created = enqueue("production.import_commit", {"batch_id": batch.pk}, request.user,
                           idempotency_key=f"import-commit-{batch.pk}")
    return json_ok(job_id=str(job.pk), created=created)


@require_cap("production.import")
def imports_list(request):
    qs = ImportBatch.objects.select_related("dataset", "source_file", "created_by")
    if not has_cap(request.user, "production.revert"):
        qs = qs.filter(created_by=request.user)
    else:
        from django.db.models import Q

        ids = allowed_area_ids(request.user)
        if ids is not None:
            qs = qs.filter(Q(created_by=request.user) | Q(dataset__area__isnull=True) | Q(dataset__area__in=ids))
    return render(request, "production/imports.html", {"page": paginate(request, qs, 30)})


def _can_view_batch(user, batch):
    """Read-only traceability: whoever may see production of the dataset area can see the batch summary."""
    if batch.created_by_id == user.id:
        return True
    if not (has_cap(user, "production.view") or has_cap(user, "production.revert")):
        return False
    ids = allowed_area_ids(user)
    if ids is None or batch.dataset.area_id is None or batch.dataset.area_id in ids:
        return True
    # files may carry their own area column: rows of the user's areas grant read access to the batch
    if ProductionRecord.objects.filter(batch=batch, area__in=ids).exists() or ProductionRecord.objects.filter(last_batch=batch, area__in=ids).exists():
        return True
    return PlanChange.objects.filter(batch=batch, work_order__area__in=ids).exists()


@login_required
def import_detail(request, batch_id):
    batch = get_object_or_404(ImportBatch.objects.select_related("dataset", "source_file", "created_by"), pk=batch_id)
    if not _can_view_batch(request.user, batch):
        raise PermissionDenied("Este lote pertenece a un área sin permiso.")
    from apps.core.permissions import can_access_file

    return render(request, "production/import_detail.html", {
        "can_download_source": can_access_file(request.user, batch.source_file),
        "can_download_errors": bool(batch.error_file) and can_access_file(request.user, batch.error_file),
        "batch": batch, "can_revert": has_cap(request.user, "production.revert") and batch.status == ImportBatch.Status.COMMITTED,
        "plan_changes": PlanChange.objects.filter(batch=batch).select_related("work_order")[:200],
    })


@require_POST
@require_cap("production.revert")
def import_revert(request, batch_id):
    batch = _get_batch(request, batch_id)
    reason = request.POST.get("reason", "").strip()
    if len(reason) < 5:
        messages.error(request, "Indique el motivo de la reversión (mínimo 5 caracteres).")
        return redirect("production:import_detail", batch_id=batch.pk)
    try:
        res = revert(batch, request.user, reason)
    except UserFacingError as exc:
        messages.error(request, str(exc))
        return redirect("production:import_detail", batch_id=batch.pk)
    if res["conflicts"]:
        messages.warning(request, f"Reversión parcial: {res['restored']} restaurados, {res['deleted']} eliminados, {len(res['conflicts'])} conservados por cambios posteriores.")
    else:
        messages.success(request, f"Lote revertido: {res['restored']} restaurados, {res['deleted']} eliminados.")
    return redirect("production:import_detail", batch_id=batch.pk)


# ---------------------------------------------------------------- datasets
@require_cap("production.import")
def datasets(request):
    return render(request, "production/datasets.html", {"datasets": Dataset.objects.select_related("area"),
                                                        "can_configure": has_cap(request.user, "production.configure")})


@require_cap("production.configure")
def dataset_edit(request, dataset_id=None):
    obj = get_object_or_404(Dataset, pk=dataset_id) if dataset_id else None
    if obj is not None and obj.area_id and not can_access_area(request.user, obj.area_id):
        raise PermissionDenied("El dataset pertenece a un área sin permiso.")
    form = DatasetForm(request.POST or None, instance=obj)
    if request.method == "POST" and form.is_valid():
        ds = form.save(commit=False)
        if not ds.created_by_id:
            ds.created_by = request.user
        if not ds.key_fields:
            ds.key_fields = DEFAULT_KEYS.get(ds.kind, [])
        ds.save()
        audit(request.user, "dataset.saved", ds, f"Dataset {ds.name} ({ds.get_kind_display()})")
        messages.success(request, "Dataset guardado.")
        return redirect("production:datasets")
    return render(request, "production/dataset_form.html", {"form": form, "obj": obj})


# ---------------------------------------------------------------- records explorer
@require_cap("production.view")
def records(request):
    f = Filters.from_dict(request.GET)
    qs = records_queryset(request.user, f, kinds=None).select_related("dataset", "area").order_by("-date", "-id")
    if request.GET.get("dataset"):
        qs = qs.filter(dataset__code=request.GET["dataset"])
    if request.GET.get("cause"):
        qs = qs.filter(cause__iexact=request.GET["cause"])
    ctx = {"page": paginate(request, qs, 100), "query": request.GET.urlencode(), "datasets": Dataset.objects.all(),
           "persist_key": "records"}
    ctx.update(_filter_context(request, f))
    return render(request, "production/records.html", ctx)


@login_required
def users_for_assignment(request):
    User = get_user_model()
    return json_ok([{"id": u.pk, "name": u.get_full_name() or u.username} for u in User.objects.filter(is_active=True)[:500]])
