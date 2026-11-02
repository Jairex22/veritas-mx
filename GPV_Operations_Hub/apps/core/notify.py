from django.contrib.auth import get_user_model

from .models import Notification


def notify(users, title, body="", url="", level="info"):
    """Create internal notifications (never e-mail or external messages)."""
    objs = []
    seen = set()
    for user in users:
        if user is None or user.pk in seen or not user.is_active:
            continue
        seen.add(user.pk)
        objs.append(Notification(user=user, title=title[:200], body=body, url=url[:300], level=level))
    Notification.objects.bulk_create(objs)
    return len(objs)


def users_for_scope(area_ids=None, roles=None, shift_ids=None, group_ids=None):
    """Active users matching the announcement/notification audience."""
    User = get_user_model()
    qs = User.objects.filter(is_active=True).select_related("profile")
    if roles:
        qs = qs.filter(profile__role__in=roles)
    if shift_ids:
        qs = qs.filter(profile__shift_id__in=shift_ids)
    if group_ids:
        qs = qs.filter(groups__id__in=group_ids)
    if area_ids:
        from django.db.models import Q

        qs = qs.filter(Q(profile__areas__id__in=area_ids) | Q(profile__all_areas=True) | Q(is_superuser=True) | Q(profile__role="admin"))
    return qs.distinct()
