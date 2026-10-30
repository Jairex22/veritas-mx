from __future__ import annotations

from backend.app.data.demo import DemoDataSource
from backend.app.services.diagnostics import DiagnosticsEngine
from tests.conftest import FIXED_NOW


def findings():
    src = DemoDataSource(now=FIXED_NOW)
    return src, [f.to_dict() for f in DiagnosticsEngine(now=lambda: FIXED_NOW).analyze(src.list_units())]


def by_rule(fs, rule):
    return [f for f in fs if f["rule_id"] == rule]


def test_all_scenarios_detected():
    _, fs = findings()
    expected = {
        "FCT_DEBUG_LOOP": "DEMO-GPV-L00001",
        "STUCK_IN_REPAIR": "DEMO-GPV-R00002",
        "RESOLVED_WITH_HOLD": "DEMO-GPV-H00003",
        "REPEATED_STATION": "DEMO-GPV-A00005",
        "INCONSISTENT_STATE": "DEMO-GPV-I00006",
        "UNVERIFIED_RESOLUTION": "DEMO-GPV-V00008",
        "MIXED_PANEL": "DEMO-GPV-M00003",
        "BLOCKED_BEFORE_DEPANEL": "DEMO-GPV-M00001",
    }
    for rule, serial in expected.items():
        assert any(serial in f["serials"] for f in by_rule(fs, rule)), rule
    assert any("DEMO-GPV-I00007" in f["serials"] for f in by_rule(fs, "INCONSISTENT_STATE"))


def test_findings_separate_facts_and_hypotheses():
    _, fs = findings()
    for f in fs:
        assert f["facts"] and all(x["kind"] == "HECHO_CONFIRMADO" for x in f["facts"])
        assert f["hypotheses"] and all(x["kind"] == "HIPOTESIS" for x in f["hypotheses"])
        assert 0 <= f["confidence"]["score"] <= 1 and f["confidence"]["basis"]
        assert f["recommended_actions"] and f["intervention_risk"]["level"] in ("BAJO", "MEDIO", "ALTO")


def test_loop_evidence_references_real_events():
    src, fs = findings()
    loop = by_rule(fs, "FCT_DEBUG_LOOP")[0]
    ids = {e.id for e in src.get_unit("DEMO-GPV-L00001").events}
    assert loop["facts"][0]["evidence"] and set(loop["facts"][0]["evidence"]) <= ids
    assert loop["severity"] == "HIGH"


def test_properly_repaired_units_not_flagged_as_unverified():
    src, fs = findings()
    flagged = {s for f in by_rule(fs, "UNVERIFIED_RESOLUTION") for s in f["serials"]}
    assert flagged == {"DEMO-GPV-V00008"}
    # Las unidades normales con retrabajo (reparación + re-prueba) no aparecen.
    reworked = [u for u in src.list_units() if u.repairs and u.serial.startswith("DEMO-GPV-0")]
    assert reworked and not flagged & {u.serial for u in reworked}


def test_findings_are_sorted_by_severity():
    _, fs = findings()
    order = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3}
    sev = [order[f["severity"]] for f in fs]
    assert sev == sorted(sev)
