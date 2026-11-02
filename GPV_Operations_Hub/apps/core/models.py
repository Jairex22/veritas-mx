"""Core domain: areas, shifts, profiles/roles, capabilities, private files, audit,
notifications and the persistent job queue."""
import hashlib
import uuid
from pathlib import Path

from django.conf import settings
from django.db import models
from django.utils import timezone


class Area(models.Model):
    code = models.CharField("código", max_length=20, unique=True)
    name = models.CharField("nombre", max_length=100)
    active = models.BooleanField("activa", default=True)

    class Meta:
        ordering = ["code"]
        verbose_name = "área"

    def __str__(self):
        return f"{self.code} · {self.name}"


class Shift(models.Model):
    code = models.CharField("código", max_length=10, unique=True)
    name = models.CharField("nombre", max_length=60)
    start = models.TimeField("inicio")
    end = models.TimeField("fin")
    active = models.BooleanField(default=True)

    class Meta:
        ordering = ["start"]
        verbose_name = "turno"

    def __str__(self):
        return f"{self.code} ({self.start:%H:%M}-{self.end:%H:%M})"


class Role(models.TextChoices):
    ADMIN = "admin", "Administrador"
    SUPERVISOR = "supervisor", "Jefe / Supervisor"
    ENGINEER = "engineer", "Ingeniero / Analista"
    OPERATOR = "operator", "Operador / Lector"


class Profile(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="profile")
    role = models.CharField("rol", max_length=20, choices=Role.choices, default=Role.OPERATOR)
    areas = models.ManyToManyField(Area, blank=True, verbose_name="áreas")
    all_areas = models.BooleanField("todas las áreas", default=False)
    shift = models.ForeignKey(Shift, null=True, blank=True, on_delete=models.SET_NULL, verbose_name="turno")
    must_change_password = models.BooleanField(default=False)
    employee_number = models.CharField("número de empleado", max_length=40, blank=True)

    def __str__(self):
        return f"{self.user.username} ({self.get_role_display()})"


class RoleCapability(models.Model):
    """Configurable permission matrix (role x capability)."""

    role = models.CharField(max_length=20, choices=Role.choices)
    capability = models.CharField(max_length=60)
    allowed = models.BooleanField(default=False)

    class Meta:
        unique_together = [("role", "capability")]
        ordering = ["capability", "role"]


class SiteSetting(models.Model):
    key = models.CharField(max_length=80, primary_key=True)
    value = models.TextField(blank=True)

    @classmethod
    def get(cls, key, default=""):
        obj = cls.objects.filter(key=key).first()
        return obj.value if obj else default

    @classmethod
    def put(cls, key, value):
        cls.objects.update_or_create(key=key, defaults={"value": value})


def _storage_path(file_id, original_name):
    ext = Path(original_name).suffix.lower()[:12]
    now = timezone.now()
    return f"{now:%Y/%m}/{file_id.hex}{ext}"


class StoredFile(models.Model):
    """A file kept in the private storage (never served as a static resource)."""

    class Visibility(models.TextChoices):
        PRIVATE = "private", "Solo propietario"
        AREA = "area", "Usuarios del área"
        ALL = "all", "Todos los usuarios internos"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    relpath = models.CharField(max_length=255, unique=True)
    original_name = models.CharField(max_length=255)
    size = models.BigIntegerField(default=0)
    sha256 = models.CharField(max_length=64, db_index=True)
    mime = models.CharField(max_length=120, blank=True)
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="files")
    area = models.ForeignKey(Area, null=True, blank=True, on_delete=models.SET_NULL)
    visibility = models.CharField(max_length=10, choices=Visibility.choices, default=Visibility.PRIVATE)
    source = models.CharField(max_length=20, default="upload")  # upload | generated | import
    parent = models.ForeignKey("self", null=True, blank=True, on_delete=models.SET_NULL, related_name="derived")
    created = models.DateTimeField(default=timezone.now)
    meta = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ["-created"]

    def __str__(self):
        return self.original_name

    @property
    def path(self) -> Path:
        return Path(settings.PRIVATE_MEDIA_ROOT) / self.relpath

    @property
    def ext(self):
        return Path(self.original_name).suffix.lower().lstrip(".")

    @classmethod
    def create_from_bytes(cls, data: bytes, name: str, owner=None, **kwargs):
        file_id = uuid.uuid4()
        relpath = _storage_path(file_id, name)
        full = Path(settings.PRIVATE_MEDIA_ROOT) / relpath
        full.parent.mkdir(parents=True, exist_ok=True)
        full.write_bytes(data)
        return cls.objects.create(
            id=file_id,
            relpath=relpath,
            original_name=name,
            size=len(data),
            sha256=hashlib.sha256(data).hexdigest(),
            owner=owner,
            **kwargs,
        )

    @classmethod
    def create_from_path(cls, src: Path, name: str, owner=None, **kwargs):
        return cls.create_from_bytes(Path(src).read_bytes(), name, owner=owner, **kwargs)


class AuditLog(models.Model):
    ts = models.DateTimeField(default=timezone.now, db_index=True)
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)
    action = models.CharField(max_length=80)
    object_type = models.CharField(max_length=60, blank=True)
    object_id = models.CharField(max_length=64, blank=True)
    area = models.ForeignKey(Area, null=True, blank=True, on_delete=models.SET_NULL)
    summary = models.CharField(max_length=300, blank=True)
    changes = models.JSONField(default=dict, blank=True)
    op_id = models.CharField(max_length=40, blank=True)

    class Meta:
        ordering = ["-ts"]


class Notification(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="notifications")
    title = models.CharField(max_length=200)
    body = models.TextField(blank=True)
    url = models.CharField(max_length=300, blank=True)
    level = models.CharField(max_length=10, default="info")  # info | high | critical
    created = models.DateTimeField(default=timezone.now, db_index=True)
    read_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created"]


class Job(models.Model):
    """Persistent background job. Executed by ``manage.py run_worker`` (or inline in demo mode)."""

    class Status(models.TextChoices):
        QUEUED = "queued", "En cola"
        RUNNING = "running", "En proceso"
        SUCCEEDED = "succeeded", "Terminado"
        FAILED = "failed", "Fallido"
        CANCELLED = "cancelled", "Cancelado"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    kind = models.CharField(max_length=60, db_index=True)
    params = models.JSONField(default=dict, blank=True)
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.QUEUED, db_index=True)
    progress = models.PositiveSmallIntegerField(default=0)
    message = models.CharField(max_length=300, blank=True)
    result = models.JSONField(default=dict, blank=True)
    error = models.TextField(blank=True)  # user friendly message
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)
    created = models.DateTimeField(default=timezone.now)
    started = models.DateTimeField(null=True, blank=True)
    finished = models.DateTimeField(null=True, blank=True)
    heartbeat = models.DateTimeField(null=True, blank=True)
    attempts = models.PositiveSmallIntegerField(default=0)
    locked_by = models.CharField(max_length=80, blank=True)
    cancel_requested = models.BooleanField(default=False)
    idempotency_key = models.CharField(max_length=120, null=True, blank=True, unique=True)

    class Meta:
        ordering = ["-created"]

    @property
    def is_final(self):
        return self.status in (self.Status.SUCCEEDED, self.Status.FAILED, self.Status.CANCELLED)


class SchedulerLease(models.Model):
    """Single-holder lease so only one scheduler process is active."""

    name = models.CharField(max_length=40, primary_key=True)
    holder = models.CharField(max_length=80, blank=True)
    expires_at = models.DateTimeField(null=True, blank=True)
