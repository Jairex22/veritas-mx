"""Máquina de estados del ciclo de vida documental."""
from __future__ import annotations

from core.errors import WorkflowError
from models.domain import DocStatus

D, R, A, J, E, X = (DocStatus.DRAFT.value, DocStatus.UNDER_REVIEW.value, DocStatus.APPROVED.value,
                    DocStatus.REJECTED.value, DocStatus.EXPIRED.value, DocStatus.ARCHIVED.value)

TRANSITIONS: dict[str, set[str]] = {
    D: {R, X},
    R: {A, J, D},
    A: {X, E},
    J: {X},
    E: {X},
    X: {A},  # solo rollback de versiones aprobadas anteriormente
}


def check_transition(current: str, target: str, *, ever_approved: bool = False) -> None:
    if target not in TRANSITIONS.get(current, set()):
        raise WorkflowError(f"Transición no permitida: {current} → {target}.")
    if current == X and target == A and not ever_approved:
        raise WorkflowError("Solo se puede restaurar una versión que haya sido aprobada anteriormente.")


SOURCE_PRIORITY_TEXT = [
    "1. Procedimiento vigente aprobado (Procedure)",
    "2. Instrucción de trabajo vigente (Work Instruction)",
    "3. Manual oficial aprobado (Official Manual)",
    "4. Base de conocimiento aprobada (Knowledge Base)",
    "5. FAQ / Q&A aprobada (FAQ, Approved Q&A)",
    "6. Contenido en revisión: NUNCA se usa para respuestas operativas",
]
