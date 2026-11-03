from django.apps import AppConfig


class ShiftConfig(AppConfig):
    name = "apps.shift"
    label = "shift"
    verbose_name = "Portal del turno (piloto SMT)"

    def ready(self):
        from . import signals  # noqa: F401
