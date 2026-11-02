from django.urls import path

from . import views

app_name = "labels"
urlpatterns = [
    path("", views.template_list, name="list"),
    path("nueva/", views.template_create, name="create"),
    path("impresoras/", views.printers, name="printers"),
    path("impresoras/<int:printer_id>/", views.printers, name="printer_edit"),
    path("impresoras/<int:printer_id>/probar/", views.printer_test, name="printer_test"),
    path("impresoras/<int:printer_id>/habilitar/", views.printer_toggle, name="printer_toggle"),
    path("contadores/", views.counter_save, name="counter_save"),
    path("trabajos/<uuid:job_id>/", views.job_detail, name="job"),
    path("trabajos/<uuid:job_id>/confirmar/", views.job_confirm, name="job_confirm"),
    path("api/trabajos/<uuid:job_id>/reimprimir/", views.api_reprint, name="reprint"),
    path("<int:pk>/disenar/", views.designer, name="designer"),
    path("<int:pk>/duplicar/", views.template_duplicate, name="duplicate"),
    path("<int:pk>/exportar.json", views.template_export, name="export_json"),
    path("<int:pk>/publicar/", views.publish, name="publish"),
    path("<int:pk>/archivo.<str:fmt>", views.export_file, name="export_file"),
    path("<int:pk>/imprimir/", views.print_page, name="print"),
    path("<int:pk>/imprimir/datos/", views.upload_data, name="upload_data"),
    path("api/<int:pk>/borrador/", views.api_save_draft, name="api_draft"),
    path("api/<int:pk>/vista-previa/", views.api_preview, name="api_preview"),
    path("api/<int:pk>/imprimir/vista-previa/", views.api_print_preview, name="api_print_preview"),
    path("api/<int:pk>/imprimir/", views.api_print, name="api_print"),
]
