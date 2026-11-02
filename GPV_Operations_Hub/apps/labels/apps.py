from django.apps import AppConfig


class LabelsConfig(AppConfig):
    name = "apps.labels"
    label = "labels"
    verbose_name = "Etiquetas"

    def ready(self):
        from . import signals  # noqa: F401
