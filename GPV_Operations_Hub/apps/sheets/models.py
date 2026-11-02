from django.conf import settings
from django.db import models
from django.utils import timezone

from apps.core.models import Area, StoredFile


class Workbook(models.Model):
    """Browser spreadsheet. ``data`` holds sheets in the GPV sheet JSON format (see sheets/engine.py)."""

    name = models.CharField("nombre", max_length=150)
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="workbooks")
    area = models.ForeignKey(Area, null=True, blank=True, on_delete=models.SET_NULL)
    shared = models.BooleanField("compartida con el área", default=False)
    data = models.JSONField(default=dict)
    version = models.PositiveIntegerField(default=1)
    updated = models.DateTimeField(default=timezone.now)
    updated_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+")
    created = models.DateTimeField(default=timezone.now)
    source_file = models.ForeignKey(StoredFile, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    dataset = models.ForeignKey("production.Dataset", null=True, blank=True, on_delete=models.SET_NULL,
                                help_text="Dataset al que se pueden publicar los cambios (con validación).")
    import_warnings = models.JSONField(default=list, blank=True)

    class Meta:
        ordering = ["-updated"]

    def __str__(self):
        return self.name

    def user_can_view(self, user):
        from apps.core.permissions import can_access_area

        if user.is_superuser or self.owner_id == user.pk:
            return True
        return self.shared and self.area_id is not None and can_access_area(user, self.area_id)

    def user_can_edit(self, user):
        from apps.core.permissions import has_cap

        return self.user_can_view(user) and has_cap(user, "sheets.edit")


class WorkbookVersion(models.Model):
    workbook = models.ForeignKey(Workbook, on_delete=models.CASCADE, related_name="versions")
    version = models.PositiveIntegerField()
    data = models.JSONField()
    user = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL)
    ts = models.DateTimeField(default=timezone.now)
    summary = models.CharField(max_length=300, blank=True)
    changed_cells = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["-version"]
        unique_together = [("workbook", "version")]
