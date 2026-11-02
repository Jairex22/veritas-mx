from django.apps import AppConfig


class KaizenConfig(AppConfig):
    name = "apps.kaizen"
    label = "kaizen"
    verbose_name = "Kaizen"

    def ready(self):
        from . import signals  # noqa: F401
