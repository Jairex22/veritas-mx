"""Acceptance tests 6–8: KPI rules and consistency across table, dashboard API, PDF and Excel."""
import io
import json
from datetime import timedelta
from decimal import Decimal

from django.test import Client, TestCase
from django.utils import timezone

from apps.core.models import Role
from apps.core.tests.helpers import areas, dataset, run_import, user
from apps.production.metrics import Filters, fpy, grouped_compliance, kpi_summary, oee, order_rows, pending_total
from apps.production.models import ProductionRecord, WorkOrder


class MetricsTests(TestCase):
    def setUp(self):
        self.a = areas()
        self.sup = user("sup", Role.SUPERVISOR, ("SMT",))
        self.inc = dataset("inc", "incremental", self.a["SMT"], station="FINAL")
        due = timezone.now() + timedelta(days=3)
        WorkOrder.objects.create(number="A", area=self.a["SMT"], qty_planned=100, due=due, line="L1")
        WorkOrder.objects.create(number="B", area=self.a["SMT"], qty_planned=200, due=due, line="L2")
        csv = ("Fecha,Turno,Linea,OT,Estacion,Buenas,Rechazo,Scrap\r\n"
               "2026-11-02,T1,L1,A,FINAL,80,2,1\r\n2026-11-02,T1,L2,B,FINAL,150,3,0\r\n"
               "2026-11-02,T1,L2,B,ICT,999,0,0\r\n")  # non-finished station must not count
        run_import(self.sup, self.inc, csv.encode(), "p.csv", mapping={"qty_good": "Buenas", "qty_reject": "Rechazo", "qty_scrap": "Scrap"})

    # 6 ------------------------------------------------------------
    def test_06_grouped_compliance_is_ratio_of_sums(self):
        rows, _ = order_rows(self.sup, Filters(period="all"))
        comp = grouped_compliance(rows)
        self.assertEqual(comp["status"], "ok")
        self.assertEqual(comp["value"], 76.67)  # 230 / 300, not (80% + 75%) / 2 = 77.5
        self.assertEqual((comp["numerator"], comp["denominator"]), (230.0, 300.0))
        self.assertEqual(pending_total(rows), Decimal("70"))

    def test_06b_excess_does_not_cancel_shortfall(self):
        WorkOrder.objects.create(number="C", area=self.a["SMT"], qty_planned=10, line="L1")
        csv = "Fecha,Turno,Linea,OT,Estacion,Buenas\r\n2026-11-02,T2,L1,C,FINAL,50\r\n"
        run_import(self.sup, self.inc, csv.encode(), "c.csv", mapping={"qty_good": "Buenas"})
        rows, _ = order_rows(self.sup, Filters(period="all"))
        self.assertEqual(pending_total(rows), Decimal("70"))  # C contributes 0, not -40

    # 7 ------------------------------------------------------------
    def test_07_not_calculable_and_insufficient(self):
        WorkOrder.objects.create(number="Z", area=self.a["SMT"], qty_planned=0)
        rows, _ = order_rows(self.sup, Filters(period="all", work_order="Z"))
        self.assertEqual(rows[0]["compliance"]["status"], "not_calculable")
        self.assertIsNone(rows[0]["pending"])
        self.assertEqual(grouped_compliance(rows)["status"], "not_calculable")
        self.assertEqual(fpy(self.sup, Filters(period="all"))["status"], "insufficient")
        self.assertEqual(oee(self.sup, Filters(period="all"))["status"], "insufficient")
        html = Client(HTTP_HOST="127.0.0.1")
        html.force_login(self.sup)
        r = html.get("/produccion/?period=all&work_order=Z")
        self.assertContains(r, "No calculable")
        r = html.get("/analitica/api/dashboard/?period=all")
        k = r.json()["data"]["kpis"]
        self.assertEqual(k["fpy"]["status"], "insufficient")
        self.assertEqual(k["oee"]["status"], "insufficient")

    def test_07b_fpy_uses_first_attempt_only(self):
        ser = dataset("ser", "serial", self.a["SMT"])
        csv = ("Serial,Estacion,Intento,Resultado,Fecha\r\nS1,ICT,1,PASS,2026-11-02\r\nS2,ICT,1,FAIL,2026-11-02\r\n"
               "S2,ICT,2,PASS,2026-11-02\r\nS3,ICT,1,PASS,2026-11-02\r\nS4,ICT,1,FAIL,2026-11-02\r\n")
        run_import(self.sup, ser, csv.encode(), "s.csv")
        m = fpy(self.sup, Filters(period="all"))
        self.assertEqual(m["value"], 50.0)  # 2 of 4 first attempts passed (repair of S2 does not count)
        # without attempt information it refuses to deduce FPY
        ProductionRecord.objects.filter(dataset=ser).update(attempt=None)
        self.assertEqual(fpy(self.sup, Filters(period="all"))["status"], "insufficient")

    def test_07c_mixed_units_not_summed(self):
        WorkOrder.objects.create(number="BOX", area=self.a["SMT"], qty_planned=10, unit="caja")
        rows, _ = order_rows(self.sup, Filters(period="all"))
        self.assertEqual(grouped_compliance(rows)["status"], "not_calculable")
        rows, _ = order_rows(self.sup, Filters(period="all", unit="pz"))
        self.assertEqual(grouped_compliance(rows)["value"], 76.67)

    # 8 ------------------------------------------------------------
    def test_08_table_dashboard_pdf_excel_match(self):
        import openpyxl
        from pypdf import PdfReader

        from apps.reports.models import ReportRun
        from apps.reports.services import create_run, generate_run

        f = {"period": "all"}
        table = order_rows(self.sup, Filters.from_dict(f))[0]
        c = Client(HTTP_HOST="127.0.0.1")
        c.force_login(self.sup)
        api = c.get("/analitica/api/dashboard/", f).json()["data"]["kpis"]
        run = create_run("daily", f, self.sup, ["pdf", "xlsx", "csv"])
        run = generate_run(run)
        self.assertEqual(run.status, ReportRun.Status.DONE)
        snap_comp = next(k for k in run.snapshot["kpis"] if k["label"] == "Cumplimiento agrupado")
        self.assertEqual(api["compliance"]["value"], 76.67)
        self.assertEqual(snap_comp["value"], 76.67)
        self.assertEqual(api["pending_total"], 70.0)
        outputs = {o.fmt: o.file.path.read_bytes() for o in run.outputs.all()}
        pdf_text = "".join(p.extract_text() for p in PdfReader(io.BytesIO(outputs["pdf"])).pages)
        self.assertIn("76.67", pdf_text)
        self.assertIn("230 / 300", pdf_text)
        wb = openpyxl.load_workbook(io.BytesIO(outputs["xlsx"]))
        ws = wb["Resumen"]
        vals = {ws.cell(r, 1).value: ws.cell(r, 2).value for r in range(1, ws.max_row + 1)}
        self.assertEqual(vals["Cumplimiento agrupado"], 76.67)
        self.assertEqual(vals["Pendiente"], 70.0)
        detail = wb["Avance por orden"]
        excel_good = {detail.cell(r, 1).value: detail.cell(r, 8).value for r in range(2, detail.max_row + 1)}
        self.assertEqual(excel_good, {r["number"]: float(r["good"]) for r in table})
        csv_text = outputs["csv"].decode("utf-8-sig")
        self.assertIn("A,", csv_text)
        # the selection export uses the same layer
        x = c.get("/analitica/exportar/", {"period": "all", "fmt": "xlsx", "table": "orders"})
        wb2 = openpyxl.load_workbook(io.BytesIO(x.content))
        ws2 = wb2["Órdenes"]
        self.assertEqual({ws2.cell(r, 1).value: ws2.cell(r, 8).value for r in range(2, ws2.max_row + 1)}, excel_good)
        # filters change all outputs consistently
        api_l1 = c.get("/analitica/api/dashboard/", {"period": "all", "line": "L1"}).json()["data"]["kpis"]
        self.assertEqual(api_l1["compliance"]["value"], 80.0)
        self.assertEqual(kpi_summary(self.sup, Filters(period="all", line="L1"))["compliance"]["value"], 80.0)

    def test_area_isolation_in_metrics(self):
        WorkOrder.objects.create(number="ENS-1", area=self.a["ENS"], qty_planned=50)
        other = user("ens_only", Role.SUPERVISOR, ("ENS",))
        rows, _ = order_rows(other, Filters(period="all"))
        self.assertEqual([r["number"] for r in rows], ["ENS-1"])
        c = Client(HTTP_HOST="127.0.0.1")
        c.force_login(other)
        wo = WorkOrder.objects.get(number="A")
        self.assertEqual(c.get(f"/produccion/ordenes/{wo.pk}/").status_code, 403)
