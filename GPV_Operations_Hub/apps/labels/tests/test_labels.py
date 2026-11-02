"""Acceptance tests 19–21: label design/export/decoding, transactional serials, printer statuses."""
import io
import json
import socket
import threading
import time

from django.db import connection
from django.test import Client, TestCase, TransactionTestCase
from django.utils import timezone
from pypdf import PdfReader

from apps.core.models import Role
from apps.core.samples import label_templates
from apps.core.tests.helpers import areas, user
from apps.labels import printing
from apps.labels.models import LabelTemplate, LabelTemplateVersion, PrintJob, Printer, SerialCounter
from apps.labels.render import base_values, build, resolve, to_pdf, to_svg, to_zpl, zpl_escape
from apps.labels.services import create_and_print, reserve_serials


try:
    import zxingcpp  # optional independent reader (requirements-optional.txt)
except ImportError:  # pragma: no cover
    zxingcpp = None
NEEDS_READER = "Lector independiente opcional zxing-cpp no instalado (pip install -r requirements-optional.txt)"


def decode_pdf(pdf_bytes, page=0, dpi=600):
    import unittest

    import pypdfium2 as pdfium

    if zxingcpp is None:
        raise unittest.SkipTest(NEEDS_READER)

    pdf = pdfium.PdfDocument(io.BytesIO(pdf_bytes))
    img = pdf[page].render(scale=dpi / 72).to_pil()
    pdf.close()
    return sorted((r.format.name, r.text) for r in zxingcpp.read_barcodes(img))


def mk_template(owner, key="caja"):
    tpl = label_templates()[key]
    t = LabelTemplate.objects.create(name=tpl["name"], code=key, owner=owner, draft=tpl)
    v = LabelTemplateVersion.objects.create(template=t, version=1, definition=tpl, published_by=owner)
    t.published = v
    t.save()
    return t, v


class LabelDesignTests(TestCase):
    def setUp(self):
        areas()
        self.eng = user("eng", Role.ENGINEER, ("SMT",))
        SerialCounter.objects.create(name="serial-producto", prefix="GPV", pad=7)
        SerialCounter.objects.create(name="serial-trazabilidad", prefix="T", pad=8)
        self.c = Client(HTTP_HOST="127.0.0.1")
        self.c.force_login(self.eng)

    def test_19_edit_bind_export_decode(self):
        t, v = mk_template(self.eng)
        draft = t.draft
        draft["elements"].append({"id": "x1", "type": "text", "name": "Nuevo", "x": 60, "y": 69, "w": 38, "h": 5, "rot": 0, "content": "PN {part_number|strip_prefix:GPV-|upper}", "font_size": 8})
        r = self.c.post(f"/etiquetas/api/{t.pk}/borrador/", json.dumps({"draft": draft, "revision": 1}), content_type="application/json")
        self.assertEqual(r.status_code, 200, r.content)
        stale = self.c.post(f"/etiquetas/api/{t.pk}/borrador/", json.dumps({"draft": draft, "revision": 1}), content_type="application/json")
        self.assertEqual(stale.status_code, 409)
        record = {"work_order": "000123", "part_number": "GPV-pn-0451", "revision": "B", "lot": "L2611-07", "qty_good": "48", "customer": "Cliente Ñandú"}
        vals = base_values(record, {"operador": "Ana"})
        pdf, warnings = to_pdf(draft, [vals])
        box = PdfReader(io.BytesIO(pdf)).pages[0].mediabox
        self.assertAlmostEqual(float(box.width) / 72 * 25.4, 101.6, places=2)  # exact physical size
        self.assertAlmostEqual(float(box.height) / 72 * 25.4, 76.2, places=2)
        found = decode_pdf(pdf)
        self.assertIn(("Code128", "000123"), found)
        self.assertIn(("Code128", "L2611-07"), found)
        self.assertIn(("QRCode", "GPV-pn-0451;L2611-07;48"), found)
        text = PdfReader(io.BytesIO(pdf)).pages[0].extract_text()
        self.assertIn("CLIENTE ÑANDÚ", text)
        self.assertIn("PN PN-0451", text)
        svg, res = to_svg(draft, vals)
        self.assertIn('width="101.6mm"', svg)
        zpl, _w = to_zpl(draft, [vals])
        self.assertIn(b"^PW812", zpl)  # 101.6 mm at 203 dpi = 812 dots
        self.assertIn(b"^FD>;000123^FS", zpl)

    def test_traceability_and_identification_templates_decode(self):
        for key, expect in (("trazabilidad", "T00000042"), ("identificacion", "GPV0000042")):
            tpl = label_templates()[key]
            vals = base_values({"work_order": "000777", "part_number": "PN-9", "revision": "A", "lot": "L1"}, {}, serial=expect)
            pdf, warnings = to_pdf(tpl, [vals])
            self.assertEqual([w for w in warnings if "no cabe" in w], [], warnings)
            decoded = dict((b, a) for a, b in decode_pdf(pdf))
            self.assertEqual(decoded.get(expect), "Code128", decode_pdf(pdf))

    def test_overflow_reported_not_deformed(self):
        tpl = label_templates()["identificacion"]
        tpl["elements"][1]["w"] = 15  # too narrow for the code
        res = build(tpl, base_values({}, {}, serial="GPV0000001"))
        self.assertTrue(any("no se deforma" in w for w in res["warnings"]))
        g = next(g for g in res["prims"] if g["id"] == "b1")
        self.assertTrue(g["overflow"])
        self.assertEqual(g["module_dots"], 2)  # 0.25 mm at 203 dpi -> 2 dots, unchanged

    def test_transforms_and_zpl_escaping(self):
        out, missing = resolve("{a|strip_prefix:GPV-|upper}-{b|pad:5}-{c|default:N/A}-{z}", {"a": "GPV-ab", "b": "42", "c": ""})
        self.assertEqual(out, "AB-00042-N/A-")
        self.assertEqual(missing, ["z"])
        self.assertEqual(zpl_escape("a^XA~JR_ñ"), "a_5EXA_7EJR_5F_C3_B1")


class PrintingTests(TestCase):
    def setUp(self):
        areas()
        self.op = user("op", Role.OPERATOR, ("SMT",))
        self.t, self.v = mk_template(self.op)
        self.c = Client(HTTP_HOST="127.0.0.1")
        self.c.force_login(self.op)

    def test_20_double_click_same_key_one_job(self):
        recs = [{"work_order": "1", "part_number": "P", "lot": "L", "qty_good": "1", "customer": "C", "revision": "A"}]
        j1, created1 = create_and_print(self.op, self.v, recs, {"operador": "x"}, 2, None, "same-key")
        j2, created2 = create_and_print(self.op, self.v, recs, {"operador": "x"}, 2, None, "same-key")
        self.assertTrue(created1)
        self.assertFalse(created2)
        self.assertEqual(j1.pk, j2.pk)
        self.assertEqual(PrintJob.objects.count(), 1)
        self.assertEqual(j1.total_labels, 2)
        self.assertEqual(j1.status, PrintJob.Status.GENERATED)
        self.assertEqual(len(PdfReader(io.BytesIO(j1.output_pdf.path.read_bytes())).pages), 2)

    def test_print_api_requires_confirmed_total(self):
        r = self.c.post(f"/etiquetas/api/{self.t.pk}/imprimir/", {"source": "manual", "mode": "single", "copies": "3", "prompt_operador": "Ana",
                                                                   "confirm_total": "1", "idempotency_key": "k1"})
        self.assertEqual(r.status_code, 400)
        r = self.c.post(f"/etiquetas/api/{self.t.pk}/imprimir/", {"source": "manual", "mode": "single", "copies": "3", "prompt_operador": "Ana",
                                                                   "confirm_total": "3", "idempotency_key": "k1"})
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual(r.json()["data"]["status"], "Generado")

    def test_reprint_requires_permission_and_reason(self):
        job, _ = create_and_print(self.op, self.v, [{"work_order": "1"}], {"operador": "x"}, 1, None, "k-r")
        r = self.c.post(f"/etiquetas/api/trabajos/{job.pk}/reimprimir/", {"reason": "dañada", "idempotency_key": "k-r2"})
        self.assertEqual(r.status_code, 403)
        sup = user("sup", Role.SUPERVISOR, ("SMT",))
        c2 = Client(HTTP_HOST="127.0.0.1")
        c2.force_login(sup)
        self.assertEqual(c2.post(f"/etiquetas/api/trabajos/{job.pk}/reimprimir/", {"reason": "x", "idempotency_key": "k-r3"}).status_code, 400)
        r = c2.post(f"/etiquetas/api/trabajos/{job.pk}/reimprimir/", {"reason": "Etiqueta dañada en línea", "idempotency_key": "k-r4"})
        self.assertEqual(r.status_code, 200, r.content)
        re = PrintJob.objects.get(reprint_of=job)
        self.assertEqual(re.reprint_reason, "Etiqueta dañada en línea")
        self.assertEqual(re.serials, job.serials)

    def test_21_connection_failure_and_ambiguous_send(self):
        # a registered, validated printer whose port refuses connections
        s = socket.socket()
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
        s.close()
        p = Printer.objects.create(name="Zebra prueba", kind="zpl_tcp", language="zpl", host="127.0.0.1", port=port, dpi=203,
                                   enabled=True, validated_at=timezone.now())
        job, _ = create_and_print(self.op, self.v, [{"work_order": "1"}], {"operador": "x"}, 1, p, "k-fail")
        self.assertEqual(job.status, PrintJob.Status.FAILED)
        self.assertIn("No se pudo conectar", job.error)
        # a server that accepts and immediately resets the connection after a few bytes -> ambiguous
        srv = socket.socket()
        srv.bind(("127.0.0.1", 0))
        srv.listen(1)
        p.port = srv.getsockname()[1]
        p.save()

        def accept_and_reset():
            conn, _a = srv.accept()
            conn.recv(10)
            conn.setsockopt(socket.SOL_SOCKET, socket.SO_LINGER, b"\x01\x00\x00\x00\x00\x00\x00\x00")
            conn.close()

        th = threading.Thread(target=accept_and_reset)
        th.start()
        big = [{"work_order": str(i)} for i in range(400)]
        job2, _ = create_and_print(self.op, self.v, big, {"operador": "x"}, 1, p, "k-amb")
        th.join(5)
        srv.close()
        self.assertIn(job2.status, (PrintJob.Status.UNKNOWN,))
        self.assertNotEqual(job2.status, PrintJob.Status.CONFIRMED)
        self.assertEqual(PrintJob.objects.filter(reprint_of=job2).count(), 0)  # no automatic reprint
        # a successful raw send is still "unknown physical state", never "printed"
        srv2 = socket.socket()
        srv2.bind(("127.0.0.1", 0))
        srv2.listen(1)
        p.port = srv2.getsockname()[1]
        p.save()
        got = []

        def sink():
            conn, _a = srv2.accept()
            data = b""
            while True:
                chunk = conn.recv(65536)
                if not chunk:
                    break
                data += chunk
            got.append(data)
            conn.close()

        th = threading.Thread(target=sink)
        th.start()
        job3, _ = create_and_print(self.op, self.v, [{"work_order": "9"}], {"operador": "x"}, 1, p, "k-ok")
        th.join(5)
        srv2.close()
        self.assertEqual(job3.status, PrintJob.Status.UNKNOWN)
        self.assertTrue(got[0].startswith(b"^XA"))
        self.assertIn("no confirma", job3.events.last().detail)

    def test_direct_printing_disabled_until_validated(self):
        p = Printer.objects.create(name="Sin validar", kind="zpl_tcp", language="zpl", host="127.0.0.1", port=9100, dpi=203)
        from apps.core.jobs import UserFacingError

        with self.assertRaises(UserFacingError):
            create_and_print(self.op, self.v, [{"work_order": "1"}], {"operador": "x"}, 1, p, "k-nv")
        # operators cannot register printers / arbitrary IPs
        self.assertEqual(self.c.post("/etiquetas/impresoras/", {"name": "x", "kind": "zpl_tcp", "host": "10.0.0.5", "port": 9100}).status_code, 403)


class SerialConcurrencyTests(TransactionTestCase):
    def test_20_concurrent_serials_unique(self):
        SerialCounter.objects.create(name="c1", prefix="S", pad=6)
        results, errors = [], []

        def worker():
            try:
                for _ in range(5):
                    results.extend(reserve_serials("c1", 3))
            except Exception as exc:  # pragma: no cover
                errors.append(exc)
            finally:
                connection.close()

        ts = [threading.Thread(target=worker) for _ in range(6)]
        for t in ts:
            t.start()
        for t in ts:
            t.join()
        self.assertEqual(errors, [])
        self.assertEqual(len(results), 90)
        self.assertEqual(len(set(results)), 90)
        self.assertEqual(SerialCounter.objects.get(name="c1").next_value, 91)
