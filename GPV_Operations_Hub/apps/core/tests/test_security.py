"""Acceptance test 12 and security checks: server-side permissions, file access, uploads."""
from django.test import Client, TestCase

from apps.core.files import validate_upload
from apps.core.jobs import UserFacingError
from apps.core.models import Role, RoleCapability, StoredFile
from apps.core.permissions import has_cap
from apps.core.tests.helpers import areas, user


class SecurityTests(TestCase):
    def setUp(self):
        self.a = areas()
        self.admin = user("root", superuser=True)
        self.op = user("op", Role.OPERATOR, ("SMT",))
        self.op2 = user("op2", Role.OPERATOR, ("ENS",))

    def c(self, u):
        c = Client(HTTP_HOST="127.0.0.1")
        c.force_login(u)
        return c

    def test_12_operator_cannot_change_permissions(self):
        c = self.c(self.op)
        self.assertEqual(c.get("/administracion/permisos/").status_code, 403)
        r = c.post("/administracion/permisos/", {"admin.users|operator": "on"})
        self.assertEqual(r.status_code, 403)
        self.assertFalse(RoleCapability.objects.filter(role="operator", capability="admin.users", allowed=True).exists())
        r = c.post(f"/administracion/usuarios/{self.op.pk}/", {"role": "admin", "first_name": "x"})
        self.assertEqual(r.status_code, 403)
        self.op.profile.refresh_from_db()
        self.assertEqual(self.op.profile.role, Role.OPERATOR)
        self.assertFalse(has_cap(self.op, "admin.users"))

    def test_12_operator_cannot_download_foreign_file(self):
        mine = StoredFile.create_from_bytes(b"%PDF-1.4 mine", "mio.pdf", owner=self.op)
        foreign = StoredFile.create_from_bytes(b"%PDF-1.4 secret", "ajeno.pdf", owner=self.op2)
        area_file = StoredFile.create_from_bytes(b"x", "ens.txt", owner=self.op2, area=self.a["ENS"], visibility="area")
        c = self.c(self.op)
        self.assertEqual(c.get(f"/archivos/{mine.pk}/").status_code, 200)
        self.assertEqual(c.get(f"/archivos/{foreign.pk}/").status_code, 403)
        self.assertEqual(c.get(f"/archivos/{area_file.pk}/").status_code, 403)
        self.assertEqual(self.c(self.op2).get(f"/archivos/{area_file.pk}/").status_code, 200)
        anon = Client(HTTP_HOST="127.0.0.1")
        self.assertEqual(anon.get(f"/archivos/{mine.pk}/").status_code, 302)  # login required

    def test_configurable_matrix(self):
        self.assertFalse(has_cap(self.op, "production.import"))
        RoleCapability.objects.create(role="operator", capability="production.import", allowed=True)
        self.assertTrue(has_cap(self.op, "production.import"))
        self.assertEqual(self.c(self.op).get("/produccion/importar/").status_code, 200)

    def test_operator_only_captures_assigned_orders(self):
        from apps.production.models import WorkOrder

        wo = WorkOrder.objects.create(number="X1", area=self.a["SMT"], qty_planned=10)
        c = self.c(self.op)
        r = c.post(f"/produccion/ordenes/{wo.pk}/capturar/", {"qty_good": "3"})
        self.assertEqual(r.status_code, 403)
        wo.assigned_users.add(self.op)
        r = c.post(f"/produccion/ordenes/{wo.pk}/capturar/", {"qty_good": "3", "date": "2026-11-02"})
        self.assertEqual(r.status_code, 302)
        self.assertEqual(c.post(f"/produccion/ordenes/{wo.pk}/editar/", {"qty_planned": "999", "reason": "intento"}).status_code, 403)

    def test_upload_validation(self):
        with self.assertRaises(UserFacingError):
            validate_upload(b"not a pdf", "x.pdf")
        with self.assertRaises(UserFacingError):
            validate_upload(b"PK\x03\x04", "macro.xlsm")
        with self.assertRaises(UserFacingError):
            validate_upload(b"<svg><script>alert(1)</script></svg>", "a.svg")
        with self.assertRaises(UserFacingError) as ctx:
            validate_upload(b"x", "viejo.xls")
        self.assertIn(".xlsx", str(ctx.exception))
        name, ext = validate_upload(b"a,b\n1,2\n", "..\\..\\evil/../datos.csv")
        self.assertEqual(name, "datos.csv")

    def test_security_headers_and_csrf(self):
        c = Client(HTTP_HOST="127.0.0.1", enforce_csrf_checks=True)
        c.force_login(self.admin)
        r = c.get("/")
        self.assertIn("default-src 'self'", r["Content-Security-Policy"])
        self.assertEqual(c.post("/comunicados/nuevo/", {"title": "x"}).status_code, 403)  # CSRF

    def test_csv_injection_neutralised(self):
        from apps.reports.exporters import to_csv

        snap = {"tables": [{"columns": [{"label": "a"}], "rows": [["=HYPERLINK(\"x\")"], [5]]}]}
        out = to_csv(snap).decode("utf-8-sig")
        self.assertIn("'=HYPERLINK", out)
