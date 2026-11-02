from django.urls import path

from . import views

app_name = "sheets"
urlpatterns = [
    path("", views.sheet_list, name="list"),
    path("nueva/", views.sheet_create, name="create"),
    path("<int:pk>/", views.sheet_edit, name="edit"),
    path("<int:pk>/versiones/", views.versions, name="versions"),
    path("<int:pk>/publicar/", views.publish, name="publish"),
    path("<int:pk>/compartir/", views.share, name="share"),
    path("api/<int:pk>/recalcular/", views.api_recalc, name="api_recalc"),
    path("api/<int:pk>/guardar/", views.api_save, name="api_save"),
    path("api/<int:pk>/copia/", views.api_save_copy, name="api_copy"),
    path("api/<int:pk>/operacion/", views.api_op, name="api_op"),
    path("api/<int:pk>/exportar/", views.api_export, name="api_export"),
]
