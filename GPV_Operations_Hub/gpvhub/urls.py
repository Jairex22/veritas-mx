from django.conf import settings
from django.contrib import admin
from django.urls import include, path, re_path
from django.views.static import serve

urlpatterns = [
    path("django-admin/", admin.site.urls),
    path("", include("apps.core.urls")),
    path("comunicados/", include("apps.comms.urls")),
    path("produccion/", include("apps.production.urls")),
    path("analitica/", include("apps.reports.urls")),
    path("hojas/", include("apps.sheets.urls")),
    path("documentos/", include("apps.documents.urls")),
    path("etiquetas/", include("apps.labels.urls")),
    path("kaizen/", include("apps.kaizen.urls")),
    path("turno/", include("apps.shift.urls")),
    path("factorylogix/", include("apps.flx.urls")),
]

if not settings.DEBUG and getattr(settings, "GPV_SERVE_STATIC", False):
    urlpatterns += [re_path(r"^static/(?P<path>.*)$", serve, {"document_root": settings.STATIC_ROOT})]

handler403 = "apps.core.views.error_403"
handler404 = "apps.core.views.error_404"
handler500 = "apps.core.views.error_500"
