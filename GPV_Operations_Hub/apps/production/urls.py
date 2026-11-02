from django.urls import path

from . import views

app_name = "production"
urlpatterns = [
    path("", views.plan, name="plan"),
    path("ordenes/<int:order_id>/", views.order_detail, name="order"),
    path("ordenes/<int:order_id>/editar/", views.order_edit, name="order_edit"),
    path("ordenes/<int:order_id>/capturar/", views.order_capture, name="order_capture"),
    path("importar/", views.import_start, name="import_start"),
    path("importar/<int:batch_id>/", views.import_wizard, name="import_wizard"),
    path("importar/<int:batch_id>/confirmar/", views.import_commit, name="import_commit"),
    path("importaciones/", views.imports_list, name="imports"),
    path("importaciones/<int:batch_id>/", views.import_detail, name="import_detail"),
    path("importaciones/<int:batch_id>/revertir/", views.import_revert, name="import_revert"),
    path("datasets/", views.datasets, name="datasets"),
    path("datasets/nuevo/", views.dataset_edit, name="dataset_create"),
    path("datasets/<int:dataset_id>/", views.dataset_edit, name="dataset_edit"),
    path("registros/", views.records, name="records"),
]
