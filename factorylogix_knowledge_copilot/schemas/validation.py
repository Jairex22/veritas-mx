"""Validación de entradas (formularios y API interna)."""
from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field

from core.errors import ValidationError
from core.utils import parse_date
from models.domain import FL_MODULES, Classification, Role, SourceType, Urgency
from security.sanitize import clean_user_text, validate_identifier

_CODE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9\-_.]{2,59}$")
_USERNAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._\-]{2,39}$")


def _text(value: str, name: str, max_chars: int, required: bool = False) -> str:
    cleaned = clean_user_text(value or "", max_chars)
    if required and not cleaned:
        raise ValidationError(f"El campo '{name}' es obligatorio.")
    return cleaned


@dataclass
class DocumentMetadataInput:
    doc_code: str
    title: str
    description: str
    source_type: str
    owner: str
    approver: str
    area: str
    fl_module: str
    classification: str
    retention_policy: str
    customer: str = ""
    product: str = ""
    line: str = ""
    process: str = ""
    station: str = ""
    tags: str = ""
    language: str = "es"
    effective_date: str = ""
    review_date: str = ""
    expiration_date: str = ""
    change_note: str = ""
    retention_options: list[str] = field(default_factory=list)

    def validated(self) -> "DocumentMetadataInput":
        self.doc_code = _text(self.doc_code, "Código", 60, True).upper()
        if not _CODE.match(self.doc_code):
            raise ValidationError("Código de documento: 3-60 caracteres (letras, números, - _ .).")
        self.title = _text(self.title, "Título", 200, True)
        self.description = _text(self.description, "Descripción", 1000, True)
        self.owner = _text(self.owner, "Propietario", 120, True)
        self.approver = _text(self.approver, "Aprobador", 120, True)
        self.area = _text(self.area, "Área", 80, True)
        for name in ("customer", "product", "line", "process", "station"):
            setattr(self, name, _text(getattr(self, name), name, 80))
        self.tags = ",".join(t.strip() for t in _text(self.tags, "Etiquetas", 300).split(",") if t.strip())
        self.change_note = _text(self.change_note, "Nota de cambio", 500)
        if self.source_type not in SourceType.values():
            raise ValidationError("Tipo de fuente inválido.")
        if self.classification not in Classification.values():
            raise ValidationError("Clasificación inválida.")
        if self.fl_module not in FL_MODULES:
            raise ValidationError("Módulo de FactoryLogix inválido.")
        if self.retention_options and self.retention_policy not in self.retention_options:
            raise ValidationError("Política de retención inválida.")
        if self.language not in {"es", "en"}:
            raise ValidationError("Idioma inválido.")
        eff, rev, exp = (parse_date(self.effective_date), parse_date(self.review_date),
                         parse_date(self.expiration_date))
        for raw, parsed, name in ((self.effective_date, eff, "efectiva"), (self.review_date, rev, "revisión"),
                                  (self.expiration_date, exp, "expiración")):
            if raw and parsed is None:
                raise ValidationError(f"Fecha {name} inválida (AAAA-MM-DD).")
        if eff is None:
            raise ValidationError("La fecha efectiva es obligatoria.")
        if rev is None:
            raise ValidationError("La fecha de revisión es obligatoria.")
        if rev < eff:
            raise ValidationError("La fecha de revisión debe ser posterior a la fecha efectiva.")
        if exp is not None and exp <= eff:
            raise ValidationError("La fecha de expiración debe ser posterior a la fecha efectiva.")
        self.effective_date = eff.isoformat()
        self.review_date = rev.isoformat()
        self.expiration_date = exp.isoformat() if exp else ""
        return self

    def document_fields(self) -> dict[str, str]:
        data = asdict(self)
        for key in ("effective_date", "review_date", "expiration_date", "change_note", "retention_options"):
            data.pop(key)
        return data


@dataclass
class IncidentInput:
    question: str = ""
    answer: str = ""
    work_order: str = ""
    serial_number: str = ""
    assembly: str = ""
    station: str = ""
    operation: str = ""
    error_message: str = ""
    sources: str = ""
    preliminary_diagnosis: str = ""
    urgency: str = Urgency.MEDIUM.value
    suggested_area: str = "MES Support"

    def validated(self, areas: list[str]) -> "IncidentInput":
        self.question = _text(self.question, "Pregunta", 2000)
        self.answer = _text(self.answer, "Respuesta", 6000)
        self.work_order = validate_identifier(self.work_order, "Work Order")
        self.serial_number = validate_identifier(self.serial_number, "Serial")
        self.assembly = validate_identifier(self.assembly, "Ensamble")
        self.station = _text(self.station, "Estación", 80)
        self.operation = _text(self.operation, "Operación", 80)
        self.error_message = _text(self.error_message, "Mensaje de error", 2000)
        self.sources = _text(self.sources, "Fuentes", 3000)
        self.preliminary_diagnosis = _text(self.preliminary_diagnosis, "Diagnóstico", 3000)
        if self.urgency not in Urgency.values():
            raise ValidationError("Urgencia inválida.")
        if areas and self.suggested_area not in areas:
            raise ValidationError("Área sugerida inválida.")
        if not (self.question or self.error_message):
            raise ValidationError("Describe la pregunta o el mensaje de error.")
        return self


def validate_username(username: str) -> str:
    username = (username or "").strip()
    if not _USERNAME.match(username):
        raise ValidationError("Usuario: 3-40 caracteres (letras, números, . _ -).")
    return username


def validate_role(role: str) -> str:
    if role not in Role.values():
        raise ValidationError("Rol inválido.")
    return role

