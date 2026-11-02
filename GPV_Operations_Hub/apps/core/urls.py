from django.contrib.auth import views as auth_views
from django.urls import path

from . import views

urlpatterns = [
    path("", views.home, name="home"),
    path("entrar/", auth_views.LoginView.as_view(template_name="core/login.html", redirect_authenticated_user=True), name="login"),
    path("salir/", auth_views.LogoutView.as_view(), name="logout"),
    path("cuenta/contrasena/", views.password_change, name="password_change"),
    path("archivos/<uuid:file_id>/", views.download, name="download"),
    path("notificaciones/", views.notifications_page, name="notifications"),
    path("api/notificaciones/", views.notifications_poll, name="notifications_poll"),
    path("api/notificaciones/leer/", views.notifications_read, name="notifications_read"),
    path("trabajos/", views.jobs_page, name="jobs"),
    path("api/trabajos/<uuid:job_id>/", views.job_status, name="job_status"),
    path("api/trabajos/<uuid:job_id>/cancelar/", views.job_cancel, name="job_cancel"),
    path("administracion/", views.admin_home, name="admin_home"),
    path("administracion/usuarios/nuevo/", views.user_create, name="user_create"),
    path("administracion/usuarios/<int:user_id>/", views.user_edit, name="user_edit"),
    path("administracion/areas/nueva/", views.area_edit, name="area_create"),
    path("administracion/areas/<int:area_id>/", views.area_edit, name="area_edit"),
    path("administracion/turnos/nuevo/", views.shift_edit, name="shift_create"),
    path("administracion/turnos/<int:shift_id>/", views.shift_edit, name="shift_edit"),
    path("administracion/permisos/", views.capability_matrix_view, name="capability_matrix"),
    path("administracion/configuracion/", views.settings_view, name="settings"),
    path("administracion/diagnostico/", views.diagnostics_view, name="diagnostics"),
    path("administracion/auditoria/", views.audit_view, name="audit"),
]
