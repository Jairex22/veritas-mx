from django.conf import settings
from django.db import models
from django.utils import timezone

from apps.core.models import Area, Shift, StoredFile


class ReportKind(models.TextChoices):
    DAILY = "daily", "Reporte diario de producción"
    WEEKLY = "weekly", "Cumplimiento semanal"
    LATE = "late", "Órdenes atrasadas"
    QUALITY = "quality", "Calidad (rechazo / scrap / Pareto)"
    BY_LINE = "by_line", "Producción por línea"
    KAIZEN = "kaizen", "Seguimiento Kaizen"


FORMATS = [("pdf", "PDF"), ("xlsx", "Excel XLSX"), ("csv", "CSV (tabla principal)"), ("docx", "Word DOCX (resumen)"), ("pptx", "PowerPoint PPTX (resumen)")]


class Dashboard(models.Model):
    name = models.CharField("nombre", max_length=120)
    description = models.CharField("descripción", max_length=300, blank=True)
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="dashboards")
    config = models.JSONField(default=dict, blank=True)  # {"widgets": [...]}
    shared_areas = models.ManyToManyField(Area, blank=True)
    shared_roles = models.JSONField(default=list, blank=True)
    shared_all = models.BooleanField("compartido con todos", default=False)
    created = models.DateTimeField(default=timezone.now)
    updated = models.DateTimeField(default=timezone.now)
    version = models.PositiveIntegerField(default=1)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name

    def user_can_view(self, user):
        if user.is_superuser or self.owner_id == user.pk or self.shared_all:
            return True
        role = getattr(getattr(user, "profile", None), "role", "")
        if role and role in (self.shared_roles or []):
            return True
        from apps.core.permissions import allowed_area_ids

        ids = allowed_area_ids(user)
        shared = set(self.shared_areas.values_list("id", flat=True))
        return bool(shared) and (ids is None or bool(shared & ids))


class ReportSchedule(models.Model):
    class Frequency(models.TextChoices):
        DAILY = "daily", "Diario"
        WEEKLY = "weekly", "Semanal"
        SHIFT = "shift", "Por turno (al terminar el turno)"

    name = models.CharField("nombre", max_length=120)
    kind = models.CharField("plantilla", max_length=20, choices=ReportKind.choices)
    filters = models.JSONField(default=dict, blank=True)
    frequency = models.CharField("frecuencia", max_length=10, choices=Frequency.choices, default=Frequency.DAILY)
    time_of_day = models.TimeField("hora (America/Mexico_City)", null=True, blank=True)
    weekday = models.PositiveSmallIntegerField("día de la semana (0=lunes)", null=True, blank=True)
    shift = models.ForeignKey(Shift, null=True, blank=True, on_delete=models.SET_NULL)
    formats = models.JSONField(default=list)
    recipients = models.ManyToManyField(settings.AUTH_USER_MODEL, blank=True, related_name="report_subscriptions")
    active = models.BooleanField(default=True)
    next_run_at = models.DateTimeField(null=True, blank=True, db_index=True)
    last_run = models.ForeignKey("ReportRun", null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")
    created = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class ReportRun(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "Pendiente"
        RUNNING = "running", "Generando"
        DONE = "done", "Generado"
        FAILED = "failed", "Fallido"

    kind = models.CharField(max_length=20, choices=ReportKind.choices)
    title = models.CharField(max_length=200)
    params = models.JSONField(default=dict, blank=True)
    notes = models.TextField("notas", blank=True)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PENDING)
    snapshot = models.JSONField(default=dict, blank=True)
    data_version = models.CharField(max_length=120, blank=True)
    formats = models.JSONField(default=list, blank=True)
    author = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)
    created = models.DateTimeField(default=timezone.now)
    finished = models.DateTimeField(null=True, blank=True)
    error = models.TextField(blank=True)
    schedule = models.ForeignKey(ReportSchedule, null=True, blank=True, on_delete=models.SET_NULL, related_name="runs")
    scheduled_for = models.DateTimeField(null=True, blank=True)
    attempts = models.PositiveSmallIntegerField(default=0)
    version = models.PositiveIntegerField(default=1)

    class Meta:
        ordering = ["-created"]
        constraints = [
            models.UniqueConstraint(fields=["schedule", "scheduled_for"], name="uniq_schedule_occurrence"),
        ]

    def __str__(self):
        return self.title

    def user_can_view(self, user):
        if user.is_superuser or self.author_id == user.pk:
            return True
        if self.schedule_id and self.schedule.recipients.filter(pk=user.pk).exists():
            return True
        from apps.core.permissions import allowed_area_ids, has_cap

        if not has_cap(user, "dashboard.view"):
            return False
        ids = allowed_area_ids(user)
        scope = self.params.get("_area_ids")  # None: generated with access to all areas
        if ids is None:
            return True
        return scope is not None and set(scope) <= ids


class ReportOutput(models.Model):
    run = models.ForeignKey(ReportRun, on_delete=models.CASCADE, related_name="outputs")
    fmt = models.CharField(max_length=10)
    file = models.ForeignKey(StoredFile, on_delete=models.PROTECT)

    class Meta:
        unique_together = [("run", "fmt")]
