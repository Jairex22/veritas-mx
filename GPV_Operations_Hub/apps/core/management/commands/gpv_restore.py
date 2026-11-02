import hashlib
import json
import shutil
import tempfile
import zipfile
from pathlib import Path, PurePosixPath

from django.conf import settings
from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction


class Command(BaseCommand):
    help = "Restaura un respaldo de gpv_backup. REEMPLAZA los datos actuales. Requiere --confirmar."

    def add_arguments(self, parser):
        parser.add_argument("archivo")
        parser.add_argument("--confirmar", action="store_true", help="Confirma que se reemplazarán los datos actuales.")

    def handle(self, *args, **opts):
        path = Path(opts["archivo"])
        if not path.exists():
            raise CommandError("No existe el archivo de respaldo.")
        if not opts["confirmar"]:
            raise CommandError("La restauración reemplaza todos los datos. Vuelva a ejecutar con --confirmar.")
        with zipfile.ZipFile(path) as zf:
            manifest = json.loads(zf.read("manifest.json"))
            data = zf.read("database.json")
            if hashlib.sha256(data).hexdigest() != manifest["database_sha256"]:
                raise CommandError("El respaldo está dañado (hash de base de datos no coincide).")
            for rel, digest in manifest["files"].items():
                if ".." in PurePosixPath(rel).parts or rel.startswith("/"):
                    raise CommandError(f"Ruta inválida en el respaldo: {rel}")
                if hashlib.sha256(zf.read(f"private/{rel}")).hexdigest() != digest:
                    raise CommandError(f"Archivo dañado en el respaldo: {rel}")
            call_command("migrate", verbosity=0)
            tmp = Path(tempfile.mkdtemp(dir=settings.TEMP_DIR))
            try:
                fixture = tmp / "database.json"
                fixture.write_bytes(data)
                with transaction.atomic():
                    call_command("flush", interactive=False, verbosity=0)
                    call_command("loaddata", str(fixture), verbosity=0)
            finally:
                shutil.rmtree(tmp, ignore_errors=True)
            root = Path(settings.PRIVATE_MEDIA_ROOT)
            staging = root.parent / "private_restore_tmp"
            shutil.rmtree(staging, ignore_errors=True)
            for rel in manifest["files"]:
                target = staging / rel
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(zf.read(f"private/{rel}"))
            old = root.parent / "private_before_restore"
            shutil.rmtree(old, ignore_errors=True)
            if root.exists():
                root.rename(old)
            staging.rename(root) if staging.exists() else root.mkdir(parents=True, exist_ok=True)
        self.stdout.write(f"Restauración completa: {len(manifest['files'])} archivos. Copia de los archivos anteriores en {old}")
