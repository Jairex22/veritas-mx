"""Acceptance test 22: full Kaizen flow with approval and A3 report."""
import io

from django.test import Client, TestCase
from pypdf import PdfReader

from apps.core.models import Role
from apps.core.tests.helpers import areas, user
from apps.kaizen.models import Improvement


class KaizenFlowTests(TestCase):
    def setUp(self):
        self.a = areas()
        self.op = user("op", Role.OPERATOR, ("SMT",))
        self.sup = user("sup", Role.SUPERVISOR, ("SMT",))

    def cl(self, u):
        c = Client(HTTP_HOST="127.0.0.1")
        c.force_login(u)
        return c

    def test_22_complete_and_report(self):
        op, sup = self.cl(self.op), self.cl(self.sup)
        r = op.post("/kaizen/nueva/", {"title": "Reducir scrap en SMT", "problem": "Scrap 3%", "objective": "Scrap 1%", "area": self.a["SMT"].pk,
                                       "responsible": self.op.pk, "priority": 1})
        self.assertEqual(r.status_code, 302)
        k = Improvement.objects.get()
        # operator cannot approve
        op.post(f"/kaizen/{k.pk}/estado/", {"to": "evaluation"})
        k.refresh_from_db()
        self.assertEqual(k.status, "proposal")
        for to in ("evaluation", "approved"):
            sup.post(f"/kaizen/{k.pk}/estado/", {"to": to})
        k.refresh_from_db()
        self.assertEqual(k.status, "approved")
        self.assertEqual(k.approved_by, self.sup)
        op.post(f"/kaizen/{k.pk}/actualizar/", {"section": "analysis", "version": k.version, "why0": "Pasta seca", "why1": "Tiempo abierto",
                                                 "root_cause": "Control de tiempo de pasta", "pdca_plan": "Plan", "results": ""})
        k.refresh_from_db()
        op.post(f"/kaizen/{k.pk}/actualizar/", {"section": "action", "version": k.version, "description": "Temporizador de pasta"})
        for to in ("implementation", "verification"):
            op.post(f"/kaizen/{k.pk}/estado/", {"to": to})
        k.refresh_from_db()
        self.assertEqual(k.status, "verification")
        r = sup.post(f"/kaizen/{k.pk}/estado/", {"to": "closed"})
        k.refresh_from_db()
        self.assertEqual(k.status, "verification")  # cannot close without results/measures
        op.post(f"/kaizen/{k.pk}/actualizar/", {"section": "measure", "version": k.version, "name": "Scrap", "unit": "%", "source": "Dataset calidad",
                                                 "before_from": "2026-09-01", "before_to": "2026-09-30", "before_value": "3.0",
                                                 "after_from": "2026-10-01", "after_to": "2026-10-31", "after_value": "1.2"})
        k.refresh_from_db()
        op.post(f"/kaizen/{k.pk}/actualizar/", {"section": "saving", "version": k.version, "kind": "scrap", "amount": "1800", "unit": "pz/año",
                                                 "formula": "(3.0%-1.2%) × 100000 pz", "calculation": "0.018 × 100000", "period": "anual"})
        k.refresh_from_db()
        saving = k.savings.get()
        self.assertIsNone(saving.approved_by)
        sup.post(f"/kaizen/{k.pk}/actualizar/", {"section": "saving_approve", "version": k.version, "saving_id": saving.pk})
        sup.post(f"/kaizen/{k.pk}/estado/", {"to": "closed"})
        k.refresh_from_db()
        self.assertEqual(k.status, "closed")
        self.assertIsNotNone(k.savings.get().approved_by)
        self.assertEqual(k.measures.get().delta_pct, -60)
        pdf = op.get(f"/kaizen/{k.pk}/a3.pdf")
        self.assertEqual(pdf.status_code, 200)
        reader = PdfReader(io.BytesIO(pdf.content))
        box = reader.pages[0].mediabox
        self.assertAlmostEqual(float(box.width), 1190.55, places=0)  # A3 landscape
        text = reader.pages[0].extract_text()
        for expected in ("Reducir scrap en SMT", "Pasta seca", "Temporizador de pasta", "aprobado por sup", "Aprobada por"):
            self.assertIn(expected, text)
        self.assertEqual(self.cl(user("ens", Role.SUPERVISOR, ("ENS",))).get(f"/kaizen/{k.pk}/").status_code, 403)
