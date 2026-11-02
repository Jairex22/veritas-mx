from django.urls import path

from . import views

app_name = "documents"
urlpatterns = [
    path("", views.doc_list, name="list"),
    path("cargar/", views.upload, name="upload"),
    path("carpetas/nueva/", views.folder_create, name="folder_create"),
    path("operacion/", views.operate, name="operate"),
    path("zip/", views.zip_download, name="zip"),
    path("<int:pk>/", views.detail, name="detail"),
    path("<int:pk>/miniatura/<int:page>.png", views.thumb, name="thumb"),
    path("<int:pk>/vista-previa/", views.preview, name="preview"),
    path("<int:pk>/desproteger/", views.decrypt, name="decrypt"),
    path("<int:pk>/duplicados/", views.csv_dedupe_preview, name="dedupe_preview"),
    path("<int:pk>/retirar/", views.delete, name="delete"),
    path("<int:pk>/datos/", views.update_meta, name="meta"),
]
