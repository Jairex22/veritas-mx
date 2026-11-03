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

    def test_backup_restore_keeps_shift_portal_data(self):
        from datetime import time
        from decimal import Decimal

        from django.utils import timezone

        from apps.core.models import Shift
        from apps.shift.models import HelpReason, HelpRequest, Line, ProductionEvent, Site, Station

        a = areas()
        u = user("op2", Role.OPERATOR, ("SMT",))
        site = Site.objects.create(code="S", name="S", synthetic=True)
        line = Line.objects.create(site=site, area=a["SMT"], code="L1", name="L1", pilot=True)
        st = Station.objects.create(line=line, code="E1", name="E1", is_count_point=True)
        HelpRequest.objects.create(reason=HelpReason.objects.create(code="m", label="M"), line=line, station=st, created_by=u)
        auto = ProductionEvent.objects.create(source="odata", line=line, station=st, qty=Decimal(5), event_at=timezone.now(), external_key="K1")
        ProductionEvent.objects.create(source="manual", line=line, station=st, qty=Decimal(5), event_at=timezone.now(), recon_status="reconciled",
                                       reconciled_with=auto, user=u)
        out = Path(tempfile.mkdtemp()) / "s.zip"
        call_command("gpv_backup", output=str(out))
        ProductionEvent.objects.all().delete()
        HelpRequest.objects.all().delete()
        call_command("gpv_restore", str(out), confirmar=True)
        self.assertEqual(HelpRequest.objects.count(), 1)
        m = ProductionEvent.objects.get(source="manual")
        self.assertEqual(m.reconciled_with.external_key, "K1")
        self.assertEqual(Station.objects.get(code="E1").qr_token, st.qr_token)
