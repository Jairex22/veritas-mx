"""Production data model.

Granularity
-----------
* ``WorkOrder``: one row per order number (the plan). Targets live only here.
* ``ProductionRecord``: one row per *record key* inside a dataset. The key columns are
  configured per dataset (e.g. date+shift+line+order+station for incremental data).
  ``is_current`` marks the active version of a key; superseded snapshot captures and
  replaced rows keep ``is_current=False`` for history and revert.
"""
from django.conf import settings
from django.db import models
from django.db.models import Q
from django.utils import timezone

from apps.core.models import Area, StoredFile


class DatasetKind(models.TextChoices):
    PLAN = "plan", "Plan de producción (órdenes y metas)"
    INCREMENTAL = "incremental", "Producción incremental (eventos que se suman)"
    SNAPSHOT = "snapshot", "Captura acumulada (snapshot: reemplaza, no suma)"
    SERIAL = "serial", "Resultados por serial (pruebas)"
    QUALITY = "quality", "Calidad / disposiciones por causa"
    GENERIC = "generic", "Datos genéricos (solo consulta/etiquetas)"


class Dataset(models.Model):
    code = models.SlugField("código", max_length=60, unique=True)
    name = models.CharField("nombre", max_length=120)
    kind = models.CharField("tipo", max_length=20, choices=DatasetKind.choices)
    area = models.ForeignKey(Area, null=True, blank=True, on_delete=models.PROTECT,
                             help_text="Área por defecto si el archivo no trae columna de área.")
    description = models.TextField("descripción", blank=True)
    key_fields = models.JSONField("campos clave", default=list, blank=True)
    unit_default = models.CharField("unidad por defecto", max_length=20, blank=True, default="pz")
    finished_station = models.CharField(
        "estación de producción terminada", max_length=60, blank=True,
        help_text="Si la fuente trae varias estaciones, solo esta cuenta como producción terminada.")
    counts_as_production = models.BooleanField("cuenta como producción terminada", default=True)
    version = models.PositiveIntegerField(default=0)
    last_import_at = models.DateTimeField(null=True, blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL)
    created = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class MappingProfile(models.Model):
    name = models.CharField(max_length=120)
    dataset = models.ForeignKey(Dataset, on_delete=models.CASCADE, related_name="profiles")
    mapping = models.JSONField(default=dict)  # {field: source column header}
    options = models.JSONField(default=dict, blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL)
    created = models.DateTimeField(default=timezone.now)

    class Meta:
        unique_together = [("dataset", "name")]
        ordering = ["name"]

    def __str__(self):
        return self.name


class ImportBatch(models.Model):
    class Status(models.TextChoices):
        DRAFT = "draft", "Borrador"
        VALIDATED = "validated", "Validado"
        COMMITTING = "committing", "Importando"
        COMMITTED = "committed", "Importado"
        FAILED = "failed", "Fallido (sin cambios aplicados)"
        REVERTED = "reverted", "Revertido"
        PARTIAL_REVERTED = "partial_reverted", "Revertido parcialmente"

    class Mode(models.TextChoices):
        APPEND = "append", "Anexar (omitir claves existentes)"
        UPSERT = "upsert", "Actualizar por clave (insertar nuevas)"
        REPLACE = "replace", "Reemplazar alcance explícito"

    dataset = models.ForeignKey(Dataset, on_delete=models.PROTECT, related_name="batches")
    source_file = models.ForeignKey(StoredFile, on_delete=models.PROTECT, related_name="import_batches")
    file_sha256 = models.CharField(max_length=64, db_index=True)
    sheet = models.CharField(max_length=120, blank=True)
    mode = models.CharField(max_length=10, choices=Mode.choices, default=Mode.APPEND)
    scope = models.JSONField(default=dict, blank=True)
    mapping = models.JSONField(default=dict, blank=True)
    options = models.JSONField(default=dict, blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.DRAFT)
    stats = models.JSONField(default=dict, blank=True)
    analysis = models.JSONField(default=dict, blank=True)
    error_file = models.ForeignKey(StoredFile, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    error_message = models.TextField(blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL)
    created = models.DateTimeField(default=timezone.now)
    committed_at = models.DateTimeField(null=True, blank=True)
    reverted_at = models.DateTimeField(null=True, blank=True)
    reverted_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    dataset_version = models.PositiveIntegerField(null=True, blank=True)

    class Meta:
        ordering = ["-created"]

    def __str__(self):
        return f"Lote #{self.pk} · {self.dataset}"


class WorkOrder(models.Model):
    number = models.CharField("orden", max_length=60, unique=True)  # text: keeps leading zeros
    customer = models.CharField("cliente", max_length=120, blank=True)
    area = models.ForeignKey(Area, on_delete=models.PROTECT)
    line = models.CharField("línea", max_length=60, blank=True)
    part_number = models.CharField("número de parte", max_length=80, blank=True)
    revision = models.CharField("revisión", max_length=20, blank=True)
    unit = models.CharField("unidad", max_length=20, default="pz")
    qty_planned = models.DecimalField("meta", max_digits=14, decimal_places=3, null=True, blank=True)
    priority = models.PositiveSmallIntegerField("prioridad", default=3)  # 1 = highest
    start = models.DateTimeField("inicio", null=True, blank=True)
    due = models.DateTimeField("vencimiento", null=True, blank=True)
    status = models.CharField("estado", max_length=40, blank=True, default="abierta")
    responsible = models.CharField("responsable", max_length=120, blank=True)
    assigned_users = models.ManyToManyField(settings.AUTH_USER_MODEL, blank=True, related_name="assigned_orders")
    notes = models.TextField("observaciones", blank=True)
    source_batch = models.ForeignKey(ImportBatch, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    last_batch = models.ForeignKey(ImportBatch, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    version = models.PositiveIntegerField(default=1)
    updated = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["due", "priority", "number"]

    def __str__(self):
        return self.number


class PlanChange(models.Model):
    work_order = models.ForeignKey(WorkOrder, on_delete=models.CASCADE, related_name="changes")
    field = models.CharField(max_length=40)
    old_value = models.TextField(blank=True, null=True)
    new_value = models.TextField(blank=True, null=True)
    reason = models.CharField(max_length=300)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL)
    batch = models.ForeignKey(ImportBatch, null=True, blank=True, on_delete=models.SET_NULL)
    ts = models.DateTimeField(default=timezone.now)
    created_order = models.BooleanField(default=False)

    class Meta:
        ordering = ["-ts"]


class ProductionRecord(models.Model):
    dataset = models.ForeignKey(Dataset, on_delete=models.PROTECT, related_name="records")
    batch = models.ForeignKey(ImportBatch, null=True, on_delete=models.PROTECT, related_name="created_records")
    last_batch = models.ForeignKey(ImportBatch, null=True, on_delete=models.PROTECT, related_name="+")
    record_key = models.CharField(max_length=400)
    is_current = models.BooleanField(default=True)
    row_number = models.PositiveIntegerField(null=True, blank=True)
    area = models.ForeignKey(Area, null=True, blank=True, on_delete=models.PROTECT)
    date = models.DateField(null=True, blank=True, db_index=True)
    timestamp = models.DateTimeField(null=True, blank=True)
    shift = models.CharField(max_length=20, blank=True)
    customer = models.CharField(max_length=120, blank=True)
    line = models.CharField(max_length=60, blank=True, db_index=True)
    work_order = models.CharField(max_length=60, blank=True, db_index=True)
    part_number = models.CharField(max_length=80, blank=True)
    revision = models.CharField(max_length=20, blank=True)
    unit = models.CharField(max_length=20, blank=True)
    station = models.CharField(max_length=60, blank=True)
    serial = models.CharField(max_length=80, blank=True, db_index=True)
    result = models.CharField(max_length=20, blank=True)
    attempt = models.PositiveIntegerField(null=True, blank=True)
    cause = models.CharField(max_length=120, blank=True)
    responsible = models.CharField(max_length=120, blank=True)
    status = models.CharField(max_length=40, blank=True)
    qty_planned = models.DecimalField(max_digits=14, decimal_places=3, null=True, blank=True)
    qty_good = models.DecimalField(max_digits=14, decimal_places=3, null=True, blank=True)
    qty_reject = models.DecimalField(max_digits=14, decimal_places=3, null=True, blank=True)
    qty_rework = models.DecimalField(max_digits=14, decimal_places=3, null=True, blank=True)
    qty_scrap = models.DecimalField(max_digits=14, decimal_places=3, null=True, blank=True)
    planned_minutes = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    downtime_minutes = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    ideal_cycle_seconds = models.DecimalField(max_digits=10, decimal_places=3, null=True, blank=True)
    start = models.DateTimeField(null=True, blank=True)
    due = models.DateTimeField(null=True, blank=True)
    notes = models.TextField(blank=True)
    extra = models.JSONField(default=dict, blank=True)
    entered_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)
    updated = models.DateTimeField(default=timezone.now)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["dataset", "record_key"], condition=Q(is_current=True), name="uniq_current_record_key"),
        ]
        indexes = [models.Index(fields=["dataset", "is_current", "date"])]


class RecordChange(models.Model):
    """Before/after image used to revert an import without destroying later changes."""

    class Action(models.TextChoices):
        CREATE = "create", "Creado"
        UPDATE = "update", "Actualizado"
        SUPERSEDE = "supersede", "Reemplazado por captura nueva"
        REMOVE = "remove", "Retirado por reemplazo de alcance"

    batch = models.ForeignKey(ImportBatch, on_delete=models.CASCADE, related_name="changes")
    record = models.ForeignKey(ProductionRecord, on_delete=models.CASCADE, related_name="changes")
    action = models.CharField(max_length=10, choices=Action.choices)
    before = models.JSONField(null=True, blank=True)
