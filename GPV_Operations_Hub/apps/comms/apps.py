from django.apps import AppConfig


class CommsConfig(AppConfig):
    name = "apps.comms"
    label = "comms"
    verbose_name = "Comunicación"

    def ready(self):
        from . import signals  # noqa: F401
