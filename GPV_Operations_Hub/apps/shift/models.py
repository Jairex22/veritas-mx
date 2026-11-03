"""Shift portal (SMT pilot): plant configuration, production events with origin and version,
manual-capture reconciliation, help requests, downtime, material requests, instructions,
checklists, handover, shift reports and the read-only OData connector state.

Instants are stored in UTC; shift calendars are evaluated in America/Mexico_City.
Identifiers (orders, serials, panels, parts) are always text.
"""
import uuid

from django.conf import settings
from django.contrib.auth.models import Group
from django.db import models
from django.db.models import Q
from django.utils import timezone

from apps.core.models import Area, Shift, StoredFile

SYNTHETIC_HELP = "Marque «sintético» en datos de ejemplo: nunca representan configuración real de GPV."


# ---------------------------------------------------------------- plant configuration
class Site(models.Model):
    code = models.CharField("código", max_length=20, unique=True)
    name = models.CharField("nombre", max_length=120)
    synthetic = models.BooleanField("dato sintético (ejemplo)", default=False, help_text=SYNTHETIC_HELP)

    def __str__(self):
        return self.name


class Line(models.Model):
    site = models.ForeignKey(Site, on_delete=models.PROTECT)
    area = models.ForeignKey(Area, on_delete=models.PROTECT)
    code = models.CharField("código", max_length=30, unique=True)
    name = models.CharField("nombre", max_length=120)
    active = models.BooleanField(default=True)
    pilot = models.BooleanField("línea del piloto", default=False)
    count_unit = models.CharField("unidad de conteo", max_length=20, default="pz")
    panel_factor = models.PositiveIntegerField("piezas por panel", null=True, blank=True)
    panel_factor_confirmed = models.BooleanField(
        "factor de panelización confirmado", default=False,
        help_text="Solo un factor confirmado por el responsable del proceso permite convertir paneles a piezas.")
    label_templates = models.ManyToManyField("labels.LabelTemplate", blank=True, verbose_name="plantillas de etiqueta del operador")
    synthetic = models.BooleanField("dato sintético (ejemplo)", default=False, help_text=SYNTHETIC_HELP)
    created = models.DateTimeField("alta", default=timezone.now, help_text="Los borradores automáticos solo cubren turnos posteriores al alta.")

    class Meta:
        ordering = ["code"]

    def __str__(self):
        return f"{self.code}{' (ejemplo)' if self.synthetic else ''}"


class Station(models.Model):
    class Side(models.TextChoices):
        NONE = "", "No aplica"
        TOP = "top", "Top"
        BOTTOM = "bottom", "Bottom"

    line = models.ForeignKey(Line, on_delete=models.PROTECT, related_name="stations")
    code = models.CharField("código", max_length=40)
    name = models.CharField("nombre", max_length=120)
    operation = models.CharField("operación", max_length=60, blank=True,
                                 help_text="Código de operación tal como llega de la fuente (FactoryLogix/OData).")
    side = models.CharField("lado", max_length=6, choices=Side.choices, blank=True, default="")
    sequence = models.PositiveSmallIntegerField("secuencia", default=10)
    is_count_point = models.BooleanField(
        "cuenta como producto terminado del área", default=False,
        help_text="Solo una estación por línea debería contar como salida del área. POR CONFIRMAR con el responsable.")
    qr_token = models.CharField(max_length=40, unique=True, default="", blank=True,
                                help_text="Identifica la estación al escanear su QR. No autentica ni da permisos.")
    active = models.BooleanField(default=True)
    synthetic = models.BooleanField("dato sintético (ejemplo)", default=False, help_text=SYNTHETIC_HELP)

    class Meta:
        ordering = ["line", "sequence", "code"]
        unique_together = [("line", "code")]

    def save(self, *args, **kwargs):
        if not self.qr_token:
            self.qr_token = uuid.uuid4().hex[:16]
        super().save(*args, **kwargs)

    def __str__(self):
        side = f" {self.get_side_display()}" if self.side else ""
        return f"{self.line.code} · {self.code}{side}"


class ShiftBreak(models.Model):
    shift = models.ForeignKey(Shift, on_delete=models.CASCADE, related_name="breaks")
    start = models.TimeField("inicio")
    end = models.TimeField("fin")
    label = models.CharField(max_length=60, blank=True)

    class Meta:
        ordering = ["shift", "start"]


class ShiftPlan(models.Model):
    """Target assigned to a shift for an order (the order total is NOT the shift target)."""

    line = models.ForeignKey(Line, on_delete=models.PROTECT)
    shift = models.ForeignKey(Shift, on_delete=models.PROTECT)
    date = models.DateField("fecha operativa del turno")
    work_order = models.CharField("orden", max_length=60)
    part_number = models.CharField(max_length=80, blank=True)
    target = models.DecimalField("meta del turno", max_digits=12, decimal_places=3)
    unit = models.CharField("unidad", max_length=20, default="pz")
    priority = models.PositiveSmallIntegerField(default=1)
    source = models.CharField("origen", max_length=20, default="manual")  # manual | odata | import
    set_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL)
    updated = models.DateTimeField(default=timezone.now)
    reason = models.CharField("motivo del último cambio", max_length=300, blank=True)

    class Meta:
        unique_together = [("line", "shift", "date", "work_order")]
        ordering = ["date", "shift", "priority"]


class UserContext(models.Model):
    """Station/order the user is working on. Changes are explicit and audited."""

    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="shift_context")
    station = models.ForeignKey(Station, null=True, blank=True, on_delete=models.SET_NULL)
    work_order = models.CharField(max_length=60, blank=True)
    confirmed_at = models.DateTimeField(null=True, blank=True)
    updated = models.DateTimeField(default=timezone.now)


class ContextChange(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    ts = models.DateTimeField(default=timezone.now)
    field = models.CharField(max_length=20)
    old = models.CharField(max_length=120, blank=True)
    new = models.CharField(max_length=120, blank=True)
    reason = models.CharField(max_length=200, blank=True)
    via = models.CharField(max_length=20, default="web")  # web | qr | scan


# ---------------------------------------------------------------- production events
class ProductionEvent(models.Model):
    """One production fact with its origin.

    * ``odata``: read from FactoryLogix OData (never written back).
    * ``manual``: contingency capture on the web; stays «pending reconciliation» until an
      authorized rule or reviewer links it to the confirmed OData fact (or rejects it).
    * ``kind``: ``incremental`` events add up; ``snapshot`` rows replace the previous value of
      their ``scope_key`` (cumulative counters must never be summed).
    """

    class Source(models.TextChoices):
        ODATA = "odata", "FactoryLogix (OData)"
        MANUAL = "manual", "Captura web"
        SYNTHETIC = "synthetic", "Fuente de ejemplo (sintética)"

    class Kind(models.TextChoices):
        INCREMENTAL = "incremental", "Incremental"
        SNAPSHOT = "snapshot", "Snapshot acumulado"

    class Recon(models.TextChoices):
        CONFIRMED = "confirmed", "Confirmado (fuente automática)"
        PENDING = "pending", "Manual pendiente de conciliación"
        REVIEW = "review", "Requiere revisión (coincidencia ambigua)"
        RECONCILED = "reconciled", "Conciliado con OData (no suma)"
        ACCEPTED = "accepted", "Manual aceptado sin equivalente automático"
        REJECTED = "rejected", "Rechazado"

    source = models.CharField(max_length=10, choices=Source.choices)
    connection = models.ForeignKey("ODataConnection", null=True, blank=True, on_delete=models.PROTECT)
    external_key = models.CharField("clave externa", max_length=300, blank=True)
    kind = models.CharField(max_length=12, choices=Kind.choices, default=Kind.INCREMENTAL)
    scope_key = models.CharField(max_length=300, blank=True, help_text="Alcance de un snapshot (p. ej. orden+operación).")
    line = models.ForeignKey(Line, null=True, blank=True, on_delete=models.PROTECT)
    station = models.ForeignKey(Station, null=True, blank=True, on_delete=models.PROTECT)
    operation = models.CharField(max_length=60, blank=True)
    side = models.CharField(max_length=6, blank=True)
    work_order = models.CharField(max_length=60, blank=True, db_index=True)
    part_number = models.CharField(max_length=80, blank=True)
    serial = models.CharField(max_length=80, blank=True, db_index=True)
    panel_id = models.CharField(max_length=80, blank=True)
    lot_ref = models.CharField("referencia del lote/panel/etiqueta", max_length=80, blank=True,
                               help_text="Identificador físico verificable; permite conciliar captura manual con OData.")
    qty = models.DecimalField(max_digits=12, decimal_places=3)
    unit = models.CharField(max_length=20, default="pz")
    result = models.CharField(max_length=20, blank=True)  # PASS | FAIL | ''
    attempt = models.PositiveIntegerField(null=True, blank=True)
    event_at = models.DateTimeField("instante del evento", db_index=True)
    period_end = models.DateTimeField(null=True, blank=True, help_text="Fin del periodo cubierto (capturas manuales).")
    received_at = models.DateTimeField("instante de recepción", default=timezone.now)
    source_modified_at = models.DateTimeField(null=True, blank=True)
    version = models.PositiveIntegerField(default=1)
    is_current = models.BooleanField(default=True)
    recon_status = models.CharField(max_length=12, choices=Recon.choices, default=Recon.CONFIRMED)
    reconciled_with = models.ForeignKey("self", null=True, blank=True, on_delete=models.SET_NULL, related_name="manual_matches")
    reason = models.CharField("motivo", max_length=300, blank=True)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)
    client_uuid = models.CharField(max_length=64, null=True, blank=True, unique=True)
    raw = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ["-event_at"]
        constraints = [
            models.UniqueConstraint(fields=["connection", "external_key"], condition=Q(is_current=True) & ~Q(external_key=""),
                                    name="uniq_current_external_event"),
        ]
        indexes = [models.Index(fields=["line", "event_at"]), models.Index(fields=["work_order", "operation"]),
                   models.Index(fields=["connection", "external_key"], name="shift_event_extkey_idx")]


class EventRevision(models.Model):
    event = models.ForeignKey(ProductionEvent, on_delete=models.CASCADE, related_name="revisions")
    ts = models.DateTimeField(default=timezone.now)
    action = models.CharField(max_length=30)
    before = models.JSONField(default=dict)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)
    note = models.CharField(max_length=300, blank=True)


# ---------------------------------------------------------------- help, downtime, materials, quality
class HelpReason(models.Model):
    code = models.SlugField(max_length=40, unique=True)
    label = models.CharField(max_length=80)
    group = models.ForeignKey(Group, null=True, blank=True, on_delete=models.SET_NULL,
                              help_text="Grupo interno que recibe la solicitud (regla de enrutamiento).")
    remind_minutes = models.PositiveIntegerField("recordatorio si no se recibe (min)", default=10)
    escalate_minutes = models.PositiveIntegerField("escalar si no se atiende (min)", default=30)
    escalate_group = models.ForeignKey(Group, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    requires_verification = models.BooleanField("requiere verificación", default=False)
    active = models.BooleanField(default=True)
    sequence = models.PositiveSmallIntegerField(default=10)

    class Meta:
        ordering = ["sequence", "label"]

    def __str__(self):
        return self.label


class HelpRequest(models.Model):
    class Status(models.TextChoices):
        REPORTED = "reported", "Reportado"
        RECEIVED = "received", "Recibido"
        IN_PROGRESS = "in_progress", "En atención"
        RESOLVED = "resolved", "Resuelto"
        VERIFIED = "verified", "Verificado"
        CANCELLED = "cancelled", "Cancelado"

    reason = models.ForeignKey(HelpReason, on_delete=models.PROTECT)
    line = models.ForeignKey(Line, on_delete=models.PROTECT)
    station = models.ForeignKey(Station, null=True, blank=True, on_delete=models.SET_NULL)
    work_order = models.CharField(max_length=60, blank=True)
    comment = models.TextField(blank=True)
    photo = models.ForeignKey(StoredFile, null=True, blank=True, on_delete=models.SET_NULL)
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.REPORTED)
    group = models.ForeignKey(Group, null=True, blank=True, on_delete=models.SET_NULL)
    assignee = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")
    created = models.DateTimeField(default=timezone.now)
    received_at = models.DateTimeField(null=True, blank=True)
    started_at = models.DateTimeField(null=True, blank=True)
    resolved_at = models.DateTimeField(null=True, blank=True)
    verified_at = models.DateTimeField(null=True, blank=True)
    resolution = models.TextField(blank=True)
    related_to = models.ForeignKey("self", null=True, blank=True, on_delete=models.SET_NULL, related_name="related")
    escalation_level = models.PositiveSmallIntegerField(default=0)
    last_reminder_at = models.DateTimeField(null=True, blank=True)
    kaizen = models.ForeignKey("kaizen.Improvement", null=True, blank=True, on_delete=models.SET_NULL)
    client_uuid = models.CharField(max_length=64, null=True, blank=True, unique=True)

    class Meta:
        ordering = ["-created"]

    @property
    def is_open(self):
        return self.status in (self.Status.REPORTED, self.Status.RECEIVED, self.Status.IN_PROGRESS)

    def __str__(self):
        return f"Ayuda #{self.pk} · {self.reason} · {self.line.code}"


class HelpEvent(models.Model):
    request = models.ForeignKey(HelpRequest, on_delete=models.CASCADE, related_name="events")
    ts = models.DateTimeField(default=timezone.now)
    status = models.CharField(max_length=12)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)
    note = models.CharField(max_length=500, blank=True)


class DowntimeReason(models.Model):
    code = models.SlugField(max_length=40, unique=True)
    label = models.CharField(max_length=80)
    active = models.BooleanField(default=True)

    def __str__(self):
        return self.label


class Downtime(models.Model):
    line = models.ForeignKey(Line, on_delete=models.PROTECT)
    station = models.ForeignKey(Station, null=True, blank=True, on_delete=models.SET_NULL)
    work_order = models.CharField(max_length=60, blank=True)
    reason = models.ForeignKey(DowntimeReason, null=True, blank=True, on_delete=models.PROTECT,
                               help_text="Puede quedar pendiente; el cierre de turno lo solicitará.")
    started_at = models.DateTimeField()
    ended_at = models.DateTimeField(null=True, blank=True)
    comment = models.CharField(max_length=300, blank=True)
    started_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")
    ended_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    corrected = models.BooleanField(default=False)
    history = models.JSONField(default=list, blank=True)
    help_request = models.ForeignKey(HelpRequest, null=True, blank=True, on_delete=models.SET_NULL)

    class Meta:
        ordering = ["-started_at"]

    def minutes(self, until=None):
        end = self.ended_at or until or timezone.now()
        return max(0, (end - self.started_at).total_seconds() / 60)


class MaterialRequest(models.Model):
    class Status(models.TextChoices):
        REQUESTED = "requested", "Solicitado"
        RECEIVED = "received", "Recibido por materiales"
        IN_PROGRESS = "in_progress", "En atención"
        DELIVERED = "delivered", "Entregado"
        CANCELLED = "cancelled", "Cancelado"

    line = models.ForeignKey(Line, on_delete=models.PROTECT)
    station = models.ForeignKey(Station, null=True, blank=True, on_delete=models.SET_NULL)
    work_order = models.CharField(max_length=60, blank=True)
    material = models.CharField("material / número de parte", max_length=120)
    qty = models.DecimalField(max_digits=12, decimal_places=3)
    unit = models.CharField(max_length=20, default="pz")
    reason = models.CharField("motivo", max_length=200)
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.REQUESTED)
    group = models.ForeignKey(Group, null=True, blank=True, on_delete=models.SET_NULL)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")
    created = models.DateTimeField(default=timezone.now)
    updated = models.DateTimeField(default=timezone.now)
    handled_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    note = models.CharField(max_length=300, blank=True)
    history = models.JSONField(default=list, blank=True)

    class Meta:
        ordering = ["-created"]


class QualityObservation(models.Model):
    class Status(models.TextChoices):
        OBSERVATION = "observation", "Observación"
        CONFIRMED = "confirmed", "Defecto confirmado"
        REWORK = "rework", "Disposición: retrabajo"
        SCRAP = "scrap", "Disposición: scrap"
        USE_AS_IS = "use_as_is", "Disposición: liberar"
        DISMISSED = "dismissed", "Descartada"

    line = models.ForeignKey(Line, on_delete=models.PROTECT)
    station = models.ForeignKey(Station, null=True, blank=True, on_delete=models.SET_NULL)
    work_order = models.CharField(max_length=60, blank=True)
    serial = models.CharField(max_length=80, blank=True)
    category = models.CharField(max_length=80)
    description = models.TextField()
    evidence = models.ForeignKey(StoredFile, null=True, blank=True, on_delete=models.SET_NULL)
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.OBSERVATION)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")
    created = models.DateTimeField(default=timezone.now)
    disposition_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    disposition_at = models.DateTimeField(null=True, blank=True)
    disposition_note = models.CharField(max_length=300, blank=True)
    official_reference = models.CharField("referencia en el sistema oficial", max_length=120, blank=True)

    class Meta:
        ordering = ["-created"]


# ---------------------------------------------------------------- instructions & checklists
class OperationInstruction(models.Model):
    class Status(models.TextChoices):
        APPROVED = "approved", "Vigente (aprobada)"
        OBSOLETE = "obsolete", "Obsoleta"

    line = models.ForeignKey(Line, null=True, blank=True, on_delete=models.CASCADE)
    operation = models.CharField(max_length=60, blank=True, help_text="Vacío = aplica a todas las operaciones de la línea.")
    part_number = models.CharField(max_length=80, blank=True, help_text="Vacío = cualquier parte.")
    title = models.CharField(max_length=160)
    revision = models.CharField(max_length=20)
    document = models.ForeignKey("documents.Document", null=True, blank=True, on_delete=models.SET_NULL)
    steps = models.JSONField(default=list, blank=True, help_text='Lista de pasos cortos: [{"text": "...", "image_file_id": ""}]')
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.APPROVED)
    published_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+")
    published_at = models.DateTimeField(default=timezone.now)
    superseded_by = models.ForeignKey("self", null=True, blank=True, on_delete=models.SET_NULL)

    class Meta:
        ordering = ["title", "-published_at"]


class InstructionRead(models.Model):
    """Records that a person opened an instruction. It does NOT certify training."""

    instruction = models.ForeignKey(OperationInstruction, on_delete=models.CASCADE)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    ts = models.DateTimeField(default=timezone.now)


class ChecklistTemplate(models.Model):
    class Kind(models.TextChoices):
        STARTUP = "startup", "Arranque"
        CHANGEOVER = "changeover", "Cambio de modelo"
        VERIFICATION = "verification", "Verificación de estación"

    name = models.CharField(max_length=120)
    kind = models.CharField(max_length=14, choices=Kind.choices)
    line = models.ForeignKey(Line, null=True, blank=True, on_delete=models.CASCADE)
    operation = models.CharField(max_length=60, blank=True)
    items = models.JSONField(default=list, help_text='[{"text": "...", "rule": "regla aprobada", "evidence": false, "fail_group": "Mantenimiento"}]')
    approved_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+")
    version = models.PositiveIntegerField(default=1)
    active = models.BooleanField(default=True)


class ChecklistRun(models.Model):
    template = models.ForeignKey(ChecklistTemplate, on_delete=models.PROTECT)
    template_version = models.PositiveIntegerField()
    station = models.ForeignKey(Station, null=True, blank=True, on_delete=models.SET_NULL)
    work_order = models.CharField(max_length=60, blank=True)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    created = models.DateTimeField(default=timezone.now)
    results = models.JSONField(default=list)  # [{"ok": bool, "note": "", "evidence_file_id": ""}]
    needs_attention = models.BooleanField(default=False)


# ---------------------------------------------------------------- handover & shift reports
class ShiftReport(models.Model):
    class Status(models.TextChoices):
        DRAFT = "draft", "Borrador"
        PENDING_DATA = "pending_data", "Pendiente de datos"
        REVIEWED = "reviewed", "Revisado"
        CLOSED = "closed", "Cerrado"

    line = models.ForeignKey(Line, on_delete=models.PROTECT)
    shift = models.ForeignKey(Shift, on_delete=models.PROTECT)
    date = models.DateField("fecha operativa")
    revision = models.PositiveIntegerField(default=1)
    status = models.CharField(max_length=14, choices=Status.choices, default=Status.DRAFT)
    snapshot = models.JSONField(default=dict)
    generated_at = models.DateTimeField(default=timezone.now)
    generated_by = models.CharField(max_length=40, default="planificador")
    reviewed_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    reviewed_at = models.DateTimeField(null=True, blank=True)
    closed_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    closed_at = models.DateTimeField(null=True, blank=True)
    previous = models.ForeignKey("self", null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    revision_reason = models.CharField(max_length=300, blank=True)
    pdf = models.ForeignKey(StoredFile, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")

    class Meta:
        ordering = ["-date", "-revision"]
        constraints = [models.UniqueConstraint(fields=["line", "shift", "date", "revision"], name="uniq_shift_report_revision")]

    def __str__(self):
        return f"Reporte {self.line.code} {self.date} {self.shift.code} rev.{self.revision}"


class Handover(models.Model):
    line = models.ForeignKey(Line, on_delete=models.PROTECT)
    shift = models.ForeignKey(Shift, on_delete=models.PROTECT, help_text="Turno saliente")
    date = models.DateField()
    summary = models.JSONField(default=dict)
    observations = models.TextField(blank=True)
    created = models.DateTimeField(default=timezone.now)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    received_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    received_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-date", "-created"]
        constraints = [models.UniqueConstraint(fields=["line", "shift", "date"], name="uniq_handover")]


# ---------------------------------------------------------------- OData connector (read-only)
class ODataConnection(models.Model):
    class Auth(models.TextChoices):
        NONE = "none", "Sin autenticación (solo si el servidor lo permite)"
        BASIC = "basic", "Básica (usuario/contraseña en variables de entorno)"
        BEARER = "bearer", "Token Bearer (variable de entorno)"
        NEGOTIATE = "negotiate", "Windows integrada (Negotiate/NTLM, requiere paquete opcional)"

    class Health(models.TextChoices):
        UNVERIFIED = "unverified", "Requiere revisión"
        CONNECTED = "connected", "Conectado"
        DELAYED = "delayed", "Con retraso"
        DISCONNECTED = "disconnected", "Desconectado"

    name = models.CharField(max_length=80, unique=True)
    service_url = models.CharField("URL del servicio OData", max_length=300, blank=True,
                                   help_text="POR CONFIRMAR. Se toma de la configuración autorizada; nunca se inventa.")
    auth_type = models.CharField(max_length=10, choices=Auth.choices, default=Auth.NONE)
    username_env = models.CharField("variable de entorno del usuario", max_length=60, blank=True, default="GPV_ODATA_USER")
    secret_env = models.CharField("variable de entorno del secreto", max_length=60, blank=True, default="GPV_ODATA_PASSWORD")
    entity_set = models.CharField("conjunto de entidades", max_length=120, blank=True, help_text="Verificado contra $metadata.")
    key_fields = models.JSONField("claves estables verificadas", default=list, blank=True)
    mapping = models.JSONField("mapeo propiedad OData → campo del portal", default=dict, blank=True)
    select_fields = models.BooleanField("usar $select con los campos mapeados", default=True)
    watermark_field = models.CharField("campo de modificación fiable (opcional)", max_length=80, blank=True)
    time_field = models.CharField("campo de instante del evento", max_length=80, blank=True)
    overlap_minutes = models.PositiveIntegerField("ventana solapada (min)", default=10)
    window_hours = models.PositiveIntegerField("ventana de refresco sin marca de modificación (h)", default=24)
    page_size = models.PositiveIntegerField(default=500)
    max_pages = models.PositiveIntegerField("máximo de páginas por ciclo", default=50)
    timeout_seconds = models.PositiveIntegerField(default=20)
    refresh_seconds = models.PositiveIntegerField("refresco (s)", default=60)
    event_kind = models.CharField(max_length=12, choices=ProductionEvent.Kind.choices, default=ProductionEvent.Kind.INCREMENTAL)
    line = models.ForeignKey(Line, null=True, blank=True, on_delete=models.SET_NULL, help_text="Línea por defecto si el registro no la trae.")
    enabled = models.BooleanField("sincronización activa", default=False)
    validated_at = models.DateTimeField(null=True, blank=True)
    odata_version = models.CharField(max_length=10, blank=True)
    metadata_summary = models.JSONField(default=dict, blank=True)
    watermark = models.DateTimeField(null=True, blank=True)
    last_attempt_at = models.DateTimeField(null=True, blank=True)
    last_success_at = models.DateTimeField(null=True, blank=True)
    last_data_at = models.DateTimeField(null=True, blank=True, help_text="Instante más reciente recibido de la fuente.")
    last_error = models.CharField(max_length=500, blank=True)
    consecutive_failures = models.PositiveIntegerField(default=0)
    next_attempt_at = models.DateTimeField(null=True, blank=True)
    synthetic = models.BooleanField("fuente de ejemplo (servidor OData sintético)", default=False, help_text=SYNTHETIC_HELP)

    def __str__(self):
        return self.name

    def health(self, now=None):
        now = now or timezone.now()
        if not self.validated_at or not self.enabled:
            return self.Health.UNVERIFIED
        if self.consecutive_failures and (not self.last_success_at or self.last_attempt_at and self.last_attempt_at > self.last_success_at):
            return self.Health.DISCONNECTED
        if not self.last_success_at:
            return self.Health.UNVERIFIED
        if (now - self.last_success_at).total_seconds() > 3 * self.refresh_seconds:
            return self.Health.DELAYED
        return self.Health.CONNECTED


class SyncRun(models.Model):
    connection = models.ForeignKey(ODataConnection, on_delete=models.CASCADE, related_name="runs")
    started = models.DateTimeField(default=timezone.now)
    finished = models.DateTimeField(null=True, blank=True)
    status = models.CharField(max_length=12, default="running")  # running | ok | failed
    pages = models.PositiveIntegerField(default=0)
    read = models.PositiveIntegerField(default=0)
    created = models.PositiveIntegerField(default=0)
    updated = models.PositiveIntegerField(default=0)
    unchanged = models.PositiveIntegerField(default=0)
    rejected = models.PositiveIntegerField(default=0)
    error_kind = models.CharField(max_length=30, blank=True)
    error = models.CharField(max_length=500, blank=True)
    query_ms = models.PositiveIntegerField(default=0)
    watermark_before = models.DateTimeField(null=True, blank=True)
    watermark_after = models.DateTimeField(null=True, blank=True)
    window_from = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-started"]


class SyncGap(models.Model):
    """Interval without queries (computer off, process stopped) and whether it was recoverable."""

    connection = models.ForeignKey(ODataConnection, on_delete=models.CASCADE, related_name="gaps")
    gap_from = models.DateTimeField()
    gap_to = models.DateTimeField()
    recoverable = models.BooleanField()
    note = models.CharField(max_length=300)
    detected = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["-gap_from"]
