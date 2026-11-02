from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand

from apps.core.samples import write_all


class Command(BaseCommand):
    help = "Genera los archivos de ejemplo SINTÉTICOS en la carpeta samples/ (producción, calidad, documentos y etiquetas)."

    def add_arguments(self, parser):
        parser.add_argument("--output", default=str(settings.BASE_DIR / "samples"))

    def handle(self, *args, **opts):
        files = write_all(Path(opts["output"]))
        self.stdout.write(f"{len(files)} archivos sintéticos en {opts['output']}")
