from django.apps import AppConfig


class SheetsConfig(AppConfig):
    name = "apps.sheets"
    label = "sheets"
    verbose_name = "Hoja de cálculo"

    def ready(self):
        from . import signals  # noqa: F401
