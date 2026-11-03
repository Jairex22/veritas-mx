"""Pilot configuration (lines, stations, reasons, groups, checklists, OData).

Every change made here is recorded in Django's admin history (who, when, what) and in
the GPV audit log. Secrets are NOT stored here: only the *names* of environment variables.
"""
from django.contrib import admin

from apps.core.audit import audit

from . import models as m


class AuditedAdmin(admin.ModelAdmin):
    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        audit(request.user, f"shift.config_{'changed' if change else 'created'}", obj,
              f"{obj._meta.verbose_name} «{obj}»: {', '.join(form.changed_data) or 'sin cambios'}")

    def delete_model(self, request, obj):
        audit(request.user, "shift.config_deleted", obj, f"{obj._meta.verbose_name} «{obj}» eliminado")
        super().delete_model(request, obj)


class StationInline(admin.TabularInline):
    model = m.Station
    extra = 0
    readonly_fields = ("qr_token",)


@admin.register(m.Line)
class LineAdmin(AuditedAdmin):
    list_display = ("code", "name", "area", "pilot", "count_unit", "panel_factor", "panel_factor_confirmed", "synthetic")
    inlines = [StationInline]


@admin.register(m.ODataConnection)
class ODataAdmin(AuditedAdmin):
    list_display = ("name", "service_url", "auth_type", "entity_set", "enabled", "validated_at", "synthetic")
    readonly_fields = ("validated_at", "odata_version", "metadata_summary", "watermark", "last_attempt_at", "last_success_at", "last_data_at",
                       "last_error", "consecutive_failures", "next_attempt_at")

    def save_model(self, request, obj, form, change):
        if change and set(form.changed_data) & {"service_url", "auth_type", "entity_set", "mapping", "key_fields", "watermark_field", "time_field"}:
            obj.validated_at = None  # connection/mapping changed: must pass a diagnostic again
            obj.enabled = False
        super().save_model(request, obj, form, change)


for model in (m.Site, m.ShiftBreak, m.HelpReason, m.DowntimeReason, m.ChecklistTemplate, m.OperationInstruction):
    admin.site.register(model, AuditedAdmin)

for model in (m.ShiftPlan, m.HelpRequest, m.Downtime, m.MaterialRequest, m.QualityObservation, m.ShiftReport, m.Handover, m.ProductionEvent,
              m.SyncRun, m.SyncGap, m.ContextChange, m.EventRevision):
    admin.site.register(model)
