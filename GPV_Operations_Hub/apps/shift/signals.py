from django.contrib.auth.signals import user_logged_in
from django.dispatch import receiver

from apps.core.permissions import can_access_area, register_file_access_hook


@register_file_access_hook
def shift_files(user, stored_file):
    """Private files attached to shift objects are visible to users of the same area."""
    from .models import HelpRequest, QualityObservation, ShiftReport

    for model, field in ((HelpRequest, "photo"), (QualityObservation, "evidence"), (ShiftReport, "pdf")):
        obj = model.objects.filter(**{field: stored_file}).select_related("line").first()
        if obj and can_access_area(user, obj.line.area_id):
            return True
    return False


@receiver(user_logged_in)
def mark_login(sender, request, user, **kwargs):
    """The first page after signing in sends pilot operators to «Mi turno» (once; «Inicio» keeps working)."""
    if request is not None and hasattr(request, "session"):
        request.session["gpv_after_login"] = True
