"""Acceptance test 23: backup and restore including associated files."""
import tempfile
from pathlib import Path

from django.core.management import call_command
from django.test import Client, TransactionTestCase

from apps.core.models import Role, StoredFile
from apps.core.tests.helpers import areas, user
from apps.documents.models import Document


class BackupRestoreTests(TransactionTestCase):
    def test_23_backup_restore_and_open_files(self):
        areas()
        u = user("own", Role.ENGINEER, ("SMT",))
        sf = StoredFile.create_from_bytes(b"%PDF-1.4 contenido de prueba", "respaldo.pdf", owner=u)
        Document.objects.create(file=sf, title="respaldo.pdf", owner=u)
        out = Path(tempfile.mkdtemp()) / "b.zip"
        call_command("gpv_backup", output=str(out))
        # simulate loss: delete data and file
        Document.objects.all().delete()
        sf.path.unlink()
        StoredFile.objects.all().delete()
        with self.assertRaises(Exception):
            call_command("gpv_restore", str(out))  # requires --confirmar
        call_command("gpv_restore", str(out), confirmar=True)
        restored = StoredFile.objects.get(original_name="respaldo.pdf")
        self.assertEqual(restored.path.read_bytes(), b"%PDF-1.4 contenido de prueba")
        c = Client(HTTP_HOST="127.0.0.1")
        c.force_login(restored.owner)
        r = c.get(f"/archivos/{restored.pk}/")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(b"".join(r.streaming_content), b"%PDF-1.4 contenido de prueba")
        self.assertTrue(Document.objects.filter(title="respaldo.pdf").exists())
