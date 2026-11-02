import signal
import time

from django.core.management.base import BaseCommand
from django.db import close_old_connections

from apps.core.jobs import claim_next, execute, recover_stale_jobs, worker_id


class Command(BaseCommand):
    help = "Trabajador de tareas persistentes (importaciones, reportes, documentos). Ctrl+C para detener; los trabajos en curso se recuperan al reiniciar."

    def add_arguments(self, parser):
        parser.add_argument("--once", action="store_true", help="Procesa la cola disponible y termina.")
        parser.add_argument("--sleep", type=float, default=2.0)

    def handle(self, *args, **opts):
        holder = worker_id()
        stop = {"flag": False}

        def _stop(*_a):
            stop["flag"] = True

        signal.signal(signal.SIGINT, _stop)
        if hasattr(signal, "SIGTERM"):
            signal.signal(signal.SIGTERM, _stop)
        n = recover_stale_jobs()
        self.stdout.write(f"Trabajador {holder} iniciado. Trabajos recuperados: {n}. Ctrl+C para detener.")
        last_recover = time.time()
        while not stop["flag"]:
            close_old_connections()
            job = claim_next(holder)
            if job is None:
                if opts["once"]:
                    break
                if time.time() - last_recover > 300:
                    recover_stale_jobs()
                    last_recover = time.time()
                time.sleep(opts["sleep"])
                continue
            self.stdout.write(f"→ {job.kind} {job.pk}")
            execute(job)
        self.stdout.write("Trabajador detenido.")
