from django.apps import AppConfig


class ProductionConfig(AppConfig):
    name = "apps.production"
    label = "production"
    verbose_name = "Producción"

    def ready(self):
        from . import signals  # noqa: F401
