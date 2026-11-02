from django.contrib.contenttypes.models import ContentType
from django.db.models import Q
from django.utils import timezone

from apps.core.models import Role
from apps.core.permissions import allowed_area_ids, has_cap, register_file_access_hook

from .models import Announcement, Comment


def visible_announcements(user, include_expired=False):
    """Announcements whose audience includes the user (server-side audience check)."""
    qs = Announcement.objects.filter(published=True)
    if not include_expired:
        now = timezone.now()
        qs = qs.filter(valid_from__lte=now).filter(Q(valid_until__isnull=True) | Q(valid_until__gt=now))
    if user.is_superuser or has_cap(user, "comms.publish") and getattr(user.profile, "role", "") == Role.ADMIN:
        return qs.distinct()
    profile = user.profile
    area_ids = allowed_area_ids(user)
    area_cond = Q(areas__isnull=True)
    if area_ids is None:
        area_cond = Q()
    else:
        area_cond |= Q(areas__in=area_ids)
    shift_cond = Q(shifts__isnull=True) | (Q(shifts=profile.shift_id) if profile.shift_id else Q(pk__in=[]))
    group_ids = list(user.groups.values_list("id", flat=True))
    group_cond = Q(groups__isnull=True) | Q(groups__in=group_ids)
    qs = qs.filter(area_cond).filter(shift_cond).filter(group_cond).distinct()
    ids = [a.pk for a in qs if not a.roles or profile.role in a.roles or a.author_id == user.pk]
    return Announcement.objects.filter(pk__in=ids)


def can_see_announcement(user, ann):
    if ann.author_id == user.pk or user.is_superuser:
        return True
    return visible_announcements(user, include_expired=True).filter(pk=ann.pk).exists()


def thread_context(request, obj):
    ct = ContentType.objects.get_for_model(obj)
    comments = (Comment.objects.filter(content_type=ct, object_id=str(obj.pk), parent__isnull=True)
                .select_related("author").prefetch_related("replies__author", "attachments"))
    return {"thread_comments": comments, "thread_ct": ct.pk, "thread_obj": obj.pk,
            "can_comment": has_cap(request.user, "comms.comment"), "can_resolve": has_cap(request.user, "comms.resolve")}


@register_file_access_hook
def announcement_files(user, stored_file):
    anns = stored_file.announcement_set.all()
    return any(can_see_announcement(user, a) for a in anns)


@register_file_access_hook
def comment_files(user, stored_file):
    from apps.core.permissions import can_access_area

    for c in stored_file.comment_set.select_related("content_type"):
        target = c.target
        if isinstance(target, Announcement):
            if can_see_announcement(user, target):
                return True
            continue
        area_id = getattr(target, "area_id", None)
        if area_id is None or can_access_area(user, area_id):
            return True
    return False


def target_url(comment):
    """Link to the object a comment belongs to."""
    model = comment.content_type.model
    prefix = {"workorder": "/produccion/ordenes/", "announcement": "/comunicados/", "improvement": "/kaizen/"}.get(model)
    return f"{prefix}{comment.object_id}/#c{comment.pk}" if prefix else "/"


def target_area_id(comment):
    target = comment.target
    return getattr(target, "area_id", None)


def resolvers_for(area_id):
    """Active users allowed to resolve incidents in an area (server-side capability check)."""
    from apps.core.notify import users_for_scope

    users = users_for_scope(area_ids=[area_id] if area_id else None)
    return [u for u in users if has_cap(u, "comms.resolve")]


def open_incidents(user, include_resolved=False):
    """Incidents and questions the user may see (area-scoped)."""
    from apps.core.permissions import can_access_area

    qs = Comment.objects.filter(parent__isnull=True, kind__in=["incident", "question"]).select_related("author", "content_type", "resolved_by")
    if not include_resolved:
        qs = qs.filter(resolved=False)
    out = []
    for c in qs.order_by("-created")[:500]:
        target = c.target
        if target is None:
            continue
        if isinstance(target, Announcement):
            if not can_see_announcement(user, target):
                continue
        else:
            area_id = getattr(target, "area_id", None)
            if area_id is not None and not can_access_area(user, area_id):
                continue
        c.url = target_url(c)
        c.target_label = str(target)
        out.append(c)
    return out
