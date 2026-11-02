import mimetypes

from django.contrib import messages
from django.contrib.auth import get_user_model, update_session_auth_hash
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import PasswordChangeForm
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from .audit import audit
from .diagnostics import run_all
from .files import store_upload
from .forms import AreaForm, ShiftForm, UserCreateForm, UserEditForm
from .jobs import job_payload
from .models import Area, AuditLog, Job, Notification, Profile, Role, RoleCapability, Shift, SiteSetting, StoredFile
from .permissions import CAPABILITIES, can_access_file, capability_matrix, require_cap
from .utils import api, json_error, json_ok, paginate


@login_required
def home(request):
    from apps.comms.services import visible_announcements
    from apps.kaizen.models import Improvement
    from apps.production.metrics import Filters, kpi_summary
    from apps.production.models import WorkOrder

    user = request.user
    anns = visible_announcements(user).order_by("-priority_rank", "-created")[:5]
    kpis = kpi_summary(user, Filters.from_dict({"period": "month"}))
    assigned = WorkOrder.objects.filter(assigned_users=user).order_by("due")[:8]
    kaizen_open = Improvement.objects.exclude(status__in=["closed", "rejected"]).count()
    jobs = Job.objects.filter(created_by=user).order_by("-created")[:5]
    return render(request, "core/home.html", {
        "announcements": anns, "kpis": kpis, "assigned": assigned, "kaizen_open": kaizen_open, "jobs": jobs,
    })


@login_required
def password_change(request):
    form = PasswordChangeForm(request.user, request.POST or None)
    if request.method == "POST" and form.is_valid():
        user = form.save()
        update_session_auth_hash(request, user)
        Profile.objects.filter(user=user).update(must_change_password=False)
        audit(user, "user.password_changed", user, "Cambio de contraseña")
        messages.success(request, "Contraseña actualizada.")
        return redirect("home")
    return render(request, "core/password_change.html", {"form": form})


# ---------------------------------------------------------------- files
@login_required
def download(request, file_id):
    f = get_object_or_404(StoredFile, pk=file_id)
    if not can_access_file(request.user, f):
        audit(request.user, "file.download_denied", f, f"Descarga denegada: {f.original_name}")
        raise PermissionDenied("No tiene permiso para descargar este archivo.")
    if not f.path.exists():
        raise Http404("El archivo ya no existe en el almacenamiento. Contacte al administrador (restaurar respaldo).")
    inline = request.GET.get("inline") == "1" and f.ext in {"pdf", "png", "jpg", "jpeg", "svg", "gif", "txt"}
    ctype = f.mime or mimetypes.guess_type(f.original_name)[0] or "application/octet-stream"
    resp = FileResponse(open(f.path, "rb"), as_attachment=not inline, filename=f.original_name, content_type=ctype)
    if f.ext == "svg":
        resp["Content-Security-Policy"] = "default-src 'none'; style-src 'unsafe-inline'"
    return resp


# ---------------------------------------------------------------- notifications
@api
def notifications_poll(request):
    qs = Notification.objects.filter(user=request.user)
    unread = qs.filter(read_at__isnull=True)
    items = [
        {"id": n.id, "title": n.title, "body": n.body[:200], "url": n.url, "level": n.level,
         "created": timezone.localtime(n.created).strftime("%d/%m %H:%M"), "read": n.read_at is not None}
        for n in qs[:15]
    ]
    return json_ok({"unread": unread.count(), "items": items, "server_time": timezone.localtime().strftime("%H:%M:%S")})


@require_POST
@api
def notifications_read(request):
    ids = request.POST.getlist("id")
    qs = Notification.objects.filter(user=request.user, read_at__isnull=True)
    if ids:
        qs = qs.filter(id__in=ids)
    n = qs.update(read_at=timezone.now())
    return json_ok({"marked": n})


@login_required
def notifications_page(request):
    page = paginate(request, Notification.objects.filter(user=request.user), 30)
    return render(request, "core/notifications.html", {"page": page})


# ---------------------------------------------------------------- jobs
@api
def job_status(request, job_id):
    job = get_object_or_404(Job, pk=job_id)
    if job.created_by_id != request.user.id and not request.user.is_superuser:
        return json_error("Este trabajo pertenece a otro usuario.", status=403)
    return json_ok(job_payload(job))


@require_POST
@api
def job_cancel(request, job_id):
    job = get_object_or_404(Job, pk=job_id)
    if job.created_by_id != request.user.id and not request.user.is_superuser:
        return json_error("Este trabajo pertenece a otro usuario.", status=403)
    if job.is_final:
        return json_error("El trabajo ya terminó; no se puede cancelar.")
    if job.status == Job.Status.QUEUED:
        Job.objects.filter(pk=job.pk, status=Job.Status.QUEUED).update(status=Job.Status.CANCELLED, finished=timezone.now(), cancel_requested=True)
    else:
        Job.objects.filter(pk=job.pk).update(cancel_requested=True)
    return json_ok({"cancel_requested": True})


@login_required
def jobs_page(request):
    qs = Job.objects.all() if request.user.is_superuser else Job.objects.filter(created_by=request.user)
    return render(request, "core/jobs.html", {"page": paginate(request, qs, 30)})


# ---------------------------------------------------------------- administration
@require_cap("admin.users")
def admin_home(request):
    return render(request, "core/admin_home.html", {
        "users": get_user_model().objects.select_related("profile").order_by("username"),
        "areas": Area.objects.all(), "shifts": Shift.objects.all(),
    })


@require_cap("admin.users")
def user_create(request):
    form = UserCreateForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        user = form.save()
        audit(request.user, "user.created", user, f"Usuario {user.username} ({user.profile.get_role_display()})")
        messages.success(request, f"Usuario {user.username} creado. Deberá cambiar su contraseña al entrar.")
        return redirect("admin_home")
    return render(request, "core/user_form.html", {"form": form, "title": "Nuevo usuario"})


@require_cap("admin.users")
def user_edit(request, user_id):
    target = get_object_or_404(get_user_model(), pk=user_id)
    Profile.objects.get_or_create(user=target)
    form = UserEditForm(request.POST or None, instance=target)
    if request.method == "POST" and form.is_valid():
        before = {"role": target.profile.role, "areas": list(target.profile.areas.values_list("code", flat=True)), "active": target.is_active}
        with transaction.atomic():
            user = form.save()
        after = {"role": user.profile.role, "areas": list(user.profile.areas.values_list("code", flat=True)), "active": user.is_active}
        audit(request.user, "user.updated", user, f"Usuario {user.username} actualizado", {"before": before, "after": after})
        messages.success(request, "Usuario actualizado.")
        return redirect("admin_home")
    return render(request, "core/user_form.html", {"form": form, "title": f"Editar {target.username}"})


@require_cap("admin.users")
def area_edit(request, area_id=None):
    obj = get_object_or_404(Area, pk=area_id) if area_id else None
    form = AreaForm(request.POST or None, instance=obj)
    if request.method == "POST" and form.is_valid():
        a = form.save()
        audit(request.user, "area.saved", a, f"Área {a.code}")
        return redirect("admin_home")
    return render(request, "core/simple_form.html", {"form": form, "title": "Área"})


@require_cap("admin.users")
def shift_edit(request, shift_id=None):
    obj = get_object_or_404(Shift, pk=shift_id) if shift_id else None
    form = ShiftForm(request.POST or None, instance=obj)
    if request.method == "POST" and form.is_valid():
        s = form.save()
        audit(request.user, "shift.saved", s, f"Turno {s.code}")
        return redirect("admin_home")
    return render(request, "core/simple_form.html", {"form": form, "title": "Turno"})


@require_cap("admin.users")
def capability_matrix_view(request):
    roles = Role.choices
    if request.method == "POST":
        changes = {}
        with transaction.atomic():
            for cap in CAPABILITIES:
                for role, _label in roles:
                    if role == Role.ADMIN and cap.startswith("admin."):
                        continue  # never lock administrators out
                    allowed = request.POST.get(f"{cap}|{role}") == "on"
                    RoleCapability.objects.update_or_create(role=role, capability=cap, defaults={"allowed": allowed})
                    changes[f"{cap}|{role}"] = allowed
        audit(request.user, "permissions.matrix_saved", None, "Matriz de permisos actualizada", changes)
        messages.success(request, "Matriz de permisos guardada.")
        return redirect("capability_matrix")
    matrix = capability_matrix()
    rows = [{"cap": cap, "desc": desc, "cells": [(role, role in matrix[cap]) for role, _ in roles]} for cap, (desc, _r) in CAPABILITIES.items()]
    return render(request, "core/capabilities.html", {"rows": rows, "roles": roles})


@require_cap("admin.settings")
def settings_view(request):
    if request.method == "POST":
        if request.FILES.get("logo"):
            try:
                f = store_upload(request.FILES["logo"], request.user, allowed={"png", "jpg", "jpeg", "svg"}, visibility=StoredFile.Visibility.ALL)
            except Exception as exc:
                messages.error(request, str(exc))
                return redirect("settings")
            SiteSetting.put("logo_file_id", str(f.pk))
            audit(request.user, "settings.logo", f, "Logotipo actualizado")
            messages.success(request, "Logotipo actualizado.")
        if request.POST.get("remove_logo"):
            SiteSetting.put("logo_file_id", "")
            messages.success(request, "Se restauró la identidad por defecto.")
        return redirect("settings")
    return render(request, "core/settings.html", {})


@require_cap("admin.settings")
def diagnostics_view(request):
    return render(request, "core/diagnostics.html", {"sections": run_all()})


@require_cap("admin.settings")
def audit_view(request):
    qs = AuditLog.objects.select_related("actor")
    q = request.GET.get("q", "").strip()
    if q:
        qs = qs.filter(summary__icontains=q) | qs.filter(action__icontains=q)
    return render(request, "core/audit.html", {"page": paginate(request, qs, 50), "q": q})


def error_403(request, exception=None):
    msg = str(exception) if exception and str(exception) else "No tiene permiso para esta página u operación."
    return render(request, "403.html", {"message": msg}, status=403)


def error_404(request, exception=None):
    return render(request, "404.html", {}, status=404)


def error_500(request):
    return render(request, "500.html", {"op_id": getattr(request, "op_id", "-")}, status=500)
