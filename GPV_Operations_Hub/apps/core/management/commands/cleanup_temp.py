import shutil
import time

from django.conf import settings
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Elimina archivos temporales de conversiones con más de N horas (por defecto 24)."

    def add_arguments(self, parser):
        parser.add_argument("--hours", type=int, default=24)

    def handle(self, *args, **opts):
        limit = time.time() - opts["hours"] * 3600
        n = 0
        for p in settings.TEMP_DIR.iterdir():
            if p.stat().st_mtime < limit:
                shutil.rmtree(p, ignore_errors=True) if p.is_dir() else p.unlink(missing_ok=True)
                n += 1
        self.stdout.write(f"{n} elementos temporales eliminados.")
