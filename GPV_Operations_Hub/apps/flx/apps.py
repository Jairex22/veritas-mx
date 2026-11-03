from django.apps import AppConfig


class FlxConfig(AppConfig):
    name = "apps.flx"
    label = "flx"
    verbose_name = "FactoryLogix (OData, solo lectura)"

    def ready(self):
        from . import jobs  # noqa: F401  (registers job handlers)
