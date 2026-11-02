from django.apps import AppConfig


class DocumentsConfig(AppConfig):
    name = "apps.documents"
    label = "documents"
    verbose_name = "Documentos"

    def ready(self):
        from . import signals  # noqa: F401
