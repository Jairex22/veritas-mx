import json

from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.db.models import Q
from django.http import Http404, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from apps.core.audit import audit
from apps.core.files import store_generated, store_upload
from apps.core.jobs import UserFacingError, enqueue
from apps.core.models import StoredFile
from apps.core.permissions import allowed_area_ids, has_cap, require_cap
from apps.core.utils import api, json_error, json_ok, read_json

from . import engines, ops_docx, ops_pdf, ops_pptx, ops_tabular
from .models import Document, Folder
from .services import OPS, describe, load_docs


def _visible(user):
    qs = Document.objects.filter(deleted=False).select_related("file", "owner", "folder", "area")
    if user.is_superuser:
        return qs
    ids = allowed_area_ids(user)
    cond = Q(owner=user) | Q(file__visibility=StoredFile.Visibility.ALL)
    if ids is None:
        cond |= Q(file__visibility=StoredFile.Visibility.AREA)
    else:
        cond |= Q(file__visibility=StoredFile.Visibility.AREA, area__in=ids)
    return qs.filter(cond)


def _doc(request, pk):
    d = get_object_or_404(Document.objects.select_related("file", "owner", "folder"), pk=pk, deleted=False)
    if not d.user_can_view(request.user):
        raise Http404()
    return d


@require_cap("documents.use")
def doc_list(request):
    qs = _visible(request.user)
    q = request.GET.get("q", "").strip()
    if q:
        qs = qs.filter(Q(title__icontains=q) | Q(tags__icontains=q))
    if request.GET.get("tipo"):
        qs = qs.filter(file__original_name__iendswith="." + request.GET["tipo"])
    folder = None
    if request.GET.get("carpeta"):
        folder = get_object_or_404(Folder, pk=request.GET["carpeta"])
        qs = qs.filter(folder=folder)
    office = engines.office_engine_status()
    return render(request, "documents/list.html", {
        "docs": qs[:300], "q": q, "folders": Folder.objects.all(), "folder": folder, "office": office,
        "ocr": engines.ocr_engine_status(), "can_transform": has_cap(request.user, "documents.transform"),
        "visibilities": StoredFile.Visibility.choices,
    })


@require_POST
@require_cap("documents.use")
def upload(request):
    files = request.FILES.getlist("files")
    if not files:
        messages.error(request, "Seleccione uno o más archivos.")
        return redirect("documents:list")
    folder = Folder.objects.filter(pk=request.POST.get("folder") or 0).first()
    vis = request.POST.get("visibility") or StoredFile.Visibility.PRIVATE
    if vis not in StoredFile.Visibility.values:
        vis = StoredFile.Visibility.PRIVATE
    area = None
    prof = getattr(request.user, "profile", None)
    if prof is not None:
        area = prof.areas.first()
    if vis == StoredFile.Visibility.AREA and area is None:
        messages.warning(request, "Su usuario no tiene un área asignada; los archivos quedan privados.")
        vis = StoredFile.Visibility.PRIVATE
    ok = 0
    for f in files:
        try:
            sf = store_upload(f, request.user, visibility=vis, area=area)
        except UserFacingError as exc:
            messages.error(request, f"{f.name}: {exc}")
            continue
        Document.objects.create(file=sf, title=sf.original_name, owner=request.user, area=area, folder=folder,
                                tags=request.POST.get("tags", "")[:300], info=describe(sf.ext, sf.path.read_bytes()))
        ok += 1
    if ok:
        audit(request.user, "document.uploaded", None, f"{ok} documento(s) cargados")
        messages.success(request, f"{ok} archivo(s) cargados. Los originales se conservan; cada transformación crea un archivo nuevo.")
    return redirect(request.POST.get("next") or "documents:list")


@require_POST
@require_cap("documents.use")
def folder_create(request):
    name = request.POST.get("name", "").strip()
    if name:
        Folder.objects.create(name=name[:120], owner=request.user)
    return redirect("documents:list")


@require_cap("documents.use")
def detail(request, pk):
    d = _doc(request, pk)
    data = d.file.path.read_bytes() if d.file.path.exists() else b""
    ctx = {"d": d, "office": engines.office_engine_status(), "ocr": engines.ocr_engine_status(),
           "can_transform": has_cap(request.user, "documents.transform"), "derivatives": d.derivatives.filter(deleted=False)[:50],
           "is_owner": d.owner_id == request.user.pk}
    try:
        if d.ext == "pdf":
            ctx["pdf"] = ops_pdf.info(data)
        elif d.ext == "pptx":
            ctx["pptx"] = ops_pptx.analyze(data)
            ctx["pptx_warnings"] = ops_pptx.preservation_warnings(ctx["pptx"], "duplicate")
        elif d.ext == "xlsx":
            ctx["xlsx"] = ops_tabular.xlsx_info(data)
        elif d.ext == "docx":
            ctx["docx"] = ops_docx.analyze(data)
        elif d.ext in ("csv", "txt"):
            rows, enc, delim = ops_tabular.read_csv_rows(data)
            ctx["csv"] = {"header": rows[0] if rows else [], "preview": rows[1:11], "rows": max(len(rows) - 1, 0), "encoding": enc,
                          "delimiter": "tab" if delim == "\t" else delim}
    except UserFacingError as exc:
        ctx["error"] = str(exc)
    thumb = f"/documentos/{d.pk}/miniatura/PAGE.png"
    has_prev = bool(d.info.get("preview_pdf"))
    if ctx.get("pdf") and ctx["pdf"].get("pages"):
        n = ctx["pdf"]["pages"]
        ctx["organizer"] = {"kind": "pdf", "rotate": True, "thumb": thumb,
                            "items": [{"page": i, "label": f"Pág. {i + 1}", "thumb": thumb.replace("PAGE", str(i))} for i in range(min(n, 500))]}
    elif ctx.get("pptx"):
        ctx["organizer"] = {"kind": "pptx", "rotate": False, "thumb": thumb, "items": [
            {"page": s_["index"], "label": s_["title"][:40], "text": f"{s_['title']} · {s_['layout']} · {s_['pictures']} img, {s_['charts']} gráf.",
             "thumb": thumb.replace("PAGE", str(s_["index"])) if has_prev else None} for s_ in ctx["pptx"]["slides"]]}
    elif ctx.get("docx"):
        ctx["organizer"] = {"kind": "docx", "rotate": False, "thumb": thumb, "items": [
            {"page": b["index"], "label": f"{b['style']}" + (f" [{', '.join(b['features'])}]" if b["features"] else ""), "text": b["text"]}
            for b in ctx["docx"]["blocks"][:2000]]}
    ctx["has_preview"] = has_prev
    return render(request, "documents/detail.html", ctx)


@require_cap("documents.use")
def thumb(request, pk, page):
    d = _doc(request, pk)
    if d.ext == "pdf":
        data = d.file.path.read_bytes()
    else:
        prev = d.info.get("preview_pdf")
        sf = StoredFile.objects.filter(pk=prev).first() if prev else None
        if sf is None:
            raise Http404("Sin vista previa")
        data = sf.path.read_bytes()
    try:
        png = ops_pdf.thumbnail(data, page=int(page), width=int(request.GET.get("w", 170)))
    except Exception:
        raise Http404("No se pudo renderizar")
    resp = HttpResponse(png, content_type="image/png")
    resp["Cache-Control"] = "private, max-age=600"
    return resp


@require_POST
@api
def preview(request, pk):
    """Render PPTX/DOCX/XLSX to a PDF once (LibreOffice) to show page/slide thumbnails."""
    d = _doc(request, pk)
    if d.ext not in ("pptx", "docx", "xlsx"):
        return json_error("No aplica.")
    if not engines.soffice_path():
        return json_error("Miniaturas no disponibles: " + engines.OFFICE_REQUIREMENT)
    if not d.info.get("preview_pdf"):
        pdf = engines.convert_with_office(d.file.path.read_bytes(), d.ext, "pdf")
        sf = store_generated(pdf, f"vista_previa_{d.pk}.pdf", d.owner, parent=d.file, visibility=d.file.visibility, area=d.area)
        d.info = {**d.info, "preview_pdf": str(sf.pk), "preview_pages": ops_pdf.info(pdf)["pages"]}
        d.save(update_fields=["info"])
    return json_ok({"pages": d.info.get("preview_pages")})


@require_POST
@api
def operate(request):
    if not has_cap(request.user, "documents.transform"):
        return json_error("Su rol no tiene permiso para transformar documentos.", status=403)
    if request.content_type.startswith("application/json"):
        body = read_json(request)
        op, ids, params, key = body.get("op"), body.get("docs", []), body.get("params", {}), body.get("idempotency_key")
    else:
        op = request.POST.get("op")
        ids = request.POST.getlist("docs")
        params = {k: (request.POST.getlist(k) if k in ("sheets", "order") else v) for k, v in request.POST.items()
                  if k not in ("op", "docs", "csrfmiddlewaretoken", "idempotency_key")}
        for k in ("plan", "selections"):
            if k in params and isinstance(params[k], str) and params[k]:
                try:
                    params[k] = json.loads(params[k])
                except ValueError:
                    return json_error("Datos de selección inválidos.")
        key = request.POST.get("idempotency_key")
    if op not in OPS:
        return json_error("Operación desconocida.")
    _func, requires, label = OPS[op]
    if requires == "office" and not engines.soffice_path():
        return json_error(f"«{label}» requiere el convertidor Office. " + engines.OFFICE_REQUIREMENT)
    if requires == "ocr" and not engines.tesseract_path():
        return json_error("OCR no disponible. " + engines.OCR_REQUIREMENT)
    load_docs(request.user, ids)
    job, _ = enqueue("documents.op", {"op": op, "docs": [int(i) for i in ids], "params": params}, request.user,
                     idempotency_key=f"doc-{request.user.pk}-{key}" if key else None)
    return json_ok(job_id=str(job.pk))


@require_POST
@api
def decrypt(request, pk):
    d = _doc(request, pk)
    if d.ext != "pdf":
        return json_error("Solo aplica a PDF.")
    password = request.POST.get("password", "")  # used in memory only; never stored or logged
    reader = ops_pdf.open_pdf(d.file.path.read_bytes(), password=password)
    blob = ops_pdf.decrypt(reader)
    sf = store_generated(blob, f"{d.title.rsplit('.', 1)[0]}_sin_proteccion.pdf", request.user, parent=d.file, area=d.area)
    nd = Document.objects.create(file=sf, title=sf.original_name, owner=request.user, area=d.area, folder=d.folder, derived_from=d,
                                 operation="pdf_decrypt", info=describe("pdf", blob))
    audit(request.user, "document.pdf_decrypt", d, "Copia sin protección generada (contraseña no almacenada)")
    return json_ok({"files": [{"name": sf.original_name, "url": f"/archivos/{sf.pk}/", "type": "PDF", "size_h": f"{sf.size // 1024} KB"}],
                    "url": f"/documentos/{nd.pk}/", "summary": "Copia sin protección creada. Si el PDF estaba firmado, la firma ya no es válida."})


@api
def csv_dedupe_preview(request, pk):
    d = _doc(request, pk)
    rows, enc, delim = ops_tabular.read_csv_rows(d.file.path.read_bytes())
    cols = [c for c in request.GET.get("columns", "").split(",") if c.strip()]
    for c in cols:
        if c not in rows[0]:
            return json_error(f"La columna «{c}» no existe.")
    body, dups = ops_tabular.dedupe(rows[0], rows[1:], cols or None)
    return json_ok({"duplicates": len(dups), "rows": dups[:50], "remaining": len(body)})


@require_cap("documents.use")
def zip_download(request):
    ids = request.GET.getlist("id") or request.POST.getlist("id")
    docs = load_docs(request.user, ids)
    if not docs:
        raise Http404()
    blob = ops_pdf.zip_files([(d.file.original_name, d.file.path.read_bytes()) for d in docs])
    resp = HttpResponse(blob, content_type="application/zip")
    resp["Content-Disposition"] = f'attachment; filename="documentos_{timezone.localtime():%Y%m%d_%H%M}.zip"'
    return resp


@require_POST
@require_cap("documents.use")
def delete(request, pk):
    d = _doc(request, pk)
    if d.owner_id != request.user.pk and not request.user.is_superuser:
        raise PermissionDenied("Solo el propietario puede quitar el documento.")
    d.deleted = True
    d.save(update_fields=["deleted"])
    audit(request.user, "document.removed", d, f"Documento retirado del centro: {d.title} (el archivo se conserva para auditoría)")
    messages.success(request, "Documento retirado del listado.")
    return redirect("documents:list")


@require_POST
@require_cap("documents.use")
def update_meta(request, pk):
    d = _doc(request, pk)
    if d.owner_id != request.user.pk and not request.user.is_superuser:
        raise PermissionDenied("Solo el propietario puede cambiar permisos y etiquetas.")
    d.tags = request.POST.get("tags", d.tags)[:300]
    d.folder = Folder.objects.filter(pk=request.POST.get("folder") or 0).first()
    vis = request.POST.get("visibility")
    if vis in StoredFile.Visibility.values:
        d.file.visibility = vis
        d.file.save(update_fields=["visibility"])
    d.save()
    audit(request.user, "document.meta", d, f"Etiquetas/permisos: {d.tags} · {d.file.visibility}")
    messages.success(request, "Datos del documento actualizados.")
    return redirect("documents:detail", pk=d.pk)
