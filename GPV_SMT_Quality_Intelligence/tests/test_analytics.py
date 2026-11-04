"""Defectos únicos, línea de tiempo, reglas de reproceso y evidencia (caso Mirion)."""
import unittest

from tests.helpers import load_fixture
from analytics.defects import group_defects, summarize_defects
from analytics.rework_rules import evaluate
from analytics.timeline import build_timeline

SMT = load_fixture("mirion_W07632100028_smt.json")
Q = load_fixture("mirion_W07632100028_quality.json")
QH = load_fixture("mirion_W07632100028_quality_history.json")
KW = ["REPAIR"]


class DefectTests(unittest.TestCase):
    def test_mirion_fod_counted_once(self):
        defects = group_defects(Q, QH, history_available=True)
        self.assertEqual(len(defects), 1)
        d = defects[0]
        self.assertEqual(d["history_entries"], 3)
        self.assertEqual(d["status"], "Closed")
        self.assertEqual(d["classification"], "CLOSED")
        self.assertEqual(d["closed_operation"], "SMT REPAIR")
        self.assertEqual(d["closed_workstation"], "AOI-3D-PC-L3")
        self.assertEqual(d["closed_operator"], "40846")
        self.assertEqual(d["comment"], "FOD")
        self.assertEqual(d["line_registered"], "SMT Line 01")
        self.assertTrue(any("False" in n for n in d["notes"]))  # 'False' no interpretado

    def test_history_rows_never_counted_as_defects(self):
        s = summarize_defects(group_defects(Q * 3, QH * 4, True))
        self.assertEqual(s["unique_defects"], 1)

    def test_defect_id_case_insensitive(self):
        q2 = [dict(Q[0], DefectID=Q[0]["DefectID"].upper())]
        self.assertEqual(len(group_defects(Q + q2, QH, True)), 1)

    def test_history_unavailable_marks_incomplete(self):
        d = group_defects(Q, [], history_available=False)[0]
        self.assertEqual(d["classification"], "HISTORY_INCOMPLETE")

    def test_closed_without_closure_history(self):
        d = group_defects(Q, [h for h in QH if h["DefectHistoryStatus"] != "Closed"], True)[0]
        self.assertEqual(d["classification"], "HISTORY_INCOMPLETE")

    def test_open_and_unknown(self):
        self.assertEqual(group_defects([dict(Q[0], DefectStatus="Open")], [], True)[0]["classification"], "ACTIVE")
        self.assertEqual(group_defects([dict(Q[0], DefectStatus=None)], [], True)[0]["classification"], "UNKNOWN_STATUS")

    def test_nulls_tolerated(self):
        d = group_defects([{"DefectID": None, "DateCreated": None}], [], True)
        self.assertEqual(len(d), 1)
        self.assertIsNone(d[0]["time_to_close_min"])


class TimelineTests(unittest.TestCase):
    def test_chronological_and_nulls_last(self):
        smt = list(reversed(SMT)) + [dict(SMT[0], EventDate=None, OperationName="SIN FECHA")]
        tl = build_timeline(smt, Q, QH)
        times = [t["time"] for t in tl if t["time"]]
        self.assertEqual(tl[-1]["title"], "SIN FECHA")
        self.assertFalse(tl[-1]["time_verified"])
        smt_ops = [t["title"] for t in tl if t["kind"] == "SMT_EVENT" and t["time"]]
        self.assertEqual(smt_ops, ["SMT Post-Reflow AOI Top", "SMT Post-Reflow AOI Top", "SMT REPAIR", "QA SMT"])
        self.assertEqual(len(times), len(tl) - 1)

    def test_mixed_offsets_sorted_by_instant(self):
        a = dict(SMT[0], EventDate="2026-11-04T21:00:00Z", OperationName="A")      # 15:00 -06:00
        b = dict(SMT[0], EventDate="2026-11-04T14:00:00-06:00", OperationName="B")  # 20:00Z
        self.assertEqual([t["title"] for t in build_timeline([a, b], [], [])], ["B", "A"])

    def test_defect_counted_once_in_timeline(self):
        tl = build_timeline(SMT, Q * 2, QH)
        self.assertEqual(sum(1 for t in tl if t["kind"] == "DEFECT_CREATED"), 1)


class ReworkTests(unittest.TestCase):
    def cats(self, alerts):
        return {a["category"] for a in alerts}

    def test_mirion_rules(self):
        defects = group_defects(Q, QH, True)
        alerts = evaluate("W07632100028", SMT, defects, KW, {})
        cats = self.cats(alerts)
        self.assertIn("REPEATED_OPERATION", cats)
        self.assertIn("REPAIR_RECORDED", cats)
        self.assertIn("POSSIBLE_REWORK", cats)
        self.assertIn("POST_REPAIR_EVENTS", cats)
        self.assertIn("DEFECT_CLOSED", cats)
        self.assertIn("LOOP_NOT_CONFIRMABLE", cats)
        self.assertNotIn("CONFIRMED_LOOP", cats)       # dos AOI no prueban un bucle
        self.assertNotIn("DUPLICATE_EVENT", cats)      # horas distintas
        rep = next(a for a in alerts if a["category"] == "REPEATED_OPERATION")
        self.assertEqual(rep["evidence"], ["SMT#1", "SMT#2"])
        for a in alerts:
            self.assertTrue(a["definition"] and a["explanation"] is not None)

    def test_duplicate_event(self):
        alerts = evaluate("X", [SMT[0], dict(SMT[0])], [], KW, {})
        self.assertIn("DUPLICATE_EVENT", self.cats(alerts))
        self.assertNotIn("REPEATED_OPERATION", self.cats(alerts))

    def test_confirmed_loop_only_with_authorized_flow(self):
        flow = {"MR.48.SM": ["SMT Post-Reflow AOI Top", "SMT REPAIR", "QA SMT"]}
        smt = SMT + [dict(SMT[0], EventDate="2026-11-04T15:40:00-06:00")]  # regresa a AOI tras QA
        self.assertIn("CONFIRMED_LOOP", self.cats(evaluate("W", smt, [], KW, flow)))
        self.assertNotIn("CONFIRMED_LOOP", self.cats(evaluate("W", smt, [], KW, {})))

    def test_no_alerts_for_clean_flow(self):
        clean = [dict(SMT[0], OperationName=op, EventDate=f"2026-11-04T1{i}:00:00-06:00")
                 for i, op in enumerate(["SPI", "P&P", "AOI", "QA"])]
        self.assertEqual(evaluate("C", clean, [], KW, {}), [])


if __name__ == "__main__":
    unittest.main()
