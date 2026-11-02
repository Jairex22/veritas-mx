import hashlib
import io
import json
import zipfile
from pathlib import Path

from django.conf import settings
from django.core.management import call_command
from django.core.management.base import BaseCommand
from django.utils import timezone

EXCLUDE = ["contenttypes", "auth.permission", "sessions", "admin.logentry"]


class Command(BaseCommand):
    help = "Respaldo coherente: datos (JSON portable SQLite/PostgreSQL), archivos privados y plantillas en un ZIP con manifiesto SHA-256."

    def add_arguments(self, parser):
        parser.add_argument("--output", help="Ruta del ZIP (por defecto data/backups/gpv_backup_FECHA.zip)")

    def handle(self, *args, **opts):
        out = Path(opts["output"] or settings.BACKUP_DIR / f"gpv_backup_{timezone.localtime():%Y%m%d_%H%M%S}.zip")
        out.parent.mkdir(parents=True, exist_ok=True)
        buf = io.StringIO()
        call_command("dumpdata", natural_foreign=True, natural_primary=True, exclude=EXCLUDE, indent=None, stdout=buf)
        data = buf.getvalue().encode("utf-8")
        manifest = {"version": settings.GPV_VERSION, "created": timezone.localtime().isoformat(), "database_sha256": hashlib.sha256(data).hexdigest(), "files": {}}
        root = Path(settings.PRIVATE_MEDIA_ROOT)
        with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("database.json", data)
            for p in sorted(root.rglob("*")):
                if p.is_file():
                    rel = p.relative_to(root).as_posix()
                    blob = p.read_bytes()
                    manifest["files"][rel] = hashlib.sha256(blob).hexdigest()
                    zf.writestr(f"private/{rel}", blob)
            zf.writestr("manifest.json", json.dumps(manifest, indent=2))
        self.stdout.write(f"Respaldo creado: {out} ({len(manifest['files'])} archivos)")
