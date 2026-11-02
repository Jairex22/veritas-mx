"""Acceptance tests 9–10: formula engine and concurrent edit conflicts."""
import json

from django.test import Client, TestCase

from apps.core.models import Role
from apps.core.tests.helpers import areas, user
from apps.sheets import engine
from apps.sheets.formula import evaluate_workbook, shift_formula
from apps.sheets.models import Workbook


def wb(cells, name="Hoja1", extra=None):
    sheets = [{"name": name, "nrows": 50, "ncols": 10, "cells": {k: {"v": v} for k, v in cells.items()}}]
    for n, c in (extra or {}).items():
        sheets.append({"name": n, "nrows": 50, "ncols": 10, "cells": {k: {"v": v} for k, v in c.items()}})
    return {"sheets": sheets}


class FormulaTests(TestCase):
    def calc(self, cells, **kw):
        return {a: (v.get("e") or v.get("v")) for a, v in engine.recalc(wb(cells, **kw))["values"]["Hoja1"].items()}

    def test_09_supported_functions(self):
        r = self.calc({
            "A1": "10", "A2": "20", "A3": "30", "B1": "x", "B2": "y", "B3": "x",
            "C1": "=SUMA(A1:A3)", "C2": "=SUM(A1:A3)", "C3": "=PROMEDIO(A1:A3)", "C4": "=MIN(A1:A3)", "C5": "=MAX(A1:A3)",
            "C6": "=CONTAR(A1:B3)", "C7": '=SI(A1>5;"alto";"bajo")', "C8": '=SUMAR.SI(B1:B3;"x";A1:A3)', "C9": '=CONTAR.SI(B1:B3,"x")',
            "C10": "=BUSCARV(20;A1:B3;2;FALSO)", "C11": '=BUSCARX("y";B1:B3;A1:A3)', "C12": "=(A1+A2)*A3/2-1", "C13": "=A1&\"-\"&B1",
            "C14": "=Hoja2!A1*2", "C15": "=50%*A1", "C16": '=XLOOKUP("zz";B1:B3;A1:A3;"no")', "C17": "=IF(AND(A1>0,A2>0),1,0)",
        }, extra={"Hoja2": {"A1": "21"}})
        self.assertEqual(r["C1"], 60.0); self.assertEqual(r["C2"], 60.0); self.assertEqual(r["C3"], 20.0)
        self.assertEqual(r["C4"], 10.0); self.assertEqual(r["C5"], 30.0); self.assertEqual(r["C6"], 3.0)
        self.assertEqual(r["C7"], "alto"); self.assertEqual(r["C8"], 40.0); self.assertEqual(r["C9"], 2.0)
        self.assertEqual(r["C10"], "y"); self.assertEqual(r["C11"], 20.0); self.assertEqual(r["C12"], 449.0)
        self.assertEqual(r["C13"], "10-x"); self.assertEqual(r["C14"], 42.0); self.assertEqual(r["C15"], 5.0)
        self.assertEqual(r["C16"], "no"); self.assertEqual(r["C17"], 1.0)

    def test_09_errors_cycles_div0_unknown(self):
        r = self.calc({"A1": "=A2+1", "A2": "=A1", "B1": "=1/0", "B2": "=FOO(1)", "B3": "=B1+1", "B4": "=IFERROR(1/0;7)",
                       "B5": "=VLOOKUP(99;A1:A2;1;FALSE)", "B6": "=Hoja9!A1", "B7": '="a"+1'})
        self.assertEqual(r["A1"], "#CIRC!"); self.assertEqual(r["A2"], "#CIRC!")
        self.assertEqual(r["B1"], "#DIV/0!"); self.assertEqual(r["B2"], "#NAME?"); self.assertEqual(r["B3"], "#DIV/0!")
        self.assertEqual(r["B4"], 7.0); self.assertEqual(r["B5"], "#N/A"); self.assertEqual(r["B6"], "#REF!"); self.assertEqual(r["B7"], "#VALUE!")
        res = engine.recalc(wb({"A1": "=FOO(1)"}))
        self.assertIn("FOO", res["warnings"][0])

    def test_09_no_code_execution(self):
        r = self.calc({"A1": "=__import__('os').system('echo hi')", "A2": '=WEBSERVICE("http://x")', "A3": "=eval(1)"})
        self.assertTrue(all(str(v).startswith("#") for v in r.values()))

    def test_09_copy_and_structure_adjust_references(self):
        self.assertEqual(shift_formula("=A1+$B$1+B$2+$C3", 1, 1), "=B2+$B$1+C$2+$C4")
        data = wb({"A1": "1", "A2": "2", "A3": "=SUM(A1:A2)", "B1": "=A2*10"})
        data = engine.structure(data, "Hoja1", "row", 1, 1)  # insert a row before row 2
        cells = data["sheets"][0]["cells"]
        self.assertEqual(cells["A4"]["v"], "=SUM(A1:A3)")
        self.assertEqual(cells["B1"]["v"], "=A3*10")
        data = engine.structure(data, "Hoja1", "row", 2, -1)  # delete row 3 (the "2")
        self.assertEqual(data["sheets"][0]["cells"]["B1"]["v"], "=#REF!*10")
        data = engine.rename_sheet(wb({"A1": "=Datos!A1"}, extra={"Datos": {"A1": "5"}}), "Datos", "Mis datos")
        self.assertEqual(data["sheets"][0]["cells"]["A1"]["v"], "='Mis datos'!A1")

    def test_server_matches_python_engine_for_reports(self):
        data = wb({"A1": "2", "A2": "3", "A3": "=A1*A2"})
        grid = engine.computed_grid(data, "Hoja1")
        self.assertEqual(grid[2][0], 6.0)
        self.assertIn(b"6", engine.to_csv(data, "Hoja1"))

    def test_pivot(self):
        data = wb({"A1": "Línea", "B1": "Buenas", "A2": "L1", "B2": "5", "A3": "L1", "B3": "7", "A4": "L2", "B4": "1"})
        t = engine.pivot(data, "Hoja1", "Línea", "Buenas", "sum")
        self.assertEqual(t[1:], [["L1", 12.0], ["L2", 1.0]])
        t = engine.pivot(data, "Hoja1", "Línea", "Buenas", "count")
        self.assertEqual(t[1][1], 2.0)

    def test_xlsx_roundtrip_types_and_warnings(self):
        import io

        import openpyxl

        w = openpyxl.Workbook()
        ws = w.active
        ws["A1"] = "000123"
        ws["A1"].number_format = "@"
        ws["A2"] = 0.25
        ws["A2"].number_format = "0%"
        ws["A3"] = "=SUMPRODUCT(A2:A2)"
        buf = io.BytesIO()
        w.save(buf)
        data, warnings = engine.from_xlsx(buf.getvalue())
        cells = data["sheets"][0]["cells"]
        self.assertEqual(cells["A1"], {"v": "000123", "fmt": "text"})
        self.assertEqual(cells["A2"]["fmt"], "percent")
        self.assertTrue(any("SUMPRODUCT" in x for x in warnings))
        out = openpyxl.load_workbook(io.BytesIO(engine.to_xlsx(data))).active
        self.assertEqual(out["A1"].value, "000123")
        self.assertEqual(out["A1"].data_type, "s")
        text_formula = engine.to_xlsx({"sheets": [{"name": "H", "cells": {"A1": {"v": "=1+1", "fmt": "text"}}}]})
        self.assertEqual(openpyxl.load_workbook(io.BytesIO(text_formula)).active["A1"].data_type, "s")


class ConflictTests(TestCase):
    def setUp(self):
        areas()
        self.u1 = user("ana", Role.ENGINEER, ("SMT",))
        self.u2 = user("beto", Role.ENGINEER, ("SMT",))
        self.wb = Workbook.objects.create(name="Compartida", owner=self.u1, data=wb({"A1": "1"}), shared=True,
                                          area=self.u1.profile.areas.first())

    def post(self, u, data, base):
        c = Client(HTTP_HOST="127.0.0.1")
        c.force_login(u)
        return c.post(f"/hojas/api/{self.wb.pk}/guardar/", json.dumps({"data": data, "base_version": base}), content_type="application/json")

    def test_10_concurrent_edit_conflict(self):
        r1 = self.post(self.u1, wb({"A1": "ana"}), 1)
        self.assertEqual(r1.status_code, 200)
        r2 = self.post(self.u2, wb({"A1": "beto"}), 1)  # beto started from version 1 too
        self.assertEqual(r2.status_code, 409)
        self.assertTrue(r2.json()["conflict"])
        self.wb.refresh_from_db()
        self.assertEqual(self.wb.data["sheets"][0]["cells"]["A1"]["v"], "ana")  # no silent overwrite
        self.assertEqual(self.wb.version, 2)
        c = Client(HTTP_HOST="127.0.0.1")
        c.force_login(self.u2)
        r = c.post(f"/hojas/api/{self.wb.pk}/copia/", json.dumps({"data": wb({"A1": "beto"})}), content_type="application/json")
        self.assertEqual(r.status_code, 200)
        self.assertTrue(Workbook.objects.filter(owner=self.u2, data__sheets__0__cells__A1__v="beto").exists())

    def test_protected_columns_server_side(self):
        d = wb({"A1": "1"})
        d["sheets"][0]["protected"] = ["A"]
        self.post(self.u1, d, 1)
        d2 = wb({"A1": "cambiado"})
        d2["sheets"][0]["protected"] = ["A"]
        r = self.post(self.u2, d2, 2)
        self.assertEqual(r.status_code, 403)
