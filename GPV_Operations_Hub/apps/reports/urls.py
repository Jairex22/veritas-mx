from django.urls import path

from . import views

app_name = "reports"
urlpatterns = [
    path("dashboard/", views.dashboard, name="dashboard"),
    path("api/dashboard/", views.dashboard_data, name="dashboard_data"),
    path("exportar/", views.export, name="export"),
    path("reportes/", views.reports, name="reports"),
    path("reportes/generar/", views.report_generate, name="report_generate"),
    path("reportes/<int:run_id>/", views.report_detail, name="report_detail"),
    path("reportes/<int:run_id>/reintentar/", views.report_retry, name="report_retry"),
    path("programaciones/nueva/", views.schedule_edit, name="schedule_create"),
    path("programaciones/<int:schedule_id>/", views.schedule_edit, name="schedule_edit"),
    path("tableros/", views.boards, name="boards"),
    path("tableros/nuevo/", views.board_create, name="board_create"),
    path("tableros/<int:board_id>/", views.board_view, name="board"),
    path("tableros/<int:board_id>/duplicar/", views.board_duplicate, name="board_duplicate"),
    path("api/tableros/<int:board_id>/guardar/", views.board_save, name="board_save"),
    path("api/widget/", views.widget_api, name="widget_api"),
    path("api/union/", views.join_check, name="join_check"),
]
