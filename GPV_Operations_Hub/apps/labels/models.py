import uuid

from django.conf import settings
from django.db import models
from django.utils import timezone

from apps.core.models import Area, StoredFile


class LabelTemplate(models.Model):
    name = models.CharField("nombre", max_length=120)
    code = models.SlugField("código", max_length=60, unique=True)
    description = models.CharField("descripción", max_length=300, blank=True)
    area = models.ForeignKey(Area, null=True, blank=True, on_delete=models.SET_NULL)
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")
    draft = models.JSONField(default=dict)
    draft_revision = models.PositiveIntegerField(default=1)
    draft_updated = models.DateTimeField(default=timezone.now)
    draft_updated_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+")
    published = models.ForeignKey("LabelTemplateVersion", null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    created = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class LabelTemplateVersion(models.Model):
    template = models.ForeignKey(LabelTemplate, on_delete=models.CASCADE, related_name="versions")
    version = models.PositiveIntegerField()
    definition = models.JSONField()
    published_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")
    published_at = models.DateTimeField(default=timezone.now)
    notes = models.CharField(max_length=300, blank=True)

    class Meta:
        ordering = ["-version"]
        unique_together = [("template", "version")]

    def __str__(self):
        return f"{self.template.name} v{self.version}"


class Printer(models.Model):
    class Kind(models.TextChoices):
        BROWSER = "browser", "Navegador / PDF (diálogo de impresión del usuario)"
        ZPL_TCP = "zpl_tcp", "Zebra compatible ZPL por red (TCP, registrada)"
        WINDOWS_QUEUE = "windows_queue", "Cola de Windows del servidor (RAW)"
        CUPS_QUEUE = "cups_queue", "Cola CUPS del servidor (RAW, Linux)"

    class Language(models.TextChoices):
        ZPL = "zpl", "ZPL II (solo impresoras que lo soporten)"
        PDF = "pdf", "PDF a escala física"

    name = models.CharField("nombre", max_length=120, unique=True)
    kind = models.CharField("tipo", max_length=20, choices=Kind.choices, default=Kind.BROWSER)
    language = models.CharField("lenguaje", max_length=10, choices=Language.choices, default=Language.PDF)
    host = models.CharField("host/IP (registrado por administrador)", max_length=120, blank=True)
    port = models.PositiveIntegerField("puerto", null=True, blank=True)
    queue_name = models.CharField("nombre de cola", max_length=200, blank=True)
    dpi = models.PositiveIntegerField("resolución real (DPI)", null=True, blank=True,
                                      help_text="Tomada de la ficha técnica/configuración de la impresora; no se infiere del nombre.")
    model_notes = models.CharField("modelo / notas", max_length=200, blank=True)
    area = models.ForeignKey(Area, null=True, blank=True, on_delete=models.SET_NULL)
    enabled = models.BooleanField("habilitada para envío directo", default=False)
    validated_at = models.DateTimeField(null=True, blank=True)
    last_test = models.CharField(max_length=300, blank=True)
    darkness = models.PositiveSmallIntegerField("oscuridad ZPL (~SD, opcional)", null=True, blank=True)
    speed = models.PositiveSmallIntegerField("velocidad ZPL (^PR, opcional)", null=True, blank=True)
    created = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name

    @property
    def is_direct(self):
        return self.kind != self.Kind.BROWSER


class SerialCounter(models.Model):
    name = models.SlugField("nombre", max_length=60, unique=True)
    prefix = models.CharField("prefijo", max_length=30, blank=True)
    pad = models.PositiveSmallIntegerField("dígitos", default=6)
    next_value = models.PositiveBigIntegerField("siguiente valor", default=1)
    updated = models.DateTimeField(default=timezone.now)

    def __str__(self):
        return self.name


class PrintJob(models.Model):
    class Status(models.TextChoices):
        GENERATED = "generated", "Generado"
        SENT = "sent", "Enviado"
        QUEUED = "queued", "Aceptado por la cola"
        UNKNOWN = "unknown", "Estado físico desconocido"
        CONFIRMED = "confirmed", "Confirmado"
        FAILED = "failed", "Fallido"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    number = models.PositiveIntegerField(unique=True, null=True, blank=True)
    template_version = models.ForeignKey(LabelTemplateVersion, on_delete=models.PROTECT, related_name="jobs")
    printer = models.ForeignKey(Printer, null=True, blank=True, on_delete=models.PROTECT)
    route = models.CharField(max_length=10, default="browser")  # browser | direct
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.GENERATED)
    records_count = models.PositiveIntegerField(default=0)
    copies = models.PositiveIntegerField(default=1)
    total_labels = models.PositiveIntegerField(default=0)
    data = models.JSONField(default=list, blank=True)  # resolved field values per label (no binary data)
    serials = models.JSONField(default=list, blank=True)
    source = models.CharField(max_length=200, blank=True)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")
    created = models.DateTimeField(default=timezone.now)
    sent_at = models.DateTimeField(null=True, blank=True)
    idempotency_key = models.CharField(max_length=120, unique=True)
    reprint_of = models.ForeignKey("self", null=True, blank=True, on_delete=models.PROTECT, related_name="reprints")
    reprint_reason = models.CharField(max_length=300, blank=True)
    error = models.TextField(blank=True)
    output_pdf = models.ForeignKey(StoredFile, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    output_zpl = models.ForeignKey(StoredFile, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    queue_reference = models.CharField(max_length=120, blank=True)
    evidence = models.TextField(blank=True)
    confirmed_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    confirmed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created"]


class PrintEvent(models.Model):
    job = models.ForeignKey(PrintJob, on_delete=models.CASCADE, related_name="events")
    ts = models.DateTimeField(default=timezone.now)
    status = models.CharField(max_length=10)
    detail = models.CharField(max_length=500)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)

    class Meta:
        ordering = ["ts"]
