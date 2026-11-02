from django.contrib import admin

from .models import Area, AuditLog, Job, Profile, RoleCapability, Shift, StoredFile

admin.site.site_header = "GPV Operations Hub · Administración técnica"
for m in (Area, Shift, Profile, RoleCapability):
    admin.site.register(m)


@admin.register(StoredFile)
class StoredFileAdmin(admin.ModelAdmin):
    list_display = ("original_name", "owner", "area", "visibility", "size", "created")
    readonly_fields = ("relpath", "sha256", "size")


@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    list_display = ("ts", "actor", "action", "summary")
    readonly_fields = [f.name for f in AuditLog._meta.fields]


@admin.register(Job)
class JobAdmin(admin.ModelAdmin):
    list_display = ("created", "kind", "status", "progress", "created_by")
