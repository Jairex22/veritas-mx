"""v1.0.1 regressions found by the role-based audit (operator, supervisor, analyst)."""
from django.contrib.contenttypes.models import ContentType
from django.test import Client, TestCase

from apps.core.models import Notification, Role
from apps.core.tests.helpers import areas, dataset, run_import, user
from apps.production.models import WorkOrder


def cl(u):
    c = Client(HTTP_HOST="127.0.0.1")
    c.force_login(u)
    return c


class RoleFlowTests(TestCase):
    def setUp(self):
        self.a = areas()
        self.op = user("op", Role.OPERATOR, ("SMT",))
        self.sup = user("sup", Role.SUPERVISOR, ("SMT",))
        self.sup_ens = user("sup_ens", Role.SUPERVISOR, ("ENS",))
        self.eng = user("eng", Role.ENGINEER, ("SMT",))
        self.admin = user("root", superuser=True)

    def test_f1_menu_hides_forbidden_sections(self):
        html = cl(self.op).get("/").content.decode()
        self.assertNotIn('href="/produccion/importar/"', html)
        self.assertNotIn('href="/hojas/"', html)
        self.assertIn('href="/produccion/"', html)
        html = cl(self.eng).get("/").content.decode()
        self.assertIn('href="/produccion/importar/"', html)
        self.assertIn('href="/hojas/"', html)

    def test_f2_batch_traceability_visible_but_revert_restricted(self):
        ds = dataset("inc", "incremental", self.a["SMT"], station="FINAL")
        b, _r, _s = run_import(self.admin, ds, b"Fecha,Turno,Linea,OT,Estacion,Buenas\r\n2026-11-02,T1,L,1,FINAL,3\r\n", "a.csv",
                               mapping={"qty_good": "Buenas"})
        self.assertEqual(cl(self.eng).get(f"/produccion/importaciones/{b.pk}/").status_code, 200)
        self.assertEqual(cl(self.op).get(f"/produccion/importaciones/{b.pk}/").status_code, 200)
        self.assertEqual(cl(self.sup_ens).get(f"/produccion/importaciones/{b.pk}/").status_code, 403)
        self.assertEqual(cl(self.eng).post(f"/produccion/importaciones/{b.pk}/revertir/", {"reason": "intento sin permiso"}).status_code, 403)
        self.assertEqual(cl(self.eng).get(f"/archivos/{b.source_file.pk}/").status_code, 200)  # importer of the area
        self.assertEqual(cl(self.op).get(f"/archivos/{b.source_file.pk}/").status_code, 403)
        self.assertNotContains(cl(self.op).get(f"/produccion/importaciones/{b.pk}/"), f"/archivos/{b.source_file.pk}/")

    def test_f3_incident_reaches_area_supervisor_and_inbox(self):
        wo = WorkOrder.objects.create(number="OT-9", area=self.a["SMT"], qty_planned=10)
        wo.assigned_users.add(self.op)
        ct = ContentType.objects.get_for_model(WorkOrder)
        r = cl(self.op).post("/comunicados/comentarios/", {"ct": ct.pk, "obj": wo.pk, "kind": "incident", "body": "Falta material",
                                                           "next": f"/produccion/ordenes/{wo.pk}/"})
        self.assertEqual(r.status_code, 302)
        self.assertTrue(Notification.objects.filter(user=self.sup, title__startswith="Nueva incidencia").exists())
        self.assertFalse(Notification.objects.filter(user=self.sup_ens).exists())
        inbox = cl(self.sup).get("/comunicados/incidencias/")
        self.assertContains(inbox, "Falta material")
        self.assertNotContains(cl(self.sup_ens).get("/comunicados/incidencias/"), "Falta material")
        self.assertContains(cl(self.sup).get("/"), "Incidencias y dudas abiertas (1)")
        from apps.comms.models import Comment

        c = Comment.objects.get()
        self.assertEqual(cl(self.op).post(f"/comunicados/comentarios/{c.pk}/resolver/", {"next": "/"}).status_code, 403)
        cl(self.sup).post(f"/comunicados/comentarios/{c.pk}/resolver/", {"next": "/"})
        c.refresh_from_db()
        self.assertTrue(c.resolved)
        self.assertNotContains(cl(self.sup).get("/comunicados/incidencias/"), "Falta material")
        self.assertTrue(Notification.objects.filter(user=self.op, title__contains="resuelta").exists())

    def test_f5_supervisor_cannot_revert_other_area(self):
        ds = dataset("inc2", "incremental", self.a["SMT"], station="FINAL")
        b, _r, _s = run_import(self.admin, ds, b"Fecha,Turno,Linea,OT,Estacion,Buenas\r\n2026-11-02,T1,L,1,FINAL,3\r\n", "b.csv",
                               mapping={"qty_good": "Buenas"})
        r = cl(self.sup_ens).post(f"/produccion/importaciones/{b.pk}/revertir/", {"reason": "otra área"})
        self.assertEqual(r.status_code, 403)
        b.refresh_from_db()
        self.assertEqual(b.status, "committed")
        self.assertNotContains(cl(self.sup_ens).get("/produccion/importaciones/"), f"#{b.pk}<")
        r = cl(self.sup).post(f"/produccion/importaciones/{b.pk}/revertir/", {"reason": "misma área"})
        b.refresh_from_db()
        self.assertEqual(b.status, "reverted")

    def test_f6_label_jobs_and_datasets_scoped_by_area(self):
        from apps.core.samples import label_templates
        from apps.labels.models import LabelTemplate, LabelTemplateVersion
        from apps.labels.services import create_and_print

        tpl = label_templates()["caja"]
        t = LabelTemplate.objects.create(name="Caja SMT", code="caja-smt", owner=self.sup, draft=tpl, area=self.a["SMT"])
        v = LabelTemplateVersion.objects.create(template=t, version=1, definition=tpl, published_by=self.sup)
        job, _ = create_and_print(self.op, v, [{"work_order": "1"}], {"operador": "x"}, 1, None, "k-area")
        self.assertEqual(cl(self.sup).get(f"/etiquetas/trabajos/{job.pk}/").status_code, 200)
        self.assertEqual(cl(self.sup_ens).get(f"/etiquetas/trabajos/{job.pk}/").status_code, 403)
        r = cl(self.sup_ens).post(f"/etiquetas/api/trabajos/{job.pk}/reimprimir/", {"reason": "otra área", "idempotency_key": "z1"})
        self.assertEqual(r.status_code, 403)
        ds = dataset("smt-ds", "incremental", self.a["SMT"])
        eng_ens = user("eng_ens", Role.ENGINEER, ("ENS",))
        self.assertEqual(cl(eng_ens).get(f"/produccion/datasets/{ds.pk}/").status_code, 403)
        self.assertEqual(cl(self.eng).get(f"/produccion/datasets/{ds.pk}/").status_code, 200)

    def test_f7_batch_visible_through_row_areas(self):
        ds = dataset("mix", "incremental", self.a["SMT"], station="FINAL")
        csv = b"Fecha,Turno,Linea,OT,Estacion,Buenas,Area\r\n2026-11-02,T1,L,1,FINAL,3,ENS\r\n"
        b, _r, s = run_import(self.admin, ds, csv, "mix.csv", mapping={"qty_good": "Buenas"})
        self.assertEqual(s["created"], 1)
        self.assertEqual(cl(self.sup_ens).get(f"/produccion/importaciones/{b.pk}/").status_code, 200)
        op_pru = user("op_pru", Role.OPERATOR, ("PRU",))
        self.assertEqual(cl(op_pru).get(f"/produccion/importaciones/{b.pk}/").status_code, 403)
        self.assertNotContains(cl(self.op).get(f"/produccion/importaciones/{b.pk}/"), 'href="/produccion/importaciones/"')

    def test_f9_report_detail_renders(self):
        from datetime import time, timedelta

        from django.utils import timezone

        from apps.reports.models import ReportRun, ReportSchedule
        from apps.reports.services import create_run, generate_run, scheduler_tick

        run = generate_run(create_run("daily", {"period": "all"}, self.sup, ["pdf"]))
        self.assertEqual(cl(self.sup).get(f"/analitica/reportes/{run.pk}/").status_code, 200)
        sch = ReportSchedule.objects.create(name="S", kind="late", frequency="daily", time_of_day=time(5), formats=["csv"], created_by=self.sup,
                                            next_run_at=timezone.now() - timedelta(days=3))
        sch.recipients.add(self.op)
        scheduler_tick()
        srun = ReportRun.objects.get(schedule=sch)
        r = cl(self.op).get(f"/analitica/reportes/{srun.pk}/")
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "se omitieron")


class TemplateCompileTests(TestCase):
    def test_all_templates_compile(self):
        """Catches template syntax errors in pages that no other test opens."""
        from pathlib import Path

        from django.conf import settings
        from django.template.loader import get_template

        root = Path(settings.BASE_DIR) / "templates"
        names = [p.relative_to(root).as_posix() for p in root.rglob("*.html")]
        self.assertGreater(len(names), 50)
        for name in names:
            with self.subTest(template=name):
                get_template(name)


class OrderAreaTests(TestCase):
    def setUp(self):
        self.a = areas()
        self.sup_ens = user("sup_ens", Role.SUPERVISOR, ("ENS",))
        self.admin = user("root", superuser=True)

    def test_order_detail_hides_records_of_other_areas(self):
        """v1.1.0: an ENS order showed SMT records (and a batch link) to an ENS-only reader."""
        ds = dataset("inc2", "incremental", self.a["SMT"], station="FINAL")
        b, _r, _s = run_import(self.admin, ds, b"Fecha,Turno,Linea,OT,Estacion,Buenas\r\n2026-11-02,T1,L,OT-X,FINAL,3\r\n", "x.csv",
                               mapping={"qty_good": "Buenas"})
        wo = WorkOrder.objects.create(number="OT-X", area=self.a["ENS"], qty_planned=10)
        html = cl(self.sup_ens).get(f"/produccion/ordenes/{wo.pk}/").content.decode()
        self.assertNotIn(f"/produccion/importaciones/{b.pk}/", html)
        self.assertIn(f"/produccion/importaciones/{b.pk}/", cl(self.admin).get(f"/produccion/ordenes/{wo.pk}/").content.decode())
