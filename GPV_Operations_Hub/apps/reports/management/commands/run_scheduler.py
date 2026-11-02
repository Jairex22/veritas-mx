from django.conf import settings
from django.core.management.base import BaseCommand

from apps.reports.services import run_scheduler_loop


class Command(BaseCommand):
    help = "Planificador de reportes programados (mantener UN proceso activo). Ctrl+C para detener."

    def add_arguments(self, parser):
        parser.add_argument("--once", action="store_true", help="Ejecuta un solo ciclo y termina (pruebas / tareas programadas de Windows).")

    def handle(self, *args, **opts):
        tick = settings.GPV["SCHEDULER_TICK_SECONDS"]
        self.stdout.write(f"Planificador iniciado (ciclo {tick}s, zona America/Mexico_City). Ctrl+C para detener.")
        try:
            run_scheduler_loop(stop_after=1 if opts["once"] else None, tick_seconds=tick)
        except KeyboardInterrupt:
            self.stdout.write("Planificador detenido.")
