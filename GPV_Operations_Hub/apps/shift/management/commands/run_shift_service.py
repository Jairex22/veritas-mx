from django.core.management.base import BaseCommand

from apps.shift.service_loop import run_loop, tick


class Command(BaseCommand):
    help = "Servicio local del portal del turno: sincronización OData de solo lectura, recordatorios y borradores de reporte."

    def add_arguments(self, parser):
        parser.add_argument("--once", action="store_true", help="Ejecuta un solo ciclo y termina.")
        parser.add_argument("--tick", type=int, default=30)

    def handle(self, *args, **opts):
        if opts["once"]:
            self.stdout.write(str(tick()))
            return
        self.stdout.write("Servicio del turno iniciado (Ctrl+C para detener).")
        try:
            run_loop(tick_seconds=opts["tick"])
        except KeyboardInterrupt:
            self.stdout.write("Detenido.")
