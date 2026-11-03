from django.urls import path

from . import views

app_name = "flx"
urlpatterns = [
    path("", views.center, name="center"),
    path("accion/", views.action, name="action"),
    path("reporte.json", views.report, name="report"),
    path("api/estado/", views.api_status, name="api_status"),
    path("entidad/<str:name>/", views.entity, name="entity"),
    path("entidad/<str:name>/accion/", views.entity_action, name="entity_action"),
    path("entidad/<str:name>/consulta/", views.entity_query, name="entity_query"),
]
