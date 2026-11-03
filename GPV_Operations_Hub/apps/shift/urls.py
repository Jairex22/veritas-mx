from django.urls import path

from . import views

app_name = "shift"
urlpatterns = [
    path("", views.my_shift, name="home"),
    path("contexto/", views.context, name="context"),
    path("estacion/<str:token>/", views.station_qr, name="station_qr"),
    path("trabajo/", views.work, name="work"),
    path("escanear/", views.scan, name="scan"),
    path("ayuda/", views.help_home, name="help"),
    path("ayuda/<int:pk>/", views.help_detail, name="help_detail"),
    path("paros/", views.downtime, name="downtime"),
    path("materiales/", views.materials, name="materials"),
    path("captura/", views.capture, name="capture"),
    path("conciliacion/", views.reconciliation, name="reconciliation"),
    path("cierre/", views.closeout, name="closeout"),
    path("reporte/<int:pk>.<str:fmt>", views.report_export, name="report_export"),
    path("relevo/", views.handover, name="handover"),
    path("instrucciones/", views.instructions, name="instructions"),
    path("lista/<int:pk>/", views.checklist, name="checklist"),
    path("calidad/", views.quality, name="quality"),
    path("supervisor/", views.board, name="board"),
    path("plan/", views.plan, name="plan"),
    path("pantalla/<str:code>/", views.area_screen, name="area_screen"),
    path("api/pantalla/<str:code>/", views.area_api, name="area_api"),
    path("api/estado/", views.state_api, name="state_api"),
    path("etiqueta/", views.labels, name="labels"),
    path("fuentes/", views.sources, name="sources"),
    path("fuentes/<int:pk>/", views.source_detail, name="source_detail"),
    path("fuentes/<int:pk>/accion/", views.source_action, name="source_action"),
]
