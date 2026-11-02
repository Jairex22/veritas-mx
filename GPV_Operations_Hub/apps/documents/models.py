from django.conf import settings
from django.db import models
from django.utils import timezone

from apps.core.models import Area, StoredFile


class Folder(models.Model):
    name = models.CharField("nombre", max_length=120)
    parent = models.ForeignKey("self", null=True, blank=True, on_delete=models.CASCADE, related_name="children")
    area = models.ForeignKey(Area, null=True, blank=True, on_delete=models.SET_NULL)
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    created = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class Document(models.Model):
    """A file in the document center. Transformations never modify ``file``: they create new Documents."""

    file = models.OneToOneField(StoredFile, on_delete=models.PROTECT, related_name="document")
    title = models.CharField(max_length=255)
    folder = models.ForeignKey(Folder, null=True, blank=True, on_delete=models.SET_NULL, related_name="documents")
    tags = models.CharField("etiquetas", max_length=300, blank=True)
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    area = models.ForeignKey(Area, null=True, blank=True, on_delete=models.SET_NULL)
    created = models.DateTimeField(default=timezone.now)
    derived_from = models.ForeignKey("self", null=True, blank=True, on_delete=models.SET_NULL, related_name="derivatives")
    operation = models.CharField(max_length=80, blank=True)
    operation_params = models.JSONField(default=dict, blank=True)
    info = models.JSONField(default=dict, blank=True)  # page count, slides, sheets, warnings...
    deleted = models.BooleanField(default=False)

    class Meta:
        ordering = ["-created"]

    def __str__(self):
        return self.title

    @property
    def ext(self):
        return self.file.ext

    def user_can_view(self, user):
        from apps.core.permissions import can_access_file

        return can_access_file(user, self.file)
