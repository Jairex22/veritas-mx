from django.conf import settings
from django.db import models
from django.utils import timezone

from . import status as st


class FlxState(models.Model):
    """Singleton (pk=1) with the observed state of the FactoryLogix service. Never stores secrets."""

    last_status = models.CharField(max_length=30, default=st.NOT_TESTED)
    last_detail = models.CharField(max_length=500, blank=True)
    last_attempt_at = models.DateTimeField(null=True, blank=True)
    last_success_at = models.DateTimeField(null=True, blank=True)
    last_latency_ms = models.PositiveIntegerField(null=True, blank=True)
    auth_configured = models.CharField(max_length=20, blank=True)
    auth_schemes_offered = models.JSONField(default=list, blank=True)  # from WWW-Authenticate (anonymous request)
    auth_detected_at = models.DateTimeField(null=True, blank=True)
    auth_blocked_at = models.DateTimeField(null=True, blank=True,
                                           help_text="Tras un 401 no se reintenta automáticamente hasta que un administrador lo indique o cambie la configuración.")
    auth_fingerprint = models.CharField(max_length=20, blank=True)
    service_doc_sets = models.JSONField(default=list, blank=True)  # names listed by the service document
    updated = models.DateTimeField(default=timezone.now)

    @classmethod
    def get(cls):
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj


class FlxSchema(models.Model):
    class Source(models.TextChoices):
        LIVE = "live", "Leído del servidor"
        FILE = "file", "Cargado de archivo (sin verificar acceso)"

    fetched_at = models.DateTimeField(default=timezone.now)
    source = models.CharField(max_length=10, choices=Source.choices)
    base_url = models.CharField(max_length=300, blank=True)
    odata_version = models.CharField(max_length=10, blank=True)
    edmx_version = models.CharField(max_length=10, blank=True)
    sha256 = models.CharField(max_length=64)
    size = models.PositiveIntegerField(default=0)
    entity_set_count = models.PositiveIntegerField(default=0)
    function_imports = models.JSONField(default=list, blank=True)
    xml = models.TextField(help_text="Documento $metadata (estructura, sin datos de producción).")
    is_current = models.BooleanField(default=True)
    loaded_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)

    class Meta:
        ordering = ["-fetched_at"]

    def __str__(self):
        return f"$metadata {self.fetched_at:%Y-%m-%d %H:%M} ({self.get_source_display()})"


class FlxEntitySet(models.Model):
    schema = models.ForeignKey(FlxSchema, on_delete=models.CASCADE, related_name="entity_sets")
    name = models.CharField(max_length=200)
    entity_type = models.CharField(max_length=300, blank=True)
    category = models.CharField(max_length=60, blank=True)
    keys = models.JSONField(default=list, blank=True)
    properties = models.JSONField(default=dict, blank=True)
    navigation = models.JSONField(default=dict, blank=True)
    declared_capabilities = models.JSONField(default=dict, blank=True)
    # results of controlled probes
    status = models.CharField(max_length=30, default=st.NOT_TESTED)
    http_status = models.PositiveSmallIntegerField(null=True, blank=True)
    latency_ms = models.PositiveIntegerField(null=True, blank=True)
    checked_at = models.DateTimeField(null=True, blank=True)
    detail = models.CharField(max_length=500, blank=True)
    returned_properties = models.JSONField(default=list, blank=True)  # property NAMES seen in a response (no values)
    capabilities = models.JSONField(default=dict, blank=True)  # {"$top": true, "$select": false, ...} verified by tests
    capabilities_checked_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["category", "name"]
        unique_together = [("schema", "name")]

    def __str__(self):
        return self.name

    @property
    def queryable(self):
        return self.status in st.OK_STATES and self.schema.source == FlxSchema.Source.LIVE


class FlxRun(models.Model):
    """Audit of each diagnostic / discovery / probe run (who, when, what, outcome)."""

    kind = models.CharField(max_length=30)  # connection | schema | probe | capabilities | schema_file
    started = models.DateTimeField(default=timezone.now)
    finished = models.DateTimeField(null=True, blank=True)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)
    via = models.CharField(max_length=10, default="web")  # web | cli
    outcome = models.CharField(max_length=30, blank=True)
    summary = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ["-started"]
