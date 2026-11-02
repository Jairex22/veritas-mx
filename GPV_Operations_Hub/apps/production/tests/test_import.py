"""Acceptance tests 1–5 (imports) plus revert, compensation and formula handling."""
from decimal import Decimal

from django.test import TestCase

from apps.core.models import Role
from apps.core.tests.helpers import areas, dataset, run_import, user, xlsx_bytes
from apps.production.models import ImportBatch, ProductionRecord, WorkOrder


class ImportTests(TestCase):
    def setUp(self):
        self.a = areas()
        self.eng = user("ing", Role.ENGINEER, ("SMT", "ENS"))
        self.inc = dataset("inc", "incremental", self.a["SMT"], station="FINAL")

    # 1 ------------------------------------------------------------
    def test_01_xlsx_multisheet_and_spanish_csv(self):
        plan = dataset("plan", "plan", self.a["SMT"])
        data = xlsx_bytes({
            "Portada": [["Archivo sintético"]],
            "Plan": [["OT", "Meta", "Cliente", "Vencimiento"], ["000101", 100, "Ñandú", "2026-11-20"], ["000102", 200, "Peña y Cía", "2026-11-21"]],
        })
        b, res, stats = run_import(self.eng, plan, data, "plan.xlsx", sheet="Plan")
        self.assertEqual([s["name"] for s in b.analysis["sheets"]], ["Portada", "Plan"])
        self.assertEqual(stats["created"], 2)
        self.assertEqual(WorkOrder.objects.get(number="000101").customer, "Ñandú")

        csv = ('Fecha;Turno;Línea;OT;Estación;Buenas;Observaciones\r\n'
               '02/11/2026;T1;SMT-1;000101;FINAL;10;"Ajuste; boquilla «A»"\r\n'
               '15/11/2026;T2;SMT-1;000101;FINAL;5;"Paro\nde 10 min"\r\n').encode("cp1252")
        b, res, stats = run_import(self.eng, self.inc, csv, "turnos.csv", mapping={"qty_good": "Buenas"})
        self.assertEqual(b.analysis["encoding"], "cp1252")
        self.assertEqual(b.analysis["delimiter"], ";")
        self.assertEqual(stats["created"], 2, res["errors"])
        notes = set(ProductionRecord.objects.values_list("notes", flat=True))
        self.assertIn("Ajuste; boquilla «A»", notes)
        self.assertIn("Paro\nde 10 min", notes)
        # 15/11 proves DD/MM for the whole column, so 02/11 is 2 November (not 11 February)
        self.assertTrue(ProductionRecord.objects.filter(date="2026-11-02").exists())

    # 2 ------------------------------------------------------------
    def test_02_different_headers_same_schema_and_invalid_date_row(self):
        es = "Fecha,Turno,Línea,Orden,Estación,Piezas buenas\r\n2026-11-02,T1,SMT-1,000201,FINAL,7\r\n2026-02-31,T1,SMT-1,000202,FINAL,3\r\n"
        en = "Date,Shift,Line,Work Order,Station,Good\r\n2026-11-02,T2,SMT-1,000203,FINAL,4\r\n"
        b1, r1, _ = run_import(self.eng, self.inc, es.encode(), "es.csv", mapping={"qty_good": "Piezas buenas"}, options={"allow_partial": True})
        b2, r2, _ = run_import(self.eng, self.inc, en.encode(), "en.csv", mapping={"qty_good": "Good"})
        self.assertEqual(b1.mapping["work_order"], "Orden")
        self.assertEqual(b2.mapping["work_order"], "Work Order")
        err = r1["errors"]
        self.assertEqual(len(err), 1)
        self.assertEqual(err[0]["row"], 3)  # spreadsheet row of the invalid date (header is row 1)
        self.assertEqual(err[0]["column"], "Fecha")
        self.assertIn("fecha válida", err[0]["message"])
        self.assertEqual(ProductionRecord.objects.filter(dataset=self.inc).count(), 2)
        self.assertIsNotNone(b1.error_file)  # downloadable error CSV

    # 3 ------------------------------------------------------------
    def test_03_reimport_same_file_does_not_duplicate(self):
        csv = b"Fecha,Turno,Linea,OT,Estacion,Buenas\r\n2026-11-02,T1,SMT-1,000301,FINAL,10\r\n2026-11-02,T2,SMT-1,000301,FINAL,12\r\n"
        _b, _r, s1 = run_import(self.eng, self.inc, csv, "a.csv", mapping={"qty_good": "Buenas"}, mode="append")
        b2, r2, s2 = run_import(self.eng, self.inc, csv, "a.csv", mapping={"qty_good": "Buenas"}, mode="append")
        self.assertEqual(s1["created"], 2)
        self.assertEqual(s2["created"], 0)
        self.assertEqual(s2["skipped"] + s2["unchanged"], 2)
        self.assertEqual(ProductionRecord.objects.filter(dataset=self.inc, is_current=True).count(), 2)
        self.assertTrue(b2.analysis["previous_imports"], "the repeated file hash must be reported")
        # upsert also does not duplicate
        _b, _r, s3 = run_import(self.eng, self.inc, csv, "a.csv", mapping={"qty_good": "Buenas"}, mode="upsert")
        self.assertEqual(s3["unchanged"], 2)
        self.assertEqual(ProductionRecord.objects.filter(dataset=self.inc).count(), 2)

    # 4 ------------------------------------------------------------
    def test_04_snapshot_replaces_not_sums(self):
        from apps.production.metrics import Filters, order_rows

        WorkOrder.objects.create(number="000401", area=self.a["EMP"], qty_planned=100)
        snap = dataset("snap", "snapshot", self.a["EMP"], station="EMPAQUE")
        packer = user("emp", Role.ENGINEER, ("EMP",))
        h = "Fecha hora,OT,Estacion,Acumulado\r\n"
        run_import(packer, snap, (h + "2026-11-02 10:00,000401,EMPAQUE,40\r\n").encode(), "s10.csv", mapping={"qty_good": "Acumulado"})
        _b, _r, s = run_import(packer, snap, (h + "2026-11-02 14:00,000401,EMPAQUE,70\r\n").encode(), "s14.csv", mapping={"qty_good": "Acumulado"})
        self.assertEqual(s["superseded"], 1)
        rows, _w = order_rows(packer, Filters(period="all"))
        self.assertEqual(rows[0]["good"], Decimal("70"))  # not 110
        self.assertEqual(ProductionRecord.objects.filter(dataset=snap).count(), 2)  # history kept
        # an older capture never replaces a newer one
        _b, r, _s = run_import(packer, snap, (h + "2026-11-02 09:00,000401,EMPAQUE,20\r\n").encode(), "s09.csv", mapping={"qty_good": "Acumulado"},
                               options={"allow_partial": True})
        self.assertEqual(r["stats"]["rejected"], 1)
        rows, _w = order_rows(packer, Filters(period="all"))
        self.assertEqual(rows[0]["good"], Decimal("70"))

    # 5 ------------------------------------------------------------
    def test_05_serials_keep_leading_zeros_and_long_digits(self):
        ser = dataset("ser", "serial", self.a["SMT"])
        csv = "Serial,Estacion,Intento,Resultado\r\n000000000000012345,ICT,1,PASS\r\n001234567890123456789,ICT,1,FAIL\r\n".encode()
        _b, r, s = run_import(self.eng, ser, csv, "s.csv")
        self.assertEqual(s["created"], 2, r["errors"])
        self.assertEqual(set(ProductionRecord.objects.values_list("serial", flat=True)), {"000000000000012345", "001234567890123456789"})
        # XLSX: text cells keep zeros; numeric cell with zero-padded format is restored; >15-digit number is flagged
        import io

        import openpyxl

        wb = openpyxl.Workbook()
        ws = wb.active
        ws.append(["Serial", "Estacion", "Intento", "Resultado"])
        ws.append(["000777", "ICT", 1, "PASS"])
        ws.append([555, "ICT", 1, "PASS"])
        ws["A3"].number_format = "000000"
        ws.append([1.23456789012345e17, "ICT", 1, "PASS"])
        buf = io.BytesIO()
        wb.save(buf)
        ser2 = dataset("ser2", "serial", self.a["SMT"])
        _b, r, s = run_import(self.eng, ser2, buf.getvalue(), "s.xlsx", options={"allow_partial": True})
        self.assertEqual(s["created"], 2)
        self.assertEqual(set(ProductionRecord.objects.filter(dataset=ser2).values_list("serial", flat=True)), {"000777", "000555"})
        self.assertEqual(r["errors"][0]["row"], 4)
        self.assertIn("15", r["errors"][0]["message"] + r["errors"][0]["value"])
        # scientific notation in CSV is reported as damaged, never "repaired"
        ser3 = dataset("ser3", "serial", self.a["SMT"])
        _b, r, _s = run_import(self.eng, ser3, b"Serial,Estacion,Intento,Resultado\r\n1.23457E+17,ICT,1,PASS\r\n", "d.csv", commit=False)
        self.assertIn("notación científica", r["errors"][0]["message"])

    # extras -------------------------------------------------------
    def test_ambiguous_dates_require_choice(self):
        csv = b"Fecha,Turno,Linea,OT,Estacion,Buenas\r\n03/04/2026,T1,SMT-1,1,FINAL,1\r\n"
        _b, r, _s = run_import(self.eng, self.inc, csv, "amb.csv", mapping={"qty_good": "Buenas"}, commit=False)
        self.assertIn("ambigua", r["errors"][0]["message"])
        _b, r, s = run_import(self.eng, self.inc, csv, "amb.csv", mapping={"qty_good": "Buenas"}, options={"date_order": "MDY"})
        self.assertEqual(s["created"], 1)
        self.assertTrue(ProductionRecord.objects.filter(date="2026-03-04").exists())

    def test_formula_without_cached_value_is_computed_or_reported(self):
        plan = dataset("plan2", "plan", self.a["SMT"])
        data = xlsx_bytes({"Plan": [["OT", "Base", "Meta"], ["000901", 50, "=B2*2"], ["000902", 10, "=FORMULAX(B3)"]]})
        _b, r, s = run_import(self.eng, plan, data, "f.xlsx", mapping={"qty_planned": "Meta"}, options={"allow_partial": True})
        self.assertEqual(WorkOrder.objects.get(number="000901").qty_planned, Decimal("100"))
        self.assertFalse(WorkOrder.objects.filter(number="000902").exists())  # never converted to 0
        self.assertIn("Fórmula sin valor", r["errors"][0]["message"])

    def test_revert_keeps_later_changes(self):
        from apps.production.importer import revert

        h = "Fecha,Turno,Linea,OT,Estacion,Buenas\r\n"
        b1, _r, _s = run_import(self.eng, self.inc, (h + "2026-11-02,T1,L,1,FINAL,10\r\n2026-11-02,T2,L,1,FINAL,5\r\n").encode(), "1.csv",
                                mapping={"qty_good": "Buenas"})
        run_import(self.eng, self.inc, (h + "2026-11-02,T1,L,1,FINAL,99\r\n").encode(), "2.csv", mapping={"qty_good": "Buenas"})
        sup = user("sup", Role.SUPERVISOR, ("SMT",))
        res = revert(b1, sup, "prueba de reversión")
        self.assertEqual(len(res["conflicts"]), 1)  # T1 changed later -> kept
        self.assertEqual(ProductionRecord.objects.get(shift="T1").qty_good, Decimal("99"))
        self.assertFalse(ProductionRecord.objects.filter(shift="T2").exists())
        b1.refresh_from_db()
        self.assertEqual(b1.status, ImportBatch.Status.PARTIAL_REVERTED)

    def test_failure_mid_import_is_compensated(self):
        from unittest import mock

        from apps.production import importer

        h = "Fecha,Turno,Linea,OT,Estacion,Buenas\r\n"
        rows = "".join(f"2026-11-02,T1,L,{i},FINAL,1\r\n" for i in range(30))
        calls = {"n": 0}
        real = importer._apply_record_chunk

        def flaky(*a, **k):
            calls["n"] += 1
            if calls["n"] == 2:
                raise RuntimeError("disk full (simulated)")
            return real(*a, **k)

        with self.settings(GPV={**__import__("django.conf").conf.settings.GPV, "IMPORT_CHUNK_ROWS": 10}), mock.patch.object(importer, "_apply_record_chunk", flaky):
            with self.assertRaises(RuntimeError):
                run_import(self.eng, self.inc, (h + rows).encode(), "big.csv", mapping={"qty_good": "Buenas"})
        b = ImportBatch.objects.latest("id")
        self.assertEqual(b.status, ImportBatch.Status.FAILED)
        self.assertIn("revirtieron", b.error_message)
        self.assertEqual(ProductionRecord.objects.filter(dataset=self.inc).count(), 0)

    def test_area_permission_enforced_on_import(self):
        op = user("op_ens", Role.ENGINEER, ("ENS",))
        csv = b"Fecha,Turno,Linea,OT,Estacion,Buenas,Area\r\n2026-11-02,T1,L,1,FINAL,1,SMT\r\n"
        _b, r, _s = run_import(op, self.inc, csv, "x.csv", mapping={"qty_good": "Buenas"}, commit=False)
        self.assertIn("permiso", r["errors"][0]["message"])
