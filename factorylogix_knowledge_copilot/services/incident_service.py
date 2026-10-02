"""Incidentes y paquetes de escalamiento (CSV, reporte imprimible y correo opcional con confirmación)."""
from __future__ import annotations

import smtplib
from email.message import EmailMessage
from typing import Any

from core.config import Settings
from core.errors import NotFound, PermissionDenied, ValidationError
from core.utils import new_id
from models.domain import AuthenticatedUser, IncidentStatus
from repositories.operations import IncidentRepository
from schemas.validation import IncidentInput
from security.file_validation import validate_image_attachment
from security.rbac import require
from security.sanitize import clean_user_text, safe_join
from services.audit_helper import Auditor
from services.export_service import html_report, to_csv_bytes

INCIDENT_COLUMNS = ["code", "created_at", "created_by", "created_by_role", "status", "urgency", "suggested_area",
                    "work_order", "serial_number", "assembly", "station", "operation", "error_message", "question",
                    "answer", "sources", "preliminary_diagnosis", "notes", "updated_at", "updated_by"]


class EmailNotifier:
    """Envío SMTP interno. Desactivado por defecto; exige configuración, dominio permitido y confirmación."""

    def __init__(self, settings: Settings, smtp_factory=smtplib.SMTP):
        self.settings = settings
        self.smtp_factory = smtp_factory

    @property
    def enabled(self) -> bool:
        return bool(self.settings.get("email.enabled")) and bool(self.settings.get("email.smtp_host"))

    def send(self, to_address: str, subject: str, body: str, confirmed: bool) -> None:
        if not self.enabled:
            raise ValidationError("El envío de correo no está configurado.")
        if not confirmed:
            raise ValidationError("Confirma explícitamente el envío del correo.")
        domain = to_address.rsplit("@", 1)[-1].lower() if "@" in to_address else ""
        allowed = [d.lower() for d in self.settings.get("email.allowed_domains", [])]
        if not domain or (allowed and domain not in allowed):
            raise ValidationError("Dominio de correo no permitido.")
        message = EmailMessage()
        message["From"] = self.settings.get("email.sender")
        message["To"] = to_address
        message["Subject"] = subject[:150]
        message.set_content(body)
        with self.smtp_factory(self.settings.get("email.smtp_host"), int(self.settings.get("email.smtp_port", 25)),
                               timeout=15) as smtp:
            if self.settings.get("email.use_tls", True):
                smtp.starttls()
            user, password = self.settings.secret("FLKC_SMTP_USERNAME"), self.settings.secret("FLKC_SMTP_PASSWORD")
            if user and password:
                smtp.login(user, password)
            smtp.send_message(message)


class IncidentService:
    def __init__(self, settings: Settings, repo: IncidentRepository, audit: Auditor, notifier: EmailNotifier):
        self.settings = settings
        self.repo = repo
        self.audit = audit
        self.notifier = notifier
        self.attachments_dir = settings.path("paths.attachments_dir")

    def create(self, user: AuthenticatedUser, data: IncidentInput, attachment: tuple[str, bytes] | None = None,
               correlation_id: str = "") -> tuple[str, str]:
        require(user, "incident.create")
        data.validated(self.settings.get("escalation.areas", []))
        attachment_path = None
        if attachment:
            name, content = attachment
            vf = validate_image_attachment(name, content)
            self.attachments_dir.mkdir(parents=True, exist_ok=True)
            target = safe_join(self.attachments_dir, f"{new_id('att-')}{vf.extension}")
            target.write_bytes(content)
            attachment_path = target.name
        iid, code = self.repo.create(created_by=user.username, created_by_role=user.role,
                                     question=data.question, answer=data.answer, work_order=data.work_order,
                                     serial_number=data.serial_number, assembly=data.assembly, station=data.station,
                                     operation=data.operation, error_message=data.error_message,
                                     attachment_path=attachment_path, sources=data.sources,
                                     preliminary_diagnosis=data.preliminary_diagnosis, urgency=data.urgency,
                                     suggested_area=data.suggested_area, status=IncidentStatus.OPEN.value,
                                     notes="", updated_by=user.username)
        self.audit(user, "incident.create", "incident", code, "success", details=f"urgency={data.urgency}",
                   correlation_id=correlation_id)
        return iid, code

    def list(self, user: AuthenticatedUser, status: str = "") -> list[dict[str, Any]]:
        if user.can("incident.manage") or user.can("audit.view"):
            return self.repo.list(status=status)
        require(user, "incident.create")
        return self.repo.list(status=status, created_by=user.username)

    def get(self, user: AuthenticatedUser, incident_id: str) -> dict[str, Any]:
        item = self.repo.get(incident_id)
        if not item:
            raise NotFound("Incidente no encontrado.")
        if item["created_by"] != user.username and not (user.can("incident.manage") or user.can("audit.view")):
            raise PermissionDenied()
        return item

    def update_status(self, user: AuthenticatedUser, incident_id: str, status: str, notes: str,
                      correlation_id: str = "") -> None:
        require(user, "incident.manage")
        if status not in IncidentStatus.values():
            raise ValidationError("Estado inválido.")
        item = self.get(user, incident_id)
        notes = clean_user_text(notes, 2000)
        merged = (item["notes"] + "\n" if item["notes"] else "") + (f"[{user.username}] {notes}" if notes else "")
        self.repo.update(incident_id, status=status, notes=merged[-6000:], updated_by=user.username)
        self.audit(user, "incident.update", "incident", item["code"], "success", details=f"status={status}",
                   correlation_id=correlation_id)

    def attachment(self, user: AuthenticatedUser, incident_id: str) -> tuple[str, bytes] | None:
        item = self.get(user, incident_id)
        if not item["attachment_path"]:
            return None
        path = safe_join(self.attachments_dir, item["attachment_path"])
        return (path.name, path.read_bytes()) if path.is_file() else None

    def export_csv(self, user: AuthenticatedUser, rows: list[dict[str, Any]], correlation_id: str = "") -> bytes:
        require(user, "incident.create")
        self.audit(user, "export.incidents_csv", "incident", "list", "success", details=f"rows={len(rows)}",
                   correlation_id=correlation_id)
        return to_csv_bytes(rows, INCIDENT_COLUMNS)

    def printable(self, user: AuthenticatedUser, incident_id: str, branding: dict[str, str]) -> str:
        item = self.get(user, incident_id)
        self.audit(user, "export.incident_report", "incident", item["code"], "success")
        return html_report(
            f"Paquete de escalamiento {item['code']}",
            [("Resumen", {"Código": item["code"], "Estado": item["status"], "Urgencia": item["urgency"],
                          "Área sugerida": item["suggested_area"], "Creado": item["created_at"],
                          "Usuario / rol": f"{item['created_by']} / {item['created_by_role']}"}),
             ("Contexto de manufactura", {"Work Order": item["work_order"] or "—",
                                          "Serial": item["serial_number"] or "—", "Ensamble": item["assembly"] or "—",
                                          "Estación": item["station"] or "—", "Operación": item["operation"] or "—",
                                          "Mensaje de error": item["error_message"] or "—",
                                          "Captura adjunta": item["attachment_path"] or "—"}),
             ("Pregunta original", item["question"] or "—"),
             ("Respuesta obtenida", item["answer"] or "—"),
             ("Fuentes consultadas", item["sources"] or "—"),
             ("Diagnóstico preliminar", item["preliminary_diagnosis"] or "—"),
             ("Notas de seguimiento", item["notes"] or "—")],
            banner=f"{branding.get('company_name', '')} · {branding.get('site', '')} · Uso interno",
            footer="Generado por FactoryLogix Knowledge Copilot. La respuesta del asistente no sustituye el "
                   "procedimiento oficial.")

    def email(self, user: AuthenticatedUser, incident_id: str, to_address: str, confirmed: bool,
              correlation_id: str = "") -> None:
        require(user, "incident.create")
        item = self.get(user, incident_id)
        body = (f"Incidente {item['code']} ({item['urgency']})\nÁrea: {item['suggested_area']}\n"
                f"WO: {item['work_order']}  Serial: {item['serial_number']}  Estación: {item['station']}\n"
                f"Error: {item['error_message']}\n\nPregunta: {item['question']}\n")
        try:
            self.notifier.send(to_address, f"[FLKC] {item['code']}", body, confirmed)
        except Exception as exc:
            self.audit(user, "incident.email", "incident", item["code"], "failure",
                       reason=getattr(exc, "user_message", type(exc).__name__), correlation_id=correlation_id)
            raise
        self.audit(user, "incident.email", "incident", item["code"], "success", correlation_id=correlation_id)
