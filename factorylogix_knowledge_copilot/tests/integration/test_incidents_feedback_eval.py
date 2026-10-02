"""Incidentes, feedback/correcciones con aprobación humana, analítica, evaluación y respaldos."""
import csv
import io
import json

import pytest

from core.errors import FileRejected, PermissionDenied, ValidationError
from schemas.validation import IncidentInput
from services.incident_service import EmailNotifier
from tests.conftest import user_for

PNG = b"\x89PNG\r\n\x1a\n" + b"0" * 100


def test_incident_package_and_exports(container):
    c = container
    op = user_for(c, "Operator", "op1")
    data = IncidentInput(question="¿Por qué no avanza?", answer="respuesta", work_order="WO-1001",
                         serial_number="SN-001", station="ICT-01", operation="ICT",
                         error_message="=cmd|' /C calc'!A0", urgency="High", suggested_area="MES Support",
                         preliminary_diagnosis="<script>alert(1)</script>")
    iid, code = c.incidents.create(op, data, ("captura.png", PNG))
    assert code.startswith("INC-")
    item = c.incidents.get(op, iid)
    assert item["attachment_path"].endswith(".png") and item["status"] == "Open"
    rows = list(csv.reader(io.StringIO(c.incidents.export_csv(op, [item]).decode("utf-8-sig"))))
    assert rows[1][rows[0].index("error_message")].startswith("'=")
    html = c.incidents.printable(op, iid, {"company_name": "X", "site": "Y"})
    assert "<script>alert" not in html and "WO-1001" in html
    other = user_for(c, "Operator", "op2")
    with pytest.raises(PermissionDenied):
        c.incidents.get(other, iid)
    with pytest.raises(PermissionDenied):
        c.incidents.update_status(op, iid, "Closed", "")
    c.incidents.update_status(user_for(c, "MES Support", "mes"), iid, "In Progress", "revisando")
    with pytest.raises(FileRejected):
        c.incidents.create(op, IncidentInput(question="x y z", urgency="Low", suggested_area="MES Support"),
                           ("malware.png", b"MZ\x90\x00"))
    with pytest.raises(ValidationError):
        c.incidents.create(op, IncidentInput(question="q", work_order="WO 1; DROP TABLE", urgency="Low",
                                             suggested_area="MES Support"))


def test_email_requires_configuration_and_confirmation(container):
    c = container
    with pytest.raises(ValidationError):
        EmailNotifier(c.settings).send("mes@planta.local", "s", "b", confirmed=True)
    settings = c.settings.copy()
    settings.set("email.enabled", True)
    settings.set("email.smtp_host", "smtp.planta.local")
    settings.set("email.allowed_domains", ["planta.local"])
    settings.set("email.use_tls", False)
    sent = []

    class FakeSMTP:
        def __init__(self, host, port, timeout):
            self.host = host

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def send_message(self, msg):
            sent.append(msg["To"])

    notifier = EmailNotifier(settings, smtp_factory=FakeSMTP)
    with pytest.raises(ValidationError):
        notifier.send("mes@planta.local", "s", "b", confirmed=False)
    with pytest.raises(ValidationError):
        notifier.send("x@gmail.com", "s", "b", confirmed=True)
    notifier.send("mes@planta.local", "s", "b", confirmed=True)
    assert sent == ["mes@planta.local"]


def test_correction_needs_human_approval_before_use(container):
    c = container
    op = user_for(c, "Operator", "op_fb")
    question = "¿Cuál es el torque del tornillo de la tapa del modelo DEMO-X?"
    first = c.chat.ask(op, question)
    assert not first.answered
    fid = c.feedback.report_incorrect(op, first.query_id, first.as_text(), "Falta el dato de torque",
                                      "El torque del tornillo de la tapa del modelo DEMO-X es 1.2 Nm.")
    assert c.chat.ask(op, question).answered is False, "la corrección no se usa sin aprobación"
    km = user_for(c, "Knowledge Manager", "km_fb")
    qa_id = c.feedback.accept_correction(km, fid, question,
                                         "El torque del tornillo de la tapa del modelo DEMO-X es 1.2 Nm.",
                                         "Production", "Internal")
    assert c.chat.ask(op, question).answered is False, "propuesta en revisión todavía no se usa"
    with pytest.raises(PermissionDenied):
        c.knowledge.approve_qa(km, qa_id)
    c.knowledge.approve_qa(user_for(c, "Data Steward", "ds_fb"), qa_id, "validado con Ingeniería")
    answer = c.chat.ask(op, question)
    assert answer.answered and answer.sources[0].source_type == "Approved Q&A" and "1.2 Nm" in answer.brief
    jsonl = c.knowledge.export_approved_jsonl(user_for(c, "Quality", "q1"))
    record = json.loads(jsonl.splitlines()[0])
    assert record["messages"][1]["content"].endswith("1.2 Nm.") and record["metadata"]["qa_id"] == qa_id


def test_analytics_has_no_employee_rankings(demo_container):
    c = demo_container
    c.chat.ask(user_for(c, "Operator"), "¿Qué significa In Process?")
    data = c.analytics.summary(user_for(c, "Supervisor"))
    assert data["total_questions"] >= 1 and "index" in data
    flat = json.dumps(data, default=str).lower()
    assert "user_id" not in flat and "username" not in flat and "ranking" not in flat
    with pytest.raises(PermissionDenied):
        c.analytics.summary(user_for(c, "Operator"))


def test_evaluation_runs_and_exports(demo_container, tmp_path):
    c = demo_container
    result = c.evaluation.run(user_for(c, "Knowledge Manager"))
    summary = result["summary"]
    assert summary["cases_passed"] == summary["cases"]
    assert summary["access_control_leaks"] == 0 and summary["hallucination_rate"] == 0
    assert summary["resilience_passed"].split("/")[0] == summary["resilience_passed"].split("/")[1]
    csv_path, html_path = c.evaluation.export(result, tmp_path)
    assert csv_path.stat().st_size > 0 and "Evaluación RAG" in html_path.read_text(encoding="utf-8")


def test_backup_created(container):
    archive = container.backup.create(user_for(container, "Administrator", "adm"))
    assert archive.is_file() and archive.stat().st_size > 0
    assert container.backup.list()[0]["archivo"] == archive.name


def test_settings_changes_are_validated_and_audited(container):
    c = container
    admin = user_for(c, "Administrator", "adm")
    assert c.settings_service.update_runtime(admin, "sentiment.enabled", False)
    c.apply_runtime()
    assert c.sentiment.enabled is False
    with pytest.raises(ValidationError):
        c.settings_service.update_runtime(admin, "rag.min_relevance", 5)
    with pytest.raises(ValidationError):
        c.settings_service.update_runtime(admin, "paths.database", "/etc/passwd")
    with pytest.raises(ValidationError):
        c.settings_service.update_branding(admin, {"primary_color": "red;}</style><script>"})
    with pytest.raises(PermissionDenied):
        c.settings_service.update_runtime(user_for(c, "Supervisor"), "sentiment.enabled", True)
    assert c.audit_repo.list(action="settings.change")
