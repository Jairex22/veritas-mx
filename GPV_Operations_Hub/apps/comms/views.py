from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from apps.core.audit import audit
from apps.core.files import store_upload
from apps.core.jobs import UserFacingError
from apps.core.notify import notify, users_for_scope
from apps.core.permissions import can_access_area, has_cap, require_cap
from apps.core.utils import paginate

from .forms import AnnouncementForm, ConversationForm
from .models import Announcement, AnnouncementRead, Comment, Conversation, ConversationRead, Message
from .services import can_see_announcement, visible_announcements


def _audience(ann):
    users = users_for_scope(
        area_ids=list(ann.areas.values_list("id", flat=True)) or None,
        roles=ann.roles or None,
        shift_ids=list(ann.shifts.values_list("id", flat=True)) or None,
        group_ids=list(ann.groups.values_list("id", flat=True)) or None,
    )
    return [u for u in users if can_see_announcement(u, ann)]


@login_required
def announcement_list(request):
    show = request.GET.get("ver", "vigentes")
    qs = visible_announcements(request.user, include_expired=(show == "todos")).select_related("author")
    q = request.GET.get("q", "").strip()
    if q:
        qs = qs.filter(title__icontains=q) | qs.filter(body__icontains=q)
    reads = {r.announcement_id: r for r in AnnouncementRead.objects.filter(user=request.user)}
    items = [(a, reads.get(a.pk)) for a in qs.order_by("-priority_rank", "-created")]
    page = paginate(request, items, 20)
    conversations = Conversation.objects.filter(participants=request.user)[:10]
    return render(request, "comms/list.html", {"page": page, "q": q, "show": show, "conversations": conversations,
                                               "can_publish": has_cap(request.user, "comms.publish")})


@login_required
def announcement_detail(request, ann_id):
    ann = get_object_or_404(Announcement.objects.select_related("author"), pk=ann_id)
    if not can_see_announcement(request.user, ann):
        raise Http404()
    read, _ = AnnouncementRead.objects.get_or_create(announcement=ann, user=request.user)
    from .services import thread_context

    ctx = {"ann": ann, "read": read, **thread_context(request, ann)}
    if ann.author_id == request.user.pk or has_cap(request.user, "comms.publish"):
        audience = _audience(ann)
        receipts = {r.user_id: r for r in ann.reads.all()}
        ctx["receipts"] = [(u, receipts.get(u.pk)) for u in audience]
        ctx["read_count"] = sum(1 for u in audience if u.pk in receipts)
        ctx["ack_count"] = sum(1 for u in audience if receipts.get(u.pk) and receipts[u.pk].ack_at)
    return render(request, "comms/detail.html", ctx)


@require_POST
@login_required
def announcement_ack(request, ann_id):
    ann = get_object_or_404(Announcement, pk=ann_id)
    if not can_see_announcement(request.user, ann):
        raise Http404()
    read, _ = AnnouncementRead.objects.get_or_create(announcement=ann, user=request.user)
    if not read.ack_at:
        read.ack_at = timezone.now()
        read.save(update_fields=["ack_at"])
        audit(request.user, "announcement.ack", ann, f"Confirmó lectura: {ann.title}")
    messages.success(request, "Lectura confirmada.")
    return redirect("comms:detail", ann_id=ann.pk)


@require_cap("comms.publish")
def announcement_edit(request, ann_id=None):
    ann = get_object_or_404(Announcement, pk=ann_id) if ann_id else None
    if ann and ann.author_id != request.user.pk and not request.user.is_superuser:
        raise PermissionDenied("Solo el autor o un administrador pueden editar este comunicado.")
    form = AnnouncementForm(request.POST or None, instance=ann)
    if request.method == "POST" and form.is_valid():
        try:
            with transaction.atomic():
                obj = form.save(commit=False)
                is_new = obj.pk is None
                if is_new:
                    obj.author = request.user
                else:
                    obj.version += 1
                    obj.updated = timezone.now()
                obj.roles = form.cleaned_data["roles"]
                obj.save()
                form.save_m2m()
                for up in request.FILES.getlist("attachments"):
                    sf = store_upload(up, request.user)
                    obj.attachments.add(sf)
        except UserFacingError as exc:
            messages.error(request, str(exc))
            return render(request, "comms/form.html", {"form": form, "ann": ann})
        audit(request.user, "announcement.published" if is_new else "announcement.updated", obj,
              f"{'Publicó' if is_new else 'Editó (v%d)' % obj.version} comunicado: {obj.title}",
              {"priority": obj.priority, "areas": list(obj.areas.values_list("code", flat=True)), "roles": obj.roles})
        if is_new or request.POST.get("renotify"):
            n = notify(_audience(obj), f"Comunicado: {obj.title}", obj.body[:180], f"/comunicados/{obj.pk}/",
                       level="critical" if obj.priority == "critical" else ("high" if obj.priority == "high" else "info"))
            messages.success(request, f"Comunicado publicado y notificado a {n} usuarios (notificación interna).")
        else:
            messages.success(request, "Comunicado actualizado.")
        return redirect("comms:detail", ann_id=obj.pk)
    return render(request, "comms/form.html", {"form": form, "ann": ann})


@require_POST
@require_cap("comms.publish")
def announcement_unpublish(request, ann_id):
    ann = get_object_or_404(Announcement, pk=ann_id)
    if ann.author_id != request.user.pk and not request.user.is_superuser:
        raise PermissionDenied("Solo el autor o un administrador pueden retirar este comunicado.")
    ann.published = False
    ann.save(update_fields=["published"])
    audit(request.user, "announcement.unpublished", ann, f"Retiró comunicado: {ann.title}")
    messages.success(request, "Comunicado retirado (se conserva en el historial).")
    return redirect("comms:list")


# ---------------------------------------------------------------- comments (generic)
def _target_access(user, target):
    from apps.comms.models import Announcement as Ann

    if isinstance(target, Ann):
        return can_see_announcement(user, target)
    area_id = getattr(target, "area_id", None)
    if area_id is not None and not can_access_area(user, area_id):
        return False
    owner_check = getattr(target, "user_can_view", None)
    if callable(owner_check):
        return owner_check(user)
    return True


@require_POST
@require_cap("comms.comment")
def comment_post(request):
    try:
        ct = ContentType.objects.get_for_id(int(request.POST.get("ct")))
        target = ct.get_object_for_this_type(pk=request.POST.get("obj"))
    except Exception:
        raise Http404("Elemento no encontrado")
    if not _target_access(request.user, target):
        raise PermissionDenied("No tiene acceso a este elemento.")
    body = request.POST.get("body", "").strip()
    nxt = request.POST.get("next") or "/"
    if not nxt.startswith("/") or nxt.startswith("//"):
        nxt = "/"
    if not body:
        messages.error(request, "Escriba el comentario.")
        return redirect(nxt)
    parent = None
    if request.POST.get("parent"):
        parent = get_object_or_404(Comment, pk=request.POST["parent"], content_type=ct, object_id=str(target.pk))
    kind = request.POST.get("kind", "comment")
    if kind not in Comment.Kind.values:
        kind = "comment"
    try:
        with transaction.atomic():
            c = Comment.objects.create(content_type=ct, object_id=str(target.pk), parent=parent, author=request.user,
                                       body=body[:5000], kind=kind if parent is None else "comment")
            for up in request.FILES.getlist("attachments"):
                c.attachments.add(store_upload(up, request.user))
    except UserFacingError as exc:
        messages.error(request, str(exc))
        return redirect(nxt)
    audit(request.user, "comment.created", c, f"{c.get_kind_display()} en {ct.model} {target.pk}: {body[:80]}")
    # notify thread participants and target owner/author
    participants = {x.author for x in Comment.objects.filter(content_type=ct, object_id=str(target.pk)).select_related("author")}
    for attr in ("author", "created_by", "owner", "responsible_user"):
        u = getattr(target, attr, None)
        if u is not None and hasattr(u, "pk"):
            participants.add(u)
    participants.discard(request.user)
    label = {"question": "Nueva duda", "incident": "Nueva incidencia"}.get(c.kind, "Nuevo comentario")
    notify([u for u in participants if _target_access(u, target)], f"{label}: {str(target)[:80]}", body[:180], nxt + "#c" + str(c.pk),
           level="high" if c.kind == "incident" else "info")
    messages.success(request, "Comentario publicado.")
    return redirect(nxt + "#c" + str(c.pk))


@require_POST
@require_cap("comms.resolve")
def comment_resolve(request, comment_id):
    c = get_object_or_404(Comment, pk=comment_id)
    if not _target_access(request.user, c.target):
        raise PermissionDenied("No tiene acceso a este elemento.")
    c.resolved = True
    c.resolved_by = request.user
    c.resolved_at = timezone.now()
    c.save()
    audit(request.user, "comment.resolved", c, f"Resuelta: {c.body[:80]}")
    notify([c.author], "Su incidencia/duda fue marcada como resuelta", c.body[:180], request.POST.get("next", "/"))
    nxt = request.POST.get("next") or "/"
    return redirect(nxt if nxt.startswith("/") and not nxt.startswith("//") else "/")


# ---------------------------------------------------------------- conversations
@login_required
def conversation_list(request):
    convs = Conversation.objects.filter(participants=request.user).prefetch_related("participants")
    marks = {m.conversation_id: m.last_read for m in ConversationRead.objects.filter(user=request.user)}
    items = [(c, marks.get(c.pk) is None or c.updated > marks[c.pk]) for c in convs]
    form = ConversationForm()
    return render(request, "comms/conversations.html", {"items": items, "form": form})


@require_POST
@require_cap("comms.comment")
def conversation_create(request):
    form = ConversationForm(request.POST)
    if not form.is_valid():
        messages.error(request, "Indique asunto, participantes y mensaje.")
        return redirect("comms:conversations")
    with transaction.atomic():
        conv = Conversation.objects.create(subject=form.cleaned_data["subject"], created_by=request.user)
        conv.participants.set(list(form.cleaned_data["participants"]) + [request.user])
        Message.objects.create(conversation=conv, author=request.user, body=form.cleaned_data["body"])
        ConversationRead.objects.create(conversation=conv, user=request.user)
    notify([u for u in form.cleaned_data["participants"] if u != request.user], f"Conversación: {conv.subject}",
           form.cleaned_data["body"][:180], f"/comunicados/conversaciones/{conv.pk}/")
    return redirect("comms:conversation", conv_id=conv.pk)


@login_required
def conversation_detail(request, conv_id):
    conv = get_object_or_404(Conversation, pk=conv_id)
    if not conv.participants.filter(pk=request.user.pk).exists():
        raise Http404()
    if request.method == "POST":
        body = request.POST.get("body", "").strip()
        if body:
            Message.objects.create(conversation=conv, author=request.user, body=body[:5000])
            conv.updated = timezone.now()
            conv.save(update_fields=["updated"])
            notify([u for u in conv.participants.all() if u != request.user], f"Mensaje en: {conv.subject}", body[:180],
                   f"/comunicados/conversaciones/{conv.pk}/")
        return redirect("comms:conversation", conv_id=conv.pk)
    ConversationRead.objects.update_or_create(conversation=conv, user=request.user, defaults={"last_read": timezone.now()})
    return render(request, "comms/conversation.html", {"conv": conv, "msgs": conv.messages.select_related("author")})


def all_users():
    return get_user_model().objects.filter(is_active=True)
