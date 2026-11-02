from django.conf import settings
from django.db import models
from django.utils import timezone

from apps.core.models import Area, StoredFile


class Status(models.TextChoices):
    PROPOSAL = "proposal", "Propuesta"
    EVALUATION = "evaluation", "Evaluación"
    APPROVED = "approved", "Aprobada"
    IMPLEMENTATION = "implementation", "Implementación"
    VERIFICATION = "verification", "Verificación"
    CLOSED = "closed", "Cerrada"
    REJECTED = "rejected", "Rechazada"


# from_status: {to_status: (capability or "owner", requires_comment)}
TRANSITIONS = {
    Status.PROPOSAL: {Status.EVALUATION: ("kaizen.evaluate", False), Status.REJECTED: ("kaizen.evaluate", True)},
    Status.EVALUATION: {Status.APPROVED: ("kaizen.evaluate", False), Status.REJECTED: ("kaizen.evaluate", True),
                        Status.PROPOSAL: ("kaizen.evaluate", True)},
    Status.APPROVED: {Status.IMPLEMENTATION: ("owner", False)},
    Status.IMPLEMENTATION: {Status.VERIFICATION: ("owner", False)},
    Status.VERIFICATION: {Status.CLOSED: ("kaizen.evaluate", False), Status.IMPLEMENTATION: ("kaizen.evaluate", True)},
    Status.CLOSED: {},
    Status.REJECTED: {Status.PROPOSAL: ("kaizen.evaluate", True)},
}


class Improvement(models.Model):
    code = models.CharField(max_length=20, unique=True, blank=True)
    title = models.CharField("título", max_length=200)
    problem = models.TextField("problema")
    current_state = models.TextField("estado actual", blank=True)
    objective = models.TextField("objetivo")
    area = models.ForeignKey(Area, on_delete=models.PROTECT, verbose_name="área")
    responsible = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
                                    related_name="kaizen_responsible", verbose_name="responsable")
    proposer = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="kaizen_proposed")
    priority = models.PositiveSmallIntegerField("prioridad", default=2, choices=[(1, "Alta"), (2, "Media"), (3, "Baja")])
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PROPOSAL)
    created = models.DateTimeField(default=timezone.now)
    start_date = models.DateField("fecha inicio", null=True, blank=True)
    target_date = models.DateField("fecha objetivo", null=True, blank=True)
    closed_date = models.DateField(null=True, blank=True)
    root_cause = models.TextField("causa raíz", blank=True)
    whys = models.JSONField("5 porqués", default=list, blank=True)
    pdca = models.JSONField(default=dict, blank=True)
    results = models.TextField("resultados", blank=True)
    indicator = models.CharField("indicador vinculado", max_length=120, blank=True)
    linked_orders = models.ManyToManyField("production.WorkOrder", blank=True)
    evidence = models.ManyToManyField(StoredFile, blank=True)
    linked_reports = models.ManyToManyField("reports.ReportRun", blank=True)
    approved_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    approved_at = models.DateTimeField(null=True, blank=True)
    version = models.PositiveIntegerField(default=1)

    class Meta:
        ordering = ["priority", "-created"]

    def __str__(self):
        return f"{self.code} {self.title}"

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        if not self.code:
            self.code = f"KZ-{self.pk:05d}"
            super().save(update_fields=["code"])

    @property
    def author(self):
        return self.proposer


class KaizenAction(models.Model):
    improvement = models.ForeignKey(Improvement, on_delete=models.CASCADE, related_name="actions")
    description = models.CharField("acción", max_length=300)
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)
    due = models.DateField(null=True, blank=True)
    done_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["due", "id"]


class KaizenMeasure(models.Model):
    """Before/after comparison with explicit periods, units and source."""

    improvement = models.ForeignKey(Improvement, on_delete=models.CASCADE, related_name="measures")
    name = models.CharField("indicador", max_length=120)
    unit = models.CharField("unidad", max_length=30)
    source = models.CharField("fuente", max_length=200)
    before_from = models.DateField()
    before_to = models.DateField()
    before_value = models.DecimalField(max_digits=14, decimal_places=4)
    after_from = models.DateField()
    after_to = models.DateField()
    after_value = models.DecimalField(max_digits=14, decimal_places=4)
    higher_is_better = models.BooleanField(default=False)
    notes = models.CharField(max_length=300, blank=True)

    @property
    def delta(self):
        return self.after_value - self.before_value

    @property
    def delta_pct(self):
        if self.before_value == 0:
            return None
        return (self.after_value - self.before_value) / self.before_value * 100

    @property
    def improved(self):
        return self.delta > 0 if self.higher_is_better else self.delta < 0


class KaizenSaving(models.Model):
    improvement = models.ForeignKey(Improvement, on_delete=models.CASCADE, related_name="savings")
    kind = models.CharField(max_length=10, choices=[("time", "Tiempo"), ("money", "Dinero"), ("scrap", "Scrap"), ("other", "Otro")])
    amount = models.DecimalField(max_digits=14, decimal_places=2)
    unit = models.CharField(max_length=30)
    formula = models.CharField("fórmula", max_length=300)
    calculation = models.TextField("cálculo detallado")
    period = models.CharField("periodo", max_length=60)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")
    approved_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    approved_at = models.DateTimeField(null=True, blank=True)


class KaizenTransition(models.Model):
    improvement = models.ForeignKey(Improvement, on_delete=models.CASCADE, related_name="transitions")
    from_status = models.CharField(max_length=20)
    to_status = models.CharField(max_length=20)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    ts = models.DateTimeField(default=timezone.now)
    comment = models.TextField(blank=True)

    class Meta:
        ordering = ["ts"]

    @property
    def from_label(self):
        return Status(self.from_status).label if self.from_status in Status.values else "—"

    @property
    def to_label(self):
        return Status(self.to_status).label if self.to_status in Status.values else self.to_status
