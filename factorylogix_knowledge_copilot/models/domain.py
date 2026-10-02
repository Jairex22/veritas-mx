"""Modelos de dominio tipados."""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class Role(str, Enum):
    OPERATOR = "Operator"
    SUPERVISOR = "Supervisor"
    PRODUCT_ENGINEER = "Product Engineer"
    QUALITY = "Quality"
    NPI = "NPI"
    MES_SUPPORT = "MES Support"
    KNOWLEDGE_MANAGER = "Knowledge Manager"
    DATA_STEWARD = "Data Steward"
    ADMINISTRATOR = "Administrator"
    AUDITOR = "Auditor"

    @classmethod
    def values(cls) -> list[str]:
        return [r.value for r in cls]


class Classification(str, Enum):
    PUBLIC = "Public"
    INTERNAL = "Internal"
    CONFIDENTIAL = "Confidential"
    RESTRICTED = "Restricted"

    @property
    def level(self) -> int:
        return ["Public", "Internal", "Confidential", "Restricted"].index(self.value)

    @classmethod
    def values(cls) -> list[str]:
        return [c.value for c in cls]


class DocStatus(str, Enum):
    DRAFT = "Draft"
    UNDER_REVIEW = "Under Review"
    APPROVED = "Approved"
    REJECTED = "Rejected"
    EXPIRED = "Expired"
    ARCHIVED = "Archived"

    @classmethod
    def values(cls) -> list[str]:
        return [s.value for s in cls]


class SourceType(str, Enum):
    PROCEDURE = "Procedure"
    WORK_INSTRUCTION = "Work Instruction"
    MANUAL = "Official Manual"
    KNOWLEDGE_BASE = "Knowledge Base"
    FAQ = "FAQ"
    APPROVED_QA = "Approved Q&A"

    @property
    def priority(self) -> int:
        """1 = mayor prioridad (procedimiento vigente aprobado)."""
        return {"Procedure": 1, "Work Instruction": 2, "Official Manual": 3, "Knowledge Base": 4,
                "FAQ": 5, "Approved Q&A": 5}[self.value]

    @property
    def authority(self) -> float:
        return {1: 1.0, 2: 0.95, 3: 0.85, 4: 0.7, 5: 0.6}[self.priority]

    @classmethod
    def values(cls) -> list[str]:
        return [s.value for s in cls]


class Urgency(str, Enum):
    LOW = "Low"
    MEDIUM = "Medium"
    HIGH = "High"
    CRITICAL = "Critical"

    @classmethod
    def values(cls) -> list[str]:
        return [u.value for u in cls]


class IncidentStatus(str, Enum):
    OPEN = "Open"
    IN_PROGRESS = "In Progress"
    ESCALATED = "Escalated"
    RESOLVED = "Resolved"
    CLOSED = "Closed"

    @classmethod
    def values(cls) -> list[str]:
        return [s.value for s in cls]


class SentimentLabel(str, Enum):
    NEUTRAL = "Neutral"
    CONFUSED = "Confused"
    FRUSTRATED = "Frustrated"
    URGENT = "Urgent"
    SATISFIED = "Satisfied"


FL_MODULES = ["Operations", "Production", "Analytics", "NPI", "xTend", "Quality", "Shipping", "General"]


@dataclass(frozen=True)
class AuthenticatedUser:
    id: str
    username: str
    display_name: str
    role: str
    permissions: frozenset[str]
    clearance: tuple[str, ...]
    must_change_password: bool = False
    language: str = "es"

    def can(self, permission: str) -> bool:
        return "*" in self.permissions or permission in self.permissions


SYSTEM_USER = AuthenticatedUser(
    id="system", username="system", display_name="Sistema", role="Administrator",
    permissions=frozenset({"*"}), clearance=tuple(Classification.values()),
)


@dataclass
class SearchFilters:
    customer: str = ""
    product: str = ""
    line: str = ""
    process: str = ""
    station: str = ""
    module: str = ""

    def active(self) -> dict[str, str]:
        return {k: v for k, v in self.__dict__.items() if v}


@dataclass
class RetrievedChunk:
    chunk_id: str
    document_id: str
    version_id: str
    doc_code: str
    title: str
    version_label: str
    source_type: str
    classification: str
    section: str
    page: int | None
    text: str
    effective_date: str | None = None
    review_date: str | None = None
    expiration_date: str | None = None
    owner: str = ""
    is_demo: bool = False
    injection_flag: bool = False
    fl_module: str = ""
    lexical_score: float = 0.0
    vector_score: float = 0.0
    fused_score: float = 0.0
    coverage: float = 0.0
    relevance: float = 0.0
    final_score: float = 0.0

    @property
    def priority(self) -> int:
        try:
            return SourceType(self.source_type).priority
        except ValueError:
            return 6


@dataclass
class ConfidenceResult:
    score: float
    level: str  # High | Medium | Low | None
    components: dict[str, float] = field(default_factory=dict)
    reasons: list[str] = field(default_factory=list)


@dataclass
class ConflictInfo:
    doc_a: str
    doc_b: str
    sentence_a: str
    sentence_b: str
    kind: str  # numeric | polarity


@dataclass
class SentimentResult:
    label: str
    confidence: float
    language: str
    signals: list[str] = field(default_factory=list)
    enabled: bool = True


@dataclass
class AnswerSource:
    chunk_id: str
    document_id: str
    version_id: str
    doc_code: str
    title: str
    version_label: str
    source_type: str
    classification: str
    section: str
    page: int | None
    excerpt: str
    relevance: float
    is_demo: bool
    review_date: str | None
    expiration_date: str | None


@dataclass
class Answer:
    question: str
    language: str
    answered: bool
    brief: str = ""
    steps: list[str] = field(default_factory=list)
    validate: list[str] = field(default_factory=list)
    expected: list[str] = field(default_factory=list)
    stop_when: list[str] = field(default_factory=list)
    escalate_when: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    sources: list[AnswerSource] = field(default_factory=list)
    confidence: ConfidenceResult | None = None
    conflicts: list[ConflictInfo] = field(default_factory=list)
    notices: list[str] = field(default_factory=list)
    escalation_route: str = ""
    mode: str = "extractive"
    sentiment: SentimentResult | None = None
    safety_stop: bool = False
    production_action_request: bool = False
    injection_in_question: bool = False
    query_id: str = ""
    correlation_id: str = ""
    latency_ms: int = 0
    system_inference: list[str] = field(default_factory=list)
    debug: dict[str, Any] = field(default_factory=dict)

    def as_text(self) -> str:
        """Texto plano copiable de la respuesta (sin HTML)."""
        lines = [self.brief]
        sections = [("Pasos", self.steps), ("Qué validar", self.validate), ("Resultado esperado", self.expected),
                    ("Cuándo detenerse", self.stop_when), ("Cuándo escalar", self.escalate_when),
                    ("Advertencias", self.warnings)]
        for title, items in sections:
            if items:
                lines.append(f"\n{title}:")
                lines.extend(f"- {item}" for item in items)
        if self.sources:
            lines.append("\nFuentes:")
            for s in self.sources:
                page = f", pág. {s.page}" if s.page else ""
                lines.append(f"- {s.doc_code} · {s.title} · v{s.version_label} · {s.section}{page}")
        if self.confidence:
            lines.append(f"\nConfianza: {self.confidence.level} ({self.confidence.score:.0%})")
        return "\n".join(lines).strip()
